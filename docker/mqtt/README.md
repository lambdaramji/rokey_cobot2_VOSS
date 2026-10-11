# VOSS 전용 MQTT 브로커 (Web PC)

관련: docs/interfaces/deployment_two_pc_trial.md (시험 제안), mqtt.md (#20).

Web PC의 localhost:1883만 열며 Nodes PC는 SSH 터널을 사용한다.
7개 토픽, QoS 및 사용자별 ACL은 기존 계약과 동일하다.

## 최초 설정 (Web PC)

```bash
cd ~/collaboration/rokey_cobot2_VOSS-t13
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

`docker/web/.env`에는 `VOSS_MQTT_WEB_PASSWORD`와 `VOSS_MQTT_ENABLED=true`를 적용한다. 안전상 `VOSS_NONSTOP_COMMANDS_ENABLED=false`를 유지한다. Nodes PC에는 `VOSS_MQTT_BRIDGE_PASSWORD`를 별도로 설정한다.

**보안:** 실제 비밀번호, `.env`, `secrets/` 파일은 Git 또는 채팅에 올리지 않는다. 시연 전 Nginx·Spring Boot의 비-stop 운전 명령 권한을 현장 안전 담당자가 검토해야 한다.

## 임시 연결

Nodes PC: `127.0.0.1:1883` → Web PC SSH → `127.0.0.1:1883`.
MQTT의 `voss/command`로 비-stop 동작 명령을 송신하지 않는다.
