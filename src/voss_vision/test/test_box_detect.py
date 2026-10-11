"""box_detect (seg) — 합성 프레임 시험: 벨트 위 박스, 빈 벨트, 손(라벨 없음), 가장자리 걸림, 버린 이유."""

import cv2
import numpy as np
import pytest
from voss_vision.box_detect import SegParams, detect_boxes, detect_candidates

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


@pytest.mark.parametrize("v", [LABEL[0] // 2 + 8, 1079 - LABEL[0] // 2 - 8])
def test_label_near_edge_but_whole_is_reported(v: int) -> None:
    # 박스(골판지)는 화면 끝에 잘려도 송장이 끝에서 8 px 떨어져 온전하면 낸다.
    # 닫힘 연산이 화면 밖을 흰색으로 보던 때는 이 틈이 메워져 '가장자리 걸림'으로 버려졌다(#76 사람 확인).
    dets = detect_boxes(frame((1130, v)))
    assert len(dets) == 1 and abs(dets[0].v - v) < 3


def test_no_belt_no_detection() -> None:
    img = np.full((1080, 1920, 3), 200, np.uint8)
    assert detect_boxes(img, SegParams()) == []


def passed(img):
    return [c.det for c in detect_candidates(img)[1] if c.reason == ""]


def on_belt(cands):
    # 벨트 열 범위 양옆 여유(belt_margin_px)에 걸린 밝은 바닥 띠는 빼고 본다 — 위아래 끝에 닿아 border
    return [c for c in cands if 995 < c.rect[0] + c.rect[2] / 2 < 1265]


@pytest.mark.parametrize("box_at", [None, (1130, 600), (1130, 40), (1130, 1079 - 60)])
def test_candidates_pass_equals_detect_boxes(box_at) -> None:
    img = frame(box_at, 25)
    assert passed(img) == detect_boxes(img)


def test_label_cut_by_bottom_edge_reason_border() -> None:
    # 하강하면 송장이 화면 아래 끝으로 빠진다 — 버린 이유가 가장자리로 나와야 한다(#30 하강 LOST)
    roi, cands = detect_candidates(frame((1130, 1079 - 40)))
    assert roi is not None and roi[0] <= 995 and roi[1] >= 1265
    cands = on_belt(cands)
    assert [c.reason for c in cands] == ["border"]
    x, y, w, h = cands[0].rect
    assert y + h >= 1079 - 4 and cands[0].det is None


def test_square_white_reason_aspect_and_small_reason_area() -> None:
    img = frame()
    cv2.rectangle(img, (1060, 300), (1200, 440), (250, 250, 250), -1)  # 정사각 흰 종이
    cv2.rectangle(img, (1100, 800), (1110, 810), (250, 250, 250), -1)  # 반사 점
    by = {c.reason: c for c in on_belt(detect_candidates(img)[1])}
    assert set(by) == {"aspect", "area"}
    assert by["aspect"].aspect == pytest.approx(1.0, abs=0.05) and by["aspect"].rot is not None
    assert by["area"].rot is None


def test_hollow_label_reason_fill() -> None:
    img = frame()
    lab = cv2.boxPoints(((1130.0, 600.0), (106, 172), 0))
    cv2.polylines(img, [np.int32(lab)], True, (250, 250, 250), 12)  # 테두리만 흰 사각형
    reasons = [c.reason for c in on_belt(detect_candidates(img)[1])]
    assert reasons == ["fill"]


def test_no_belt_candidates_none() -> None:
    assert detect_candidates(np.full((1080, 1920, 3), 200, np.uint8)) == (None, [])
