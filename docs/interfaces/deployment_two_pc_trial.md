# 두 PC 분리 배포 — 통합 시험용 인터페이스 변경 제안 (2026-10-11)

> **상태: 제안 / 비구동 통합 시험용. 공식 인터페이스 승인 전.** 담당자가 2026-10-11 팀의 구두 시험 허락을 전달함. 서면 PR 리뷰·승인은 아직 필요하다.
> 기존 확정 계약 `docs/interfaces/mqtt.md` (#20), `web_api.md` (#68), ADR-0006보다 이 문서가 우선하지 않는다. 현재 위치·접속 제한이 충돌하는 항목만 분리 시험에서 임시로 사용한다.

## 변경 전 / 변경 제안

| 항목 | 기존 계약 | 현재 시험 배치 제안 | 영향받는 상대·승인 필요 |
|---|---|---|---|
| Nodes PC | 공용 PC에 모든 서비스 | `172.24.3.240`: ROS/비전, 마이크·voice_listener·intent_parser·speech_out, hmi_bridge·sort_logger | 남현지 PL, 김학민 |
| Web PC | 별도 서버 위치 미적용 | `172.24.0.51`: docker/ai (Whisper·LLM·TTS), docker/web (React·Spring Boot), docker/db, Mosquitto | 남현지 PL, 김학민, 정의석 |
| MQTT 브로커 (#20) | 공용 PC 127.0.0.1:1883 | Web PC **127.0.0.1:1883**; Nodes PC는 SSH 로컬 포워드 `127.0.0.1:1883 → Web PC:1883` | 정의석·김학민 |
| HTTP API (#68) | Nodes PC localhost 8000·8080 | Web PC 127.0.0.1:8000·8080, Nodes PC는 SSH 로컬 포워드로 동일 포트 접속 | 정의석·남현지 |
| DB (#21) | Nodes PC localhost 5432 | Web PC 127.0.0.1:5432, Nodes PC 127.0.0.1:**5432** → Web PC:5432 (Nodes PC의 기존 PostgreSQL 서비스 정지 및 Docker 정리 후 포트 일치) | 정의석·김학민 |
| 웹 운전 명령 (#68) | **공용 PC 로컬만** start/resume/priority/answer/reset_zone, stop은 어디서든 | Web PC의 로컬 브라우저를 공용 PC로 간주하면 안 됨. **비구동 통합 시험에서는 비-stop 명령 기본 차단**. 현장 승인 후 Nodes PC 브라우저 원격 IP `172.24.3.240`만 추가 확인하는 방식은 **제안**이며 IP만으로 사용자를 인증할 수 없어 추가 보안 검토 필요 | 남현지 PL·김학민 안전 승인 필수 |

## 유지할 계약 (변경하지 않음)

- ROS 토픽·메시지 타입, Intent JSON, MQTT 7토픽 JSON·QoS·retained·ACL은 기존 `docs/interfaces` 그대로.
- `sort_log` 유일한 writer는 Nodes PC `sort_logger`. Spring Boot는 `sort_log` SELECT만 가능하며 `session_plan`은 별도.
- FastAPI `/ai`는 Nginx로 공개하지 않음. Web PC localhost 바인드, SSH 인증 경로를 통해 Nodes PC 음성 노드만 사용.
- Mosquitto `allow_anonymous false`; Web PC localhost 전용 listener, `web`/ `bridge`/ `debug` ACL 유지. 자격 증명은 커밋하지 않음.
- `stop`은 LLM과 zone_map을 기다리지 않고 로컬에서 판정; 웹의 stop은 원격 차단 예외 유지.
- 로봇 제어망 `192.168.1.0/24`에 웹 서비스 포트를 열지 않음.

## 임시 시험용 SSH 포워드 (Nodes PC → Web PC)

```text
127.0.0.1:8000  -> Web PC 127.0.0.1:8000   /ai/stt·/ai/intent·/ai/tts
127.0.0.1:8080  -> Web PC 127.0.0.1:8080   /api/stats
127.0.0.1:1883  -> Web PC 127.0.0.1:1883   MQTT broker
127.0.0.1:5432  -> Web PC 127.0.0.1:5432   sort_logger (db_port 기본값 5432 유지)
```

`ssh -N -o ExitOnForwardFailure=yes`로 터널 실패 시 기동을 중단한다. Web PC 22번 SSH 인증/호스트 키를 현장에서 확인한다. Wi-Fi 평균 RTT 약 74~80ms, 최대 284ms(2026-10-11 ICMP 실측)는 참고일 뿐 앱 지연 보장값이 아니다.

## 비구동 통합 시험 게이트 / 증거

1. Web PC 자체 서비스·MOSQUITTO 인증/ACL 확인, Nodes SSH 포워드 HTTP·MQTT·DB 접속.
2. 모의 MQTT `voss/state` → Spring Boot SSE → HMI 상태 표시. **실로봇을 움직이는 명령은 보내지 않는다.**
3. 시험 `sort_log` 행 → API 이력/집계 확인; Nodes PC 5432는 PostgreSQL 로컬 서버 없이 SSH 포워드로만 점유.
4. Nodes 음성 HTTP `/ai/stt`·`/ai/intent`·`/ai/tts`와 `sort_logger` 연동 검사. TTS 자동 출력은 별도 현장 점검.
5. Wi-Fi·SSH 장애 시 상태 UNKNOWN/DB_ERROR, 데이터 스풀 및 복구·HMI 반영 1초 기준을 실측 후 기록한다.
6. 정식 변경 시 기존 `mqtt.md`, `web_api.md`, ADR-0006 내용을 승인된 배치로 조정하고 남현지 PL·김학민 리뷰 기록을 남긴다.

## 범위 구분

- A(G0): 박스 1개 인식→픽업→적재→DB commit·조회→복귀 (로봇 현장 검증 담당)
- B(T13 #22): HMI·음성·MQTT·이력·오류·성능과 두 PC 분리 시험 (이번 작업)
- C: 규칙 변경·구역 재교시 (이번 시험 제외)
