# voss_msgs 필드 정의 (src/voss_msgs 와 1:1 — 둘 다 같이 고친다)

## msg
| 타입 | 필드 | 비고 |
|---|---|---|
| Intent | `string type` (start/stop/resume/priority/answer/update_zone_map), `string dong`, `string zone`, `int32 count`, `string raw_text` | intent_parser → sort_manager |
| SortState | `string state` (IDLE/RUNNING/PICKING/RECHECK/ASKING/PAUSED), `string box_id`, `string pending_question`, `int32 track_id` | `track_id` = 현재 처리 중인 박스의 BoxTrack.track_id (없으면 -1). box_tracker 가 LabelCrop stage 를 정하는 데 쓴다 |
| SortResult | `string box_id`, `string code`, `string dong`, `float32 confidence`, `string decided_by` (ocr/recheck/operator), `string zone`, `string outcome` (placed/held/failed), `builtin_interfaces/Time stamp` | sort_logger 가 DB 1행으로 |
| ZoneMapEntry | `string dong`, `string zone`, `string code`, `string[] aliases` | `code` = 분류코드(예 `S07-01`), `aliases` = 자연어 별칭(예 `[역삼, 역삼동]`). 둘 다 voss_config.yaml 에서 sort_manager 가 채운다. UpdateZoneMap 요청에서는 `dong`·`zone` 만 쓰고 나머지는 비워도 된다 — **빈 `code`·`aliases` = 기존 값 유지**. `dong`(정식 이름)은 항상 허용되고 `aliases` 는 추가 별칭만 담는다(빈 목록이어도 안전) |
| ZoneMap | `ZoneMapEntry[] entries`, `string version` | transient_local |
| BoxTrack | `int32 track_id`, `float32 u`, `float32 v`, `int32[4] bbox` (x,y,w,h), `builtin_interfaces/Time stamp` | 30 Hz, 픽셀 좌표 |
| LabelRead | `int32 track_id`, `string code`, `string dong`, `float32 confidence`, `uint8 stage` (1 입구 / 2 추종 중 / 3 재확인) | |
| LabelCrop | `std_msgs/Header header`, `int32 track_id`, `uint8 stage`, `float32 sharpness`, `sensor_msgs/Image image` | box_tracker → label_reader. `header.stamp` = 원본 카메라 프레임 시각(보존). `stage` 는 box_tracker 가 `/voss/sort/state` 로 정한다: **`track_id == SortState.track_id`** 인 트랙만 PICKING→2·RECHECK→3, 그 밖의 트랙과 상태 수신 전에는 1. `sharpness` = 선명도 점수(클수록 선명), 2단계 프레임 선택·다수결 가중에 쓴다. `image` = 송장 영역 크롭(전처리 전 원본 색) |

## srv
| 타입 | 요청 | 응답 |
|---|---|---|
| Command | `string command`, `string arg` | `bool ok`, `string message` |
| UpdateZoneMap | `ZoneMapEntry[] entries` | `bool ok`, `string message` |
| Stats | — | `int32 total`, `int32 placed`, `int32 held`, `int32 failed`, `string json` |
| MoveToZone | `string zone`, `int32 slot` | `bool ok`, `string message` |
| Gripper | `float32 width` (mm), `float32 force` (N) | `bool ok`, `float32 width_actual` |
| TeachZone | `string zone` | `bool ok`, `string message` |
| ReadLabel | `int32 track_id` (-1 = 시야 안 박스 아무거나. 재확인 구역에는 박스 1개뿐), `uint8 max_frames` (0 = 기본 5), `float32 timeout_s` (0 = 기본 2.0) | `bool ok`, `voss_msgs/LabelRead label` (stage = 3), `string message` (실패 사유: timeout / no_box / no_text). 호출 전 sort_manager 가 `MoveToZone(zone=RECHECK, mode=VIEW)` 로 카메라를 재확인 구역 위로 옮긴다(SRD 상호확인 #51 MC-017) |

## action
| 타입 | goal | feedback | result |
|---|---|---|---|
| TrackAndGrasp | `int32 track_id` | `float32 err_u`, `float32 err_v`, `string phase` (approach/track/descend/grasp) | `bool grasped`, `string reason` |

## 변경 이력
- 2026-10-05: 초안. 필드명은 제안이며 10/05 확정.
- 2026-10-06: pending #1 승인 PR에서 추가 (#10).
  - `LabelCrop` msg 신설: 기존 `/voss/vision/label_crop` 이 `sensor_msgs/Image` 라서 label_reader 가 `LabelRead.track_id`·`stage` 를 채울 수 없었음.
  - `ReadLabel` srv 신설: 3단계(재확인 구역 정지 재판독)를 sort_manager 가 시작시킬 인터페이스가 없었음.
  - `SortState` 끝에 `int32 track_id` 추가: LabelCrop stage 규칙(현재 박스 트랙만 2·3)에 필요 (김학민 리뷰 ③).
  - `ZoneMapEntry` 에 `code`·`aliases` 추가 (끝에 붙임): BRD 2.4·TR-SYS-06 의 별칭과 분류코드를 노드들이 YAML 을 직접 읽지 않고 zone_map 토픽으로 받게 함 (intent_parser 별칭 해석, label_reader 퍼지 매칭 후보).
