# 입력 ② — 레포 실제 계약·결정 현황 (main `fe11ded`, 2026-10-15 19:21)

- 기준: `git show fe11ded:<path>` (작업 트리의 docs/requirements 로컬 변경은 무시). 아래 "파일:줄"은 모두 fe11ded 기준.
- v1.0 대조 기준: `671c67f`(10/07 15:12, BRD v1.3 커밋). `671c67f..fe11ded` = **커밋 119개**.
- PR 번호 표기: `#n` = 옛 레포(`lambdaramji/rokey_cobot2_VOSS`), `_2#n` = 임시 레포 `rokeyhak/rokey_cobot2_VOSS_2`(ADR-0015). 커밋 메시지 기준으로 **73ed548(10/13 11:40) ~ 32f9366(10/14 21:48) 구간의 `(#n)` 은 `_2#n`**, 그 앞(~c90623f 10/11)과 뒤(42ba57d 10/15 이후: #163·#164·#165~#181·#204)는 옛 레포 `#n` (ADR-0015:38).
- 범례: ✅ 있음 · 🟡 부분 · ❌ 없음 · ⚠️ 문서 간 불일치

---

## A. 인터페이스 현황 · v1.0 이후 변화

### A-1. 현재 노드·토픽·서비스·액션 (topics.md)

| 이름 | 타입 | 발행/제공 → 구독/호출 | QoS | 근거 |
|---|---|---|---|---|
| `/voss/voice/transcript` | std_msgs/String | voice_listener → intent_parser | reliable·volatile·10 | topics.md:11,29 |
| `/voss/voice/status` | String(JSON `phase`·`event_id`·`utterance_id`) | voice_listener → hmi_bridge (표시 전용, 10/14 승인) | reliable·10 | topics.md:11,59; voice_status.md |
| `/voss/voice/intent` | voss_msgs/Intent | intent_parser → sort_manager | reliable·10 | topics.md:12 |
| `/voss/voice/say` | String | sort_manager·intent_parser·voice_listener(TIMED_OUT)·**hmi_bridge**(voss/voice/request 버튼 문구) → speech_out | reliable·10 | topics.md:11-15 |
| `/voss/voice/text` · `/voss/voice/text/reply` | String(JSON) | hmi_bridge(Web PC, local_text_enabled) ↔ intent_parser | reliable·10 | topics.md:12,15,64-67; hmi_bridge.py:106-109; intent_parser.py:62,88 |
| `/voss/sort/state` | SortState | sort_manager → box_tracker·intent_parser·hmi_bridge (≥2 Hz, 실제 0.4 s) | reliable·volatile·10 | topics.md:14,29,42; sort_manager.yaml:18 |
| `/voss/sort/result` | SortResult | sort_manager → sort_logger·hmi_bridge | reliable·10 | topics.md:14 |
| `/voss/sort/zone_map` | ZoneMap | sort_manager → 전원 | reliable·**transient_local**·1 | topics.md:33 |
| `/voss/pallet/state` | PalletState | sort_manager → hmi_bridge (Sprint 2) | reliable·transient_local·1 | topics.md:14,34 |
| `/voss/pallet/result` | PalletResult | sort_manager → sort_logger (Sprint 2) | reliable·10 | topics.md:14,29 |
| `/voss/sort/command` (srv) | Command | sort_manager 제공 ← hmi_bridge | — | topics.md:14; sort_manager.py:151 |
| `/voss/sort/update_zone_map` (srv) | UpdateZoneMap | sort_manager 제공(문서) | — | topics.md:14 — **코드 미구현**(F-2) |
| `/voss/log/status` | String STARTING/OK/DB_ERROR/SPOOL_FULL 1 Hz | sort_logger → sort_manager·hmi_bridge | reliable·volatile·1 | topics.md:16,30 |
| `/voss/log/list_placements` (srv) | ListPlacements | sort_logger 제공 ← sort_manager (palletize 때 1회) | — | topics.md:14,16; sort_manager.py:156 |
| `/voss/vision/box` | BoxTrack 30 Hz | box_tracker → sort_manager·belt_servo·hmi_bridge | best_effort·volatile·1 (구독 depth ≥ 5 권고) | topics.md:18,26,36 |
| `/voss/vision/label_crop` | LabelCrop | box_tracker → label_reader | reliable·volatile·5 | topics.md:32 |
| `/voss/vision/label` | LabelRead | label_reader → sort_manager | reliable·10 | topics.md:19 |
| `/voss/vision/read_label` (srv) | ReadLabel | label_reader 제공 ← sort_manager(RECHECK) | — | topics.md:19 |
| `/voss/robot/servo_cmd` | geometry_msgs/TwistStamped 30 Hz (TCP·base_link, stamp=belt_servo 발행 시각) | belt_servo → robot_gateway | best_effort·volatile·1 | topics.md:20,26 |
| `/voss/robot/pose` | PoseStamped ~50 Hz (TCP) | robot_gateway → belt_servo·box_tracker·hmi_bridge | best_effort·1 | topics.md:21,26 |
| `/voss/robot/state` | RobotState (변경 시 + 2 Hz) | robot_gateway → sort_manager·hmi_bridge | reliable·transient_local·1 | topics.md:21,31 |
| `/voss/robot/stop` (srv) | std_srvs/Trigger | robot_gateway 제공 ← sort_manager·belt_servo | — | topics.md:14,20,21; robot_gateway.py:155-157 |
| `/voss/robot/move_to_zone` (srv) | MoveToZone | robot_gateway ← sort_manager | — | robot_gateway.py:278-282 |
| `/voss/robot/gripper` (srv) | Gripper | robot_gateway ← belt_servo (goal 중 유일 호출자) | — | topics.md:14,20; robot_gateway.py:192-196; belt_servo.py:383 |
| `/voss/robot/teach_zone` (srv) | TeachZone | robot_gateway 제공(문서) | — | topics.md:21 — **코드 미구현**(F-3) |
| `/voss/servo/track_and_grasp` (action) | TrackAndGrasp | belt_servo 제공 ← sort_manager | — | topics.md:20; sort_manager.py:152 |
| `/dsr01/joint_states` | (두산) | → robot_gateway(pose_source=joint_states)·hmi_bridge(표시) | best_effort·1 | topics.md:27 |
| `/voss/hmi/box_motion` | BoxMotion (**제안, IDL 없음**) | sort_manager·robot_gateway → hmi_bridge | reliable·10 (제안) | topics.md:3-5,28; voss_msgs.md:3-10 |

### A-2. voss_msgs 현재 필드 (src/voss_msgs, 19개 타입)

| 타입 | 현재 필드(요지) | 근거 |
|---|---|---|
| Intent | type(start/stop/resume/priority/answer/**recheck**/update_zone_map/**palletize**), dong, zone, count(미사용), raw_text, box_id, **route[]** | Intent.msg:2-8 |
| SortState | state(…/PAUSED/**PALLETIZING**), box_id, pending_question, track_id, ready, not_ready[], session_id | SortState.msg:1-7 |
| SortResult | box_id … attempts, **int32 slot -1** | SortResult.msg:1-17 |
| BoxTrack | track_id,u,v,bbox,stamp,position_base,position_valid,position_source,calib_version, **yaw_base, yaw_valid** | BoxTrack.msg:5-15 |
| LabelCrop / LabelRead | (v1.0 이후 변경 없음) | LabelCrop.msg, LabelRead.msg |
| ZoneMap / ZoneMapEntry | (변경 없음) | ZoneMap.msg, ZoneMapEntry.msg |
| RobotState (**신규**) | header, connected, state(READY/BUSY/STOPPED/ERROR), action, gripper_width_mm, error_code, detail | RobotState.msg:1-8 |
| Placement (**신규**) | box_id, dong, zone, slot -1, stamp, palletized | Placement.msg |
| PalletState (**신규**) | run_id, state, route[], dongs[], load[], overflow[], excluded[], overflow_warning, total, done, failed, box_id, slot_state[16], slot_box_id[16], slot_dong[16] | PalletState.msg |
| PalletResult (**신규**) | run_id, session_id, box_id, dong, route_index, zone, slot, pallet_slot, pallet_col, pallet_lane, pallet_layer, outcome(DONE/FAILED/OVERFLOW/EXCLUDED), reason, attempts, stamp | PalletResult.msg |
| Command.srv | command(start/priority/stop/resume/answer/reset_zone/**palletize**), arg — ⚠️ `recheck` 는 .srv 주석에 없음 | Command.srv:1-3 (vs voss_msgs.md:31) |
| UpdateZoneMap.srv | entries → ok, message (변경 없음) | UpdateZoneMap.srv |
| MoveToZone.srv | zone(A/B/C/RECHECK/HOLD/**PALLET**/OBSERVE), slot, mode(""=PLACE/**DROP**/VIEW/PICK) → ok, message(GRIP_FAIL/TIMEOUT/LIMIT/BUSY/RETURN_FAILED/STOPPED/INVALID/NOT_CONFIGURED), placed_stamp | MoveToZone.srv:1-11 |
| Gripper.srv | width, force → ok, width_actual, **grip_detected, message** | Gripper.srv |
| TeachZone.srv | (변경 없음) | TeachZone.srv |
| ReadLabel.srv | track_id, max_frames, timeout_s, **slot -1** → ok, label, message(+bad_slot) | ReadLabel.srv |
| ListPlacements.srv (**신규**) | session_id → ok, message(DB_ERROR/SPOOL_PENDING/INVALID), placements[] | ListPlacements.srv |
| TrackAndGrasp.action | goal track_id / result grasped, reason(OK/GRASP_FAILED/LOST/OUT_OF_REACH/STALE_INPUT/DEVICE_ERROR/CANCELED), attempts / feedback **phase 만**(err_u·err_v 삭제) | TrackAndGrasp.action |

### A-3. v1.0(671c67f) → fe11ded 변화 (`git diff 671c67f fe11ded -- docs/interfaces src/voss_msgs config`, 32파일 +939/−74)

| # | 항목 | 변화 | 성격 | 근거 커밋/PR |
|---|---|---|---|---|
| 1 | RobotState.msg | 신규 (transient_local, 2 Hz) | IDL 추가 | acd6c8a `#92` |
| 2 | Gripper.srv 응답 | `grip_detected`, `message` 추가 (타입 해시 변경) | IDL | acd6c8a `#92`; voss_msgs.md:76 |
| 3 | `/voss/robot/stop` | std_srvs/Trigger 신설, F-04(멱등·이전 stamp 버림·watchdog 200 ms) | 토픽표 | f509d26 `#84`; topics.md:49,54 |
| 4 | MoveToZone 실패 코드 | BUSY/RETURN_FAILED/STOPPED/INVALID/NOT_CONFIGURED 명시, OBSERVE=이동만 | .srv 주석 | fbdb148 `#100`, 014a7b4 `#104` |
| 5 | TrackAndGrasp feedback | `err_u`·`err_v` 삭제, `phase` 만 | IDL(해시 변경) | 33e9d3f `#103` |
| 6 | ReadLabel.srv | `int32 slot -1`, `bad_slot` | IDL | 6cd7443 `#113` |
| 7 | BoxTrack position_source 주석 | moving_verified 면 관측 자세도 HAND_EYE | 주석만 | 23237a4 `#90` |
| 8 | Intent | `recheck`·`palletize` type, `string[] route` | IDL | 601e129 `_2#47` |
| 9 | SortState | `PALLETIZING` 상태(주석) | 주석만(해시 동일) | 601e129 `_2#47`; voss_msgs.md:93 |
| 10 | SortResult | `int32 slot -1` (DB sort_log.slot) | IDL | 601e129 `_2#47` |
| 11 | Command.srv | `palletize`, `reset_zone PALLET` | 주석만 | 601e129 `_2#47` |
| 12 | MoveToZone | zone `PALLET`, mode `DROP`, PICK 확장(A·B·C·RECHECK·HOLD), PALLET slot=격자 칸 (적재 순서 slot과 별개, sort_manager 변환). v1.4안 `int32 cols` 는 머지 전 삭제 → **해시 v1.0 과 동일** | 주석만 | 601e129 `_2#47`; voss_msgs.md:94,96 |
| 13 | Placement·PalletState·PalletResult·ListPlacements | 신규 | IDL 추가 | 601e129 `_2#47` |
| 14 | BoxTrack | `yaw_base`(rad, (−π/2,π/2]), `yaw_valid` | IDL(해시 변경, 비전 컨테이너 재빌드) | 945c67d `_2#51`; voss_msgs.md:85,99 |
| 15 | servo_cmd `angular.z` | 의미 확정: `rotate.enable`(기본 off)일 때만 베이스 Z 각속도. gateway `servo_angular_enable`(기본 false)·`servo_max_ang_dps` 60·`servo_ang_acc_dps2` 90·`servo_yaw_limit_deg` 100(운용 130) | 계약(타입 동일) | dd55e56 `_2#48`, 50da027 `#164`, 5cbf98b `#179`; topics.md:61-63,68 |
| 16 | `/voss/pallet/state`·`/voss/pallet/result`·`/voss/log/list_placements` | 신설 | 토픽표 | 601e129 `_2#47`; topics.md:57 |
| 17 | hmi_bridge 표시 구독 | `/voss/vision/box`·`/voss/robot/pose`·`/dsr01/joint_states`·`/voss/voice/status` (승인), `/voss/hmi/box_motion`(제안) | 토픽표 | e8547a7 `_2#37`, 4fa31d0 `_2#38`; topics.md:3-5,58-60 |
| 18 | `/voss/voice/text`·`/text/reply`, MQTT `voss/voice/text`·`/reply`·`voss/voice/request` | 신설(웹 텍스트 명령·버튼 음성) | 토픽표·MQTT | a7fe364 `#176`; topics.md:64-67; mqtt.md:17-23,39-41 |
| 19 | MQTT 표시 토픽 | `voss/box_track`·`robot_pose`·`robot_joints`·`voice_status`(승인), `voss/box_motion`(제안), `voss/pallet/state`(retained) | MQTT | mqtt.md:3,33-37,44,111-114 |
| 20 | MQTT 계정 | `voice_preview`, `voice_web` 추가 | ACL | mqtt.md:20-21; docker/mqtt/acl:30-37 |
| 21 | web_api | `palletize`·`recheck` 명령, SSE `pallet_state`·`box_track`·`robot_pose`·`robot_joints`·`voice_status`·`text_reply`, `POST /api/voice/announce`·`/api/voice/text`, `GET /api/pallet/placements/latest` | REST | web_api.md:79-123,165-174 |
| 22 | intent_json | `recheck`·`palletize`(route 1~3·중복·미등록 되묻기), 로컬 답변(#124), stop 최종 안내 **제안** | JSON | intent_json.md:7-12,21,37,40,65-86 |
| 23 | 새 인터페이스 문서 | calibration.md, voice_status.md, robot_joints_fk_proposal.md, box_carry_proposal.md(제안), deployment_two_pc_trial.md(제안) | 문서 | docs/interfaces/README.md:115-120 |
| 24 | voss_config.yaml | A·B·C grid 3×1 → **3×2×2층**(order [2,5,1,4,0,3]), C in_tray_tcp_z_mm 40, recheck view_pose, `zones.pallet` 4×2×2, `belt.speed_cmps` 4.8 → **4.56**, `gripper.place_open_mm`·`pick_open_mm` 50 | 설정 | 518ca41 `#116`, 4ef1a1a `_2#52`, a7d9dd6(`_2#46`, ADR-0015:39) |
| 25 | config 신규 파일 | `belt_homography.yaml`, `hand_eye.yaml`, `mosquitto.acl.example`, `mosquitto.conf.example` | 설정 | diff --stat |

---

## B. 설정

### B-1. config/voss_config.yaml (sha256 앞 12 = `5e6989ffee80`, 4ef1a1a 이후 불변)

| 키 | 값 | 근거 |
|---|---|---|
| zone_map | 역삼동 A · 대치동 B · 청담동 C | voss_config.yaml:3-6 |
| aliases | [역삼,역삼동] [대치,대치동] [청담,청담동] | :7-10 |
| zones.A / B | 플랜지 posx, grid cols 3·rows 2·pitch 60·pitch_y 60·**layers 2**·order [2,5,1,4,0,3] (= 12칸) | :13-14 |
| zones.C | grid cols 3·rows 2·**pitch 50·offset −30**·pitch_y 60·layers 2·order 동일, `in_tray_tcp_z_mm: 40` | :15 |
| zones.recheck | grid 2×1 pitch 60, view_pose [520.58, −37.92, 367.14, …] | :16 |
| zones.hold | grid 2×1 pitch 60 | :17 |
| zones.pallet | pose [−158.82, 251.05, 258.27,…], grid cols 4·rows 2·pitch 50·pitch_y 60·layers 2 (**grid.order 없음**, Q12) | :18 |
| observe_pose | [−11.51, −271.11, 450.16, 85.25, −179.07, −6.03] | :19 |
| robot.tcp_offset_mm | [1.382, 2.684, 246.642] | :21 |
| belt.speed_cmps | **4.56** (실측 46.92 mm/s 보다 낮춘 FF 상쇄값, U13 6.6) | :23 |
| belt.direction_base | [0.99992, −0.01292, 0.0] | :24 |
| gripper.pre_open_mm | **90** (벨트 사전 개방) | :26 |
| gripper.place_open_mm | 50 | :27 |
| gripper.pick_open_mm | 50 | :28 |
| gripper.grasp_width_mm (close) | 39 | :29 |
| gripper.force_n | 14.0 (12 N 안은 미머지, voss_config.md:102) | :30 |
| ocr.confidence_min | 0.6 | :32 |
| ocr.codes | S07-01 역삼 / -02 대치 / -03 청담 | :33 |
| timing.latency_offset_ms | 0 | :35 |
| **defer_recheck** | voss_config 에 없음 — sort_manager 노드 파라미터 `false` | src/voss_manager/config/sort_manager.yaml:5 |
| 시연 설정 sha | 시연 공용 PC `~/voss_ws/config/voss_config.yaml` = `844f45cfc0a2` ≠ 레포 `5e6989ffee80` — 값 동일 여부 **확인 못 함**(주석 차이 가능) | measurements-1015:27 |

### B-2. v1.0 이후 설정 변화 (voss_config.md 변경 이력)

| 날짜 | 변화 | 근거 |
|---|---|---|
| 10/08 | C 칸 −80/−30/+20 (pitch 50, offset −30), recheck.view_pose 실측 | voss_config.md:83-84 |
| 10/12 (로컬 시험) | grid layers·pitch_y_mm·order·col_dy_mm, in_tray_tcp_z_mm, place_open/pick_open, zones.truck, mode STAY | :88-95 |
| 10/13 | truck→pallet, TRUCK→PALLET, STAY→DROP; v1.5 초안 키(lanes·pitch_x_mm·drop_margin_mm) 미사용; pallet grid.order 삭제(Q12) | :96-98 |
| 10/14 | speed_cmps 4.8→4.56(S2-T15), 현장값 레포 승격(Q23 앞부분), force 14 N 유지 | :100-102 |
| 미반영 | Q23 뒷부분 "노드별 기본 경로 ~/voss_ws/config 통일"은 없음 | :101 |

### B-3. 노드 파라미터 · launch 기본값 중 요구사항 관련

| 항목 | 값 | 근거 |
|---|---|---|
| robot_gateway MoveToZone 속도 | launch `zone_vel_mm_s` **300**, `zone_acc_mm_s2` 900, `zone_blend_mm` 30 (노드 기본 100/200/0) | robot_gateway.launch.py:61-69,93-95; robot_gateway.py:253. 450→300 변경 43318d4 `_2#57`(J1 특이점 9015), 그 전 450 = 52518e9 `_2#50` |
| robot_gateway servo watchdog | `servo_watchdog_s` 0.2 | robot_gateway.py:126 |
| 각속도 통과 | `servo_angular_enable` false, `servo_max_ang_dps` 60, `servo_yaw_limit_deg` 100 (launch 로 130) | robot_gateway.py:120,133,136; launch:70-75 |
| gateway pose_source | 노드 기본 service, voss_host.launch 기본 `joint_states` | voss_host.launch.py:58 |
| sort_manager | defer_recheck false, ask_timeout 30 s, stop_timeout 3.0 s, move_timeout 60 s, read_timeout 15 s, list_timeout 3 s, pallet_layers 2, pallet_hold_width [39.5, 44.0] | sort_manager.yaml:5-21 |
| label_reader | `stage2.enable: true` (10/15 저녁, ADR-0008) | label_reader.yaml:13-14 |
| belt_servo | grasp.tcp_z_below_top 19, hold_width 39.5~**44.0**, close_time_max 2.5, reach.x_max 550, retry.max_attempts 1, gripper_timeout 4.0, rate 30 Hz, `z.profile p`, `rotate.enable false` | belt_servo.yaml:12-19,23,43,53,55,60,63 |
| belt_servo 실기 예시 | `rotate.enable true`, max_deg 110, flip_above 70, rotate.lost_timeout 1.2, pose_lag 0, z.profile p(주석: 시연 실기 = trapezoid) | belt_servo_real.yaml.example:48,53,68,74,90,91 |
| 웹 투입 예정 수량 기본 | **10** | docker/web/backend/.../PlanRepository.java:15 |
| AI | OPENAI_MODEL gpt-4o, WHISPER_MODEL small | docker/ai/.env.example:5,8 |

---

## C. ADR 0001~0016

| ADR | 상태(문서 표기) | 날짜 | 핵심 결정 | 근거 |
|---|---|---|---|---|
| 0001 | 승인됨 | 10/05(승인 10/06) | `/voss/<영역>/<이름>`, voss_msgs 단일, `/dsr01` 은 gateway 만. 영역 voice·vision·sort·robot·servo·log | 0001:3-14 ⚠️ 이후 생긴 영역 `pallet`·`hmi` 미기재 |
| 0002 | 승인됨 + **10/10 G1 판정: 통과, A안 유지** | 10/05, 판정 10/10(확인 10/11) | 20사례 중 20 성공(최초 20, 무효 6; 17:01 회차 포함해도 19/20). B안 준비 안 함 | 0002:5,22-34; bc4a3e4 `#150` |
| 0003 | 승인됨 | 10/06 (판정 10/07, 갱신 10/08) | 관측 자세 = 벨트 평면 호모그래피(최대 2.63 mm), 이동 중 = 핸드아이(`moving_verified`, 광축 +9.2 mm, 영상-pose 지연 60 ms), 수직 공구에서만 유효 | 0003:38-47 |
| 0004 | 승인됨 | 10/06 | 분할 먼저 → YOLO 학습·비교 | 0004:3-19 ⚠️ 0011 이 대체했으나 상태 미갱신 |
| 0005 | 승인됨 | 10/06 | RG2 = gateway 내 Modbus TCP 직접, 판정 grip_detected 주·폭 보조 | 0005:11-15 |
| 0006 | 승인됨 | 10/06 | React+Spring Boot+FastAPI+PostgreSQL, MQTT 가 유일 경계, writer=sort_logger, 배포 = 공용 PC 컨테이너 | 0006:12-41 |
| 0007 | 승인됨 | 10/07 | 에너지 VAD + Whisper 전사 매칭, "헬로 로키(야)", 정지어 호출어 없이 | 0007:12-17,36 |
| 0008 | **제안됨**(표기) | 10/07, 추가 10/08·**10/15** | PaddleOCR korean + 방향 고정 + 자모 편집거리, 180° 재판독; **10/15 PL 결정: 2단계 OCR 기본 켬**(stage2.enable true, 180° 먼저·집으러 간 트랙 1단계 중단) | 0008:4,16,18; d905565 `#181` ⚠️ 상태 줄이 '제안됨' 그대로 |
| 0009 | 승인됨 | 10/07 | 31 mm 폭 파지(46×27 긴 옆면), pre_open 90(실 80)·39 mm·14 N, 파지 높이 z−19 | 0009:4,19-26 ⚠️ :34 "격자 X 한 줄만" 은 3×2 로 바뀜 |
| 0010 | 승인됨 | 10/07 (F-04 10/08) | speedl_stream 주 경로, servol 대안, move_line ASYNC 미사용, gateway watchdog 200 ms·move_stop, TCP z 하한 | 0010:4,21,45-70 |
| 0011 | 승인됨 | 10/08 | 기본 검출기 seg 확정, YOLO 대비책, box_tracker GPU 불필요 | 0011:3-26 |
| 0012 | 승인됨 + **10/13 D7 변경** | 10/08, 변경 10/13 | 수치 5개 승인(파지 ≥70%, OCR ≥90/95%, 지시 ≥95%, 사이클 ≤30 s, 시연); **시연: 10개 중 8 → 20개 중 16(80 %)** | 0012:4,16-24,37-38 |
| 0013 | 승인됨 | 10/10 | TTS = OpenAI gpt-4o-mini-tts·coral, FastAPI `/ai/tts` PCM, speech_out FIFO·aplay, VT-049 미실측 | 0013:4,19-27,53-55 |
| 0014 | **승인(조건부)** | 10/12, 판정 10/13 18:00, 시연 결과 10/15 | 팔레타이징 D3(16칸 3개 동) 통과 → 단계 9 포함; 음성 기동 실패(voss_launcher 미구현) → 단계 0 수동. 조건 ①cc1d0fe ②HMI·MQTT·되읽기·멈춤재개 ③즉시 재확인. 시연: 20/20, 팔레트 16 DONE·OVERFLOW 3, 멈춤·재개 미확인 | 0014:4-5,32-48 ⚠️ :51-65 "판정 문구 초안" A~D 빈칸 잔존 |
| 0015 | 승인됨 → **종료(10/15)** | 10/13, 종료 10/15 | 임시 레포 `_2` 사용 → 10/15 `_2` main(32f9366) 을 옛 main 에 FF, `_2` 보관, `(#n)` 대응표 | 0015:4,34-42 |
| 0016 | **제안**(PL·로봇 안전 담당 검토 전) | 날짜 줄 없음(PR #176, 10/15) | Web PC intent_parser `command_transport=web_api` → POST /api/commands → Spring → MQTT → Nodes PC hmi_bridge; stop 은 ROS `/voss/voice/intent` 먼저 + REST 동시, manager 가 진행 중 stop 묶음. 음성 정지는 안전 정지 수단 아님 | 0016:3,12-31 ⚠️ 코드는 이미 main 에 구현(E-2) |

---

## D. pending-decisions #1~37 (docs/pending-decisions.md, 줄 = #+6)

| # | 항목 | 상태 | 결정 내용(한 줄) | 표시 |
|---|---|---|---|---|
| 1 | 인터페이스 이름 | 결정 | 제안 수용 + LabelCrop·ReadLabel·ZoneMapEntry 확장, ADR-0001 | |
| 2 | 역할 배정 | 결정 | 추종·파지 박병후, 로봇·환경 김학민 | |
| 3 | 10/10 게이트 기준 | 결정 | 20 중 14, 자동 전환 없음, ADR-0002 | ⚠️ G1 결과(20/20 통과)는 이 행에 없음 |
| 4 | 수치 목표 5개 | 결정 | SRD v1.0 값 승인, ADR-0012 | ⚠️ 행 안 "시연 10개 중 8개" — #35(D7)로 바뀐 것 미표기 |
| 5 | 호출어 엔진 | 결정 | VAD + Whisper 매칭, ADR-0007 | |
| 6 | Whisper 모델 크기 | **미정** | 동시 부하 시험 뒤(기본 small) | docker/ai/.env.example:8 small 그대로 |
| 7 | 검출 방식 | 결정 | 분할 먼저→YOLO 학습, ADR-0004 | |
| 8 | 두산 제어 경로 | 결정 | speedl_stream, ADR-0010 | ⚠️ architecture.md:64 와 다름 |
| 9 | RG2 경로 | 결정 | Modbus TCP 직접, ADR-0005 | |
| 10 | 흐린 송장 | 결정 | 번짐 처리 S07-01 1종 | |
| 11 | 받는 사람 이름 | 결정 | 팀원 4명, 시연 박스 10개 | ⚠️ 박스 수는 #19 로 20개 |
| 12 | TTS | 결정 | gpt-4o-mini-tts·coral, ADR-0013 | |
| 13 | 웹 스택·MQTT | 결정 | ADR-0006, MQTT 7토픽 | ⚠️ 현재 MQTT 토픽 수는 7 초과(mqtt.md 표 16행) |
| 14 | DB 종류 | 결정 | PostgreSQL, writer sort_logger | |
| 15 | 코드↔동 | 결정 | 01 역삼/02 대치/03 청담 | |
| 16 | 파지 방향 | 결정 | 31 mm 폭 파지, ADR-0009 | ⚠️ 항목 제목이 ADR-0009 금지 표현 "31 mm 면" 사용 |
| 17 | 기본 검출기 | 결정 | seg, ADR-0011 | |
| 18 | LLM 모델 | 결정 | gpt-4o, 20/20 | |
| 19 | [S2] 시연 박스 구성 | 결정 | 20개 = 각 6 + 흐린 1 + 판별 불가 1 | |
| 20 | [S2] 베이스 기준점 차이 | 결정 | 재측정 없이 10/12 실측 좌표에 포함(BRD v1.7 결정 2) | |
| 21 | [S2] 음성 기동 범위 | **미정** | 제안: 전원·펜던트 사람, 음성은 ROS 스택부터 | voss_launcher 미구현 |
| 22 | [S2] voss_launcher 실행 방식 | **미정** | 제안: systemd user 서비스 | 〃 |
| 23 | [S2] 팔레트 피치·개방 폭 | 결정 | X 50·Y 60·층 27·놓기 50 mm | |
| 24 | [S2] 팔레타이징 이력 질의 | 결정 | 필수(TR-PAL-12) | ⚠️ 구현 없음(F-4) |
| 25 | [S2] 성공률 집계 담당 | 결정 | 박병후 → 정의석 | |
| 26 | [S2] 추종·파지 새 사이클 목표 | **미정** | 사다리꼴 실측 뒤, NFR-04 30 s 유지 | |
| 27 | [S2] J6 허용 범위 | 결정 | − 쪽 최대 110°, + 70° 초과는 반대 회전, 범위 밖은 그대로 진행; 에뮬레이터 단계는 실기 저속으로 대체(10/15) | 40c98c9 `#180` |
| 28 | [S2] hold_width_max 43.5→44.0 | **미정** "PR 반영" | — | ⚠️ 레포 값 이미 44.0(belt_servo.yaml:16, dbbdca8 옛 `#36`) → 사실상 결정 |
| 29 | [v1.5 D1] A·B·C 칸 수 3 → 동별 7+ | **미정** "제안: A·B 4×2=8, C 3×2=6" | — | ⚠️ 레포 config 3×2×2층=12칸(4ef1a1a `_2#52`), BRD v1.7 "구역 2층 12칸 승인"(VOSS_BRD.md:597,889) → 표 미갱신·제안 내용도 실제와 다름 |
| 30 | [v1.5 D2] PALLET slot 규칙 | 결정 | 기록 = 적재 순서 pallet_slot, MoveToZone 만 격자 칸, cols 미사용 | bc3c4d6 `#175` |
| 31 | [v1.5 D3] 게이트 기준 | 결정 | 16칸 3개 동 실기 1회 완주 | |
| 32 | [v1.5 D4] 단계 9 경로 | 결정 | "대치, 역삼, 청담" 유지 | ⚠️ 시연 실제 입력은 청담→역삼→대치(measurements-1015:62,70) |
| 33 | [v1.5 D5] 3D HMI | 결정 | 3D 사용, 2D 폴백 불필요 | |
| 34 | [v1.5 D6] 줄 순서 | 결정 | 1열→4열, 열 안 1층1줄→1층2줄→2층1줄→2층2줄 | |
| 35 | [v1.5 D7] 시연 20개 기준 | 결정 | 20개 중 16개 이상(80 %) | |
| 36 | [v1.5] 초과 시 남길 박스 | 결정 | 현행 확정(위층 먼저, 같은 층 칸 오름차순) | |
| 37 | [v1.5] 1층 FAILED 시 위층 | 결정 | 위층 박스를 빈 1층 칸에 당겨 놓음 | pallet_fsm.py:376-389 |

미정 6건: #6 · #21 · #22 · #26 · #28 · #29 (이 중 #28·#29 는 레포 값이 이미 정해짐).

---

## E. 시연 빌드 vs main · 제안 경로

### E-1. measurements-1015 §0·§5 "main 에 없는 것" → fe11ded 현황

시연 빌드 = 25a726e(태그 demo-20261015) = main 32f9366 + 코드 5파일(measurements-1015:10,22-23). 그 뒤 a7fe364(`#176`, 10/15)가 웹·음성·MQTT·카메라를 main 에 통합했다.

| measurements-1015 가 "main 에 없음"이라 한 것 | fe11ded | 근거 |
|---|---|---|
| ROS `/voss/voice/text`·`/text/reply` (hmi_bridge 새 경로) | ✅ 있음 + intent_parser 가 `/voss/voice/text` 구독(25a726e 에는 구독 노드 없었음) | hmi_bridge.py:106-109,169-188; intent_parser.py:62,88; topics.md:64-67 |
| MQTT `voss/voice/text`·`voss/voice/text/reply` | ✅ mqtt.md·docker/mqtt/acl 에 있음 | mqtt.md:17-23,40-41; docker/mqtt/acl:5-6,10-11,21,34-37 ⚠️ config/mosquitto.acl.example 은 미반영 |
| MQTT `voss/voice/request` → `/voss/voice/say` (hmi_bridge 새 발행자) | ✅ 있음 | mqtt.md:39; hmi_bridge.py:52,106; voice_request.py |
| pallet_fsm `reset_zone PALLET` 을 RUNNING 에서도 받기 | ❌ **반대로 결정** — main 은 IDLE·PAUSED 만(PR `#176` PL 안전 결정) | pallet_fsm.py:282-285; voss_msgs.md:31,101; web_api.md:174 |
| `usb_camera_preview` (25a726e 엔 진입점 없음) | ✅ 모듈 + setup.py 진입점 | voss_vision/setup.py:29 |
| 시연 뒤 main 추가분 | #163 레포 복귀, #164 각속도 통과(기본 off), #167·#179 J6 회전(기본 off), #171·#181 2단계 OCR(**기본 on** — 시연 때는 off), #173, #176, #180, #204 | git log 32f9366..fe11ded |

⚠️ measurements-1015:24-25·99 의 "main 에 없는 것" 서술은 fe11ded 기준으로 낡음(문서 자체는 시연 시점 사실 기록).

### E-2. ADR-0016 제안 경로와 실제 코드

| 경로 | 문서 상태 | 코드 | 근거 |
|---|---|---|---|
| Web PC 음성·텍스트 명령: intent_parser(`command_transport=web_api`) → `POST /api/commands` → Spring → MQTT `voss/command` → Nodes PC hmi_bridge → `/voss/sort/command` | ADR-0016 "현재 구현" | ✅ intent_parser 파라미터 `command_transport`(기본 ros)·`web_context_stream` | 0016:12-18; intent_parser.py:43-49,233-247; scripts/web_pc_voice.sh |
| 텍스트 입력: 웹 → `voss/voice/text` → Web PC hmi_bridge(`voice_status_only`·`local_text_enabled`, `voice_web` 계정) → `/voss/voice/text` → intent_parser → `/text/reply` → SSE `text_reply` | mqtt.md 계약 | ✅ | mqtt.md:23; hmi_bridge.py:89-92,169-188 |
| stop 이중 경로(ROS `/voss/voice/intent` 먼저 + REST) | ADR-0016 **P0 제안·실환경 검증 대기**, intent_json.md:67 "PR #176 선택 계약" | ✅ 구현됨 | intent_parser.py:233-243 (`attempt_stop`) |
| manager 의 진행 중 stop 묶기(coalescing), 실패 뒤 재시도 | 제안 | ✅ 구현됨 | sort_manager.py:488-505; test_stop_coalescing.py |
| stop 최종 안내("정지되었습니다" 등 4문장, stop_timeout_s 3.0) | intent_json.md:65-86 **제안(승인 전)** | ❌ 미구현(sort_manager 에 해당 문장 없음) | grep 결과 0 |
| BoxMotion `/voss/hmi/box_motion`·MQTT `voss/box_motion` | 제안(IDL 미반영) | ❌ IDL 없음, hmi_bridge 는 선택 import 만 | voss_msgs.md:3-10; hmi_bridge.py:37 |

---

## F. 구현 존재 확인 (코드 grep 수준)

| # | 항목 | 판정 | 근거 (fe11ded 파일:줄) |
|---|---|---|---|
| 1 | 음성 시스템 기동 voss_launcher (TR-VOICE-11~16, S2-T09) | ❌ 없음 | 코드 검색 결과 `scripts/voss_up.py:454` 도움말 문자열뿐. 기동 프로필(S2-T10)은 ✅ `scripts/voss_up.py:1-16`(단계별 준비 확인, IDLE 로 끝, voss_down.sh 역순 종료). ADR-0014:33, measurements-1015:36 |
| 2 | 규칙 변경 UpdateZoneMap (TR-VOICE-09) | ❌ 없음(IDL 만) | UpdateZoneMap.srv 있음, sort_manager 서비스 목록에 없음(sort_manager.py:151-156); intent_parser `allow_update_zone_map` 기본 False(intent_parser.py:45, intent_logic.py:410-411); sort_fsm.intent_to_command → None(sort_fsm.py:164); measurements-1015:40 "미구현" |
| 3 | 신규 구역 교시 TeachZone (TR-VOICE-10) | ❌ 없음(IDL 만) | TeachZone.srv 있음, src 전체 `teach_zone`/`TeachZone` 사용 0건; topics.md:21 은 제공한다고 기재 |
| 4 | TR-PAL-12 남은 수에 팔레타이징 반영 (S2-T22) | ❌ 없음 | `remaining = planned − completed(sort_log PLACED/HELD/FAILED)` (HistoryController.java:59-62, HistoryRepository.java:36; SessionController.java:53), pallet_log 미참조; 기본 투입 수량 **10**(PlanRepository.java:15, BRD 는 20 — VOSS_BRD.md:707,851) |
| 5 | `/voss/robot/stop` | ✅ 있음 | robot_gateway.py:155-157; 호출 sort_manager.py:154,488-505, belt_servo.py:382 |
| 6 | MoveToZone TCP 미등록 거부 (BRD 6.1 v1.7) | 🟡 부분 | 모르는 TCP(등록≠tcp_offset, ≠없음) → `NOT_CONFIGURED` 거부(robot_gateway.py:958-961, :838); **등록 없음이면 플랜지 모드로 이동(경고만)** (robot_gateway.py:963-966). BRD v1.7 은 등록 없음도 거부(VOSS_BRD.md:377,885,893) |
| 7 | grid.order 삭제 | 🟡 부분 | `zones.pallet.grid.order` 없음(voss_config.yaml:18, pallet_plan.slot_order 상수 pallet_plan.py:40). A·B·C `grid.order` 는 config 에 있고 sort_manager 가 읽음(voss_config.yaml:13-15; sort_fsm.py:62-72,123-134). BRD v1.7 "아직 코드에 없는 결정"(VOSS_BRD.md:885) |
| 8 | 설정 기본 경로 `~/voss_ws/config` 통일 | 🟡 부분 | 통일됨: voss_host.launch.py:31, robot_gateway.launch.py:103, belt_servo.launch.py:54. 레포 경로 기본 그대로: sort_manager.launch.py:18-19, sort_manager.py:49-50, label_reader.launch.py:21-22, label_reader.py:54-55, voss_vision.launch.py:19-20, voss_dry_run.launch.py:33. voss_config.md:101 "Q23 뒷부분 없음" |
| 9 | 재확인 흐름 defer_recheck | ✅ 있음(기본 false = 즉시 재판독→질문→30 s 보류) | sort_manager.yaml:5; sort_manager.py:101-119; sort_fsm.py:278-283; `recheck` 명령 sort_fsm.py:172 |
| 10 | 위층 박스 실패 → FAILED + PAUSED (TR-PAL-05) | ✅ 있음 | pallet_fsm.py:15-17,482-488 |
| 11 | J6 회전 (`rotate.enable` 기본값) | ✅ 있음, **기본 off** | belt_servo.yaml:62-63 false; params.py:183; gateway servo_angular_enable False(robot_gateway.py:120). 실기 예시만 true(belt_servo_real.yaml.example:68), 결정값 pending #27 |
| 12 | 사다리꼴 z | ✅ 있음, **기본 p** | control.py:42,247; params.py:32; belt_servo.yaml:43 `profile: p`; 예시 주석 "시연 실기 = trapezoid"(belt_servo_real.yaml.example:48) — 시연 실제 값은 **확인 못 함** |
| 13 | 속도 추정 단계 적용 (S2-T15) | 🟡 1단계(로그 전용)만 | control.py:576 "U9-c, 로그 전용"; log_schema.py:63; FF 는 설정값(belt.speed_cmps 4.56 상쇄값, voss_config.yaml:23) |
| 14 | 2단계 OCR 기본 켬 (ADR-0008) | ✅ | label_reader.yaml:13-14 |
| 15 | SortState PALLETIZING · palletize | ✅ | sort_fsm.py:29, 172-175; pallet_fsm.py |
| 16 | reset_zone PALLET IDLE·PAUSED 제한 | ✅ | pallet_fsm.py:282-285 |
| 17 | BoxMotion | ❌ | IDL 없음 (E-2) |

---

## G. 아키텍처·배포 (architecture.md·plan.md)

| 항목 | 현재 문서 | 실제/다른 근거 | 근거 |
|---|---|---|---|
| 노드 그림 | v1.0 그림 그대로(음성·비전·로봇·manager·hmi·logger) | 그림에 없음: `/voss/robot/stop`, `/voss/robot/state`, `/voss/pallet/*`, `/voss/log/list_placements`, `/voss/voice/text`, hmi_bridge 표시 구독, Spring→DB `pallet_log` | architecture.md:7-39 vs topics.md |
| SM → `/gripper` 화살표 | 있음 | sort_manager 에 Gripper 클라이언트 없음(goal 중 호출자는 belt_servo 하나) | architecture.md:28; sort_manager.py:151-156; topics.md:14 |
| Web PC 시연 배치 | 문단 추가(PR #176): Web PC 에 voice_listener·intent_parser·speech_out, web_api 경로, ADR-0016 결정 대기 | 배포 표에는 Web PC 행 없음 | architecture.md:42,44-51 |
| 배포 표 | 호스트(공용 PC)에 음성 3노드·Mosquitto 포함, 웹·AI·DB 컨테이너 | 시연 웹·음성은 정의석 PC(Web PC) — 커밋 시점 **확인 필요** | measurements-1015:26; deployment_two_pc_trial.md:10-14 |
| 상태기계 | IDLE→RUNNING→PICKING→RECHECK→ASKING→PAUSED | PALLETIZING 없음 | architecture.md:56 vs SortState.msg:1 |
| 파지 A안 설명 | "픽셀 오차 → 속도 명령" | 베이스 좌표(m) 오차 제어, feedback err_u/v 삭제 | architecture.md:60 vs voss_msgs.md:42,78 |
| 두산 제어 | "servol_stream 있으면, 없으면 move_line ASYNC" | speedl_stream 주 경로 | architecture.md:64 vs ADR-0010:21, pending #8 |
| 10/10 게이트 | 절차만 | 결과(20/20 통과) 미기재 | architecture.md:62 vs ADR-0002:22-28 |
| 핵심 수치 | "시연 10개 중 8개" | D7: 20개 중 16개 | architecture.md:67-68 vs ADR-0012:37-38 |
| box_tracker | OpenCV 분할(ADR-0011) 반영됨 | 일치 | architecture.md:48 |
| plan.md 마일스톤 | 10/10 G1 통과, 10/11 Sprint 1 마감, 10/13 S2 게이트, 10/15 결과 20/20 | 반영됨 | plan.md:14-18 |
| plan.md Sprint 2 | S2-T01~T22 표(S2-T09 voss_launcher, S2-T22 남은 수 등) | S2-T09·S2-T22 미구현, S2-T21 "A·B 4×2=8" 은 실제 3×2×2 | plan.md:76,84,87,104 |

---

## H. 문서 사이 불일치 목록

| # | 불일치 | 쪽 A | 쪽 B | 비고 |
|---|---|---|---|---|
| H1 | MoveToZone **TCP 등록 없음** 처리 | BRD v1.7: 거부(VOSS_BRD.md:377,885,893) | 코드·topics.md·voss_msgs.md: 플랜지 모드로 이동(robot_gateway.py:963-966; topics.md:21; voss_msgs.md:33) | 요구 vs 구현 |
| H2 | **벨트 사전 개방 폭** | BRD v1.7 TR-PICK-06·6.1: "벨트·트레이 모두 50 mm" (VOSS_BRD.md:261,337) | voss_config `pre_open_mm: 90`(:26), demo.yaml 90, ADR-0009·architecture 90 | 레포 값은 90 |
| H3 | **MoveToZone 속도** | BRD v1.7: 450 mm/s·900 (VOSS_BRD.md:889,893) | launch 기본 300(robot_gateway.launch.py:93, 43318d4 `_2#57`), 시연 300(measurements-1015:28) | BRD 이후 변경 |
| H4 | **pending #29 미정** | pending-decisions.md:35 "미정, 제안 A·B 4×2" | config 3×2×2층 12칸(voss_config.yaml:13-15), BRD v1.7 12칸 승인, plan.md:76,104 "4×2=8" | 표·plan 미갱신 |
| H5 | **pending #28 미정** | pending-decisions.md:34 | belt_servo.yaml:16·예시:24 = 44.0 (dbbdca8 옛 `#36`) | 사실상 결정 |
| H6 | **시연 수치 기준** | architecture.md:67, CLAUDE.md "핵심 수치"·pending #4 행: 10개 중 8개 | ADR-0012:37-38, pending #35, plan.md:18: 20개 중 16개 | |
| H7 | **두산 제어 경로·A안 설명** | architecture.md:60,64 (픽셀 오차, servol/move_line) | ADR-0010 speedl_stream, 베이스 좌표 제어(voss_msgs.md:78) | |
| H8 | **시연 배치(1 PC vs Web PC)** | deployment_two_pc_trial.md:37 · interfaces/README.md:120 "시연은 공용 PC 단일", mqtt.md:14 Mosquitto 공용 PC 호스트, ADR-0006 | architecture.md:42 "Web PC 시연 배치", ADR-0016, measurements-1015:26(웹·음성 정의석 PC) | 시연 때 브로커 위치 **확인 못 함** |
| H9 | **ADR-0016 '제안' vs 구현 머지** | ADR-0016:3 제안·검토 전 | intent_parser.py:233-243 stop 이중 경로, sort_manager.py:488-505 stop 묶기 (a7fe364 `#176`) | |
| H10 | **measurements-1015 "main 에 없는 것"** | measurements-1015:24-25,99 | fe11ded 에 있음(E-1) — 단 reset_zone PALLET RUNNING 은 반대로 결정 | 시점 차이 |
| H11 | `/voss/sort/update_zone_map`·`/voss/robot/teach_zone` | topics.md:14,21 "제공" | 코드 미구현(F-2·F-3), intent_json.md:39 "C 범위·미채택", measurements-1015:40 | BRD TR-VOICE-09·10, 대본 단계 4 |
| H12 | Command 명령 목록 | Command.srv:1 (recheck 없음) | voss_msgs.md:31, mqtt.md:66,78, sort_fsm.py:172 (recheck 있음) | .srv 주석만 |
| H13 | MoveToZone 칸 서술 | voss_msgs.md:33 "A·B·C 3칸 … −60/0/+60", "PICK 은 RECHECK 만"(10/11) | 같은 행 뒤쪽·config: 3×2×2층, PICK = A·B·C·RECHECK·HOLD; `zones.pallet.grid.order [0,4,8,12…]` 언급(삭제됨) | 한 행 안 모순 |
| H14 | voss_config.md 스키마 예시 | voss_config.md:6 구역 목록에 PALLET 없음, :28-30 A·B·C 3×1 예시 | config 실제 3×2×2, PALLET | |
| H15 | ADR-0009 결과 | 0009:34 "격자 X 방향 한 줄만" | config 3×2 | |
| H16 | ADR 상태 줄 | ADR-0008:4 "제안됨" | 10/15 PL 결정으로 운용(0008:18), ADR-0004 승인됨 그대로(0011 이 대체), ADR-0014:51-65 판정 초안 빈칸 잔존 | |
| H17 | TR-PAL-12·투입 수량 기본 | BRD v1.7 20, 남은 수 팔레타이징 반영(VOSS_BRD.md:664,707,851), pending #24 필수 | PlanRepository.java:15 = 10, HistoryController 반영 없음 | |
| H18 | 설정 기본 경로 | BRD v1.7·Q23 통일 | F-8 노드별 혼재 | |
| H19 | MQTT ACL 템플릿 | docker/mqtt/acl (voice/text·표시 토픽·voice_web) | config/mosquitto.acl.example (#20 7토픽만, web 개별 read) | 두 템플릿 불일치 |
| H20 | pending #16 제목 | "31 mm 면 vs 46 mm 면" | ADR-0009:10 · 메모리 규칙: "31 mm 면" 금지 | 용어 |
| H21 | pending #32(D4) vs 시연 | "대치→역삼→청담" | 실제 입력 청담→역삼→대치(measurements-1015:62,70) | 결과 기록은 됨 |
| H22 | 레포 config vs 시연 config | 레포 sha 5e6989ffee80 | 시연 844f45cfc0a2 (measurements-1015:27) | 값 차이 여부 확인 못 함 |
| H23 | ADR-0001 영역 목록 | voice·vision·sort·robot·servo·log | 실제 `pallet`(/voss/pallet/*), `hmi`(/voss/hmi/box_motion 제안) 추가 | |
| H24 | architecture.md 그림 | SM→`/gripper` | sort_manager 는 gripper 를 부르지 않음(topics.md:14) | |
