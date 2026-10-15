# voss_config.yaml 스키마

위치: 호스트 `~/voss_ws/config/voss_config.yaml` (레포의 `config/voss_config.yaml` 을 복사). 비전 컨테이너에는 읽기 전용 마운트.
**쓰는 노드는 sort_manager 뿐.** 다른 노드는 `/voss/sort/zone_map` 토픽을 구독한다.

구역 이름: MoveToZone·TeachZone·SortResult 의 zone 문자열은 대문자(A/B/C/RECHECK/HOLD/OBSERVE). robot_gateway 는 아래 `zones` 키를 대소문자 무시로 찾고, OBSERVE 는 `observe_pose` 를 쓴다.

```yaml
# 형태 예시. 실제 값은 config/voss_config.yaml. 미측정은 null (아래 값 규칙)
version: 1
zone_map:            # 동 → 구역. 자연어로 변경 가능
  역삼동: A
  대치동: B
  청담동: C
aliases:             # 동 → 자연어 별칭 (BRD 2.4). zone_map 토픽의 aliases 로 전파
  역삼동: [역삼, 역삼동]
  대치동: [대치, 대치동]
  청담동: [청담, 청담동]
zones:               # 두산 posx: x y z rx ry rz, mm/deg. 플랜지 기준(TCP 미적용), 구역 중심, 박스 밑면 +5 mm.
                     # grid: 같은 구역에 여러 개를 놓을 칸. cols = X(벨트 방향) 칸 수, rows = Y 칸 수, pitch_mm = 칸 간격, offset_mm(선택, 기본 0) = 칸 줄 중심의 X 위치(pose 기준). pose 는 트레이 중심
                     # layers(선택, 기본 1) = 쌓는 층 수, layer_mm(선택, 기본 27 = 박스 높이) = 층 간격. 칸 수 = cols × rows × layers.
                     # 칸 번호는 1층부터 채운다: slot = layer × (cols × rows) + row × cols + col, 놓기 z = pose z + layer × layer_mm
                     # pitch_y_mm(선택, 기본 pitch_mm) = Y 줄 간격. 줄 위치 = ((rows−1)/2 − row) × pitch_y_mm (pose 기준, **row 0 이 +Y** — 10/12 실측 기준, 커밋 7373e06·zone_motion.py)
                     # col_dy_mm(선택, cols 개) = 열마다 Y 보정(mm). 그 열의 모든 줄·층 칸에 더한다(트럭 +X 끝 열 +10)
                     # order(선택) = 앞쪽 칸을 채우는 순서(0..n−1 을 한 번씩, sort_manager 만 씀). n 번째 박스 → order[n], 넘어가면 n 그대로(2층 등)
                     # in_tray_tcp_z_mm(선택, zones.<z> 키) = 이 구역의 트레이 안 이동 최저 TCP z(robot_gateway). 없으면 zone_min_in_tray_tcp_z_mm(60). **이 높이는 지나가는 칸이 비어 있는 순서일 때만 안전**(채움 = grid.order 로 +X 끝부터, 집기 = pallet_plan 의 칸 번호 순서·위층부터 — test_pick_order_keeps_the_exit_path_empty)
                     # 자세는 ry = ±180° 라 rx·rz 가 한 값으로 정해지지 않는다(rx − rz 만 의미). robot_gateway 가 정규화한다
  A:       {pose: null, grid: {cols: 3, rows: 1, pitch_mm: 60}}
  B:       {pose: null, grid: {cols: 3, rows: 1, pitch_mm: 60}}
  C:       {pose: null, grid: {cols: 3, rows: 1, pitch_mm: 60}}
  recheck: {pose: null, grid: {cols: 2, rows: 1, pitch_mm: 60}, view_pose: null}   # view_pose: MoveToZone(RECHECK, VIEW) 때 카메라가 재확인 구역 송장을 보는 자세. 플랜지 posx, 교시 전 null(김학민 T35, #51 MC-017)
  hold:    {pose: null, grid: {cols: 2, rows: 1, pitch_mm: 60}}
  pallet:  {pose: null, grid: {cols: 4, rows: 2, pitch_mm: 50, pitch_y_mm: 60, layers: 2}}   # 선택. 팔레타이징 트레이(BRD 10.7) — robot_gateway MoveToZone(PALLET) 격자 칸(cell) 좌표. 적재 순서는 sort_manager 내부 상수(`pallet_plan.slot_order`) — `zones.pallet.grid.order` 는 쓰지 않는다(10/13 PL 결정 Q12, 아무도 읽지 않음)
                     # 팔레트(BRD v1.5, 10/13 통합): 4열 × 2줄 × 2층 = 16칸. 칸 위치는 다른 구역과 같은 grid 규칙 — robot_gateway 는 MoveToZone(PALLET, slot = 격자 칸 번호)로 놓는다.
                     # sort_manager(pallet_fsm)는 적재 순서 slot(D2: (열−1)×4 + (층−1)×2 + (줄−1))로 계획하고 격자 번호 = (층−1)×8 + (줄−1)×4 + (열−1) 로 바꿔 부른다.
                     # 열 1 = col 0 = −X(트럭 머리), 줄 1 = row 0 = +Y(D6 전 임시). pose 교시 전(null)이면 sort_manager 가 palletize 를 거부한다.
observe_pose: null   # 벨트 위 관측·대기 자세 (= 홈). 플랜지 기준
robot:
  tcp_offset_mm: [1.382, 2.684, 246.642]   # 플랜지 → TCP(핑거 끝) 오프셋, 툴 좌표 mm. 펜던트 툴·TCP 등록(GripperDA_v1) 또는 등록 없음이어야 하고(gateway 가 MoveToZone 마다 재서 맞춤),
                                          # /voss/robot/pose·servo_cmd(TCP 기준)와 zones·observe_pose(플랜지) 사이를 변환한다
belt:
  speed_cmps: null       # 10/06 실측
  direction_base: [1.0, 0.0, 0.0]   # 벨트 진행 방향 단위벡터, 두산 베이스 기준(부호 포함). z = 0 = 수평 성분만 쓴다(벨트 기울기 0.18° 무시)
gripper:                 # 폭은 RG2 보고값. 실측 안쪽 간격: 보고 90 → 80 mm, 빈손 보고 39 → 28 mm(10/08), 박스 파지 보고 40.3 → 30 mm(10/06) — 차이 10~11 mm 의 관측 특성이라 보정식으로 쓰지 않는다 (measurements #8)
  pre_open_mm: 90
  place_open_mm: null     # 선택. 트레이 안에서 놓을 때 여는 폭(보고값). 벽·옆 박스에 핑거가 닿지 않게 박스가 떨어지는 최소 폭. null·없음 = pre_open_mm
  pick_open_mm: null      # 선택. 트레이(A·B·C·재확인·보류)에서 MoveToZone PICK 전 여는 폭(보고값). null = pre_open_mm. 벨트 사전 개방은 pre_open_mm 그대로
  grasp_width_mm: 39     # 파지 목표 폭 (예시 = 10/06 실측값). 박스보다 작아야 grip_detected 가 켜진다
  force_n: null          # 10/06 실측 (종이 박스 안 찌그러지는 값)
ocr:
  confidence_min: 0.6    # 미만이면 재확인 구역
  codes: {"S07-01": "역삼동", "S07-02": "대치동", "S07-03": "청담동"}  # 끝 두 자리 = 동 번호 (확정 10/05)
timing:
  latency_offset_ms: 0   # 관측→명령 지연 보정. 0 = 보정 없음(유효값). 양수 = 박스 위치를 벨트 방향으로 그만큼 앞당겨 예측. 튜닝 결과는 measurements 에 기록 (박병후)
```

## 값 규칙 (SRD 상호확인 MC-009·010, #50·#51)
- 키에 단위를 적는다(`_mm`, `_deg`, `_cmps`, `_n`). pose 배열(zones·observe_pose)은 두산 posx (mm, deg).
- 표준 geometry_msgs(`/voss/robot/pose`, `/voss/robot/servo_cmd`, `BoxTrack.position_base`)는 SI(m, rad, m/s). robot_gateway 가 두산 mm·deg 와 변환한다.
- voss_msgs 커스텀 필드는 이름·주석의 단위를 따른다(예: `Gripper.width` mm).
- **미측정 값은 0 이 아니라 `null`.** 그 값을 쓰는 노드는 READY 가 되지 않는다. 0 은 의미 있는 값일 때만 쓴다.
- **null 전달:** launch 파라미터는 null(None)을 받지 않으므로 bringup 은 null 키를 **넘기지 않는다**. 노드는 선언됐지만 값이 오지 않은 파라미터를 미측정으로 보고 READY 를 거부한다(박병후 제안, 김학민 bringup 구현 시 확정).
- `/voss/robot/pose`·`/voss/robot/servo_cmd` 의 기준점 = **TCP(핑거 끝)**, `header.frame_id` = `base_link`. servo_cmd twist 는 같은 기준점의 선속도(m/s)·각속도(rad/s) (topics.md, #53 MC-010).
- `belt.direction_base` 는 단위벡터 — 소비 노드는 기동 때 `‖direction_base‖` 가 1 ± 0.01 이 아니면 거부한다.
- zones·observe_pose 는 **플랜지 기준** posx(김학민). TCP 기준 값(캘리브레이션 파일 등)과 비교할 때는 TCP 오프셋으로 변환한다.
- 정적 값은 voss_bringup launch 가 이 파일을 읽어 노드 파라미터로 넘기고, `config_version`·`config_sha256` 파라미터도 함께 넘긴다(구현 김학민). 각 노드는 기동 때 그 두 값을 로그에 남긴다.
- 비전 컨테이너 노드(box_tracker·label_reader)는 호스트 bringup 이 아니라 컨테이너 launch 로 뜨므로, 읽기 전용 마운트된 같은 파일을 직접 읽고 version·sha256 을 계산해 로그에 남긴다. 런타임에 쓰는 노드는 sort_manager 뿐.
- **launch 로 넘기는 정적 값은 정지 상태에서만 바꾼다.** 바꾼 뒤에는 같은 version 을 모든 노드에 다시 적용하고 ready 를 확인한 다음 재개한다(#53 MC-009). 운전 중 일부 노드만 새 값을 쓰는 상태를 만들지 않는다.
- **런타임 zone_map** 은 sort_manager 가 IDLE·PAUSED 에서만 UpdateZoneMap 을 받아 한 번에 바꾸고 version 을 올려 `/voss/sort/zone_map` 으로 발행한다. RUNNING·PICKING 중 요청은 `ok=false`(남현지 #84 리뷰).
- **`zones.pallet`(Sprint 2, BRD v1.5)** 은 MoveToZone(`zone=PALLET`, `mode=DROP`, slot 0~15)만 쓴다. 격자는 4 × 2 × 2 고정이라 `cols`·`lanes`·`layers` 는 확인용이다(다르면 gateway 가 기동 거부 — S2-T03 제안). sort_manager 의 구역 칸 수(capacity, `grid`)에는 들지 않고, 팔레트 칸 카운터는 sort_manager 가 따로 센다(`reset_zone PALLET` 으로 0). 교시 전 `pose: null` 이면 gateway 는 `NOT_CONFIGURED`, sort_manager 는 palletize 를 거부한다. 지금 gateway(`config_params.ZONES`)·sort_manager(`sort_fsm.ZONES`)는 정해진 구역 키만 읽어 `pallet` 키가 있어도 기동에 영향이 없다.
- 서보 전용 값(Kp, 높이, 오프셋, age·입력 상실 watchdog)은 voss_config 가 아니라 belt_servo 파라미터 YAML 에 둔다(#53 MC-009). robot_gateway 의 `servo_cmd` 만료 watchdog 은 gateway 파라미터다.

## 변경 이력
- 2026-10-05: 초안. codes 매핑 확정 (01 역삼 / 02 대치 / 03 청담).
- 2026-10-06: `aliases` 추가 (#10, pending #1 승인 PR). sort_manager 는 zone_map 발행 때 각 ZoneMapEntry 에 `code`(ocr.codes 역참조)와 `aliases` 를 채운다. 별칭이 없는 동은 빈 목록.
- 2026-10-06: 실측값 입력(zones, observe_pose, belt.speed_cmps 4.8, gripper.force_n 14, grasp_width_mm 39). pose 기준점(플랜지·구역 중심)과 gripper 폭 단위(RG2 보고값)를 주석으로 명시. 값 출처 measurements-1006.md #1 #6 #8. 같은 날 구역마다 트레이를 놓아 zones 를 트레이 안쪽 바닥 중심으로 다시 잼. 구역에 놓을 때도 pre_open_mm(90)으로 벌린다. **grid 변경:** A·B·C 2×2 → 3×1, recheck·hold 에 grid 2×1 추가 (트레이 안에서 X 방향 한 줄로만 놓는다. 총 13칸, 시연 10개 기준). grid 의 cols/rows 방향 명시.
- 2026-10-07: `robot.tcp_offset_mm` 추가 (#65 리뷰, #53 MC-010). `/voss/robot/pose`·`servo_cmd` 는 TCP 기준이고 zones·observe_pose 는 플랜지 기준이라, robot_gateway 가 이 값으로 변환한다. 값은 measurements #6 펜던트 TCP.
- 2026-10-06: `belt.direction_axis`(문자) → `belt.direction_base`(베이스 기준 단위벡터, 부호 포함). 값 규칙 절 추가 (SRD 상호확인 MC-009, 김학민 합의).
- 2026-10-06: #64 리뷰 반영. 단위 규칙 범위(pose 배열 = 두산 mm·deg, 표준 geometry_msgs = SI, 커스텀 필드 = 주석 단위), 스키마 예시를 null 로, bringup 의 `config_version`·`config_sha256` 전달.
- 2026-10-07: #64 를 main 위로 다시 쌓으며 #57 최종본과 합침. 박병후 리뷰 반영 — latency_offset_ms 0 = 보정 없음·양수 = 앞당김, null 키는 launch 로 넘기지 않음, pose·servo_cmd 기준점 TCP·base_link, direction_base 크기 검사·z = 0 의미.
- 2026-10-07: SRD v1.0 정합 (#6). `zones.recheck.view_pose`(null, MC-017) 추가, 정지 상태에서만 정적 설정 변경(MC-009)·런타임 zone_map 은 IDLE·PAUSED 에서만(남현지 #84 리뷰)·서보 전용 값 위치·gateway watchdog 위치를 값 규칙에 추가.
- 2026-10-08: gripper 주석의 "실제 간격 ≈ 보고값 − 10 mm" 를 실측표로 바꿈 — 보고 90 → 80, 빈손 보고 39 → 28 mm(김학민 10/08), 박스 40.3 → 30(10/06). 값·단위(보고값) 변경 없음 (#41).
- 2026-10-08: grid `offset_mm` 추가, **C 칸 −60/0/+60 → −80/−30/+20**(pitch 50, offset −30) (김학민 #41). 수직 놓기 자세로는 C 트레이(x ≈ 675)의 +X 쪽에 팔이 닿지 않는다 — fkin 으로 검증한 ikin(J3 ≥ 15°): +60 은 해 없음, 0 위 최고 TCP 100, +20 위 61. 트레이는 고정, 우선 트레이 안에 넣는 것이 목표라 칸을 −X 로 모았다(벽 4.5 mm·박스 사이 4 mm, 통합 뒤 조정). 칸 수 3 그대로라 sort_manager 영향 없음. 먼 칸은 robot_gateway 가 칸 0 위로 들어가 트레이 안에서 낮게(TCP ≥ 60) 옆으로 간다.
- 2026-10-08: `zones.recheck.view_pose` 실측값 입력 [520.58, −37.92, 367.14, 169.44, −180.0, 79.38] (플랜지, 김학민 T35 #44). 펜던트 TCP [517.9, −39.3, 120.5, …] 교시를 tcp_offset_mm 로 변환. 카메라 광축이 재확인 트레이 중심 위, 송장 면까지 약 300 mm. 스키마·키 변경 없음. 출처 measurements-1008 #13.
- 2026-10-08 저녁: `robot.tcp_offset_mm` 주석 — gateway 는 TCP 를 등록하지 않고, 컨트롤러 등록이 이 값이거나 없을 때만 MoveToZone 을 한다로 고침 (#41, 10/08 18:26 사고). 값 변경 없음.
- 2026-10-12: **Sprint 2**(BRD v1.4 10.7, S2-T01 — 제안, 김학민 확인 필요). `zones.pallet`(pose·size_mm·max_cols·rows·row_pitch_mm·drop_margin_mm) 스키마 추가. 값은 S2-T02 교시·pending #23 실측 뒤 `config/voss_config.yaml` 에 넣는다(이 PR 은 스키마만).
- 2026-10-12 저녁: **BRD v1.5**(결정 D1·D2 — 제안). `zones.pallet` 를 4열·2줄·2층(`cols`·`lanes`·`layers`, `pitch_x_mm`·`pitch_y_mm`, `layer_mm` 27, `drop_margin_mm`)으로. **A·B·C 트레이 grid 는 동별 7개 이상**(D1: A·B 4×2 = 8칸, C 는 +X 도달 한계로 3×2 = 6칸 검토 — 김학민 S2-T21). sort_manager 의 구역 칸 수는 grid 에서 그대로 계산하므로 코드는 바뀌지 않는다.
- 2026-10-12 (로컬 시험 브랜치 `local/1012-recheck-flow`, 원격 막힘 — 담당 확인 전): grid `layers`·`layer_mm` 추가(선택, 기본 1층·27 mm). 시연 시나리오(A·B·C 6칸을 채운 뒤 사람이 판정한 흐린 송장 1개를 칸 0 위 2층에)용. 칸 수 = cols × rows × layers 라 sort_manager 의 구역 용량과 robot_gateway 의 칸 범위가 함께 바뀐다. layers 를 안 쓰면 기존과 같다.
- 2026-10-12 (로컬 시험 브랜치): `gripper.place_open_mm` 추가(선택). robot_gateway 가 PLACE 개방과 PICK 확인 실패 후퇴 때 이 폭으로 연다. 3×2 칸에서 90 으로 열면 핑거가 트레이 벽·옆 박스에 닿을 수 있어서다. 10/12 실측: 보고 50 mm 에서 박스가 떨어짐(최소). 없으면 pre_open_mm 그대로. belt_servo 의 사전 개방(pre_open_mm)·PICK 하강 전 개방은 바꾸지 않는다.
- 2026-10-12 (로컬 시험 브랜치): grid `pitch_y_mm` 추가(선택, 기본 pitch_mm). A·B·C 3×2 칸에서 Y 줄 간격을 X 칸 간격과 따로 정하려고(기존 pose 에서 ±y 실측). 없으면 기존과 같다.
- 2026-10-12 (로컬 시험 브랜치): grid `order`·zones.<z>.`in_tray_tcp_z_mm` 추가(선택). C 3×2 칸 5(+X·+Y 끝)는 그 위로 TCP 60 이 안 닿는다(ikin: TCP 40 까지 J3 16°, 50 은 12°). 트레이가 빌 때 먼저 놓도록 C `order: [5, 2, 4, 1, 3, 0]`, 트레이 안 이동을 C 만 TCP 40 으로. TCP 40 이면 든 박스 밑면(≈ 32)이 놓인 박스 윗면(≈ 28~33)과 같아서 칸 5 는 반드시 빈 트레이에 먼저 놓아야 한다. 2층(칸 6)은 칸 0 위 그대로. 같은 날 실기 요청으로 경로 수정: 칸 0 위에서는 공통 높이(TCP 60)까지만 내려가 칸 5 위 TCP 40 으로 비스듬히 간다(칸 0 에서 트레이 깊이 들어가지 않게, 사선 11 점 ikin 확인 — 실측 J3 59°→16°). 돌아올 때도 같은 사선. 이어서 출입구를 같은 Y 줄의 −X 끝 칸으로(C 칸 2 → 칸 0, 칸 5 → 칸 3): 칸 3 위 TCP 60 → 칸 5 위 TCP 40 을 줄 따라(ikin J3 55°→16°, 칸 3 위 TCP 120 은 46°).
- 2026-10-12 (로컬 시험 브랜치): zones `truck` 추가(선택). 분류 20개를 마친 뒤 16개를 트럭 트레이에 4×2 × 2층으로 옮기는 시연용. 칸 규칙은 다른 트레이와 같다(pose = 트레이 중심, Y 줄 ±30). X 4칸은 46 mm 박스가 안쪽 215 mm 에 들어가도록 pitch 50(칸 −75/−25/+25/+75, 벽까지 9.5 mm). 지금은 robot_gateway 만 읽는다(sort_manager 는 모름).
- 2026-10-12 (로컬 시험 브랜치): 팔레타이징(구역 트레이 → 트럭)용. `gripper.pick_open_mm` 추가(선택) — 3×2 트레이에서 90 으로 열면 옆 줄 박스에 핑거가 닿아서. robot_gateway: MoveToZone PICK 을 A·B·C·HOLD 에도 허용(칸 위로 TCP 120 이 안 되면 출입구 칸 위로 트레이 안에서 나와 올라감 — 집는 순서는 놓은 순서의 역순이어야 지나가는 칸이 비어 있다), 수평 이동이 베이스 뒤(−X)를 지나면 앞쪽으로 원호 경유(OBSERVE ↔ 트럭, 10/12 실기 TIMEOUT).
- 2026-10-12 (로컬 시험 브랜치): grid `col_dy_mm` 추가(선택). 트럭 칸 3(베이스에서 166 mm)이 놓는 높이에서 1206(닿지 않음) — 성공한 모든 칸은 J2 ≥ −20.3°·J3 ≤ 132.7°, 칸 3 은 −26.0°·135.8°. 사용자 결정으로 +X 끝 열(칸 3·7·11·15)만 +Y 10 mm(ikin: J3 135.0°, 성공 여부는 실기 확인).
- 2026-10-12 (로컬 시험 브랜치): MoveToZone mode `STAY` 추가(voss_msgs) — 놓고 OBSERVE 로 돌아가지 않고 칸 위(못 닿으면 출입구 칸 위)로 올라가 멈춘다. 트럭 적재 뒤 바로 다음 구역 박스 집기. 실기 16개 집기·트럭 적재 성공(집은 폭 40.3~41.2 mm). robot_gateway launch `zone_acc_mm_s2` 인자 추가(속도 올리기).
- 2026-10-13 (로컬 시험 브랜치, BRD v1.5 10.7 이름에 맞춤 — 10/13 결정): zones `truck` → `pallet`, MoveToZone zone `TRUCK` → `PALLET`, mode `STAY` → `DROP`. `zones.pallet.grid.order` = 적재 순서(말한 순서대로 트럭 안쪽 1열부터 열 단위: 1층 0·4 → 2층 8·12 → 2열 1·5·9·13 …). 칸 번호(층 × 8 + 줄 × 4 + 열, 줄 0 = +Y)는 그대로라 robot_gateway 좌표는 바뀌지 않는다. sort_manager 가 칸 수(16)와 order 를 읽는다. 트레이는 10/12 에 +Y 80 mm 옮겨 재교시(칸 3 1206 해결, col_dy 는 쓰지 않음).
- 2026-10-13 낮: **김학민 로컬 시험 브랜치(10/12 실기) 통합**(PL 결정). `zones.pallet` 는 김학민의 grid 형식(cols 4·rows 2·layers 2·pitch_mm·pitch_y_mm·order)을 쓴다 — v1.5 초안의 `lanes`·`pitch_x_mm`·`drop_margin_mm` 는 쓰지 않는다(개방 폭은 `gripper.place_open_mm`). grid `layers`·`layer_mm`·`pitch_y_mm`·`col_dy_mm`·`order`, zones.<z>.`in_tray_tcp_z_mm`, `gripper.place_open_mm`·`pick_open_mm` 그대로. 말한 순서 = 배송 순서(10/13 PL) — 위 10/13 줄의 "말한 순서대로 트럭 안쪽부터"는 쓰지 않는다.
- 2026-10-13 저녁: `zones.pallet.grid.order` 삭제(10/13 PL 결정 Q12) — 아무도 읽지 않고 적재 순서는 `pallet_plan.slot_order` 상수다. A·B·C 의 `zones.<z>.grid.order`(앞쪽 칸 채우는 순서, sort_manager)는 그대로. 설정 파일에서 지우는 것은 demo.yaml 레포 승격(Q23) 때 함께.
- 2026-10-14: `in_tray_tcp_z_mm` 안전 전제(지나가는 칸이 빈 순서)를 명시하고 pallet_plan 시험으로 고정 (#47 박병후 리뷰). 값·필드 변경 없음.
- 2026-10-14: belt.speed_cmps 4.8 → 4.56 (S2-T15, #28). 10/13 S4 실기 36/36: FF 와 닫힘 순간 TCP−박스 중심 오프셋이 선형(3.0~3.9 mm per 0.1 cm/s), 중심 파지 FF* = 4.553(사다리꼴)·4.57(p). 값은 실측 속도가 아니라 상쇄값이며 재조정 규칙은 voss_config.yaml 주석과 src/voss_servo/design/U13-belt-along.md 6.6. sim.launch.py 가 같은 키로 fake_box 속도를 정하므로 sim 박스 속도도 4.56 이 된다.
- 2026-10-14: **레포 `config/voss_config.yaml` 에 현장 값 승격**(10/13 PL 결정 Q23 의 앞부분, S2-T21 김학민). 공용 PC 설정(10/12 저녁 시나리오·10/13 게이트·10/14 통합)과 같은 값: A·B·C `grid` 3×2 × 2층(`pitch_y_mm` 60, `layers` 2, `order` [2, 5, 1, 4, 0, 3]), C `in_tray_tcp_z_mm` 40, `zones.pallet`(pose 교시값, 4×2 × 2층 — `grid.order` 는 Q12 대로 넣지 않음), `gripper.place_open_mm`·`pick_open_mm` 50. 필드·스키마 변경 없음(값만). voss_manager 로직 시험은 옛 3×1 값을 `src/voss_manager/test/fixtures/voss_config_3x1.yaml` 로 고정해 읽고, 레포 값은 `test_repo_config.py` 가 따로 확인한다. Q23 의 뒷부분(노드별 기본 경로를 `~/voss_ws/config` 로 통일)은 이 변경에 없다.
- 2026-10-14: `gripper.force_n` 은 **14 N 유지**(값 변경 없음, #52 박병후 리뷰). 옛 레포의 14 → 12 N 변경(10/11, 커밋 74608fc, 브랜치 `fix/45-gripper-force-12n`)은 옛 main 에도 머지되지 않았고 레포 이관 때 이 레포 main 에도 들어오지 않았다. 10/12 저녁 시나리오·10/13 S4 36/36·게이트 팔레타이징 16/16·10/14 통합은 모두 공용 PC 설정 14 N 으로 돌았다. 12 N 으로 바꾸려면 벨트 추종 파지를 12 N 으로 다시 재야 한다(74608fc 는 벨트 추종 미실시).
