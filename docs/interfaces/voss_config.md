# voss_config.yaml 스키마

위치: 호스트 `~/voss_ws/config/voss_config.yaml` (레포의 `config/voss_config.yaml` 을 복사). 비전 컨테이너에는 읽기 전용 마운트.
**쓰는 노드는 sort_manager 뿐.** 다른 노드는 `/voss/sort/zone_map` 토픽을 구독한다.

```yaml
# 형태 예시. 실제 값은 config/voss_config.yaml. 미측정은 null (아래 값 규칙)
version: 1
zone_map:            # 동 → 구역. 자연어로 변경 가능
  역삼동: A
  대치동: B
  청담동: C
zones:               # 두산 posx: x y z rx ry rz, mm/deg. 플랜지 기준(TCP 미적용), 구역 중심, 박스 밑면 +5 mm.
                     # grid: 같은 구역에 여러 개를 놓을 칸. cols = X(벨트 방향) 칸 수, rows = Y 칸 수, pitch_mm = 칸 간격. pose 가 격자 중심
  A:       {pose: null, grid: {cols: 3, rows: 1, pitch_mm: 60}}
  B:       {pose: null, grid: {cols: 3, rows: 1, pitch_mm: 60}}
  C:       {pose: null, grid: {cols: 3, rows: 1, pitch_mm: 60}}
  recheck: {pose: null, grid: {cols: 2, rows: 1, pitch_mm: 60}}
  hold:    {pose: null, grid: {cols: 2, rows: 1, pitch_mm: 60}}
observe_pose: null   # 벨트 위 관측·대기 자세 (= 홈). 플랜지 기준
belt:
  speed_cmps: null       # 10/06 실측
  direction_base: [1.0, 0.0, 0.0]   # 벨트 진행 방향 단위벡터, 두산 베이스 기준(부호 포함)
gripper:                 # 폭은 RG2 보고값 (실제 핑거 간격 ≈ 보고값 − 10 mm, measurements #8)
  pre_open_mm: 90
  grasp_width_mm: 40     # 파지 목표 폭. 박스보다 작아야 grip_detected 가 켜진다
  force_n: null          # 10/06 실측 (종이 박스 안 찌그러지는 값)
ocr:
  confidence_min: 0.6    # 미만이면 재확인 구역
  codes: {"S07-01": "역삼동", "S07-02": "대치동", "S07-03": "청담동"}  # 끝 두 자리 = 동 번호 (확정 10/05)
timing:
  latency_offset_ms: 0   # 실측 튜닝. 0 = 보정 없음(유효값)으로 볼지 null 로 둘지 박병후 확인
```

## 값 규칙 (SRD 상호확인 MC-009·010, #50·#51)
- 키에 단위를 적는다(`_mm`, `_deg`, `_cmps`, `_n`). pose 배열(zones·observe_pose)은 두산 posx (mm, deg).
- 표준 geometry_msgs(`/voss/robot/pose`, `/voss/robot/servo_cmd`, `BoxTrack.position_base`)는 SI(m, rad, m/s). robot_gateway 가 두산 mm·deg 와 변환한다.
- voss_msgs 커스텀 필드는 이름·주석의 단위를 따른다(예: `Gripper.width` mm).
- **미측정 값은 0 이 아니라 `null`.** 그 값을 쓰는 노드는 READY 가 되지 않는다. 0 은 의미 있는 값일 때만 쓴다.
- zones·observe_pose 는 **플랜지 기준** posx(김학민). TCP 기준 값(캘리브레이션 파일 등)과 비교할 때는 TCP 오프셋으로 변환한다.
- 정적 값은 voss_bringup launch 가 이 파일을 읽어 노드 파라미터로 넘기고, `config_version`·`config_sha256` 파라미터도 함께 넘긴다(구현 김학민). 각 노드는 기동 때 그 두 값을 로그에 남긴다.
- 비전 컨테이너 노드(box_tracker·label_reader)는 호스트 bringup 이 아니라 컨테이너 launch 로 뜨므로, 읽기 전용 마운트된 같은 파일을 직접 읽고 version·sha256 을 계산해 로그에 남긴다. 런타임에 쓰는 노드는 sort_manager 뿐.

## 변경 이력
- 2026-10-05: 초안. codes 매핑 확정 (01 역삼 / 02 대치 / 03 청담).
- 2026-10-06: 실측값 입력(zones, observe_pose, belt.speed_cmps 4.8, gripper.force_n 14, grasp_width_mm 39). pose 기준점(플랜지·구역 중심)과 gripper 폭 단위(RG2 보고값)를 주석으로 명시. 값 출처 measurements-1006.md #1 #6 #8. 같은 날 구역마다 트레이를 놓아 zones 를 트레이 안쪽 바닥 중심으로 다시 잼. 구역에 놓을 때도 pre_open_mm(90)으로 벌린다. **grid 변경:** A·B·C 2×2 → 3×1, recheck·hold 에 grid 2×1 추가 (트레이 안에서 X 방향 한 줄로만 놓는다. 총 13칸, 시연 10개 기준). grid 의 cols/rows 방향 명시.
- 2026-10-06: `belt.direction_axis`(문자) → `belt.direction_base`(베이스 기준 단위벡터, 부호 포함). 값 규칙 절 추가 (SRD 상호확인 MC-009, 김학민 합의).
- 2026-10-06: #64 리뷰 반영. 단위 규칙 범위(pose 배열 = 두산 mm·deg, 표준 geometry_msgs = SI, 커스텀 필드 = 주석 단위), 스키마 예시를 null 로, bringup 의 `config_version`·`config_sha256` 전달.
