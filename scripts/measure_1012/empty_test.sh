#!/usr/bin/env bash
# 빈손 칸 확인: 칸마다 Enter → MoveToZone PLACE(놓는 높이까지 내려가 열고 OBSERVE 복귀).
# ⚠ 로봇이 움직인다 — 사람이 비상정지 옆에서 실행(CLAUDE.md 규칙 6). robot_gateway 서비스만 부른다.
# 사용: bash scripts/measure_1012/empty_test.sh PALLET 0 4 8 12 1 5 3 7 11 15
source ~/voss_g0_env.sh
z=$1; shift
mz() { ros2 service call /voss/robot/move_to_zone voss_msgs/srv/MoveToZone "{zone: $1, slot: $2, mode: ''}" | grep -m1 "Response("; }
echo "== OBSERVE 로 이동"; mz OBSERVE 0
for s in "$@"; do
  read -r -p "[$z 칸 $s] Enter → 이동 (중단: Ctrl-C) " < /dev/tty
  res=$(mz "$z" "$s"); echo "  이동: $res"
  if ! echo "$res" | grep -q "ok=True"; then
    read -r -p "  → 실패. 확인 후 Enter 하면 다음 칸 (중단: Ctrl-C) " < /dev/tty
  fi
done
echo "== 끝"
