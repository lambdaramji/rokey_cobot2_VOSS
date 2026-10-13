"""팔레타이징 배치 계획 (S2-T04, BRD v1.5 10.4·TR-PAL-01·03·04·11). ROS·로봇 없음, pytest 대상.

경로(첫 배송지부터 1~3개 동) + 이번 세션 적재 기록(ListPlacements) → 실을 박스와 칸, 싣지 않을 박스와 사유.
팔레트 = 트럭 짐칸, **4열 × 2줄 × 2층 = 16칸 고정**(결정 D2). 열 1 = 왼쪽(−X, 트럭 머리 = 가장 안쪽), 열 4 = 오른쪽(+X, 문).
- 대상 = 결과 PLACED · 구역 A/B/C · 동이 경로에 있음 · 아직 팔레트로 안 옮김(작업자 답으로 적재된 흐린 송장 박스 포함).
  같은 구역·칸에 PLACED 가 둘 이상이면(세션 중 reset_zone 으로 칸을 다시 씀) 나중 것만 트레이에 있다.
  경로 밖 동의 박스는 EXCLUDED(경로 제외)로 센다. 동별 상한은 없다.
- 수량: 대상이 16개 이하면 모두 싣는다. 넘으면 동을 물량 많은 순으로(동률이면 경로상 먼저 방문하는 동이 후순위)
  min(물량, 남은 칸)만큼 배정하고, 못 실은 박스는 OVERFLOW — 원래 칸에 그대로 둔다(TR-PAL-11).
  한 동의 일부만 실을 때는 (구역, 칸, box_id) 순으로 앞의 박스부터 싣는다(명세 미정 — 어느 박스를 남길지).
- 2층 트레이(tray_layer_cells)는 구역 안에서 위층 박스부터 집는다 — 2층 박스가 덮은 1층 칸을 먼저 집지 않게
  (10/13: A 7번째 = 칸 6 이 칸 0 위). 일부만 실으면 아래층이 남는다. 층 = slot // 한 층 칸 수.
- 위치: 수량과 따로, 마지막 방문 동부터 slot 0 부터 차례로. slot = (열−1)×4 + (층−1)×2 + (줄−1) — 열 단위, 열 안은
  1층 2칸 → 2층 2칸, 같은 층은 1줄 → 2줄(결정 D6 제안). 한 열에 두 동이 섞이면 먼저 내릴 동이 위층에 온다.
  옮기는 순서 = slot 순서(1 → 16).
- 같은 입력이면 같은 결과: 입력 목록 순서와 무관하게 정렬한다. 계획 하나를 HMI·TTS·DB·로봇 시퀀스가 함께 쓴다.
- 재개(TR-PAL-08)는 계획을 다시 세우지 않고 remaining() 으로 남은 것만 — 다시 세우면 칸 번호가 당겨진다.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass

# sort_fsm.SORT_ZONES 와 같다 (sort_fsm 이 이 모듈을 부르게 되므로 import 하지 않는다)
SORT_ZONES = ("A", "B", "C")
MAX_ROUTE = 3  # 경로 동 최대
COLS, LANES, LAYERS = 4, 2, 2  # 열(X) × 줄(Y) × 층(Z), 결정 D2
CAPACITY = COLS * LANES * LAYERS  # 16


def grid_cell(slot: int) -> int:
    """적재 순서 slot(D2) → robot_gateway 격자 칸 번호 = (층−1)×8 + (줄−1)×4 + (열−1) (voss_msgs.md MoveToZone PALLET).
    gateway 는 다른 구역과 같은 grid 규칙(layer×(cols×rows) + row×cols + col, col 0 = −X 트럭 머리)으로 놓고,
    줄 1 = row 0(+Y, 결정 D6 전 임시)이다. 10/12 실기 `zones.pallet.grid.order` [0,4,8,12,1,5,…] 와 같은 대응."""
    col, layer, lane = slot_cell(slot)
    return (layer - 1) * COLS * LANES + (lane - 1) * COLS + (col - 1)


def slot_order(layers: int = LAYERS) -> tuple[int, ...]:
    """채우는 칸 순서. layers=2(기본) = slot 0 → 15. layers=1 = 1층 칸만(0·1·4·5·8·9·12·13) — 게이트에서 2층 놓기를
    시연에서 뺄 때(ADR-0014 B, sort_manager `pallet_layers`). 칸 번호 규칙(D2)·메시지는 그대로다."""
    if layers not in (1, 2):
        raise ValueError(f"layers={layers} — 1 | 2")
    return tuple(s for s in range(CAPACITY) if slot_cell(s)[1] <= layers)


OVERFLOW, EXCLUDED = "OVERFLOW", "EXCLUDED"


class PlanError(ValueError):
    """계획을 세울 수 없다 — 팔레타이징을 시작하지 않고 이유를 알린다 (메시지는 Command 응답·음성 안내용)."""


@dataclass(frozen=True)
class Placement:
    """이번 세션 적재 기록 한 줄 = ListPlacements 응답 항목 (voss_msgs.md Placement)."""

    box_id: str
    dong: str
    zone: str  # SortResult.zone
    slot: int  # SortResult.slot (S2-T07), 기록 없으면 -1
    outcome: str  # SortResult.outcome
    stamp_ns: int  # SortResult.stamp (PLACED = 놓은 시각)
    palletized: bool = False  # pallet_log 에 DONE 이 있다


def slot_cell(slot: int) -> tuple[int, int, int]:
    """팔레트 slot 0~15 → (열, 층, 줄), 모두 1부터. slot = (열−1)×4 + (층−1)×2 + (줄−1)."""
    if not 0 <= slot < CAPACITY:
        raise ValueError(f"pallet slot {slot} 는 0~{CAPACITY - 1}")
    col, w = divmod(slot, LANES * LAYERS)
    layer, lane = divmod(w, LANES)
    return col + 1, layer + 1, lane + 1


@dataclass(frozen=True)
class Move:
    """실을 박스 하나: zone·slot 에서 PICK → 팔레트 pallet_slot 에 DROP."""

    box_id: str
    dong: str
    route_index: int  # 경로 순번 (0 = 첫 배송지)
    zone: str
    slot: int
    pallet_slot: int  # 0~15. 기본(2층)은 옮기는 순서 − 1, 1층만이면 slot_order(1) 의 차례

    @property
    def cell(self) -> tuple[int, int, int]:
        """(열, 층, 줄), 1부터."""
        return slot_cell(self.pallet_slot)


@dataclass(frozen=True)
class Unloaded:
    """싣지 않는 박스 — 원래 구역·칸에 그대로 둔다 (TR-PAL-11)."""

    box_id: str
    dong: str
    route_index: int  # 경로 순번, EXCLUDED 는 -1
    zone: str
    slot: int
    reason: str  # OVERFLOW | EXCLUDED


@dataclass(frozen=True)
class Plan:
    route: tuple[str, ...]  # 첫 배송지부터
    moves: tuple[Move, ...]  # 옮길 순서 = slot 0 → 15
    unloaded: tuple[Unloaded, ...] = ()  # 초과·경로 제외 (구역, 칸 순)
    empty: tuple[str, ...] = ()  # 경로에 있지만 대상이 없는 동
    skipped: tuple[str, ...] = ()  # 대상에서 뺀 기록과 이유 (로그용)
    # 지금 A·B·C 트레이에 있는 박스 (구역, 칸, box_id) — 경로 밖·초과 포함. 다 옮긴 구역의 칸 카운터를 되돌리는 데 쓴다
    occupied: tuple[tuple[str, int, str], ...] = ()
    capacity: int = CAPACITY  # 쓸 수 있는 칸 수 (1층만이면 8)

    def counts(self) -> tuple[tuple[str, int, int, int], ...]:
        """(동, 실을 수, 초과 수, 경로 제외 수) — 경로 동(방문 순서) 다음에 경로 밖 동(이름 순). HMI·TTS·DB 가 함께 쓴다."""
        load = {d: 0 for d in self.route}
        over = {d: 0 for d in self.route}
        excl: dict[str, int] = {}
        for m in self.moves:
            load[m.dong] += 1
        for u in self.unloaded:
            if u.reason == OVERFLOW:
                over[u.dong] += 1
            else:
                excl[u.dong] = excl.get(u.dong, 0) + 1
        rows = [(d, load[d], over[d], 0) for d in self.route]
        rows += [(d, 0, 0, excl[d]) for d in sorted(excl)]
        return tuple(rows)

    @property
    def overflow(self) -> int:
        return sum(1 for u in self.unloaded if u.reason == OVERFLOW)

    @property
    def excluded(self) -> int:
        return sum(1 for u in self.unloaded if u.reason == EXCLUDED)


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


def allocate(
    route: Sequence[str], counts: dict[str, int], capacity: int = CAPACITY
) -> dict[str, int]:
    """동별 실을 수 (TR-PAL-04 ①②). capacity(16) 이하면 전부, 넘으면 물량 많은 순 · 동률이면 먼저 방문하는 동이 후순위."""
    total = sum(counts.get(d, 0) for d in route)
    if total <= capacity:
        return {d: counts.get(d, 0) for d in route}
    visit = {d: i for i, d in enumerate(route)}
    left, load = capacity, {}
    for d in sorted(route, key=lambda d: (-counts.get(d, 0), -visit[d])):
        load[d] = min(counts.get(d, 0), left)
        left -= load[d]
    return load


def plan_pallet(
    route: Sequence[str],
    placements: Iterable[Placement],
    layers: int = LAYERS,
    tray_layer_cells: Mapping[str, int] | None = None,
) -> Plan:
    """경로 + 적재 기록 → Plan. 대상에 칸 기록이 없거나 옮길 박스가 없으면 PlanError (TR-PAL-03).
    layers=1 이면 1층 칸만 쓴다(용량 8, slot_order). tray_layer_cells = 2층 트레이 구역 → 한 층 칸 수
    (sort_fsm.Config.layer_cells) — 그 구역은 위층 박스부터 집는다. 없는 구역은 칸 순서 그대로."""
    order = slot_order(layers)
    cells = {z.upper(): n for z, n in (tray_layer_cells or {}).items() if n > 0}

    def pick_key(b: tuple[str, int, str]) -> tuple:
        zone, slot, box_id = b
        n = cells.get(zone)
        return (zone, -(slot // n) if n else 0, slot, box_id)

    route = tuple(route)
    check_route(route)
    in_route = set(route)
    skipped: list[str] = []
    no_slot: list[str] = []
    excluded: list[Unloaded] = []

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

    # 2) 이미 옮긴 것은 빼고, 경로 밖 동은 EXCLUDED
    by_dong: dict[str, list[tuple[str, int, str]]] = {d: [] for d in route}
    occupied = []
    for (zone, slot), p in sorted(latest.items()):
        if p.palletized:
            skipped.append(f"{p.box_id} {p.dong} 이미 팔레트")
            continue
        occupied.append((zone, slot, p.box_id))
        if p.dong in in_route:
            by_dong[p.dong].append((zone, slot, p.box_id))
        else:
            excluded.append(Unloaded(p.box_id, p.dong, -1, zone, slot, EXCLUDED))
    if not any(by_dong.values()):
        raise PlanError(f"옮길 박스가 없음: {', '.join(route)}")

    # 3) 수량 (위치와 따로)
    load = allocate(route, {d: len(b) for d, b in by_dong.items()}, len(order))
    overflow: list[Unloaded] = []
    for i, d in enumerate(route):
        for zone, slot, box_id in sorted(by_dong[d], key=pick_key)[load[d] :]:
            overflow.append(Unloaded(box_id, d, i, zone, slot, OVERFLOW))

    # 4) 위치: 마지막 방문 동부터 slot 0 → (열 단위, 열 안 1층 2칸 → 2층 2칸)
    moves = []
    for i in reversed(range(len(route))):
        d = route[i]
        for zone, slot, box_id in sorted(by_dong[d], key=pick_key)[: load[d]]:
            moves.append(Move(box_id, d, i, zone, slot, order[len(moves)]))
    unloaded = tuple(sorted(overflow + excluded, key=lambda u: (u.zone, u.slot, u.box_id)))
    empty = tuple(d for d in route if not by_dong[d])
    return Plan(
        route,
        tuple(moves),
        unloaded,
        empty,
        tuple(sorted(skipped)),
        tuple(sorted(occupied)),
        len(order),
    )


def emptied_zones(plan: Plan, done: Iterable[str]) -> tuple[str, ...]:
    """옮긴(DONE) 박스로 트레이가 다 빈 구역 — 그 구역 칸 카운터를 0 으로 (TR-PAL-09). 하나라도 남으면(초과·경로 제외·실패)
    그대로 둔다(칸 카운터는 '다음 칸 = 놓은 횟수' 라 중간 칸만 비울 수 없다)."""
    moved = set(done)
    zones = sorted({z for z, _, _ in plan.occupied})
    return tuple(z for z in zones if all(b in moved for zz, _, b in plan.occupied if zz == z))


def remaining(plan: Plan, finished: Iterable[str]) -> tuple[Move, ...]:
    """재개: 결과(DONE·FAILED)를 낸 box_id 를 뺀 남은 순서. 칸은 처음 계획 그대로 쓴다."""
    done = set(finished)
    return tuple(m for m in plan.moves if m.box_id not in done)
