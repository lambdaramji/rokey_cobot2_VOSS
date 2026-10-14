"""box_detect (seg) — 합성 프레임 시험: 벨트 위 박스, 빈 벨트, 손(라벨 없음), 가장자리 걸림, 버린 이유."""

from dataclasses import replace

import cv2
import numpy as np
import pytest
from voss_vision.belt_plane import rot_zyz_deg
from voss_vision.box_detect import DEFAULT_PARAMS, SegParams, detect_boxes, detect_candidates
from voss_vision.hand_eye import make_t

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


@pytest.mark.parametrize("angle", [0, 15, 30, 45, -30, 90])
def test_half_axis_follows_label_long_side(angle: float) -> None:
    """S2-T16: Detection.half_axis = 중심 → 송장 긴 변 끝(픽셀). frame() 의 송장 긴 변은 각 0 에서 세로(v)다."""
    (d,) = detect_boxes(frame((1130, 600), angle))
    hx, hy = d.half_axis
    assert np.hypot(hx, hy) == pytest.approx(LABEL[0] / 2, abs=4)
    want = np.arctan2(
        np.cos(np.radians(angle)), -np.sin(np.radians(angle))
    )  # boxPoints 의 높이 방향
    diff = (np.arctan2(hy, hx) - want + np.pi / 2) % np.pi - np.pi / 2  # 180° 대칭
    assert abs(np.degrees(diff)) < 1.5


def turned(img: np.ndarray, deg: float, center=(1130, 600)) -> np.ndarray:
    """카메라가 J6 로 돈 것처럼 화면 전체를 center 둘레로 돌린다(벨트가 기운다). 빈 곳은 밝은 바닥."""
    m = cv2.getRotationMatrix2D(center, deg, 1.0)
    return cv2.warpAffine(img, m, (img.shape[1], img.shape[0]), borderValue=(200, 200, 205))


@pytest.mark.parametrize("deg", [0, 15, 30, 45, 60, 75, 90])
def test_hull_roi_finds_label_on_a_tilted_belt(deg: float) -> None:
    """S2-T16: J6 로 벨트가 화면에서 기울어도 송장을 자르지 않는다 — 중심·긴 변 방향이 그대로."""
    (d,) = detect_boxes(turned(frame((1130, 600), 0), deg))
    assert abs(d.u - 1130) < 3 and abs(d.v - 600) < 3
    want = np.arctan2(1.0, 0.0) - np.radians(
        deg
    )  # 각 0 의 긴 변 = 세로, warpAffine 양각은 반시계(화면)
    diff = (np.arctan2(d.half_axis[1], d.half_axis[0]) - want + np.pi / 2) % np.pi - np.pi / 2
    assert abs(np.degrees(diff)) < 1.5


@pytest.mark.parametrize("deg", [0, 15, 30, 45, 60, 75, 90])
def test_columns_roi_never_reports_a_cut_label(deg: float) -> None:
    """이전 열 방식은 기운 벨트에서 송장을 자를 수 있다 — 그래도 잘린 송장을 틀린 중심으로 내지는 않는다."""
    dets = detect_boxes(
        turned(frame((1130, 600), 0), deg), replace(DEFAULT_PARAMS, belt_roi="columns")
    )
    assert all(abs(d.u - 1130) < 3 and abs(d.v - 600) < 3 for d in dets)


def test_label_cut_by_belt_region_edge_reason_border() -> None:
    """벨트 영역 경계(여유 60 px 밖)에 걸친 송장은 화면 가장자리처럼 버린다."""
    img = frame()
    lab = cv2.boxPoints(
        ((1350.0, 600.0), (LABEL[1], LABEL[0]), 0)
    )  # 벨트(995~1265) 오른쪽 여유 끝에 걸침
    cv2.fillPoly(img, [np.int32(lab)], (250, 250, 250))
    for mode in ("hull", "columns"):
        _, cands = detect_candidates(img, replace(DEFAULT_PARAMS, belt_roi=mode))
        cut = [c for c in cands if c.area > 5000]
        assert cut and all(c.reason == "border" for c in cut), mode


def test_unknown_belt_roi_is_rejected() -> None:
    with pytest.raises(ValueError):
        detect_boxes(frame((1130, 600)), replace(DEFAULT_PARAMS, belt_roi="box"))


# ---- 원근 장면: 관측 자세에서 J6 만 돌린 카메라로 본 벨트·박스 (test_hand_eye 와 같은 배치, 10/13 합성 녹화와 같은 장면)
K3 = np.array([[1367.5, 0, 978.5], [0, 1367.7, 552.0], [0, 0, 1]])
T_TCP_CAM = make_t(rot_zyz_deg(30, 22, -100), [-16.0, -44.0, -208.0])
T_OBS = make_t(rot_zyz_deg(0, 180, 0), [-110.0, -380.0, 231.0])
TOP_Z = 101.0


def scene(j6: float, box_yaw: float) -> tuple[np.ndarray, np.ndarray, float]:
    """(영상, 송장 중심 픽셀, 송장 긴 변 화면 각 rad). 박스는 TCP 바로 아래(공구축 점), 벨트는 J6 0 에서 화면 세로."""
    cam = T_OBS @ make_t(rot_zyz_deg(j6, 0, 0), [0, 0, 0]) @ T_TCP_CAM
    cam0 = T_OBS @ T_TCP_CAM
    down = cam0[:3, :3] @ np.array([0, 1.0, 0])
    bd_ = np.array([down[0], down[1], 0]) / np.hypot(down[0], down[1])
    pp = np.array([-bd_[1], bd_[0], 0])
    c = np.array([-110.0, -380.0, TOP_Z])
    a = np.radians(box_yaw)
    bx, by = np.array([np.cos(a), np.sin(a), 0]), np.array([-np.sin(a), np.cos(a), 0])

    def rect(u, v, lu, lv, z):
        return np.array(
            [c + s * lu / 2 * u + r * lv / 2 * v for s, r in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        ) + [0, 0, z - TOP_Z]

    def proj(pts):
        pc = (np.linalg.inv(cam) @ np.hstack([pts, np.ones((len(pts), 1))]).T).T[:, :3]
        return (K3 @ (pc / pc[:, 2:3]).T).T[:, :2]

    img = np.full((1080, 1920, 3), (200, 200, 205), np.uint8)
    cv2.fillPoly(img, [np.int32(np.round(proj(rect(bd_, pp, 900, 80, TOP_Z - 27))))], (60, 70, 10))
    top, bot = rect(bx, by, 46, 31, TOP_Z), rect(bx, by, 46, 31, TOP_Z - 27)
    for i in range(4):
        side = np.array([bot[i], bot[(i + 1) % 4], top[(i + 1) % 4], top[i]])
        cv2.fillPoly(img, [np.int32(np.round(proj(side)))], (80, 110, 150))
    cv2.fillPoly(img, [np.int32(np.round(proj(top)))], (110, 150, 200))
    lab = proj(rect(bx, by, 40, 25, TOP_Z))
    cv2.fillPoly(img, [np.int32(np.round(lab))], (250, 250, 250))
    ends = proj(np.array([c - 20 * bx, c + 20 * bx]))
    d = ends[1] - ends[0]
    return img, lab.mean(0), float(np.arctan2(d[1], d[0]))


@pytest.mark.parametrize("j6", [0, 15, 30, 45, 60, 75, 90])
@pytest.mark.parametrize("box_yaw", [0, 30])
def test_hull_roi_keeps_label_whole_when_camera_turns(j6: float, box_yaw: float) -> None:
    """S2-T16: 이전 열 방식은 J6 30~75° 에서 송장을 잘라 놓치거나(박스 0°) 틀린 중심·각을 냈다(박스 30°·J6 45°:
    12.8 mm·89°, 10/13 합성 녹화). hull 은 모든 각에서 송장 하나를 맞는 중심·긴 변 방향으로 낸다."""
    img, center, axis = scene(j6, box_yaw)
    (d,) = detect_boxes(img)
    assert np.hypot(d.u - center[0], d.v - center[1]) < 3
    diff = (np.arctan2(d.half_axis[1], d.half_axis[0]) - axis + np.pi / 2) % np.pi - np.pi / 2
    assert abs(np.degrees(diff)) < 2.0


@pytest.mark.parametrize("j6", [0, 15, 30, 45, 60, 75, 90])
def test_columns_roi_drops_but_never_misplaces_a_cut_label(j6: float) -> None:
    """이전 열 방식 + 영역 경계 거부: 잘린 송장은 버린다 — 내는 것은 늘 맞는 중심이다."""
    img, center, _ = scene(j6, 30)
    for d in detect_boxes(img, replace(DEFAULT_PARAMS, belt_roi="columns")):
        assert np.hypot(d.u - center[0], d.v - center[1]) < 3
