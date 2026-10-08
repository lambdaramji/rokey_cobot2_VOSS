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
                     # grid: 같은 구역에 여러 개를 놓을 칸. cols = X(벨트 방향) 칸 수, rows = Y 칸 수, pitch_mm = 칸 간격. pose 가 격자 중심
                     # 자세는 ry = ±180° 라 rx·rz 가 한 값으로 정해지지 않는다(rx − rz 만 의미). robot_gateway 가 정규화한다
  A:       {pose: null, grid: {cols: 3, rows: 1, pitch_mm: 60}}
  B:       {pose: null, grid: {cols: 3, rows: 1, pitch_mm: 60}}
  C:       {pose: null, grid: {cols: 3, rows: 1, pitch_mm: 60}}
  recheck: {pose: null, grid: {cols: 2, rows: 1, pitch_mm: 60}, view_pose: null}   # view_pose: MoveToZone(RECHECK, VIEW) 때 카메라가 재확인 구역 송장을 보는 자세. 플랜지 posx, 교시 전 null(김학민 T35, #51 MC-017)
  hold:    {pose: null, grid: {cols: 2, rows: 1, pitch_mm: 60}}
observe_pose: null   # 벨트 위 관측·대기 자세 (= 홈). 플랜지 기준
robot:
  tcp_offset_mm: [1.382, 2.684, 246.642]   # 플랜지 → TCP(핑거 끝) 오프셋, 툴 좌표 mm. robot_gateway 가 브링업마다 등록하고,
                                          # /voss/robot/pose·servo_cmd(TCP 기준)와 zones·observe_pose(플랜지) 사이를 변환한다
belt:
  speed_cmps: null       # 10/06 실측
  direction_base: [1.0, 0.0, 0.0]   # 벨트 진행 방향 단위벡터, 두산 베이스 기준(부호 포함). z = 0 = 수평 성분만 쓴다(벨트 기울기 0.18° 무시)
gripper:                 # 폭은 RG2 보고값. 실측 안쪽 간격: 보고 90 → 80 mm, 빈손 보고 39 → 28 mm(10/08), 박스 파지 보고 40.3 → 30 mm(10/06) — 차이 10~11 mm 의 관측 특성이라 보정식으로 쓰지 않는다 (measurements #8)
  pre_open_mm: 90
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
