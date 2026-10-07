"""박스 트래커 — BoxTrack.track_id 규칙(docs/interfaces/voss_msgs.md)을 순수 파이썬으로 구현.

- 새 박스마다 1 부터 +1, 재사용하지 않는다. 노드가 재시작하면 1 부터(새 Tracker).
- 연속 `max_missed`(15) 프레임 안 보이면 폐기, 그 안에 다시 보이면 같은 ID.
- `hold_id`(= SortState.track_id, PICKING 중) 트랙은 폐기하지 않는다(파지 중 손가락 가림).
- `update` 는 이번 프레임에 **검출된** 트랙만 돌려준다 → 미검출 프레임은 발행하지 않는다.
- `min_hits` 번 넘게 검출된 트랙만 돌려준다(확정). 손으로 박스를 올리는 순간 1~2 프레임
  잡혔다 가려지는 트랙(10/06 C bag)이 발행되지 않게 한다. 버려진 번호는 재사용하지 않으므로
  발행되는 ID 는 건너뛸 수 있다.
검출기(seg·yolo)와 무관하다. 연결은 예측 위치(등속)와의 거리로 탐욕 매칭한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Detection:
    u: float  # 박스 중심 픽셀
    v: float
    bbox: tuple[int, int, int, int]  # x, y, w, h
    score: float = 1.0


@dataclass
class Track:
    id: int
    u: float
    v: float
    bbox: tuple[int, int, int, int]
    du: float = 0.0  # 프레임당 이동(px), 지수 평균
    dv: float = 0.0
    missed: int = 0
    hits: int = 1
    history: list[tuple[float, float]] = field(default_factory=list, repr=False)

    def predict(self) -> tuple[float, float]:
        k = self.missed + 1
        return self.u + self.du * k, self.v + self.dv * k


class Tracker:
    def __init__(
        self,
        max_missed: int = 15,
        gate_px: float = 120.0,
        vel_alpha: float = 0.5,
        min_hits: int = 1,
    ):
        self.min_hits = min_hits
        self.max_missed = max_missed
        self.gate_px = gate_px
        self.vel_alpha = vel_alpha
        self.tracks: dict[int, Track] = {}
        self._next_id = 1

    def update(self, dets: list[Detection], hold_id: int = -1) -> list[Track]:
        """한 프레임 처리. 이번 프레임에 검출과 이어진 트랙(새 트랙 포함)을 돌려준다."""
        pairs = []
        for tid, t in self.tracks.items():
            pu, pv = t.predict()
            for j, d in enumerate(dets):
                dist = ((d.u - pu) ** 2 + (d.v - pv) ** 2) ** 0.5
                if dist <= self.gate_px:
                    pairs.append((dist, tid, j))
        used_t: set[int] = set()
        used_d: set[int] = set()
        seen: list[Track] = []
        for _, tid, j in sorted(pairs):
            if tid in used_t or j in used_d:
                continue
            used_t.add(tid)
            used_d.add(j)
            t, d = self.tracks[tid], dets[j]
            k = t.missed + 1
            a = self.vel_alpha
            t.du = (1 - a) * t.du + a * (d.u - t.u) / k
            t.dv = (1 - a) * t.dv + a * (d.v - t.v) / k
            t.u, t.v, t.bbox = d.u, d.v, d.bbox
            t.missed, t.hits = 0, t.hits + 1
            seen.append(t)
        for tid, t in list(self.tracks.items()):
            if tid in used_t:
                continue
            t.missed += 1
            if t.missed > self.max_missed and tid != hold_id:
                del self.tracks[tid]
        for j, d in enumerate(dets):
            if j in used_d:
                continue
            t = Track(self._next_id, d.u, d.v, d.bbox)
            self._next_id += 1
            self.tracks[t.id] = t
            seen.append(t)
        return sorted((t for t in seen if t.hits >= self.min_hits), key=lambda t: t.id)
