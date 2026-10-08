"""label_preprocess 시험 — 합성 송장으로 크롭 방향·크기를 본다 (OCR 없이)."""

import cv2
import numpy as np
import pytest
from voss_vision.label_preprocess import crop_upright, find_label_in_crop, find_label_rect

LONG, SHORT = 172, 106  # 10/06 관측 자세에서 송장 크기(px)


def synthetic(angle_deg: float) -> tuple[np.ndarray, tuple]:
    """초록 벨트 위 흰 송장. 글자 시작 쪽(진행 방향 반대 끝, 글자 위쪽)에 검은 점.

    기본(0°)은 관측 자세 그대로: 송장이 세로로 서고 글자가 화면 아래로 나아간다.
    """
    img = np.full((1080, 1920, 3), (60, 60, 60), np.uint8)
    cv2.rectangle(img, (900, 0), (1300, 1079), (40, 110, 20), -1)  # 벨트(초록)
    c = np.array([1100.0, 600.0])
    t = np.radians(angle_deg)
    u = np.array([-np.sin(t), np.cos(t)])  # 글자 진행 방향 (0° 에서 화면 아래)
    up = np.array([u[1], -u[0]])
    corners = [
        c + sx * u * LONG / 2 + sy * up * SHORT / 2
        for sx, sy in ((-1, 1), (1, 1), (1, -1), (-1, -1))
    ]
    cv2.fillPoly(img, [np.int32(corners)], (250, 250, 250))
    dot = c - u * LONG * 0.35 + up * SHORT * 0.3
    cv2.circle(img, tuple(np.int32(dot)), 8, (0, 0, 0), -1)
    return img, ((c[0], c[1]), (SHORT, LONG), 0.0)


@pytest.mark.parametrize("angle", [0, 15, -30, 40, -60, 80])
def test_crop_is_landscape_and_reads_from_top_left(angle: float) -> None:
    img, _ = synthetic(angle)
    rect = find_label_rect(img)
    assert rect is not None
    crop = crop_upright(img, rect, scale=2.0, pad_px=0)
    h, w = crop.shape[:2]
    assert w > h  # 글자가 가로로
    assert w == pytest.approx(LONG * 2, rel=0.06) and h == pytest.approx(SHORT * 2, rel=0.08)
    ys, xs = np.where(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) < 40)
    assert xs.mean() < w / 2 and ys.mean() < h / 2  # 점이 왼쪽 위 = 글자가 바로 섰다


def box_crop(angle_deg: float, neighbor: bool = False) -> np.ndarray:
    """LabelCrop 흉내: 골판지색 박스 영역 가운데 송장, 가장자리에 옆 박스 송장 일부(선택)."""
    img, _ = synthetic(angle_deg)
    crop = img[600 - 160 : 600 + 160, 1100 - 130 : 1100 + 130].copy()
    crop[np.all(crop == (40, 110, 20), axis=-1)] = (80, 130, 170)  # 벨트 대신 골판지색
    if neighbor:
        cv2.rectangle(crop, (0, 0), (60, 90), (250, 250, 250), -1)  # 옆 송장이 모서리에 걸림
    return crop


@pytest.mark.parametrize("angle", [0, 25, -40])
@pytest.mark.parametrize("neighbor", [False, True])
def test_find_label_in_crop_picks_centre_label(angle: float, neighbor: bool) -> None:
    crop = box_crop(angle, neighbor)
    rect = find_label_in_crop(crop)
    assert rect is not None
    (cx, cy), (w, h), _ = rect
    assert abs(cx - 130) < 6 and abs(cy - 160) < 6  # 가운데 송장
    assert max(w, h) == pytest.approx(LONG, rel=0.08) and min(w, h) == pytest.approx(SHORT, rel=0.1)
    up = crop_upright(crop, rect, scale=2.0, pad_px=0)
    ys, xs = np.where(cv2.cvtColor(up, cv2.COLOR_BGR2GRAY) < 40)
    assert up.shape[1] > up.shape[0] and xs.mean() < up.shape[1] / 2  # 바로 섰다


def test_find_label_in_crop_none_without_label() -> None:
    assert find_label_in_crop(np.full((300, 240, 3), (80, 130, 170), np.uint8)) is None
