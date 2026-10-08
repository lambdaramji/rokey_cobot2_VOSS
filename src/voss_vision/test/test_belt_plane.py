"""belt_plane 순수 함수 시험 — 알려진 H 로 만든 가상 대응점을 되찾는지 본다."""

import numpy as np
import pytest
from voss_vision.belt_plane import apply_homography, fit_homography, point_errors_mm

# 관측 자세에서 1920×1080, 벨트 약 200×70 mm 가 보이는 상황을 흉내 낸 H (픽셀 → mm)
H_TRUE = np.array(
    [
        [0.0, -0.105, 520.0],
        [0.104, 0.0, -180.0],
        [1e-6, 2e-6, 1.0],
    ]
)
# 계산용 6점: 벨트 앞·뒤 가장자리 × 상류·중간·하류 (픽셀)
PX_CAL = np.array([[300, 250], [960, 250], [1620, 250], [300, 800], [960, 800], [1620, 800]])
PX_VAL = np.array([[500, 540], [960, 540], [1400, 540]])


def test_recovers_known_homography() -> None:
    xy = apply_homography(H_TRUE, PX_CAL)
    h = fit_homography(PX_CAL, xy)
    assert np.allclose(h, H_TRUE, rtol=1e-6, atol=1e-9)
    assert point_errors_mm(h, PX_VAL, apply_homography(H_TRUE, PX_VAL)).max() < 1e-6


def test_noise_keeps_validation_error_small() -> None:
    # 클릭 ±2 px, 터치 ±0.5 mm 오차를 넣어도 검증점 오차가 5 mm(제안값) 안쪽이어야 한다
    rng = np.random.default_rng(0)
    xy = apply_homography(H_TRUE, PX_CAL) + rng.normal(0, 0.5, (6, 2))
    h = fit_homography(PX_CAL + rng.normal(0, 2, (6, 2)), xy)
    err = point_errors_mm(h, PX_VAL, apply_homography(H_TRUE, PX_VAL))
    assert err.max() < 5.0


def test_mm_to_pixel_roundtrip() -> None:
    xy = apply_homography(H_TRUE, PX_VAL)
    back = apply_homography(np.linalg.inv(H_TRUE), xy)
    assert np.allclose(back, PX_VAL, atol=1e-6)


def test_rejects_too_few_points() -> None:
    with pytest.raises(ValueError, match="4개 이상"):
        fit_homography(PX_CAL[:3], apply_homography(H_TRUE, PX_CAL[:3]))


def test_rejects_collinear_points() -> None:
    line = np.array([[300, 500], [700, 500], [1100, 500], [1500, 500]])
    with pytest.raises(ValueError, match="직선"):
        fit_homography(line, apply_homography(H_TRUE, line))


# ---- #48 리뷰 반영 회귀 시험 ----------------------------------------------------------
from voss_vision.belt_plane import (  # noqa: E402
    convex_hull,
    flange_to_tcp,
    inside_hull,
    pixel_to_base_xy,
    tool_axis_angle_deg,
)


def test_four_points_ok() -> None:
    px = np.array([[300, 250], [1620, 250], [300, 800], [1620, 800]])
    h = fit_homography(px, apply_homography(H_TRUE, px))
    assert point_errors_mm(h, PX_VAL, apply_homography(H_TRUE, PX_VAL)).max() < 1e-6


def test_rejects_three_collinear_plus_one() -> None:
    # 병후 리뷰 P2 재현: 4점 중 3점 일직선(rank 7) 은 거부해야 한다
    px = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0], [0.0, 1.0]])
    with pytest.raises(ValueError, match="퇴화"):
        fit_homography(px, 100 * px)


def test_flange_to_tcp_matches_measurement() -> None:
    # 10/06 김학민 실측: 같은 관측 자세의 플랜지·TCP posx, TCP 오프셋 (1.382, 2.684, 246.642)
    flange = [-11.51, -271.11, 450.16, 85.25, -179.07, -6.03]
    tcp = flange_to_tcp(flange, [1.382, 2.684, 246.642])
    assert np.allclose(tcp, [-14.49, -276.54, 203.58], atol=0.05)


def test_tool_axis_angle_across_180() -> None:
    # ry 가 180 과 -179.07 로 갈려도 같은 수직 자세 (각도 차 ~0.93°, ZYZ 를 빼면 359°)
    a = [0, 0, 0, 85.25, -179.07, -6.03]
    b = [0, 0, 0, 85.25, 180.0, -6.03]
    assert tool_axis_angle_deg(a, b) == pytest.approx(0.93, abs=0.01)
    # ry=±180 이면 rx 가 달라도(rz 와 함께 돌아감) 툴 축은 같다
    assert tool_axis_angle_deg([0, 0, 0, 14.28, 180, -75.33], [0, 0, 0, 35.36, -180, -54.64]) < 0.01


def test_hull_and_pixel_to_base() -> None:
    hull = convex_hull(PX_CAL)
    assert inside_hull(hull, [[960, 540]]).all()
    assert not inside_hull(hull, [[960, 100]]).any()  # 위쪽(상류) 외삽 구간
    calib = {"H_px_to_base_xy": H_TRUE.tolist(), "calib_hull_px": hull.tolist(), "undistort": None}
    xy, valid = pixel_to_base_xy(calib, [[960, 540], [960, 100]])
    assert np.allclose(xy[0], apply_homography(H_TRUE, [[960, 540]])[0])
    assert valid.tolist() == [True, False]
