# VOSS 전용 MQTT 브로커 (공용 PC)

관련: docs/interfaces/deployment_two_pc_trial.md (시험 제안), mqtt.md (#20).

공식 배치(mqtt.md #20, ADR-0006)는 **공용 PC** 한 대에서 `127.0.0.1:1883` 만 연다. 두 PC 시험
([deployment_two_pc_trial.md](../../docs/interfaces/deployment_two_pc_trial.md), 제안)에서는 같은 설정을 Web PC 에
띄우고 Nodes PC 가 SSH 터널을 쓴다. 공용 PC 에는 시스템 mosquitto 패키지가 없으므로 이 compose 가 브로커다.
#20 확정 7개 토픽·QoS는 그대로다.
추적·관절·음성 표시 토픽(`voss/box_track`·`robot_pose`·`robot_joints`·`voice_status`)은 10/14 PL 리뷰로
표시 전용 승인, `voss/box_motion` 은 메시지가 생길 때까지 제안이다(ACL 에 미리 있어도 발행자가 없다).
격리 시험 계정 `voice_preview` 는 `voss/voice_status` write 만 허용한다.

## 최초 설정 (공용 PC — 두 PC 시험이면 Web PC)

```bash
cd <레포 루트>   # 공용 PC: ~/voss_ws/src/rokey_cobot2_VOSS
mkdir -p docker/mqtt/secrets
chmod 700 docker/mqtt/secrets
```

Mosquitto 공식 유틸리티로 `web`, `bridge`, `debug` 사용자를 대화형으로 생성한다. 세 계정의 암호는 서로 달라야 한다.

```bash
docker run --rm -it --user "$(id -u):$(id -g)" -v "$PWD/docker/mqtt/secrets:/secrets" eclipse-mosquitto:2 mosquitto_passwd -c /secrets/passwd web
docker run --rm -it --user "$(id -u):$(id -g)" -v "$PWD/docker/mqtt/secrets:/secrets" eclipse-mosquitto:2 mosquitto_passwd /secrets/passwd bridge
docker run --rm -it --user "$(id -u):$(id -g)" -v "$PWD/docker/mqtt/secrets:/secrets" eclipse-mosquitto:2 mosquitto_passwd /secrets/passwd debug
```

`-c`는 처음 한 번만 사용해야 기존 계정이 지워지지 않는다. Mosquitto 2.1.x는 비밀번호·ACL 파일이 다른 사용자에게 공개되는 설정을 경고하므로 파일 소유자를 컨테이너의 mosquitto 사용자로 바꾸고 읽기 권한을 제한한다.
기존 브로커에 `voice_preview`를 추가할 때는 먼저 현재 설정·ACL·비밀번호
파일을 권한 600의 Git 제외 위치에 백업하고, `-c` 없이 계정을 추가한다.
비밀번호를 명령 인수에 넣지 말고 대화형 입력을 사용한다. 적용 전 새 계정의
write 범위와 기존 계정 ACL이 유지됐는지 확인한다.

최초 설정에서 파일 소유권을 컨테이너 사용자로 바꾸기 전에는 다음처럼
전용 시험 계정도 대화형으로 생성한다.

```bash
docker run --rm -it --user "$(id -u):$(id -g)" -v "$PWD/docker/mqtt/secrets:/secrets" eclipse-mosquitto:2 mosquitto_passwd /secrets/passwd voice_preview
docker run --rm -it --user "$(id -u):$(id -g)" -v "$PWD/docker/mqtt/secrets:/secrets" eclipse-mosquitto:2 mosquitto_passwd /secrets/passwd voice_web
```

```bash
MOSQUITTO_UID="$(docker run --rm --entrypoint id eclipse-mosquitto:2 -u mosquitto)"
MOSQUITTO_GID="$(docker run --rm --entrypoint id eclipse-mosquitto:2 -g mosquitto)"
sudo install -o "$MOSQUITTO_UID" -g "$MOSQUITTO_GID" -m 600 docker/mqtt/acl docker/mqtt/secrets/acl
sudo chown "$MOSQUITTO_UID:$MOSQUITTO_GID" docker/mqtt/secrets/passwd
sudo chmod 600 docker/mqtt/secrets/passwd
```

기존 컨테이너가 켜져 있다면 `docker exec voss_mosquitto id -u mosquitto`, `id -g mosquitto`로 UID/GID를 확인해도 된다. Git에 추적되는 원본 `docker/mqtt/acl`의 소유권은 바꾸지 않는다. 런타임 사본 `docker/mqtt/secrets/acl`과 `passwd`는 `.gitignore`로 보호한다. 비밀번호 자체는 터미널 인수나 로그에 출력하지 않는다.

```bash
docker compose -f docker/mqtt/compose.yml up -d
docker compose -f docker/mqtt/compose.yml logs --tail=30 broker
```

`docker/web/.env`에는 `VOSS_MQTT_WEB_PASSWORD`와 `VOSS_MQTT_ENABLED=true`를 적용한다. 비-stop 웹 명령은 Spring Boot 가 공용 PC 로컬(Nginx X-Real-IP 127.0.0.1/::1)에서만 받는다(web_api.md). hmi_bridge 를 띄우는 터미널에는 `VOSS_MQTT_BRIDGE_PASSWORD`를 export 한다.

Web PC의 `scripts/web_pc_voice.sh`를 쓰기 전에는 위 대화형 명령으로 `voice_web`을 생성하고, 변경된 `docker/mqtt/acl`을 런타임 `docker/mqtt/secrets/acl`에 다시 설치한 뒤 브로커를 재시작한다. 별도로 정한 암호를 Web PC의 `deploy/node/.env`의 `VOSS_MQTT_VOICE_WEB_PASSWORD`에 기록한다(파일은 커밋 금지). 운영 `bridge` 암호를 복사하지 않는다. 기존 `voice_preview`는 표시 전용 격리 시험에만 쓴다.
이미 비밀번호 파일을 Mosquitto 사용자 소유로 바꾼 환경에서는 위에서 확인한 `MOSQUITTO_UID`·`MOSQUITTO_GID`로 `docker run --rm -it --user "$MOSQUITTO_UID:$MOSQUITTO_GID" -v "$PWD/docker/mqtt/secrets:/secrets" eclipse-mosquitto:2 mosquitto_passwd /secrets/passwd voice_web`을 실행한다. 실제 암호는 대화형으로 입력하고 명령 인수에 넣지 않는다.

**보안:** 실제 비밀번호, `.env`, `secrets/` 파일은 Git 또는 채팅에 올리지 않는다. 시연 전 Nginx·Spring Boot의 비-stop 운전 명령 권한을 현장 안전 담당자가 검토해야 한다.

## 두 PC 시험 연결 (제안)

Nodes PC: `127.0.0.1:1883` → Web PC SSH → `127.0.0.1:1883`.
MQTT의 `voss/command`로 비-stop 동작 명령을 송신하지 않는다.
