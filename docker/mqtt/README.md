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

Mosquitto 공식 `mosquitto_passwd` 유틸리티로 로컬 `docker/mqtt/secrets/passwd` 파일을 생성하고 `web`, `bridge`, `debug` 사용자를 등록한다. 명령 인수에 실제 암호를 적지 말고, 대화형 입력을 사용한다. 세 사용자 암호는 서로 달라야 한다. 컨테이너 사용자에게 passwd 해시 파일 읽기 권한이 필요하다.

```bash
docker compose -f docker/mqtt/compose.yml up -d
docker compose -f docker/mqtt/compose.yml logs --tail=30 broker
```

`docker/web/.env`에는 `VOSS_MQTT_WEB_PASSWORD`와 `VOSS_MQTT_ENABLED=true`를 적용한다. 안전상 `VOSS_NONSTOP_COMMANDS_ENABLED=false`를 유지한다. Nodes PC에는 `VOSS_MQTT_BRIDGE_PASSWORD`를 별도로 설정한다.

**보안:** 실제 비밀번호, `.env`, `secrets/` 파일은 Git 또는 채팅에 올리지 않는다. 시연 전 Nginx·Spring Boot의 비-stop 운전 명령 권한을 현장 안전 담당자가 검토해야 한다.

## 임시 연결

Nodes PC: `127.0.0.1:1883` → Web PC SSH → `127.0.0.1:1883`.
MQTT의 `voss/command`로 비-stop 동작 명령을 송신하지 않는다.
