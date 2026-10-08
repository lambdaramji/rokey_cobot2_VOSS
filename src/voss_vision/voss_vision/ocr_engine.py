"""OCR 엔진 감싸기 — label_reader 는 `read(이미지) → [(글자, 점수)]` 만 안다(ADR-0008: PaddleOCR korean).

paddleocr 는 무거워서 이 모듈을 import 할 때가 아니라 엔진을 만들 때 불러온다.
시험에서는 같은 `read` 를 가진 가짜 엔진을 넣는다.
"""

from __future__ import annotations

import time

import cv2
import numpy as np

from voss_vision.label_match import Candidate, Match, match_label


class PaddleEngine:
    def __init__(
        self, device: str = "cpu", lang: str = "korean", enable_mkldnn: bool = False
    ) -> None:
        from paddleocr import PaddleOCR

        # 문서 방향·펴기·줄 방향 분류는 끈다: 크롭은 crop_upright 로 이미 바로 서 있다(ADR-0008)
        # enable_mkldnn=False: paddle 3.3 CPU 의 oneDNN 오류 회피 (GPU 에서는 해당 없음)
        self.ocr = PaddleOCR(
            lang=lang,
            device=device,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            enable_mkldnn=enable_mkldnn,
        )

    def read(self, img: np.ndarray) -> list[tuple[str, float]]:
        r = self.ocr.predict(img)[0]
        return list(zip(r["rec_texts"], map(float, r["rec_scores"]), strict=True))


def read_label(engine, upright: np.ndarray, cands: list[Candidate]) -> tuple[Match, float, bool]:
    """펴진 송장 → (판정, OCR ms 합, 180° 돌렸는지).

    crop_upright 는 기본 방향에서 ±90° 안만 바로 세운다. 박스를 벨트에 거꾸로(180°) 올리면 글자가 뒤집혀
    아무것도 안 읽히므로(10/06 A_MIX 10개 중 1개), **판정이 없을 때만** 180° 돌려 한 번 더 읽는다.
    """
    t0 = time.perf_counter()
    m = match_label(engine.read(upright), cands)
    if m.dong:
        return m, (time.perf_counter() - t0) * 1000, False
    m2 = match_label(engine.read(cv2.rotate(upright, cv2.ROTATE_180)), cands)
    ms = (time.perf_counter() - t0) * 1000
    return (m2, ms, True) if m2.dong else (m, ms, False)
