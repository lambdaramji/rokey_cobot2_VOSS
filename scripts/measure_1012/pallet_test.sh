#!/usr/bin/env bash
# 팔레타이징 확인: 작업자가 말한 동 순서대로 구역 칸에서 집어(PICK) 팔레트에 적재 순서대로 놓는다(DROP). 16개면 끝.
# (sort_manager palletize 의 초과 규칙(물량 많은 동부터)은 없다 — 말한 순서대로 16개에서 자른다. 좌표·동작 확인용)
# ⚠ 로봇이 움직인다 — 사람이 비상정지 옆에서 실행(CLAUDE.md 규칙 6). robot_gateway 서비스만 부른다.
# 사용: bash scripts/measure_1012/pallet_test.sh <2층 구역> <동1> <동2> <동3>
#   예) bash scripts/measure_1012/pallet_test.sh A 청담동 대치동 역삼동
#       → C 6개 → B 6개 → A 2층 1개 + 4개 = 16, A 에 3개 남음(다음 트럭)
# 전제: place_test.sh fill <2층 구역> 으로 채운 상태(1층 6개씩 + 그 구역 칸 6).
# AUTO=1 bash ... 이면 짝마다 Enter 없이 이어서(실패하면 멈춰 묻는다). 팔레트에 놓은 뒤 홈 복귀 없이 다음 집기(DROP).
# 구역 안 집는 순서 = 놓은 순서의 역순(2층 먼저, C 칸 5 마지막 — 트레이 안으로 지나가는 칸이 비어 있어야 함)
source ~/voss_g0_env.sh
two=$1; shift
declare -A ZONE_OF=([역삼동]=A [대치동]=B [청담동]=C)   # voss_config zone_map
declare -A PICKS=([A]="3 0 4 1 5 2" [B]="3 0 4 1 5 2" [C]="3 0 4 1 5 2")   # 채운 순서 2 5 1 4 0 3 의 역순
PICKS[$two]="6 ${PICKS[$two]}"
CAP=16
PORDER=(0 4 8 12 1 5 9 13 2 6 10 14 3 7 11 15)   # 적재 순서 → 팔레트 칸(트럭 안쪽 열부터, 10/13)
mz() { ros2 service call /voss/robot/move_to_zone voss_msgs/srv/MoveToZone "{zone: $1, slot: $2, mode: '$3'}" | grep -m1 "Response("; }
ask() { read -r -p "$1" REPLY < /dev/tty; }

PAIRS=(); t=0
for d in "$@"; do
  z=${ZONE_OF[$d]}
  [ -z "$z" ] && { echo "모르는 동: $d (역삼동·대치동·청담동)"; exit 1; }
  for s in ${PICKS[$z]}; do
    [ $t -ge $CAP ] && break 2
    PAIRS+=("$z:$s/$t"); t=$((t + 1))
  done
done
echo "== 순서: $*  →  ${#PAIRS[@]}개: ${PAIRS[*]}"
ask "== 팔레트 비어 있으면 Enter (중단: Ctrl-C) "
echo "== OBSERVE 로 이동"; mz OBSERVE 0 ""
for pr in "${PAIRS[@]}"; do
  z=${pr%%:*}; rest=${pr#*:}; s=${rest%%/*}; t=${rest#*/}
  [ -z "$AUTO" ] && ask "[$z 칸 $s → 팔레트 칸 ${PORDER[$t]}] Enter → 집기 (중단: Ctrl-C) "
  [ -n "$AUTO" ] && echo "[$z 칸 $s → 팔레트 칸 ${PORDER[$t]}]"
  res=$(mz "$z" "$s" PICK); echo "  집기: $res"
  if ! echo "$res" | grep -q "ok=True"; then
    ask "  → 집기 실패. 박스·그리퍼 확인 후 Enter 하면 다음 짝 (중단: Ctrl-C) "; continue
  fi
  [ -z "$AUTO" ] && ask "  Enter → 팔레트 칸 ${PORDER[$t]} 에 놓기 "
  res=$(mz PALLET "${PORDER[$t]}" DROP); echo "  놓기: $res"   # DROP: 홈 복귀 없이 팔레트 칸 위에서 멈춤 → 바로 다음 집기
  if ! echo "$res" | grep -q "ok=True"; then
    ask "  → 놓기 실패. 확인 후 Enter 하면 다음 짝 (중단: Ctrl-C) "
  fi
done
echo "== 끝: 팔레트 ${#PAIRS[@]}개 → OBSERVE 로 복귀"; mz OBSERVE 0 ""
