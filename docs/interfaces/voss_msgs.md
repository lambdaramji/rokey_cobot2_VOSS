# voss_msgs 필드 정의 (src/voss_msgs 와 1:1 — 둘 다 같이 고친다)

## msg
| 타입 | 필드 | 비고 |
|---|---|---|
| Intent | `string type` (start/stop/resume/priority/answer/update_zone_map), `string dong`, `string zone` (A/B/C/HOLD/""), `int32 count`, `string raw_text`, `string box_id` | intent_parser → sort_manager. `dong` 은 정식 이름(별칭은 intent_parser 가 변환). `box_id` 는 answer 일 때만 = 질문 중인 SortState.box_id(회차 없이 box_id 그대로), 그 밖은 "". `count` 는 현재 미사용(타입 해시 유지를 위해 남김). `query_history` 는 Intent 로 보내지 않음(REST `/api/stats`). 상세: intent_json.md |
| SortState | `string state` (IDLE/RUNNING/PICKING/RECHECK/ASKING/PAUSED), `string box_id`, `string pending_question`, `int32 track_id`, `bool ready`, `string[] not_ready`, `string session_id` | `track_id` = 현재 처리 중인 박스의 BoxTrack.track_id (없으면 -1). box_tracker 가 LabelCrop stage 를 정하는 데 쓴다. `ready`·`not_ready` = sort_manager 의 준비 판단(ROBOT/SERVO/VISION/OCR/LOG). ROBOT 은 RobotState 가 생기기 전까지 "`/voss/robot/pose` 가 0.5 s 안에 들어오고 `/voss/robot/move_to_zone` 서비스가 있음"으로 임시 판정 — **과도 규칙**이다. RobotState 가 IDL 에 들어오면 RobotState 의 신선도·`connected`·`state` 로 바꾸고(신선도 기준값은 SRD v0.4 F-05, 남현지·김학민 — HMI UNKNOWN 의 3 s 와 같은 값으로 할지도 거기서 정한다), 서비스 존재만으로 READY 라고 하지 않는다(SRD v0.4 §5.7). LOG 는 `/voss/log/status` 가 `STARTING` 이거나 3 s 동안 안 오면 not_ready(start 거부, G0 는 DB 필수). 운전 중 `DB_ERROR`·`SPOOL_FULL` 은 경고만 — PAUSED 로 가지 않고 not_ready 에도 넣지 않는다(MC-027 비차단). `session_id` = 현재 세션 — `start` 로 새 세션을 열 때 sort_manager 가 만들고 `SortResult.session_id` 와 같은 값(`YYYYMMDDTHHMMSS-xxxx`). 다음 `start` 까지 유지(IDLE·PAUSED 에서도 유지)하고, 첫 `start` 전에는 `""`. HMI·투입 수량은 첫 결과가 나오기 전에도 이 값으로 세션을 안다(#68) |
| SortResult | `string box_id`, `string code`, `string dong`, `float32 confidence`, `string decided_by` (OCR/RECHECK/OPERATOR/NONE), `string zone` (A/B/C/RECHECK/HOLD/""), `string outcome` (PLACED/HELD/FAILED/PASSED), `builtin_interfaces/Time stamp`, `string session_id` (`YYYYMMDDTHHMMSS-xxxx`, 랜덤 4자리 hex), `int32 track_id`, `builtin_interfaces/Time started_at`, `string raw_text`, `string dong_alt`, `string rule_version`, `string reason`, `int32 attempts` | box_id 당 1건. sort_logger 가 DB `sort_log` 1행으로(유일키 box_id). 빈 값은 ""·0, 추정값으로 채우지 않음. 무응답 보류 = decided_by NONE + reason NO_ANSWER. `reason` 허용값: `""`·`LOW_CONF`·`NO_ANSWER`·`NON_TARGET`·`STOPPED`·`DEVICE_ERROR`·TrackAndGrasp reason. PASSED 는 attempts 0. **DB `sort_log` 대응(#52 MC-003·020, #54):** PK `box_id` varchar(32)(24자), `session_id` varchar(24)(20자), `result` ← outcome, `second_region` ← dong_alt, `retries` = max(attempts − 1, 0), 0 시각 started_at → NULL, 같은 box_id 재수신은 `ON CONFLICT DO NOTHING` + duplicate 로그. `inserted_at` 은 commit 시각이 아니다 |
| ZoneMapEntry | `string dong`, `string zone`, `string code`, `string[] aliases` | `code` = 분류코드(예 `S07-01`), `aliases` = 자연어 별칭(예 `[역삼, 역삼동]`). 둘 다 voss_config.yaml 에서 sort_manager 가 채운다. UpdateZoneMap 요청에서는 `dong`·`zone` 만 쓰고 나머지는 비워도 된다 — **빈 `code`·`aliases` = 기존 값 유지**. `dong`(정식 이름)은 항상 허용되고 `aliases` 는 추가 별칭만 담는다(빈 목록이어도 안전) |
| ZoneMap | `ZoneMapEntry[] entries`, `string version` | transient_local |
| BoxTrack | `int32 track_id`, `float32 u`, `float32 v`, `int32[4] bbox` (x,y,w,h), `builtin_interfaces/Time stamp`, `geometry_msgs/Point position_base`, `bool position_valid`, `uint8 position_source`, `string calib_version` | 30 Hz 목표. 픽셀 필드 유지. `position_base` = **촬영 시각(`stamp`)에 관측한 박스 윗면 중심**, m, 두산 베이스 축. 관측값이지 TCP 목표가 아니다 — 지연·벨트 속도 예측, 파지 높이·오프셋을 반영한 TCP 목표·위치 오차·속도 목표는 belt_servo 가 계산한다(#50 MC-001, 박병후). servo 는 비전 변환 함수를 가져다 쓰거나 같은 변환을 따로 구현하지 않는다. `position_source` 는 msg 상수 `SOURCE_NONE`·`SOURCE_OBSERVE_HOMOGRAPHY`(관측 자세 정지)·`SOURCE_HAND_EYE`(**이동 중에도 촬영 시각 pose 보간으로 갱신 — G0 필수**, #50 MC-002)로 비교한다(숫자 직접 쓰지 않음). 동적 변환 검증 전·pose 정합 불가 시 `position_valid=false`. `/voss/robot/pose`(TCP) stamp 는 조회 **응답 수신 시각**(topics.md, #53 MC-004)이라 실제 측정 시점과 RTT 만큼 어긋날 수 있으므로 시점 오차를 보장값으로 쓰지 않는다. stamp 나이(100 ms 초과)만으로 정지·폐기하지 않는다(MC-031) — 이것은 비전·서보의 입력 판단 규칙이고, robot_gateway 의 `servo_cmd` 만료 워치독(값은 실측 후)과는 별개다. **`track_id` 규칙**(검출 방식 seg·yolo 공통): box_tracker 실행 중 새 박스마다 1부터 1씩 증가, 재사용하지 않는다. 연속 15프레임(30 Hz 에서 0.5 s, 제안값) 동안 안 보이면 트랙을 폐기하고, 그 안에 다시 보이면(하강 중 손가락 가림 등) 같은 ID 를 유지한다. 노드가 재시작하면 1부터 다시 세므로 재시작 전후 ID 를 비교하지 않는다 — 박스 구분은 sort_manager 의 `box_id`. **파지 중 가림:** `SortState.track_id` 와 같은 트랙은 PICKING 동안 15프레임 규칙으로 폐기하지 않는다(RG2 개폐 약 1.2 s 동안 손가락이 가림, measurements #4). **검출되지 않은 프레임에는 BoxTrack 을 발행하지 않는다** — `position_valid=false` 는 검출은 됐지만 좌표를 믿을 수 없을 때만 쓴다 |
| LabelRead | `int32 track_id`, `string code`, `string dong`, `float32 confidence`, `uint8 stage` (1 입구 / 2 추종 중 / 3 재확인), `builtin_interfaces/Time stamp`, `string raw_text`, `string dong_alt`, `float32 confidence_alt` | `stamp` = 판정에 쓴 원본 프레임의 촬영 시각 — sort_manager 는 `track_id` 가 현재 박스이고 `stamp ≥ 단계 시작` 인 결과만 채택. `dong_alt`·`confidence_alt` = 2위 후보(재확인 질문 SYS-FR-026). code 는 정규화(`S07-0x`), dong 은 등록 이름 |
| LabelCrop | `std_msgs/Header header`, `int32 track_id`, `uint8 stage`, `float32 sharpness`, `sensor_msgs/Image image` | box_tracker → label_reader. `header.stamp` = 원본 카메라 프레임 시각(보존). `stage` 는 box_tracker 가 `/voss/sort/state` 로 정한다: **`track_id == SortState.track_id`** 인 트랙만 PICKING→2·RECHECK→3, 그 밖의 트랙과 상태 수신 전에는 1. `sharpness` = 선명도 점수(클수록 선명), 2단계 프레임 선택·다수결 가중에 쓴다. 2단계 프레임은 PICKING 동안 액션 result 가 올 때까지(GRASP 중 추종 포함) **영상 품질(선명도·가림·송장 크기)로만** 고른다 — phase 문자열에 의존하지 않는다(#50 MC-007). `image` = 송장 영역 크롭(전처리 전 원본 색) |

## srv
| 타입 | 요청 | 응답 |
|---|---|---|
| Command | `string command`, `string arg` | `bool ok`, `string message` — 응답은 **접수** 의미(완료는 SortState·SortResult). command: `start`(arg ""/`ALL`, IDLE→RUNNING, RUNNING 중이면 전체 모드로 전환) · `priority`(arg 동 이름 필수) · `stop` · `resume`(PAUSED 에서만) · `answer`(arg `<box_id>\|<동 또는 HOLD>`, ASKING 에서만) · `reset_zone`(arg 구역, PAUSED) |
| UpdateZoneMap | `ZoneMapEntry[] entries` | `bool ok`, `string message` |
| MoveToZone | `string zone` (A/B/C/RECHECK/HOLD/OBSERVE), `int32 slot`, `string mode` (""=PLACE / VIEW / PICK) | `bool ok`, `string message`, `builtin_interfaces/Time placed_stamp` (PLACE 의 RG2 개방 완료 시각) | zone 은 대문자, robot_gateway 는 voss_config `zones` 키를 대소문자 무시로 찾고 OBSERVE 는 `observe_pose`. slot = `zones.<zone>.grid` 칸 번호(A·B·C 3칸, RECHECK·HOLD 2칸 — #57), VIEW·OBSERVE 는 무시. **PLACE 응답은 OBSERVE 복귀 완료 후**(`placed_stamp` 는 개방 시각). 실패는 `ok=false`, message 는 대문자 코드(GRIP_FAIL/TIMEOUT/LIMIT, 합의 추가 BUSY/RETURN_FAILED — .srv 주석 반영 대기, 아래 절)로 시작. **RETURN_FAILED**(#53, 김학민, IDL 주석 반영 대기): 개방 후 복귀에 실패 — `ok=false` 이고 `placed_stamp` 는 채운다. 개방 전 실패는 `placed_stamp` = 0. 응답이 유실돼도 상태 확인 없이 자동 재호출하지 않는다. 이때의 업무 결과(outcome·reason)와 slot 점유는 SRD v0.4 F-06. **slot 카운터**(#51 MC-018): sort_manager 소유, PLACED 성공 응답 후에만 증가, 개방 전 실패면 같은 slot 재사용, IDLE 에서 start(새 session) 때 0. 다음 박스의 구역이 가득 차면 PAUSED → 작업자가 비움 → `reset_zone` → resume. **경로**(#51 MC-015): 항상 현재 x·y 에서 플랜지 z ≥ 446.6 mm 까지 수직 상승한 뒤 수평 이동(T35). **PICK**(#51 MC-017): 작업대 파지 높이 = 핑거 끝이 박스 밑면 +8 mm(놓기 +5 mm 와 다름), 성공 판정 = `grip_detected` + 보고폭 범위. **VIEW** = `zones.recheck.view_pose`(voss_config.md, 교시 전 null). **재확인 실패 분기**(#51 MC-017): VIEW·ReadLabel 실패 → 질문 경로, PICK 실패 → HELD(박스는 재확인 구역에 남기고 사람 확인) |
| Gripper | `float32 width` (mm), `float32 force` (N) | `bool ok`, `float32 width_actual` — 응답 확장(`grip_detected`·`message`)은 합의됨, 아래 "합의·IDL 반영 대기" |
| TeachZone | `string zone` (MoveToZone 과 같은 값) | `bool ok`, `string message` |
| ReadLabel | `int32 track_id` (-1 = 시야 안 박스 아무거나. 재확인 구역에는 박스 1개뿐), `uint8 max_frames` (0 = 기본 5), `float32 timeout_s` (0 = 기본 2.0) | `bool ok`, `voss_msgs/LabelRead label` (stage = 3), `string message` (실패 사유: timeout / no_box / no_text). 호출 전 sort_manager 가 `MoveToZone(zone=RECHECK, mode=VIEW)` 로 카메라를 재확인 구역 위로 옮긴다(SRD 상호확인 #51 MC-017) |

## action
| 타입 | goal | feedback | result |
|---|---|---|---|
| TrackAndGrasp | `int32 track_id` | `float32 err_u`, `float32 err_v` (px), `string phase` (PREPARE/TRACK/DESCEND/GRASP/LIFT/VERIFY) | `bool grasped` (LIFT·VERIFY 완료 = 인계), `string reason`, `int32 attempts` (goal 안 총 시도, 최대 3, servo 단독 카운터). goal 1개당 result 1건. **reason ↔ action status (박병후, #53 최소안):** `OK`(grasped=true, SUCCEEDED, LIFT·VERIFY 완료) · `GRASP_FAILED`(ABORTED, 3회 모두 실패) · `LOST`(ABORTED, 트랙 폐기 후 재검출 없음) · `OUT_OF_REACH`(ABORTED, 추종 가능 구간 748 mm 끝 도달, measurements #6) · `STALE_INPUT`(ABORTED, `position_valid=false` 또는 pose 미수신 지속, 기준은 belt_servo 파라미터) · `DEVICE_ERROR`(ABORTED, gripper·gateway 서비스 실패, **정지 요청 응답 없음/오류 포함**) · `CANCELED`(CANCELED, 취소 후 `/voss/robot/stop` 정상 응답). 정지 요청 실패는 정상 취소가 아니다 → ABORTED + `DEVICE_ERROR` + 로그 "정지 요청 응답 없음/오류", sort_manager 는 PAUSED, 사람이 로봇을 확인한 뒤 수동 재개(#53 MC-006·014, 별도 `STOP_UNCONFIRMED`·자동 정지 판별 없음). sort_manager 는 status 가 아니라 **reason 으로 분기**한다. `grasped=false` 는 "인계 미완료"이지 빈손이 아니다 — 자동 개방하지 않는다. 바쁘거나 READY 가 아니면 goal 을 reject(result 없음). gripper 호출 조건은 topics.md belt_servo 행 **GRASP → LIFT 전환** = 유효 통신의 닫힘 완료 응답 + `grip_detected` + 검증된 보고폭 범위(값은 T34 후 확정). 닫힘 완료만으로 LIFT 하지 않는다. 이전 attempt 의 늦은 Gripper 응답은 belt_servo 가 버린다(goal/attempt 별 future, #53 MC-012·013) |

## 합의·IDL 반영 대기 (다음 voss_msgs PR — 김학민 T32)
아래는 상호확인에서 합의했지만 `src/voss_msgs` 에 아직 없다. 이 문서가 먼저이고, IDL·gateway 구현·소비자 재빌드는 다음 PR 에서 함께 한다(README 변경 절차 2).

| 타입 | 필드 | 비고 |
|---|---|---|
| RobotState (msg, 신설) | `std_msgs/Header header`, `bool connected`, `string state` (READY/BUSY/STOPPED/ERROR), `string action`, `float32 gripper_width_mm`, `string error_code`, `string detail` | robot_gateway → `/voss/robot/state`, reliable·transient_local·depth 1, 상태가 바뀔 때 + 2 Hz(#55 MC-019). `connected` = 두산 컨트롤러·RG2 Modbus 모두 연결. `action` 예 `MOVE_TO_ZONE:B`·`SERVO`·`GRIPPER`, 없으면 "". `gripper_width_mm` = RG2 보고 폭(실제 간격 ≈ 보고값 − 10 mm 는 관측 특성이지 보정식이 아니다 — SRD v0.4 §5.5). `error_code` 예 `ESTOP`·`SAFETY_STOP`·`GRIPPER_ERROR`·`TIMEOUT`, 없으면 "". 비상정지 = `state=ERROR` + `error_code=ESTOP`(물리 E-stop 을 대신하지 않음). `STOP_UNCONFIRMED` 는 없다(#53 최소안). hmi_bridge 가 직접 구독하고, 받지 못했거나 3 s 동안 갱신이 없으면 HMI 는 UNKNOWN |
| Gripper (srv 응답 확장) | 요청 그대로 / 응답 `bool ok`, `float32 width_actual` (RG2 보고 폭 mm), `bool grip_detected`, `string message` (OK/TIMEOUT/INVALID/BUSY/COMM_ERROR) | 응답은 RG2 busy 해제(동작 완료) 뒤에 반환(#53 MC-012·013). 요청에 attempt 필드를 넣지 않는다 — 이전 attempt 의 늦은 응답은 belt_servo 가 goal/attempt 별 future 로 버린다. 끝에 붙이므로 기존 필드 순서는 그대로지만 **타입 해시가 바뀐다** — belt_servo·robot_gateway·sort_manager 를 같은 voss_msgs 로 함께 재빌드한다(필드 추가만으로 wire 호환이 보장되지 않음) |
| MoveToZone (srv 주석) | 필드 변경 없음 | `message` 코드에 `BUSY`·`RETURN_FAILED` 추가, `placed_stamp` 의 실패 의미(위 MoveToZone 비고)를 .srv 주석에 옮긴다 |
| `/voss/robot/stop` | `std_srvs/srv/Trigger` | 표준 타입이라 voss_msgs 에 넣지 않는다(conventions.md). 의미는 topics.md robot_gateway 행 |

## 변경 이력
- 2026-10-05: 초안. 필드명은 제안이며 10/05 확정.
- 2026-10-06: pending #1 승인 PR에서 추가 (#10).
  - `LabelCrop` msg 신설: 기존 `/voss/vision/label_crop` 이 `sensor_msgs/Image` 라서 label_reader 가 `LabelRead.track_id`·`stage` 를 채울 수 없었음.
  - `ReadLabel` srv 신설: 3단계(재확인 구역 정지 재판독)를 sort_manager 가 시작시킬 인터페이스가 없었음.
  - `SortState` 끝에 `int32 track_id` 추가: LabelCrop stage 규칙(현재 박스 트랙만 2·3)에 필요 (김학민 리뷰 ③).
  - `ZoneMapEntry` 에 `code`·`aliases` 추가 (끝에 붙임): BRD 2.4·TR-SYS-06 의 별칭과 분류코드를 노드들이 YAML 을 직접 읽지 않고 zone_map 토픽으로 받게 함 (intent_parser 별칭 해석, label_reader 퍼지 매칭 후보).
- 2026-10-06: SRD v0.2 상호확인 합의 반영 (#51 김학민, #52 정의석).
  - `SortResult`: enum 대문자, outcome `PASSED` 추가, 끝에 `session_id`·`track_id`·`started_at`·`raw_text`·`dong_alt`·`rule_version`·`reason`·`attempts` 추가 (MC-003·020).
  - `SortState`: 끝에 `ready`·`not_ready` 추가 (MC-019, SYS-FR-001 주담당 남현지).
  - `MoveToZone`: 요청 끝에 `mode`(PLACE/VIEW/PICK), 응답 끝에 `placed_stamp` 추가 (MC-016·017).
  - `Command`: canonical 명령 표 명시 (MC-023).
  - `Stats` srv 삭제: 집계는 DB 하나가 원천이고 정의석 측 REST `GET /api/stats` 로 제공 (MC-022, `docs/interfaces/web_api.md` 예정).
  - 리뷰 반영(#63 김학민·정의석): zone 대문자·대소문자 무시 조회, MoveToZone slot·PLACE 응답 시점·실패 코드, TeachZone 값 목록, Command.srv 주석을 canonical 표와 일치, SortState ROBOT 임시 판정·LOG 비차단 규칙.
- 2026-10-06: #50(박병후) 합의 반영.
  - `BoxTrack` 끝에 `position_base`·`position_valid`·`position_source`·`calib_version` 추가 — 픽셀→베이스 변환은 비전 단일 책임, 이동 중 갱신은 G0 필수 (MC-001·002). voss_msgs 가 geometry_msgs 에 의존.
  - `TrackAndGrasp`: phase·reason 대문자, result 끝에 `attempts` 추가, `grasped` = LIFT·VERIFY 완료 (MC-005·006).
  - `SortResult.session_id` 에 랜덤 4자리 붙임 — 같은 초 재시작 충돌 방지 (MC-003). DB 컬럼 길이는 정의석.
  - LabelCrop 2단계 프레임 선택 기준 (MC-007).
  - 리뷰 반영(#65 김학민, #50 박병후 21:23): `position_base` 는 관측 박스 윗면 중심(TCP 목표 아님), `/voss/robot/pose` stamp 정의, 워치독과 입력 나이 규칙 구분, belt_servo 의 gripper 호출. (pose 를 플랜지로, STOP_UNCONFIRMED 를 reason 으로 적었으나 10/07 정정 — 아래)
  - `LabelRead` 끝에 `stamp`·`raw_text`·`dong_alt`·`confidence_alt` 추가 (SRD 회신 NEW-V-01: 오래된 결과 판정, OCR 원문, 1·2위 후보 질문).
  - `BoxTrack.track_id` 부여 규칙 명시 — 증가·재사용 금지·15프레임 폐기·재시작 시 초기화 (#49 박병후 리뷰 🟡3, 필드 변경 없음).
- 2026-10-07: #65 리뷰(김학민 01:23, 박병후) 반영.
  - `/voss/robot/pose` = **TCP** pose (#53 MC-010). pose stamp = 응답 수신 시각(#53 MC-004)으로 topics.md·BoxTrack 비고 통일(22:01 박병후 🔴2·01:23 김학민 리뷰의 "중간값" 철회).
  - `TrackAndGrasp` 비고에 GRASP → LIFT 전환 조건(닫힘 완료 + `grip_detected` + 보고폭 범위, 늦은 Gripper 응답 버림) 추가 (#65 박병후 00:50, #53 MC-012·013).
  - `TrackAndGrasp.reason` 최종 목록: `STOP_UNCONFIRMED` 삭제(#53 박병후 최소안), `OUT_OF_REACH` 추가, status 대응·정지 요청 실패 처리(ABORTED + DEVICE_ERROR)·reason 분기·자동 개방 금지 명시.
  - `BoxTrack.position_source` 를 msg 상수(`SOURCE_*`)로 정의 — 필드·값은 그대로.
  - `BoxTrack` 파지 중 가림: 현재 트랙(`SortState.track_id`)은 PICKING 동안 폐기 보류, 미검출 프레임은 발행하지 않음(박병후 🟡2).
- 2026-10-06: `Intent` 끝에 `string box_id` 추가, `zone` 에 HOLD, `count` 미사용 표기 (#18, SRD 상호확인 #52 MC-023·024).
- 2026-10-07: SRD v0.4 정합 (#6). SortResult 에 reason 허용값·DB `sort_log` 대응, MoveToZone 에 RETURN_FAILED·placed_stamp 실패 의미·slot 카운터·수직 상승 경로·PICK 높이·VIEW 자세, SortState ROBOT 임시 판정을 과도 규칙으로 표시. "합의·IDL 반영 대기" 절 신설 — RobotState(#55)·Gripper 응답 확장(#53)·MoveToZone 주석·`/voss/robot/stop`. 필드(IDL) 변경 없음.
- 2026-10-07: `SortState` 끝에 `string session_id` 추가 — HMI·투입 수량이 첫 SortResult 전에도 현재 세션을 알도록 (#68 정의석 요청, sort_manager 담당 수용). 타입 해시가 바뀌므로 각자 voss_msgs 재빌드.
