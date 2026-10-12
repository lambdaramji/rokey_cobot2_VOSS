"""팔레타이징 배치 계획 (S2-T04, BRD v1.4 10.4·TR-PAL-01·03·04). ROS·로봇 없음, pytest 대상.

경로(첫 배송지부터 1~3개 동) + 이번 세션 적재 기록(ListPlacements) → 옮길 순서와 박스마다 팔레트 열·칸.
- 열 수 = 경로 동 수 n. 열 0 = 가장 왼쪽(−X, 분류 구역 slot 0 = −X 끝과 같은 방향), 첫 배송지 = 열 n−1(+X, 트럭 문 쪽).
- 옮기는 순서 = 마지막 배송지부터(열 0 → n−1). 열 안은 칸 0 → 1 → 2 차례로 채운다 — 놓을 때 옆 박스가 한쪽에만 있다
  (가운데 칸을 마지막에 채우면 양쪽 박스 사이로 손가락이 내려간다).
- 대상 = 결과 PLACED · 구역 A/B/C · 동이 경로에 있음 · 아직 팔레트로 안 옮김. 같은 구역·칸에 PLACED 가 둘 이상이면
  (세션 중 reset_zone 으로 칸을 다시 씀) 나중에 놓인 것만 트레이에 있다.
- 같은 입력이면 같은 결과: 입력 목록 순서와 무관하게 (구역, 칸, box_id) 로 정렬한다.
- MoveToZone(PALLET) 칸 번호 = 열 × 3 + 칸, cols = n (BRD v1.4 10.7). 열·칸의 실제 좌표는 gateway(김학민 S2-T03).
- 재개(TR-PAL-08)는 계획을 다시 세우지 않고 remaining() 으로 남은 것만 — 다시 세우면 칸 번호가 당겨진다.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

# sort_fsm.SORT_ZONES 와 같다 (sort_fsm 이 이 모듈을 부르게 되므로 import 하지 않는다)
SORT_ZONES = ("A", "B", "C")
MAX_ROUTE = 3  # 경로 동 최대 = 팔레트 열 최대
PALLET_ROWS = 3  # 열 안 최대 칸 (세로 Y, 1단)


class PlanError(ValueError):
    """계획을 세울 수 없다 — 팔레타이징을 시작하지 않고 이유를 알린다 (메시지는 Command 응답·음성 안내용)."""


@dataclass(frozen=True)
class Placement:
    """이번 세션 적재 기록 한 줄 = ListPlacements 응답 항목 (필드는 S2-T01 에서 확정, 지금은 제안)."""

    box_id: str
    dong: str
    zone: str  # SortResult.zone
    slot: int  # SortResult.slot (S2-T07), 기록 없으면 -1
    outcome: str  # SortResult.outcome
    stamp_ns: int  # SortResult.stamp (PLACED = 놓은 시각)
    palletized: bool = False  # pallet_log 에 DONE 이 있다


@dataclass(frozen=True)
class Move:
    """박스 하나: zone·slot 에서 PICK → 팔레트 col·row 에 DROP."""

    box_id: str
    dong: str
    route_index: int  # 경로 순번 (0 = 첫 배송지)
    zone: str
    slot: int
    col: int  # 팔레트 열 (0 = 가장 왼쪽 −X)
    row: int  # 열 안 칸 (0 부터 차례로)

    @property
    def pallet_slot(self) -> int:
        """MoveToZone(PALLET) slot = 열 × 3 + 칸."""
        return self.col * PALLET_ROWS + self.row


@dataclass(frozen=True)
class Plan:
    route: tuple[str, ...]  # 첫 배송지부터
    moves: tuple[Move, ...]  # 옮길 순서 (마지막 배송지부터)
    empty: tuple[str, ...] = ()  # 경로에 있지만 옮길 박스가 없는 동
    skipped: tuple[str, ...] = ()  # 대상에서 뺀 기록과 이유 (로그용)

    @property
    def cols(self) -> int:
        """MoveToZone(PALLET) cols = 경로 동 수."""
        return len(self.route)


def col_of(route_index: int, n: int) -> int:
    """경로 순번 → 팔레트 열. 첫 배송지(0) = 가장 오른쪽 열 n−1."""
    return n - 1 - route_index


def check_route(route: Sequence[str]) -> None:
    """1~3개, 중복 없음. 아니면 PlanError (TR-PAL-01)."""
    if not 1 <= len(route) <= MAX_ROUTE:
        raise PlanError(f"경로는 1~{MAX_ROUTE}개 동 (받은 {len(route)}개)")
    dup = sorted({d for d in route if list(route).count(d) > 1})
    if dup:
        raise PlanError(f"경로에 같은 동이 두 번: {', '.join(dup)}")


def parse_route(arg: str, dong_of: Callable[[str], str]) -> tuple[str, ...]:
    """Command palletize arg("역삼동,대치동,청담동") → 정식 동 이름 경로. 별칭은 dong_of(sort_fsm.Config.dong_of)로
    바꾼다. 미등록·중복·0개·4개 이상이면 PlanError — 실행하지 않고 되묻는다 (TR-PAL-01)."""
    names = [s.strip() for s in arg.split(",") if s.strip()]
    unknown = [s for s in names if not dong_of(s)]
    if unknown:
        raise PlanError(f"등록되지 않은 동: {', '.join(unknown)}")
    route = tuple(dong_of(s) for s in names)
    check_route(route)
    return route


def plan_pallet(route: Sequence[str], placements: Iterable[Placement]) -> Plan:
    """경로 + 적재 기록 → Plan. 동별 대상이 3개를 넘거나, 대상에 칸 기록이 없거나, 옮길 박스가 없으면 PlanError (TR-PAL-03)."""
    route = tuple(route)
    check_route(route)
    in_route = set(route)
    skipped: list[str] = []
    no_slot: list[str] = []

    # 1) A·B·C 트레이에 지금 있는 박스: 구역·칸마다 마지막 PLACED
    latest: dict[tuple[str, int], Placement] = {}
    for p in sorted(placements, key=lambda p: (p.stamp_ns, p.box_id)):
        zone = p.zone.upper()
        if p.outcome != "PLACED":
            skipped.append(f"{p.box_id} {p.dong or '?'} {p.outcome}")
            continue
        if zone not in SORT_ZONES:
            skipped.append(f"{p.box_id} {p.dong} 구역 {p.zone or '?'}")
            continue
        if p.slot < 0:
            if p.dong in in_route and not p.palletized:
                no_slot.append(p.box_id)
            else:
                skipped.append(f"{p.box_id} {p.dong} 칸 기록 없음")
            continue
        old = latest.get((zone, p.slot))
        if old is not None:
            skipped.append(f"{old.box_id} {old.dong} {zone} 칸 {p.slot} 에 나중 박스 {p.box_id}")
        latest[(zone, p.slot)] = p
    if no_slot:
        raise PlanError(f"칸 기록이 없어 집을 수 없는 박스: {', '.join(no_slot)}")

    # 2) 이미 옮긴 것·경로 밖 동은 트레이에 그대로 둔다
    by_dong: dict[str, list[tuple[str, int, str]]] = {d: [] for d in route}
    for (zone, slot), p in latest.items():
        if p.palletized:
            skipped.append(f"{p.box_id} {p.dong} 이미 팔레트")
        elif p.dong not in in_route:
            skipped.append(f"{p.box_id} {p.dong} 경로 밖")
        else:
            by_dong[p.dong].append((zone, slot, p.box_id))

    over = [f"{d} {len(b)}개" for d, b in by_dong.items() if len(b) > PALLET_ROWS]
    if over:
        raise PlanError(f"동별 최대 {PALLET_ROWS}개를 넘음: {', '.join(over)}")
    if not any(by_dong.values()):
        raise PlanError(f"옮길 박스가 없음: {', '.join(route)}")

    # 3) 마지막 배송지부터, 열 안은 칸 0 → 2
    n = len(route)
    moves = []
    for i in reversed(range(n)):
        dong = route[i]
        for row, (zone, slot, box_id) in enumerate(sorted(by_dong[dong])):
            moves.append(Move(box_id, dong, i, zone, slot, col_of(i, n), row))
    empty = tuple(d for d in route if not by_dong[d])
    return Plan(route, tuple(moves), empty, tuple(sorted(skipped)))


def remaining(plan: Plan, finished: Iterable[str]) -> tuple[Move, ...]:
    """재개: 결과(DONE·FAILED)를 낸 box_id 를 뺀 남은 순서. 칸은 처음 계획 그대로 쓴다."""
    done = set(finished)
    return tuple(m for m in plan.moves if m.box_id not in done)
