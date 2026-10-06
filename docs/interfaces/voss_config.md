# voss_config.yaml 스키마

위치: 호스트 `~/voss_ws/config/voss_config.yaml` (레포의 `config/voss_config.yaml` 을 복사). 비전 컨테이너에는 읽기 전용 마운트.
**쓰는 노드는 sort_manager 뿐.** 다른 노드는 `/voss/sort/zone_map` 토픽을 구독한다.

```yaml
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
  A:       {pose: [0, 0, 0, 0, 0, 0], grid: {cols: 3, rows: 1, pitch_mm: 60}}
  B:       {pose: [0, 0, 0, 0, 0, 0], grid: {cols: 3, rows: 1, pitch_mm: 60}}
  C:       {pose: [0, 0, 0, 0, 0, 0], grid: {cols: 3, rows: 1, pitch_mm: 60}}
  recheck: {pose: [0, 0, 0, 0, 0, 0], grid: {cols: 2, rows: 1, pitch_mm: 60}}
  hold:    {pose: [0, 0, 0, 0, 0, 0], grid: {cols: 2, rows: 1, pitch_mm: 60}}
observe_pose: [0, 0, 0, 0, 0, 0]   # 벨트 위 관측·대기 자세 (= 홈). 플랜지 기준
robot:
  tcp_offset_mm: [1.382, 2.684, 246.642]   # 플랜지 → TCP(핑거 끝) 오프셋, 툴 좌표 mm. robot_gateway 가 브링업마다 등록하고,
                                          # /voss/robot/pose·servo_cmd(TCP 기준)와 zones·observe_pose(플랜지) 사이를 변환한다
belt:
  speed_cmps: 0.0        # 10/06 실측
  direction_axis: "x"    # 로봇 베이스 기준 벨트 진행 축
gripper:                 # 폭은 RG2 보고값 (실제 핑거 간격 ≈ 보고값 − 10 mm, measurements #8)
  pre_open_mm: 90
  grasp_width_mm: 39     # 파지 목표 폭 (예시 = 10/06 실측값). 박스보다 작아야 grip_detected 가 켜진다
  force_n: 0.0           # 10/06 실측 (종이 박스 안 찌그러지는 값)
ocr:
  confidence_min: 0.6    # 미만이면 재확인 구역
  codes: {"S07-01": "역삼동", "S07-02": "대치동", "S07-03": "청담동"}  # 끝 두 자리 = 동 번호 (확정 10/05)
timing:
  latency_offset_ms: 0   # 실측 튜닝
```

## 변경 이력
- 2026-10-05: 초안. codes 매핑 확정 (01 역삼 / 02 대치 / 03 청담).
- 2026-10-06: `aliases` 추가 (#10, pending #1 승인 PR). sort_manager 는 zone_map 발행 때 각 ZoneMapEntry 에 `code`(ocr.codes 역참조)와 `aliases` 를 채운다. 별칭이 없는 동은 빈 목록.
- 2026-10-06: 실측값 입력(zones, observe_pose, belt.speed_cmps 4.8, gripper.force_n 14, grasp_width_mm 39). pose 기준점(플랜지·구역 중심)과 gripper 폭 단위(RG2 보고값)를 주석으로 명시. 값 출처 measurements-1006.md #1 #6 #8. 같은 날 구역마다 트레이를 놓아 zones 를 트레이 안쪽 바닥 중심으로 다시 잼. 구역에 놓을 때도 pre_open_mm(90)으로 벌린다. **grid 변경:** A·B·C 2×2 → 3×1, recheck·hold 에 grid 2×1 추가 (트레이 안에서 X 방향 한 줄로만 놓는다. 총 13칸, 시연 10개 기준). grid 의 cols/rows 방향 명시.
- 2026-10-07: `robot.tcp_offset_mm` 추가 (#65 리뷰, #53 MC-010). `/voss/robot/pose`·`servo_cmd` 는 TCP 기준이고 zones·observe_pose 는 플랜지 기준이라, robot_gateway 가 이 값으로 변환한다. 값은 measurements #6 펜던트 TCP.
