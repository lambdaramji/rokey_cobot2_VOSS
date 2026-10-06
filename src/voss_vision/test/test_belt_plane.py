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
