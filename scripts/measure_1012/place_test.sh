#!/usr/bin/env bash
# 10/12 3×2(+2층) 칸 적재 확인: 사람이 그리퍼에 박스를 넣고 → 닫기 → MoveToZone PLACE.
# ⚠ 로봇이 움직인다 — 사람이 비상정지 옆에서 실행(CLAUDE.md 규칙 6). robot_gateway 서비스만 부른다.
# 사용: bash scripts/measure_1012/place_test.sh          (A → B → C 전부)
#       bash scripts/measure_1012/place_test.sh C        (C 만, 여러 개면 B C 처럼, 트럭은 TRUCK)
#       bash scripts/measure_1012/place_test.sh fill A   (시연 상태 19개: 1층 6개씩 + A 만 2층)
# T1 브링업·T2 robot_gateway 만 띄운 상태에서. sort_manager·belt_servo 는 끈다.
source ~/voss_g0_env.sh

declare -A ORDER=(
  [A]="2 5 1 4 0 3 6"   # 10/12 칸 번호: 위 줄(+Y) 0·1·2, 아래 줄 3·4·5. +X 끝부터 채움, 2층 6 = 칸 0 위
  [B]="2 5 1 4 0 3 6"
  [C]="2 5 1 4 0 3 6"   # C 칸 2(+X·+Y 끝)는 빈 트레이에 맨 먼저 (칸 0 위 거쳐 TCP 40)
  [TRUCK]="0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15"   # 4×2 1층(0~7) → 2층(8~15, 같은 자리 위)
)
ZONES=("$@")
[ ${#ZONES[@]} -eq 0 ] && ZONES=(A B C)
# 시연 상태(19개): bash place_test.sh fill A  → A·B·C 1층 6개씩 + 작업자가 답한 구역(A)만 2층 칸 6
if [ "$1" = "fill" ]; then
  two=${2:-A}
  for z in A B C; do
    [ "$z" != "$two" ] && ORDER[$z]=${ORDER[$z]% 6}
  done
  ZONES=(A B C)
fi

mz() { ros2 service call /voss/robot/move_to_zone voss_msgs/srv/MoveToZone "{zone: $1, slot: $2, mode: ''}" | grep -m1 "Response("; }
gr() { ros2 service call /voss/robot/gripper voss_msgs/srv/Gripper "{width: $1, force: 14.0}" | grep -m1 "Response("; }
ask() { read -r -p "$1" REPLY < /dev/tty; }

echo "== OBSERVE 로 이동"
mz OBSERVE 0

for z in "${ZONES[@]}"; do
  ask "
== $z 구역 (칸 순서: ${ORDER[$z]}) — 트레이 비우고 박스 $(wc -w <<< "${ORDER[$z]}")개 준비되면 Enter "
  for s in ${ORDER[$z]}; do
    while true; do
      gr 90.0 > /dev/null
      ask "[$z 칸 $s] 핑거 사이에 박스 넣고(46 mm 변이 X 방향) 옆면만 받친 채 Enter "
      out=$(gr 39.0); echo "  그리퍼: $out"
      if echo "$out" | grep -q "grip_detected=True"; then break; fi
      ask "  → 파지 안 됨. 박스 빼고 Enter 하면 다시 (건너뛰기: s) "
      [ "$REPLY" = "s" ] && continue 2
    done
    ask "  손 떼고 Enter → $z 칸 $s 로 이동 (중단: Ctrl-C) "
    res=$(mz "$z" "$s"); echo "  이동: $res"
    if ! echo "$res" | grep -q "ok=True"; then
      ask "  → 실패. 박스·로봇 상태 확인 후 Enter 하면 다음 칸 (중단: Ctrl-C) "
    fi
  done
done
echo "== 끝. 그리퍼 열린 채 OBSERVE."
