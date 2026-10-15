"""2단계(추종 중) 판독할 크롭 고르기 — T19 2차, BRD TR-OCR-02, LabelCrop.sharpness(MC-007). ROS 없음·pytest 대상.

- box_tracker 는 PICKING 동안 sort_manager 의 트랙만 stage 2 크롭을 보낸다(5 Hz, voss_msgs.md LabelCrop).
  OCR 은 CPU 장당 약 2 s 라 다 읽을 수 없다 → 작업 스레드가 비면 그사이 온 크롭 중 **가장 선명한 한 장**을 읽고,
  트랙당 `max_ocr` 장까지만 읽는다(goal 약 11 s 안에 결과를 내고, belt_servo 와 CPU 를 덜 다투게).
- sort_manager 는 2단계를 **재확인 구역으로 가려던 박스**에만 쓴다(sort_fsm._on_label_tracking — 확실해지면 목적
  구역으로 바꿈). 그래서 1단계 발행이 모두 확실했던 트랙은 읽지 않는다(`skip_confident_stage1`). sort_manager 가 어느
  1단계 발행으로 정했는지 label_reader 는 모르므로, 불확실한 발행이 한 번이라도 있었거나 1단계 발행이 없었으면 읽는다.
- 같은 트랙 2단계가 이미 확실하면(같은 동 min_agree 장 + confidence_min) 노드가 더 넘기지 않는다(`drop`).
- **발행도 그때만 한다**(`publishable`, #171 리뷰 박병후). sort_manager 는 확실한 2단계 발행 **한 번**에 목적 구역을
  바꾸므로, 1장 오판이면 재확인(안전한 쪽) 대신 틀린 구역으로 간다. 모이기 전에 goal 이 끝나면 원래대로 재확인으로 간다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# offer 결과 (노드 통계 키)
OFF = "off"  # 2단계 꺼짐
SKIP_CONFIDENT = "skip_confident"  # 1단계가 모두 확실 — sort_manager 가 2단계를 쓰지 않는다
CAP = "cap"  # 이 트랙은 max_ocr 장을 이미 읽었다
BLURRY = "blurry"  # min_sharpness 미만
KEPT = "kept"  # 기다리는 크롭이 없어 이것을 둔다
REPLACED = "replaced"  # 기다리던 크롭보다 선명해 바꿨다
DULLER = "duller"  # 기다리던 크롭보다 흐려 버렸다


def publishable(dong: str, confidence: float, agree: int, conf_min: float, min_agree: int) -> bool:
    """2단계 투표를 /voss/vision/label 로 낼지 — 같은 동 min_agree 장 이상 + confidence_min 이상일 때만."""
    return bool(dong) and confidence >= conf_min and agree >= min_agree


@dataclass(frozen=True)
class Stage2Params:
    enable: bool = False
    max_ocr: int = 3
    min_sharpness: float = 0.0
    skip_confident_stage1: bool = True


@dataclass
class Stage2Picker:
    p: Stage2Params
    pending: dict[int, tuple[float, Any]] = field(default_factory=dict)  # track → (선명도, 크롭)
    taken: dict[int, int] = field(default_factory=dict)  # track → OCR 로 넘긴 장수
    unsure_s1: dict[int, bool] = field(
        default_factory=dict
    )  # track → 1단계 발행 중 불확실이 있었나
    seen: dict[int, float] = field(default_factory=dict)  # track → 마지막 갱신 monotonic

    def note_stage1(
        self, track_id: int, dong: str, confidence: float, conf_min: float, now: float
    ) -> None:
        """1단계 투표를 발행할 때마다 부른다."""
        unsure = not dong or confidence < conf_min
        self.unsure_s1[track_id] = self.unsure_s1.get(track_id, False) or unsure
        self.seen[track_id] = now

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
        for t in old:
            for d in (self.pending, self.taken, self.unsure_s1, self.seen):
                d.pop(t, None)
        return len(old)
