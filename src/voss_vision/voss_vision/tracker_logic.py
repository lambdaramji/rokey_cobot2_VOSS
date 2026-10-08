"""box_tracker 의 판단 로직 (ROS 없음, pytest 대상). 노드는 입출력만 맡는다.

- LabelCrop stage: `track_id == SortState.track_id` 인 트랙만 PICKING→2·RECHECK→3, 나머지는 1 (voss_msgs.md)
- 보류 트랙: PICKING 중 현재 트랙은 15 프레임 규칙으로 버리지 않는다(BoxTrack 규칙)
- 관측 자세 판정: TCP 가 관측 자세에서 1 mm·0.5°(공구축) 안이면 호모그래피, 아니면 핸드아이(calibration.md)
- 크롭 창·선명도·전송 간격, 지연 통계
"""

from __future__ import annotations

import math

import cv2
import numpy as np

STAGE_OBSERVE, STAGE_TRACK, STAGE_RECHECK = 1, 2, 3


def label_stage(track_id: int, sort_state: str, sort_track_id: int) -> int:
    """이 트랙의 크롭 단계. 상태를 아직 못 받았거나 다른 트랙이면 1(입구 관측)."""
    if track_id == sort_track_id:
        if sort_state == "PICKING":
            return STAGE_TRACK
        if sort_state == "RECHECK":
            return STAGE_RECHECK
    return STAGE_OBSERVE


def hold_track_id(sort_state: str, sort_track_id: int) -> int:
    """폐기하지 않을 트랙 ID. PICKING 중에만 현재 트랙, 그 밖에는 -1."""
    return sort_track_id if sort_state == "PICKING" else -1


def near_observe(
    t_base_tcp: np.ndarray, t_observe: np.ndarray, tol_mm: float = 1.0, tol_deg: float = 0.5
) -> bool:
    """TCP 가 관측 자세에 있는가: 위치 차 ≤ tol_mm, **자세 전체 각** ≤ tol_deg.

    공구축 둘레 회전도 본다 — 카메라가 TCP 에서 떨어져 있어 rz 만 달라도 화면 전체가 돈다(#95 리뷰).
    """
    d = float(np.linalg.norm(t_base_tcp[:3, 3] - t_observe[:3, 3]))
    r = t_base_tcp[:3, :3].T @ t_observe[:3, :3]
    c = float(np.clip((np.trace(r) - 1.0) / 2.0, -1.0, 1.0))
    return d <= tol_mm and math.degrees(math.acos(c)) <= tol_deg


SRC_NONE, SRC_HOMOGRAPHY, SRC_HAND_EYE = 0, 1, 2  # BoxTrack.SOURCE_* 와 같은 값


def choose_position(
    pose_ok: bool,
    at_obs: bool,
    homo_xyz,
    homo_inside: bool,
    homo_ok: bool,
    he_xyz,
    he_ok: bool,
    he_verified: bool,
    observe_source: str = "hand_eye",
) -> tuple[int, bool, tuple | None]:
    """BoxTrack 의 (출처, position_valid, 좌표 mm) — calibration.md 규칙을 한곳에 모은다.

    pose_ok: 촬영 시각 + lag 의 TCP pose 를 구했다 · at_obs: 관측 자세 · homo_xyz: 관측 자세 호모그래피 값(없으면 None),
    homo_inside: 그 픽셀이 calib_hull_px 안 · homo_ok/he_ok: 파일 있음 + camera_info 확인됨 · he_xyz: 핸드아이 광선
    교점(없으면 None) · he_verified: moving_verified · observe_source: hand_eye(기본) | homography(되돌림).
    """
    if not pose_ok:
        return SRC_NONE, False, None
    he_usable = he_xyz is not None and he_ok and he_verified
    if observe_source != "homography" and he_usable:
        return SRC_HAND_EYE, True, tuple(he_xyz)  # 검증됐으면 관측 자세에서도 — 트랙 안 출처 고정
    if at_obs and homo_xyz is not None:
        if homo_inside and homo_ok:
            return SRC_HOMOGRAPHY, True, tuple(homo_xyz)
        if he_usable:
            return (
                SRC_HAND_EYE,
                True,
                tuple(he_xyz),
            )  # 호모그래피 유효 영역 밖은 핸드아이로 이어 간다
        return SRC_HOMOGRAPHY, False, tuple(homo_xyz)
    if he_xyz is not None:
        return SRC_HAND_EYE, he_ok and he_verified, tuple(he_xyz)
    return SRC_NONE, False, None


def crop_window(
    bbox: tuple[int, int, int, int], shape: tuple[int, ...], margin: float = 0.15
) -> tuple[int, int, int, int] | None:
    """박스 bbox 를 margin 비율만큼 넓힌 크롭 창 (x0, y0, x1, y1), 화면 밖은 자른다. 비면 None."""
    x, y, w, h = bbox
    mx, my = w * margin, h * margin
    x0, y0 = max(int(x - mx), 0), max(int(y - my), 0)
    x1, y1 = min(int(math.ceil(x + w + mx)), shape[1]), min(int(math.ceil(y + h + my)), shape[0])
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    return x0, y0, x1, y1


def sharpness(gray: np.ndarray) -> float:
    """선명도 = 라플라시안 분산. 흔들리거나 초점이 나가면 작아진다."""
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


class CropGate:
    """트랙·단계별 LabelCrop 전송 여부: 최소 간격, 단계별 최대 장수, 최소 선명도.

    stage 1 은 입구에서 몇 장이면 충분하고(다수결), stage 2·3 은 단계가 끝날 때까지 간격만 지킨다.
    """

    def __init__(
        self,
        period_s: float = 0.2,
        max_per_stage: dict[int, int] | None = None,
        min_sharpness: float = 0.0,
    ) -> None:
        self.period_s = period_s
        self.max_per_stage = max_per_stage or {1: 10, 2: 1000, 3: 1000}
        self.min_sharpness = min_sharpness
        self._last: dict[tuple[int, int], float] = {}
        self._count: dict[tuple[int, int], int] = {}

    def due(self, track_id: int, stage: int, t: float) -> bool:
        """간격·장수만 본다(선명도 계산 전에 걸러서 연산을 아낀다)."""
        key = (track_id, stage)
        if self._count.get(key, 0) >= self.max_per_stage.get(stage, 0):
            return False
        last = self._last.get(key)
        return last is None or t - last >= self.period_s

    def accept(self, track_id: int, stage: int, t: float, sharp: float) -> bool:
        """선명도까지 통과하면 보낸 것으로 기록하고 True."""
        if sharp < self.min_sharpness or not self.due(track_id, stage, t):
            return False
        key = (track_id, stage)
        self._last[key] = t
        self._count[key] = self._count.get(key, 0) + 1
        return True

    def forget(self, live_ids: set[int]) -> None:
        """폐기된 트랙의 기록을 지운다."""
        for key in [k for k in self._last if k[0] not in live_ids]:
            self._last.pop(key, None)
            self._count.pop(key, None)


class LoopStats:
    """주기 로그용 통계: 프레임 수, 검출·루프 시간, 카메라 시각 대비 지연, 발행 수, 좌표 출처."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.frames = 0
        self.det_ms: list[float] = []
        self.loop_ms: list[float] = []
        self.age_ms: list[float] = []
        self.boxes = 0
        self.crops = 0
        self.sources: dict[str, int] = {}
        self.invalid = 0
        self.homo_vs_he_mm = 0.0
        self.pose_n = 0  # pose 를 찾은 프레임 (이력이 있을 때)
        self.pose_fail = 0  # 촬영 시각 + lag 의 pose 를 보간·외삽 못 함
        self.extrap_ms: list[float] = []  # 외삽한 길이 (보간이면 넣지 않음)

    def add_frame(self, det_ms: float, loop_ms: float, age_ms: float | None) -> None:
        self.frames += 1
        self.det_ms.append(det_ms)
        self.loop_ms.append(loop_ms)
        if age_ms is not None:
            self.age_ms.append(age_ms)

    def add_pose(self, extrap_ms: float | None) -> None:
        """None = pose 를 못 구함, 0 = 보간, 양수 = 그만큼 앞으로 외삽."""
        if extrap_ms is None:
            self.pose_fail += 1
            return
        self.pose_n += 1
        if extrap_ms > 0:
            self.extrap_ms.append(extrap_ms)

    def add_box(self, source: str, valid: bool) -> None:
        self.boxes += 1
        self.sources[source] = self.sources.get(source, 0) + 1
        self.invalid += 0 if valid else 1

    def summary(self, period_s: float) -> str:
        if not self.frames:
            return "영상 0 프레임"

        def p95(v: list[float]) -> float:
            return float(np.percentile(v, 95)) if v else float("nan")

        src = ", ".join(f"{k} {n}" for k, n in sorted(self.sources.items())) or "-"
        age = f", 카메라→발행 p95 {p95(self.age_ms):.0f} ms" if self.age_ms else ""
        diff = (
            f", 호모그래피↔핸드아이 최대 {self.homo_vs_he_mm:.1f} mm" if self.homo_vs_he_mm else ""
        )
        if self.pose_n or self.pose_fail:
            ex = f"외삽 {len(self.extrap_ms)}"
            if self.extrap_ms:
                ex += f"(최대 {max(self.extrap_ms):.0f} ms)"
            diff += f", pose {self.pose_n}·{ex}·실패 {self.pose_fail}"
        return (
            f"{self.frames / period_s:.1f} Hz, 검출 평균 {np.mean(self.det_ms):.1f}·p95 {p95(self.det_ms):.1f} ms, "
            f"루프 p95 {p95(self.loop_ms):.1f} ms{age}, box {self.boxes}(무효 {self.invalid}; {src}), "
            f"crop {self.crops}{diff}"
        )
