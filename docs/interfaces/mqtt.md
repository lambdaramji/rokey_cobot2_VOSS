# MQTT (hmi_bridge ↔ Spring Boot) — #20 확정 (2026-10-08)

2026-10-14 확장(T13 #37, PL 리뷰): 표시 전용 `voss/box_track`·`voss/robot_pose`(10/13 담당 3인 승인)·`voss/robot_joints`·`voss/voice_status` 를 **승인**한다 — 로봇 제어·명령 경로는 바뀌지 않는다. `voss/box_motion` 은 BoxMotion IDL·발행자가 생길 때까지 **제안**이다([box_carry_proposal.md](box_carry_proposal.md)). 6축 관절 상세는 [robot_joints_fk_proposal.md](robot_joints_fk_proposal.md), 음성은 [voice_status.md](voice_status.md).

격리 통합시험에서는 `VOSS_MQTT_HOST`/`VOSS_MQTT_PORT`(bridge)와
`VOSS_MQTT_BROKER_URL`(Spring)로 **별도 루프백 브로커**를 지정할 수 있다.
운영 기본값은 기존 `127.0.0.1:1883`이며 토픽·JSON 계약은 그대로다.

브라우저는 MQTT 에 붙지 않는다. **Spring Boot 가 MQTT 클라이언트**이고 브라우저는 HTTP·SSE(`web_api.md`)만 쓴다. hmi_bridge(ROS) 는 MQTT ↔ ROS 변환만 하고 원격 여부를 다시 판단하지 않는다(판정은 Spring Boot, web_api.md).

## 브로커
- **확정:** Mosquitto 는 공용 PC **호스트**에서 1883/TCP 로 실행한다(ADR-0006, #55 MC-026, #20). Spring Boot 와 hmi_bridge 는 모두 `127.0.0.1:1883` 로 연결한다.
- Mosquitto listener 자체는 `0.0.0.0:1883` 을 사용하되 방화벽으로 노출을 제한한다. `enp4s0`(로봇망)은 항상 차단한다. `wlo1` 은 개발 중 개인 PC의 읽기 전용 디버깅이 필요할 때만 임시로 열고, **시연 때는 1883/wlo1 을 닫는다**. HMI는 공용 PC의 Spring Boot가 로컬로 붙으므로 시연 기능에는 영향이 없다.
- `allow_anonymous false`. 비밀번호 파일과 실제 비밀번호는 Git에 넣지 않고 공용 PC에서 생성한다(`.env`/로컬 파일만). ACL은 아래처럼 고정한다.
  - `web`: `voss/command` write, `voss/#` read
  - `bridge`: `voss/command` read. write는 #20 확정 6개(`voss/state`·`voss/result`·`voss/zone_map`·`voss/robot`·`voss/command/ack`·`voss/log_status`)와 10/14 승인 표시 토픽 `voss/box_track`·`voss/robot_pose`·`voss/robot_joints`·`voss/voice_status`, Sprint 2 `voss/pallet/state`, 제안 `voss/box_motion`(발행자 생기기 전엔 쓰지 않음)만 허용한다 (`voss/command` write 금지). 템플릿 = `docker/mqtt/acl`
  - `debug`: `voss/#` read only
  - `voice_preview`: `voss/voice_status` write 하나만 (격리 음성 시험 전용, 아래 "음성 표시등 이벤트")
- 런타임 계정의 비밀번호는 환경 변수로 주입한다. hmi_bridge 는 `VOSS_MQTT_BRIDGE_PASSWORD`, Spring Boot 는 웹 컨테이너의 MQTT 비밀번호 변수를 사용한다.

## 토픽
| 토픽 | 방향 | QoS | retained | JSON |
|---|---|---|---|---|
| `voss/state` | ROS → 웹 | 1 | false | SortState 필드 이름 그대로: `state`, `box_id`, `pending_question`, `track_id`, `ready`, `not_ready`, `session_id`. Spring Boot 가 최신값을 메모리에 두고 SSE 로 넘긴다 |
| `voss/result` | ROS → 웹 | 1 | false | SortResult 필드 이름 그대로. `stamp`·`started_at` 은 ISO 문자열(0 시각은 `null` — DB 규약(#52 MC-020)과 같다, 정의석 #84 확인) |
| `voss/zone_map` | ROS → 웹 | 1 | **true** | `{"version", "entries": [{"dong", "zone", "code", "aliases"}]}` |
| `voss/robot` | ROS → 웹 | 0 | false | `{"connected", "state", "action", "gripper_width_mm", "error_code", "detail", "stamp"}` — RobotState(voss_msgs.md), `stamp` = header.stamp |
| `voss/box_track` | ROS → 웹 | 0 | false | `{"track_id", "stamp", "position_valid", "position_base":{"x","y","z"}, "position_source", "calib_version"}` — BoxTrack. 좌표는 `base_link`의 m, 유효하지 않으면 `position_base:null`. 트랙당 최대 10 Hz, SSE `box_track` |
| `voss/robot_pose` | ROS → 웹 | 0 | false | `{"stamp", "frame_id":"base_link", "position":{"x","y","z"}, "orientation":{"x","y","z","w"}}` — TCP PoseStamped, m. frame_id 가 `base_link` 가 아니거나 비유한값이면 버린다. 최대 20 Hz, SSE `robot_pose` |
| `voss/robot_joints` | ROS → 웹 | 0 | false | `{"stamp","frame_id":"base_link","name":["joint_1"…"joint_6"],"position":[rad 6개]}` — 기존 `/dsr01/joint_states`를 `joint_1`…`joint_6` 순서로 최대 20 Hz 전달, SSE `robot_joints` |
| `voss/voice_status` | ROS → 웹 | 0 | false | `{"phase","event_id","utterance_id"}` — `/voss/voice/status` 검증·필드 최소화 후 연결 중에만 전달, SSE `voice_status`(retained 거부). 아래 "음성 표시등 이벤트" |
| `voss/box_motion` (제안) | ROS → 웹 | 1 | false | `{"session_id","box_id","track_id","phase":"GRASPED|RELEASED","stamp","zone"}` — BoxMotion IDL 생긴 뒤. SSE `box_motion` |
| `voss/command` | 웹 → ROS | 1 | false | `{"command_id", "type", "args", "raw_text", "sent_at"}` — Spring Boot 가 `command_id`(UUID)·`sent_at` 을 붙인다(web_api.md `POST /api/commands`) |
| `voss/command/ack` | ROS → 웹 | 1 | false | `{"command_id", "ok", "message", "acked_at"}` — `/voss/sort/command` 응답(= manager **접수**, 완료 아님) |
| `voss/log_status` | ROS → 웹 | 1 | **true** | `{"status":"STARTING|OK|DB_ERROR|SPOOL_FULL","stamp":"…"}` — `/voss/log/status` 값을 hmi_bridge 가 전달. Spring Boot 재기동 직후에도 마지막 logger 상태를 받기 위해 retained |
| `voss/pallet/state` | ROS → 웹 | 1 | **true** | **Sprint 2.** PalletState 필드 이름 그대로: `run_id`, `state`, `route`, `dongs`, `load`, `overflow`, `excluded`, `overflow_warning`, `total`, `done`, `failed`, `box_id`, `slot_state`, `slot_box_id`, `slot_dong`(voss_msgs.md, 칸 배열 16 = slot 0~15). 3D 팔레트·진행률·구역별 실을 수/초과/경로 제외·"배송 물량 남음" 경고(TR-PAL-10, BRD v1.5). Spring Boot 재기동 직후에도 마지막 배치도를 받기 위해 retained |

### Workspace 위치 스트림 (box_track·robot_pose 10/13 담당 3인 승인)

`hmi_bridge`는 `/voss/vision/box`와 `/voss/robot/pose`를 구독해 위 두 토픽으로
샘플링 전달한다. Spring Boot는 내용을 저장하지 않고 같은 이름의 SSE 이벤트로
전달한다. 위치 이벤트는 retained와 접속 직후 재전송을 하지 않는다.

- BoxTrack: 유효 좌표만 화면 박스로 생성한다. 같은 `track_id`의 후속 메시지는
  위치 갱신이며, 0.7초 동안 갱신이 없으면 화면에서 제거한다. 같은 `track_id`의 `result`(SortResult.track_id)
  또는 `box_motion` RELEASED 를 받으면 바로 지우고 0.7초 동안 다시 그리지 않는다. 별도 추적 종료 이벤트는
  없으므로 tracker 재시작 직후 0.7초 안의 ID 재사용은 제한 사항이다.
- TCP PoseStamped: 화면은 수신 시각 0.5초 이내를 최신값으로 표시한다. 이후에는
  마지막 위치에 멈추고 갱신 중단으로 표시한다. `frame_id`가 `base_link`가 아니거나
  좌표가 비정상적이면 버린다.
- 브라우저는 위치 이벤트(`box_track`·`robot_pose`·`robot_joints`·`box_motion`)의 원본 `stamp` 가 브라우저 시계와
  1초 넘게 차이 나면(과거·미래 모두) 버린다. 두 PC 배치에서는 NTP 동기가 전제다. `robot_pose.orientation` 은
  노름이 0.99~1.01 밖이면 무시한다.
- 팔 자세는 `voss/robot_joints` 가 있을 때만 FK 로 그리고, 없으면 TCP 끝점만 실제 좌표로 표시한다. 검증된 픽셀 `u/v`→작업공간 변환은 현재 웹 계약에 없다.
- 승인: 남현지(BoxTrack), 김학민(TCP 상태·관절), 정의석(웹·MQTT). 관절 상세는 [robot_joints_fk_proposal.md](robot_joints_fk_proposal.md).

- 시각은 모두 ISO-8601 `+09:00` 문자열(공용 PC 시스템 시계). ROS Time 은 hmi_bridge 가 바꾼다.
- `type` 은 Command canonical 명령(voss_msgs.md): `start`·`stop`·`resume`·`priority`·`answer`·`reset_zone`·`palletize`(Sprint 2). 다른 문자열은 실행하지 않는다.
- `voss/result` 의 SortResult 필드에는 Sprint 2 의 `slot`(놓은 칸, 없으면 -1)이 끝에 붙는다.

### `voss/command.args` → `Command.arg` 변환표

| type | MQTT `args` | ROS `Command.arg` |
|---|---|---|
| `start` | `{}` | `"ALL"` |
| `stop` | `{}` | `""` |
| `resume` | `{}` | `""` |
| `priority` | `{"dong":"역삼동"}` | 정식 동 이름, 예 `"역삼동"` |
| `answer` | `{"box_id":"<현재 질문 box_id>","dong":"역삼동"}` **또는** `{"box_id":"…","zone":"HOLD"}` | `"<box_id>|<동 또는 HOLD>"` |
| `reset_zone` | `{"zone":"A"}` | `"A"` (A/B/C/RECHECK/HOLD, Sprint 2 `PALLET`) |
| `palletize` | `{"route":["역삼동","대치동","청담동"]}` | `"역삼동,대치동,청담동"` — 배송 순서(첫 배송지부터) 정식 동 이름을 쉼표로 (Sprint 2) |

- `priority.dong` 은 zone_map 의 정식 동 이름이어야 한다. 별칭 변환은 음성 intent_parser 역할이며 HMI는 정식 이름을 보낸다.
- `answer` 는 `dong` 과 `zone` 중 정확히 하나만 허용하고, `zone` 은 `HOLD` 만 허용한다.
- `palletize.route` 는 zone_map 정식 동 이름 문자열 배열, 1~3개·중복 없음. 아니면 `INVALID_ARGS`(등록 여부·시작 조건은 manager 가 다시 본다).
- 정의되지 않은 `args` 키나 필수값 누락은 실행하지 않고 `INVALID_ARGS` ack 로 거부한다.

## 명령 처리 규칙 (hmi_bridge)
- 필수 필드: `command_id`(UUID 문자열), `type`, `args`(object), `raw_text`(string), `sent_at`(timezone 포함 ISO-8601).
- 같은 `command_id` 는 10분 동안 기억하고 다시 실행하지 않는다. 이미 manager 응답을 받은 명령이면 저장한 ack 를 그대로 다시 발행한다. 아직 응답 대기 중이면 재실행하지 않고 최초 요청의 ack 만 기다린다.
- `sent_at` 이 30초보다 오래된 명령은 실행하지 않고 `ok=false`, `message="EXPIRED"` 로 ack 한다. **단 `stop` 은 예외** — 늦게 와도 실행한다(멈추는 쪽은 막지 않는다는 web_api.md 원칙, 정의석 #84 리뷰).
- bridge 자체 거부 코드는 `INVALID_JSON`·`INVALID_COMMAND`·`INVALID_ARGS`·`INVALID_SENT_AT`·`EXPIRED`·`SERVICE_UNAVAILABLE` 이다. 이 경우 `/voss/sort/command` 를 부르지 않는다.
- 유효 명령은 `/voss/sort/command` 응답의 `ok`·`message` 를 그대로 ack 로 보낸다. 실제 완료는 `voss/state`·`voss/result` 로 본다.

## HMI 지연 (≤ 1초, #54 MC-031)
- manager 상태 변경 로그 → 브라우저 DOM(전체 구간)과 hmi_bridge 수신 → DOM(부분 구간)을 둘 다 기록한다.
- 측정 브라우저는 공용 PC 에서 띄워 같은 시스템 시계를 쓴다. 개인 PC 브라우저 수치는 참고로만 쓴다.

## 음성 표시등 이벤트 (`voss/voice_status`, 10/14 승인)

**QoS 0, retain false**, JSON `phase`·`event_id`·`utterance_id`. bridge 는 연결 중에만 발행하고
끊긴 동안의 상태를 보관/재전송하지 않는다. Spring은 retained 음성 메시지를 거부하고 snapshot 에 넣지 않는다.
일반 `bridge` 계정이 발행한다(ACL 템플릿 `docker/mqtt/acl`). **격리 시험에는 별도 `voice_preview` 계정**을
쓴다 — `hmi_bridge voice_status_only:=true` 에서만 `VOSS_MQTT_PREVIEW_USERNAME`/`VOSS_MQTT_PREVIEW_PASSWORD`를
읽고(둘 중 하나라도 없으면 시작하지 않음) 명령은 구독하지 않는다. web의 기존 `voss/#` read는 유지한다.
전사 수락(`COMMAND_ACCEPTED`)과 명령 완료는 구분한다. 상세는 [voice_status.md](voice_status.md).

## 변경 이력
- 2026-10-08: #20 확정 — Mosquitto=공용 PC 호스트 1883, 시연 때 wlo1/1883 차단, 7개 토픽의 QoS/retained 확정, command args→Command.arg 표와 bridge 거부 코드 확정, `voss/log_status` 채택.
- 2026-10-05: 초안.
- 2026-10-07: SRD v1.0 정합 (#6). #52 MC-026 합의(정의석 결정)를 옮김 — 6개 토픽·QoS·retained, command/ack JSON, 10분 중복 억제·30초 EXPIRED, ISO 시각, Spring Boot 가 클라이언트. `voss/robot` 필드(#55). 브로커 위치·args 변환표·로그 상태 토픽은 #20. #84 리뷰 반영: stop 은 EXPIRED 예외, result 0 시각 = null 확정, `voss/log_status` 제안.
- 2026-10-12: **Sprint 2**(BRD v1.4 10.7, S2-T01 — 제안, 정의석 확인 필요). `voss/pallet/state`(QoS 1, retained) 추가·bridge ACL write 에 추가, command `palletize`(args `route` 배열 → 쉼표 문자열), `reset_zone` 에 `PALLET`, `voss/result` 에 `slot`.
- 2026-10-12 저녁: BRD v1.5 — `voss/pallet/state` 필드에 집계(`dongs`·`load`·`overflow`·`excluded`·`overflow_warning`)·`slot_dong` 추가, 칸 16 고정.
- 2026-10-13: (T13 #37) `voss/box_track`·`voss/robot_pose` 추가(남현지·김학민·정의석 승인). 제안: `voss/robot_joints`·`voss/box_motion`·`voss/voice_status`, 격리 시험 계정 `voice_preview`, `VOSS_MQTT_HOST/PORT`·`VOSS_MQTT_BROKER_URL`. Web PC 기존 브로커에는 시험 계정·ACL 만 백업 후 적용(기존 web·bridge·debug 유지).
- 2026-10-14: #37 PL 리뷰(김학민) — `voss/robot_joints`·`voss/voice_status` 승인(표시 전용), `voss/box_motion` 은 제안 유지. PC 주소 삭제(ADR-0015), `robot_pose.orientation`, ACL 서술을 `docker/mqtt/acl` 과 맞춤, 브라우저 stamp ±1 s·트랙 제거 규칙 명시.
