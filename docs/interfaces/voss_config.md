# voss_config.yaml 스키마

위치: 호스트 `~/voss_ws/config/voss_config.yaml` (레포의 `config/voss_config.yaml` 을 복사). 비전 컨테이너에는 읽기 전용 마운트.
**쓰는 노드는 sort_manager 뿐.** 다른 노드는 `/voss/sort/zone_map` 토픽을 구독한다.

```yaml
version: 1
zone_map:            # 동 → 구역. 자연어로 변경 가능
  역삼동: A
  대치동: B
  청담동: C
zones:               # 10/06 실측 후 입력 (두산 posx: x y z rx ry rz, mm/deg)
  A:       {pose: [0, 0, 0, 0, 0, 0], grid: {cols: 2, rows: 2, pitch_mm: 60}}
  B:       {pose: [0, 0, 0, 0, 0, 0], grid: {cols: 2, rows: 2, pitch_mm: 60}}
  C:       {pose: [0, 0, 0, 0, 0, 0], grid: {cols: 2, rows: 2, pitch_mm: 60}}
  recheck: {pose: [0, 0, 0, 0, 0, 0]}
  hold:    {pose: [0, 0, 0, 0, 0, 0]}
observe_pose: [0, 0, 0, 0, 0, 0]   # 벨트 위 관측·대기 자세
belt:
  speed_cmps: 0.0        # 10/06 실측
  direction_axis: "x"    # 로봇 베이스 기준 벨트 진행 축
gripper:
  pre_open_mm: 90
  grasp_width_mm: 40
  force_n: 0.0           # 10/06 실측 (종이 박스 안 찌그러지는 값)
ocr:
  confidence_min: 0.6    # 미만이면 재확인 구역
  codes: {"S07-01": "역삼동", "S07-02": "대치동", "S07-03": "청담동"}  # 끝 두 자리 = 동 번호 (확정 10/05)
timing:
  latency_offset_ms: 0   # 실측 튜닝
```

## 변경 이력
- 2026-10-05: 초안. codes 매핑 확정 (01 역삼 / 02 대치 / 03 청담).
