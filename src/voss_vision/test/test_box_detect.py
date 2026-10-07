"""box_detect (seg) — 합성 프레임 시험: 벨트 위 박스, 빈 벨트, 손(라벨 없음), 가장자리 걸림."""

import cv2
import numpy as np
import pytest
from voss_vision.box_detect import SegParams, detect_boxes

LABEL = (172, 106)  # 관측 자세 송장 px (긴 변, 짧은 변)


def frame(box_at=None, angle=0.0, hand=False) -> np.ndarray:
    img = np.full((1080, 1920, 3), (200, 200, 205), np.uint8)  # 밝은 바닥
    cv2.rectangle(img, (995, 0), (1265, 1079), (60, 70, 10), -1)  # 초록 벨트 (BGR)
    if hand:
        cv2.ellipse(
            img, (1130, 300), (110, 200), 0, 0, 360, (150, 170, 225), -1
        )  # 살색, 흰 사각형 없음
    if box_at is not None:
        c = tuple(float(v) for v in box_at)
        box = cv2.boxPoints((c, (LABEL[1] * 31 / 25, LABEL[0] * 46 / 40), angle))
        cv2.fillPoly(img, [np.int32(box)], (110, 150, 200))  # 골판지
        lab = cv2.boxPoints((c, (LABEL[1], LABEL[0]), angle))
        cv2.fillPoly(img, [np.int32(lab)], (250, 250, 250))  # 송장
        cv2.putText(img, "S07-01", (int(c[0]) - 20, int(c[1]) - 60), 0, 0.6, (40, 40, 40), 2)
    return img


@pytest.mark.parametrize("angle", [0, 25, -40, 90])
def test_detects_box_center_on_belt(angle: float) -> None:
    dets = detect_boxes(frame((1130, 600), angle))
    assert len(dets) == 1
    d = dets[0]
    assert abs(d.u - 1130) < 3 and abs(d.v - 600) < 3
    x, y, w, h = d.bbox
    assert x < 1130 < x + w and y < 600 < y + h


def test_empty_belt_and_hand_give_nothing() -> None:
    assert detect_boxes(frame()) == []
    assert detect_boxes(frame(hand=True)) == []


def test_box_cut_by_image_edge_is_not_reported() -> None:
    assert detect_boxes(frame((1130, 40))) == []  # 위쪽(상류)에서 들어오는 중


def test_no_belt_no_detection() -> None:
    img = np.full((1080, 1920, 3), 200, np.uint8)
    assert detect_boxes(img, SegParams()) == []
