"""송장 OCR 결과 → 등록 동 퍼지 매칭 (TR-OCR-05). 순수 함수, ROS·OpenCV 의존 없음.

- 분류코드: `S07-02` = 대리점(07) + 동 번호(02). 접두 S 는 무시하고(BRD 3.2) 숫자 4자리를 뽑아
  동 번호(끝 두 자리)가 같은 후보를 찾는다. 대리점 번호가 다르면 감점.
- 동 이름: 한글을 자모로 풀어 편집거리를 잰다. 흐린 글자 오독(삼→심)은 자모 1개 차이라
  음절 단위(1/3)보다 훨씬 가깝게(1/9) 나온다. 별칭(역삼 등)도 후보 이름으로 쓴다.
- 판정: 코드·동이 같은 후보를 가리키면 확정, 다르면 코드를 따르되 신뢰도를 낮춘다(재확인행).
  한쪽만 읽히면 그 쪽으로 정하되 낮춘다. 가중치는 제안값이며 실측(T18·T19)으로 조정한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# 판정 가중치 (제안값, docs/adr 참고). confidence_min(0.6) 과 함께 본다.
CODE_ONLY = 0.8  # 동 이름 없이 코드만 읽힘
DONG_ONLY = 0.7  # 코드 없이 동 이름만 읽힘
CONFLICT = 0.5  # 코드와 동 이름이 다른 후보를 가리킴 → 코드 쪽, 재확인으로 보내도록 낮춤
DONG_MIN_SIM = 0.6  # 이보다 낮은 동 이름 유사도는 증거로 쓰지 않는다
AGENCY = "07"  # 대리점 번호. 다르면 코드 유사도 0.8 배

_CONFUSABLE = str.maketrans({"O": "0", "o": "0", "D": "0", "Q": "0", "I": "1", "l": "1", "|": "1"})
_CODE_RE = re.compile(r"(\d)\s*(\d)\s*[-‐‑–—_.~]?\s*(\d)\s*(\d)")

_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_JONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"


@dataclass(frozen=True)
class Candidate:
    """등록 동 하나 (zone_map 의 ZoneMapEntry 또는 voss_config 에서)."""

    dong: str
    code: str  # 예 "S07-01"
    aliases: tuple[str, ...] = ()

    @property
    def number(self) -> str:
        return re.sub(r"\D", "", self.code)[-2:]


@dataclass(frozen=True)
class Match:
    """LabelRead 에 그대로 옮길 판정 결과. 모르면 code·dong 은 ""."""

    code: str
    dong: str
    confidence: float
    dong_alt: str = ""
    confidence_alt: float = 0.0
    raw_text: str = ""
    reason: str = ""  # AGREE | CODE_ONLY | DONG_ONLY | CONFLICT | NONE
    scores: dict[str, tuple[float, float]] = field(default_factory=dict, compare=False)


def levenshtein(a: str, b: str) -> int:
    """삽입·삭제·교체 각 1."""
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def to_jamo(s: str) -> str:
    """완성형 한글을 초·중·종성 자모로 푼다. 한글이 아닌 글자는 그대로."""
    out = []
    for ch in s:
        k = ord(ch) - 0xAC00
        if 0 <= k < 11172:
            out += [_CHO[k // 588], _JUNG[(k % 588) // 28]]
            if k % 28:
                out.append(_JONG[k % 28])
        else:
            out.append(ch)
    return "".join(out)


def code_numbers(text: str) -> list[str]:
    """한 줄에서 분류코드 숫자 4자리 후보들. 접두 S·공백·하이픈 변형을 무시한다."""
    t = text.translate(_CONFUSABLE)
    return ["".join(m.groups()) for m in _CODE_RE.finditer(t)]


def code_similarity(text: str, cand: Candidate) -> float:
    """0~1. 동 번호(끝 두 자리)가 같아야 점수가 있다."""
    best = 0.0
    for digits in code_numbers(text):
        if digits[2:] == cand.number:
            best = max(best, 1.0 if digits[:2] == AGENCY else 0.8)
    return best


def name_similarity(text: str, name: str) -> float:
    """줄 안에서 name 과 가장 비슷한 구간의 자모 유사도(0~1). 공백·기호는 무시."""
    t = re.sub(r"[^가-힣A-Za-z0-9]", "", text)
    if not t or not name:
        return 0.0
    n = len(name)
    target = to_jamo(name)
    best = 0.0
    for size in (n - 1, n, n + 1):
        if size < 1:
            continue
        for i in range(max(1, len(t) - size + 1)):
            win = to_jamo(t[i : i + size])
            best = max(best, 1.0 - levenshtein(win, target) / max(len(target), len(win)))
    return best


def match_label(lines: list[tuple[str, float]], candidates: list[Candidate]) -> Match:
    """OCR 줄 [(글자, 점수)] → 등록 후보 하나로 판정 (TR-OCR-05).

    후보마다 코드 증거 sc = max(코드 유사도 × OCR 점수), 동 증거 sd = max(이름 유사도 × OCR 점수)
    (이름 유사도 DONG_MIN_SIM 미만은 버림). 코드 1위와 동 1위가 같으면 AGREE.
    """
    raw = "\n".join(t for t, _ in lines)
    if not candidates:
        return Match("", "", 0.0, raw_text=raw, reason="NONE")
    scores: dict[str, tuple[float, float]] = {}
    for c in candidates:
        sc = max((code_similarity(t, c) * s for t, s in lines), default=0.0)
        sd = 0.0
        for t, s in lines:
            sim = max(name_similarity(t, nm) for nm in (c.dong, *c.aliases))
            if sim >= DONG_MIN_SIM:
                sd = max(sd, sim * s)
        scores[c.dong] = (sc, sd)

    by = {c.dong: c for c in candidates}
    code_top = max(scores, key=lambda d: scores[d][0])
    dong_top = max(scores, key=lambda d: scores[d][1])
    sc, sd = scores[code_top][0], scores[dong_top][1]

    if sc > 0 and sd > 0 and code_top == dong_top:
        pick, conf, reason = code_top, 1.0 - (1.0 - sc) * (1.0 - sd), "AGREE"
    elif sc > 0 and sd > 0:
        pick, conf, reason = code_top, CONFLICT * sc, "CONFLICT"
    elif sc > 0:
        pick, conf, reason = code_top, CODE_ONLY * sc, "CODE_ONLY"
    elif sd > 0:
        pick, conf, reason = dong_top, DONG_ONLY * sd, "DONG_ONLY"
    else:
        return Match("", "", 0.0, raw_text=raw, reason="NONE", scores=scores)

    # 2위 후보 (작업자 질문용, TR-OCR-07): 고른 후보를 빼고 코드·동 증거 중 큰 값
    others = {d: max(v) for d, v in scores.items() if d != pick}
    alt = max(others, key=others.get) if others else ""
    alt_conf = others.get(alt, 0.0)
    if reason == "CONFLICT":  # 동 이름이 가리킨 후보가 2위
        alt, alt_conf = dong_top, CONFLICT * sd
    return Match(
        code=by[pick].code,
        dong=pick,
        confidence=round(conf, 4),
        dong_alt=alt if alt_conf > 0 else "",
        confidence_alt=round(alt_conf, 4),
        raw_text=raw,
        reason=reason,
        scores=scores,
    )


def candidates_from_config(cfg: dict) -> list[Candidate]:
    """voss_config.yaml(dict) → 후보. 런타임 노드는 /voss/sort/zone_map 으로 만든다(규칙 5)."""
    aliases = cfg.get("aliases") or {}
    return [
        Candidate(dong=d, code=code, aliases=tuple(aliases.get(d, ())))
        for code, d in (cfg.get("ocr") or {}).get("codes", {}).items()
    ]
