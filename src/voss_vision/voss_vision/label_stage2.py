"""2단계(추종 중) 판독할 크롭 고르기 — T19 2차, BRD TR-OCR-02, LabelCrop.sharpness(MC-007). ROS 없음·pytest 대상.

- box_tracker 는 PICKING 동안 sort_manager 의 트랙만 stage 2 크롭을 보낸다(5 Hz, voss_msgs.md LabelCrop).
  OCR 은 CPU 장당 약 2 s 라 다 읽을 수 없다 → 작업 스레드가 비면 그사이 온 크롭 중 **가장 선명한 한 장**을 읽고,
  트랙당 `max_ocr` 장까지만 읽는다(goal 약 11 s 안에 결과를 내고, belt_servo 와 CPU 를 덜 다투게).
- sort_manager 는 2단계를 **재확인 구역으로 가려던 박스**에만 쓴다(sort_fsm._on_label_tracking — 확실해지면 목적
  구역으로 바꿈). 그래서 1단계 발행이 모두 확실했던 트랙은 읽지 않는다(`skip_confident_stage1`). sort_manager 가 어느
  1단계 발행으로 정했는지 label_reader 는 모르므로, 불확실한 발행이 한 번이라도 있었거나 1단계 발행이 없었으면 읽는다.
- 같은 트랙 2단계가 이미 확실하면(같은 동 min_agree 장 + confidence_min) 노드가 더 넘기지 않는다(`drop`).
- **발행도 그때만, 반대표가 없을 때만 한다**(`publishable`, #171 리뷰 박병후·김학민·정의석). sort_manager 는 확실한
  2단계 발행 **한 번**에 목적 구역을 바꾸므로, 1장 오판이나 갈린 판독(대치·대치·역삼)이면 재확인(안전한 쪽) 대신
  틀린 구역으로 간다. 1단계에서 이미 불확실했던 박스가 또 갈렸다는 것은 그 자체로 위험 신호다. 조건이 안 되면 내지
  않고, goal 이 끝나면 원래대로 재확인으로 간다(voss_msgs.md LabelRead 발행 시점).

10/15 T19 실기(김학민, main 377e972): 안전은 확인(틀린 구역 0, 2단계 판독 10장 모두 정답)했으나 거꾸로 올린 박스
5개가 모두 goal 뒤에 확정됐다 — 파지 약 8 s 안에 2장이 모이지 않았다. 원인 두 가지를 고쳐 기본으로 켠다(ADR-0008).
- **집으러 간 트랙의 1단계 읽기 그만**(`start_picking`·`held`): sort_manager 는 트랙마다 1단계 첫 발행으로 정하고
  (`sort_fsm._on_label`), 2단계 크롭이 온다는 것은 그 트랙을 집으러 갔다는 뜻이다(box_tracker 는 SortState.track_id
  트랙만 stage 2). 그 트랙의 1단계 대기 크롭은 쓰일 데가 없어 버린다. 다만 1단계를 발행한 직후 작업 스레드가 같은 트랙의
  다음 1단계 크롭을 곧바로 집으면(실기: 파지 시작 때 1단계 2번째 읽기 2.5 s) 2단계 크롭이 오기 전에 OCR 을 차지한다
  → 1단계를 발행한 트랙의 다음 1단계 읽기를 `stage1_hold_s` 만큼 미룬다. 그사이 2단계 크롭이 오면 버리고, 안 오면
  (sort_manager 가 다른 박스를 집는 중·관측 시작 전 촬영 등) 미룬 만큼만 늦게 읽는다. 다른 트랙 크롭은 그사이에도 읽는다.
- **180° 먼저**(`flip_first`): 1단계에서 송장은 찾았는데 글자를 못 읽은 트랙(1단계는 180° 다시 읽기를 끔)은 2단계를
  180° 쪽부터 읽는다(장당 약 5.5 → 2.3 s). 한 번 판정이 나온 방향은 그 트랙에 기억해 다음 크롭도 그 방향부터 읽는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from voss_vision.label_vote import Vote

# offer 결과 (노드 통계 키)
OFF = "off"  # 2단계 꺼짐
SKIP_CONFIDENT = "skip_confident"  # 1단계가 모두 확실 — sort_manager 가 2단계를 쓰지 않는다
CAP = "cap"  # 이 트랙은 max_ocr 장을 이미 읽었다
BLURRY = "blurry"  # min_sharpness 미만
KEPT = "kept"  # 기다리는 크롭이 없어 이것을 둔다
REPLACED = "replaced"  # 기다리던 크롭보다 선명해 바꿨다
DULLER = "duller"  # 기다리던 크롭보다 흐려 버렸다


def publishable(v: Vote, conf_min: float, min_agree: int) -> bool:
    """2단계 투표를 /voss/vision/label 로 낼지 — 같은 동 min_agree 장 이상 + confidence_min 이상 + 반대표 없음.
    반대표 = 다른 동을 읽은 크롭(`agree < picked`). 글자를 못 읽은 크롭(NONE)은 증거가 아니라 반대표도 아니다."""
    m = v.match
    return (
        bool(m.dong) and m.confidence >= conf_min and v.agree >= min_agree and v.agree == v.picked
    )


@dataclass(frozen=True)
class Stage2Params:
    enable: bool = True  # 10/15 실기 뒤 기본 켬(ADR-0008)
    max_ocr: int = 3
    min_sharpness: float = 0.0
    skip_confident_stage1: bool = True
    stage1_hold_s: float = 0.5  # 1단계를 발행한 트랙의 다음 1단계 읽기를 미루는 시간(0 = 안 미룸)
    flip_first: bool = True  # 1단계가 글자를 못 읽은 트랙은 2단계를 180° 먼저


@dataclass
class Stage2Picker:
    p: Stage2Params
    pending: dict[int, tuple[float, Any]] = field(default_factory=dict)  # track → (선명도, 크롭)
    taken: dict[int, int] = field(default_factory=dict)  # track → OCR 로 넘긴 장수
    unsure_s1: dict[int, bool] = field(
        default_factory=dict
    )  # track → 1단계 발행 중 불확실이 있었나
    seen: dict[int, float] = field(default_factory=dict)  # track → 마지막 갱신 monotonic
    # 2단계 크롭이 온 트랙 = sort_manager 가 집으러 간 트랙
    picking: set[int] = field(default_factory=set)
    # track → 1단계 읽기를 미루는 끝 monotonic
    hold_until: dict[int, float] = field(default_factory=dict)
    # 1단계에서 송장은 찾았는데 글자를 못 읽은 트랙
    blank_s1: set[int] = field(default_factory=set)
    # track → 판정이 나온 방향(True = 180°)
    upside: dict[int, bool] = field(default_factory=dict)

    def note_stage1(
        self, track_id: int, dong: str, confidence: float, conf_min: float, now: float
    ) -> None:
        """1단계 투표를 발행할 때마다 부른다. 켜져 있으면 그 트랙의 다음 1단계 읽기를 stage1_hold_s 만큼 미룬다."""
        unsure = not dong or confidence < conf_min
        self.unsure_s1[track_id] = self.unsure_s1.get(track_id, False) or unsure
        self.seen[track_id] = now
        if self.p.enable and self.p.stage1_hold_s > 0 and track_id not in self.picking:
            self.hold_until[track_id] = now + self.p.stage1_hold_s

    def note_read(
        self, track_id: int, stage: int, found_label: bool, dong: str, flipped: bool
    ) -> None:
        """크롭 한 장을 읽을 때마다(1·2단계) 부른다 — 2단계에서 어느 방향부터 읽을지."""
        if dong:
            self.upside[track_id] = flipped
        elif stage == 1 and found_label:
            self.blank_s1.add(track_id)

    def flip_first(self, track_id: int) -> bool:
        """이 트랙 2단계를 180° 먼저 읽을지 — 판정이 나온 방향이 있으면 그쪽, 없으면 1단계가 글자를 못 읽었을 때."""
        if not self.p.flip_first:
            return False
        if track_id in self.upside:
            return self.upside[track_id]
        return track_id in self.blank_s1

    def start_picking(self, track_id: int, now: float) -> bool:
        """2단계 크롭이 올 때마다 부른다. 이 트랙의 첫 2단계 크롭이면 True — 노드가 1단계 대기 크롭을 버린다."""
        if not self.p.enable:
            return False
        self.seen[track_id] = now
        self.hold_until.pop(track_id, None)
        if track_id in self.picking:
            return False
        self.picking.add(track_id)
        return True

    def held(self, track_id: int, now: float) -> bool:
        """이 트랙의 1단계 크롭을 지금 읽지 않는다 — 집으러 간 트랙이거나 미루는 중."""
        return track_id in self.picking or self.hold_until.get(track_id, 0.0) > now

    def hold_left(self, track_ids, now: float) -> float | None:
        """주어진 트랙 중 미루는 중인 것의 가장 빠른 남은 시간(s). 없으면 None."""
        left = [self.hold_until[t] - now for t in track_ids if self.hold_until.get(t, 0.0) > now]
        return min(left) if left else None

    def offer(self, track_id: int, sharpness: float, crop: Any, now: float) -> str:
        """2단계 크롭 하나를 받는다. 결과는 위 상수 중 하나 — KEPT·REPLACED 면 작업 스레드를 깨운다."""
        if not self.p.enable:
            return OFF
        self.seen[track_id] = now
        if self.p.skip_confident_stage1 and self.unsure_s1.get(track_id) is False:
            return SKIP_CONFIDENT
        if self.taken.get(track_id, 0) >= self.p.max_ocr:
            return CAP
        if sharpness < self.p.min_sharpness:
            return BLURRY
        cur = self.pending.get(track_id)
        if cur is None:
            self.pending[track_id] = (sharpness, crop)
            return KEPT
        if sharpness >= cur[0]:
            self.pending[track_id] = (sharpness, crop)
            return REPLACED
        return DULLER

    def take(self) -> tuple[int, Any] | None:
        """OCR 로 넘길 크롭 (가장 선명한 트랙부터 — 보통 PICKING 트랙 하나). 없으면 None."""
        if not self.pending:
            return None
        track_id = max(self.pending, key=lambda t: self.pending[t][0])
        _, crop = self.pending.pop(track_id)
        self.taken[track_id] = self.taken.get(track_id, 0) + 1
        return track_id, crop

    def drop(self, track_id: int) -> None:
        """그 트랙 2단계가 확실해졌다 — 기다리던 크롭을 버린다."""
        self.pending.pop(track_id, None)

    def forget(self, now: float, older_than_s: float) -> int:
        old = [t for t, s in self.seen.items() if now - s > older_than_s]
        maps = (self.pending, self.taken, self.unsure_s1, self.seen, self.hold_until, self.upside)
        for t in old:
            for d in maps:
                d.pop(t, None)
            self.picking.discard(t)
            self.blank_s1.discard(t)
        return len(old)
