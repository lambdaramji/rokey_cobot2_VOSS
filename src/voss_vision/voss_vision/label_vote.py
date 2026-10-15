"""트랙별 판독 모으기 — 크롭 여러 장의 `label_match.Match` 를 다수결로 하나로 (T19, ROS 없음·pytest 대상).

- 표: 판독된 크롭(동이 정해진 것)마다 그 동에 신뢰도만큼 표를 준다. 1위 동의 신뢰도 = 1위 표 합 / 판독된 크롭 수.
  → 크롭들이 같은 동을 가리키면 크롭 신뢰도의 평균, 엇갈리면 그만큼 낮아져 재확인으로 간다.
- 글자를 못 찾은 크롭(NONE)은 반대 증거가 아니라 증거 없음이라 분모에 넣지 않는다(첫 장이 흐려도 늦어지지 않게).
- 2위 동 = 2위 표(없으면 1위 동 크롭 중 가장 확실한 것의 dong_alt) — 작업자 질문용(TR-OCR-07).
- stamp = 판정에 쓴 크롭 중 가장 최근 촬영 시각(voss_msgs.md LabelRead).
- 선명도 가중(MC-007, 2단계 — `weighted`): 크롭마다 선명도 / 가장 선명한 크롭 만큼만 표를 준다. 1위 동의 신뢰도
  = 가중 표 합 / 가중치 합 → 흐린 크롭의 엇갈린 판독은 덜 끌어내린다. 선명도가 모두 같으면(또는 0) 가중 없는 것과 같다.
  1단계(입구 관측)는 가중하지 않는다 — box_tracker 가 간격·장수만 거른다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from voss_vision.label_match import Match


@dataclass(frozen=True)
class Read:
    """크롭 한 장의 판독."""

    match: Match
    stamp_ns: int
    sharpness: float = 0.0


@dataclass(frozen=True)
class Vote:
    match: Match  # LabelRead 로 옮길 값
    stamp_ns: int
    agree: int  # 1위 동을 가리킨 크롭 수
    picked: int  # 동이 정해진 크롭 수
    total: int  # 처리한 크롭 수


def vote(reads: list[Read], weighted: bool = False) -> Vote:
    picks = [r for r in reads if r.match.dong]
    if not picks:
        last = max(reads, key=lambda r: r.stamp_ns) if reads else None
        raw = last.match.raw_text if last else ""
        return Vote(
            Match("", "", 0.0, raw_text=raw, reason="NONE"),
            last.stamp_ns if last else 0,
            0,
            0,
            len(reads),
        )

    sharpest = max(r.sharpness for r in picks)

    def weight(r: Read) -> float:
        return r.sharpness / sharpest if weighted and sharpest > 0 else 1.0

    score: dict[str, float] = {}
    for r in picks:
        score[r.match.dong] = score.get(r.match.dong, 0.0) + r.match.confidence * weight(r)
    total = sum(weight(r) for r in picks)  # 가중 없으면 = 판독된 크롭 수
    ranked = sorted(score, key=lambda d: score[d], reverse=True)
    top = ranked[0]
    n = len(picks)
    mine = [r for r in picks if r.match.dong == top]
    best = max(mine, key=lambda r: r.match.confidence)
    if len(ranked) > 1:
        alt, alt_conf = ranked[1], score[ranked[1]] / total
    else:
        alt, alt_conf = best.match.dong_alt, best.match.confidence_alt
    m = Match(
        code=best.match.code,
        dong=top,
        confidence=round(score[top] / total, 4),
        dong_alt=alt,
        confidence_alt=round(alt_conf, 4),
        raw_text=best.match.raw_text,
        reason=f"{best.match.reason} {len(mine)}/{n}",
    )
    return Vote(m, max(r.stamp_ns for r in picks), len(mine), n, len(reads))


@dataclass
class TrackReads:
    """(track_id, stage) 별 판독 기록. 오래 안 들어온 트랙은 forget 으로 지운다.
    weighted_stages 의 단계는 선명도 가중 다수결(2단계)."""

    reads: dict[tuple[int, int], list[Read]] = field(default_factory=dict)
    seen: dict[tuple[int, int], float] = field(default_factory=dict)  # 마지막 갱신 monotonic
    weighted_stages: frozenset[int] = frozenset()

    def add(self, track_id: int, stage: int, read: Read, now: float) -> Vote:
        key = (track_id, stage)
        self.reads.setdefault(key, []).append(read)
        self.seen[key] = now
        return vote(self.reads[key], stage in self.weighted_stages)

    def enough(self, track_id: int, stage: int, conf_min: float, min_agree: int) -> bool:
        """이미 확실하다(신뢰도 ≥ conf_min 이고 같은 동 크롭 ≥ min_agree) → 더 읽지 않아도 된다."""
        rs = self.reads.get((track_id, stage))
        if not rs:
            return False
        v = vote(rs, stage in self.weighted_stages)
        return v.match.confidence >= conf_min and v.agree >= min_agree

    def forget(self, now: float, older_than_s: float) -> int:
        old = [k for k, t in self.seen.items() if now - t > older_than_s]
        for k in old:
            self.reads.pop(k, None)
            self.seen.pop(k, None)
        return len(old)
