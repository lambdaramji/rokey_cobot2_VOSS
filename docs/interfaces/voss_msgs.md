# voss_msgs 필드 정의 (src/voss_msgs 와 1:1 — 둘 다 같이 고친다)

## msg
| 타입 | 필드 | 비고 |
|---|---|---|
| Intent | `string type` (start/stop/resume/priority/answer/update_zone_map), `string dong`, `string zone`, `int32 count`, `string raw_text` | intent_parser → sort_manager |
| SortState | `string state` (IDLE/RUNNING/PICKING/RECHECK/ASKING/PAUSED), `string box_id`, `string pending_question` | |
| SortResult | `string box_id`, `string code`, `string dong`, `float32 confidence`, `string decided_by` (ocr/recheck/operator), `string zone`, `string outcome` (placed/held/failed), `builtin_interfaces/Time stamp` | sort_logger 가 DB 1행으로 |
| ZoneMapEntry | `string dong`, `string zone` | |
| ZoneMap | `ZoneMapEntry[] entries`, `string version` | transient_local |
| BoxTrack | `int32 track_id`, `float32 u`, `float32 v`, `int32[4] bbox` (x,y,w,h), `builtin_interfaces/Time stamp` | 30 Hz, 픽셀 좌표 |
| LabelRead | `int32 track_id`, `string code`, `string dong`, `float32 confidence`, `uint8 stage` (1 입구 / 2 추종 중 / 3 재확인) | |

## srv
| 타입 | 요청 | 응답 |
|---|---|---|
| Command | `string command`, `string arg` | `bool ok`, `string message` |
| UpdateZoneMap | `ZoneMapEntry[] entries` | `bool ok`, `string message` |
| Stats | — | `int32 total`, `int32 placed`, `int32 held`, `int32 failed`, `string json` |
| MoveToZone | `string zone`, `int32 slot` | `bool ok`, `string message` |
| Gripper | `float32 width` (mm), `float32 force` (N) | `bool ok`, `float32 width_actual` |
| TeachZone | `string zone` | `bool ok`, `string message` |

## action
| 타입 | goal | feedback | result |
|---|---|---|---|
| TrackAndGrasp | `int32 track_id` | `float32 err_u`, `float32 err_v`, `string phase` (approach/track/descend/grasp) | `bool grasped`, `string reason` |

## 변경 이력
- 2026-10-05: 초안. 필드명은 제안이며 10/05 확정.
