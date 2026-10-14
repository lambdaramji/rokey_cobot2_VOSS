"""servo_cmd → speedl 안전 판단 (ROS·두산 import 없음). ADR-0010 '결과' 절의 robot_gateway 적용 조건.

- 단위: 입력은 servo_cmd 그대로(m/s·rad/s, base_link, TCP 기준점), 출력은 두산 speedl vel 의 선속도(mm/s)와
  베이스 Z 각속도(deg/s).
- 각속도: 기본(angular_enable False)은 G0 그대로 0 — 0 이 아니면 버리고 플래그만 남긴다(#53 MC-010).
  켜면(S2-T17, topics.md robot_gateway 행) angular.z 만 넘기고 x·y 는 버린다. 상한 max_ang_dps, 공구 yaw 는
  관측 자세 yaw ± yaw_limit_deg 안에서만(감속 각을 빼고 자름). yaw 를 모르면 각속도는 0.
- 거부(속도를 내지 않음): stop 이전 stamp, watchdog 보다 오래된 stamp, pose 가 오래됨(작업 영역 판단 불가),
  모션 자원 사용 중(MoveToZone, topics.md 자원 규칙 — 토픽이라 응답 대신 무시·로그).
- 자르기: 속도 크기 상한, TCP z 하한(−z 성분 0), 추종 구간 x 범위(바깥으로 가는 x 성분 0).
  위치는 마지막 pose + 마지막 지령 속도 × (경과 시간 + pose 지연) 으로 예측한다(pose 는 응답 수신 시각, MC-004).
- watchdog: 마지막 명령 수신 뒤 watchdog_s 가 지나면 'expire' — gateway 가 속도 0 speedl 을 보내고
  이어서 항상 move_stop 을 부른다(정지 판별 안 함, #53 MC-014). 컨트롤러는 끊김을 감지하지 않는다.
시간은 모두 같은 시계의 초(gateway 는 노드 시계)로 넘긴다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class ServoParams:
    watchdog_s: float = 0.2  # F-04 실측(ADR-0010)
    max_speed_mm_s: float = 100.0  # 선속도 크기 상한 (벨트 48 mm/s 추종 + 보정 여유)
    # 벨트 위 파지 TCP z = 송장 윗면 100.8 − 19 = 81.8 mm, 벨트 면 ≈ 100.8 − 27 = 73.8 mm → 그 사이 78 mm
    z_min_mm: float = 78.0
    x_range_mm: tuple[float, float] = (-107.0, 638.0)  # measurements #6 추종 구간 TCP x
    pose_max_age_s: float = 0.1  # 이보다 오래된 pose 로는 작업 영역을 판단하지 않는다(명령 거부)
    # pose 가 실제 로봇 상태보다 늦은 만큼(10/08 he_moving_01: 영상 대비 약 60 ms) 더 앞을 예측한다.
    # F-04 zmin(5 mm/s)에서 보정 없이 하한을 0.42 mm 넘었다
    pose_latency_s: float = 0.06
    # speedl 선가속(gateway servo_acc[0]). 0 을 보내도 v²/(2a) 만큼 더 가므로 그만큼 먼저 자른다
    # (50 mm/s·100 mm/s² → 12.5 mm. 10/08 F-04: 5 mm/s 에서 하한을 0.28 mm 넘음)
    lin_acc_mm_s2: float = 100.0
    # ---- 각속도 (S2-T17). 끄면 지금처럼 자른다 ----
    angular_enable: bool = False
    max_ang_dps: float = 60.0  # belt_servo rotate.omega_max_dps 제안 60
    ang_acc_dps2: float = 90.0  # speedl 각가속(gateway servo_acc[1]). 감속 각 ω²/(2α) 계산용
    yaw_center_deg: float | None = None  # 관측 자세 공구 yaw. None 이면 범위를 모름 → 각속도 0
    yaw_limit_deg: float = 100.0  # 중심 ± 이 각 밖으로는 돌지 않는다(손목 카메라 케이블)


@dataclass
class CmdResult:
    vel_mm_s: list[float] | None  # None = 거부(내보내지 않음)
    reason: str = ""  # 거부 사유 (stop/old/no_pose/busy)
    # 자른 항목 (speed/z_min/x_min/x_max/angular/ang_speed/yaw_limit)
    clamps: list[str] = field(default_factory=list)
    wz_dps: float = 0.0  # 내보낼 베이스 Z 각속도 (deg/s, + = 위에서 반시계)


class ServoGuard:
    def __init__(self, p: ServoParams | None = None) -> None:
        self.p = p or ServoParams()
        self.active = False  # speedl 로 0 이 아닌 속도를 내보낸 뒤 아직 정지 처리 전
        self.last_rx = -math.inf  # 마지막으로 받아들인 명령의 수신 시각
        self.last_vel = [0.0, 0.0, 0.0]  # 마지막으로 내보낸 선속도 (mm/s)
        self.last_wz = 0.0  # 마지막으로 내보낸 각속도 (deg/s)
        self.stop_stamp = -math.inf  # 이 stamp 이하 명령은 버린다(stop 이전 것)
        self.motion_busy = False  # MoveToZone 등 다른 모션 사용 중
        self._pose: tuple[float, float, float, float] | None = None  # (수신 시각, x, y, z) mm
        self._yaw: float | None = None  # 같은 pose 의 공구 yaw (deg)

    # ---------------- 입력 ----------------
    def set_pose(
        self, now: float, x_mm: float, y_mm: float, z_mm: float, yaw_deg: float | None = None
    ) -> None:
        self._pose = (now, x_mm, y_mm, z_mm)
        self._yaw = yaw_deg

    def predicted_xyz(self, now: float) -> tuple[float, float, float] | None:
        """마지막 pose + 마지막 지령 속도 × 경과. pose 가 오래됐으면 None."""
        if self._pose is None:
            return None
        t, x, y, z = self._pose
        age = now - t
        if age > self.p.pose_max_age_s:
            return None
        v = self.last_vel if self.active else [0.0, 0.0, 0.0]
        ahead = age + self.p.pose_latency_s
        return x + v[0] * ahead, y + v[1] * ahead, z + v[2] * ahead

    def on_cmd(self, now: float, stamp: float, lin_m_s, ang_rad_s=(0.0, 0.0, 0.0)) -> CmdResult:
        """servo_cmd 1개 → 내보낼 선속도(mm/s) 또는 거부."""
        if stamp <= self.stop_stamp:
            return CmdResult(None, "stop")
        if now - stamp > self.p.watchdog_s:
            return CmdResult(None, "old")
        if self.motion_busy:
            return CmdResult(None, "busy")
        xyz = self.predicted_xyz(now)
        if xyz is None:
            return CmdResult(None, "no_pose")
        clamps: list[str] = []
        wz = 0.0
        if self.p.angular_enable:
            if abs(ang_rad_s[0]) > 1e-9 or abs(ang_rad_s[1]) > 1e-9:
                clamps.append("angular")  # 공구는 수직 아래 그대로 — 베이스 Z 둘레만
            wz = math.degrees(float(ang_rad_s[2]))
            if abs(wz) > self.p.max_ang_dps:
                wz = math.copysign(self.p.max_ang_dps, wz)
                clamps.append("ang_speed")
            wz, yc = self._limit_yaw(now, wz)
            clamps += yc
        elif any(abs(w) > 1e-9 for w in ang_rad_s):
            clamps.append("angular")  # 끄면 G0 그대로 각속도 0
        v = [float(c) * 1000.0 for c in lin_m_s]
        n = math.sqrt(sum(c * c for c in v))
        if n > self.p.max_speed_mm_s:
            v = [c * self.p.max_speed_mm_s / n for c in v]
            clamps.append("speed")
        v, ws = self._limit_workspace(xyz, v)
        clamps += ws
        self.last_rx = now
        self.last_vel = v
        self.last_wz = wz
        self.active = True
        return CmdResult(v, "", clamps, wz)

    def predicted_yaw_rel(self, now: float) -> float | None:
        """관측 자세 yaw 기준 예측 공구 yaw (deg, (−180, 180]). 모르면 None."""
        if self._pose is None or self._yaw is None or self.p.yaw_center_deg is None:
            return None
        age = now - self._pose[0]
        if age > self.p.pose_max_age_s:
            return None
        w = self.last_wz if self.active else 0.0
        d = self._yaw + w * (age + self.p.pose_latency_s) - self.p.yaw_center_deg
        return (d + 180.0) % 360.0 - 180.0

    def _limit_yaw(self, now: float, wz: float) -> tuple[float, list[str]]:
        """범위 밖으로 가는 각속도는, 예측 yaw 에서 감속 각만큼 더 돌면 범위를 넘을 때 0. yaw 를 모르면 0."""
        if wz == 0.0:
            return 0.0, []
        rel = self.predicted_yaw_rel(now)
        if rel is None:
            return 0.0, ["yaw_limit"]
        a = self.p.ang_acc_dps2
        brake = wz * wz / (2.0 * a) if a > 0 else 0.0
        lim = self.p.yaw_limit_deg
        if (wz > 0 and rel + brake >= lim) or (wz < 0 and rel - brake <= -lim):
            return 0.0, ["yaw_limit"]
        return wz, []

    def _brake(self, v: float) -> float:
        """속도 v(mm/s)에서 0 까지 감속하는 동안 더 가는 거리(mm)."""
        a = self.p.lin_acc_mm_s2
        return v * v / (2.0 * a) if a > 0 else 0.0

    def _limit_workspace(self, xyz, v):
        """한계 쪽으로 가는 성분은, 예측 위치에서 감속 거리만큼 더 가면 한계를 넘을 때 0 으로 자른다."""
        x, _y, z = xyz
        out, clamps = list(v), []
        if out[2] < 0 and z - self._brake(out[2]) <= self.p.z_min_mm:
            out[2] = 0.0
            clamps.append("z_min")
        lo, hi = self.p.x_range_mm
        if out[0] < 0 and x - self._brake(out[0]) <= lo:
            out[0] = 0.0
            clamps.append("x_min")
        if out[0] > 0 and x + self._brake(out[0]) >= hi:
            out[0] = 0.0
            clamps.append("x_max")
        return out, clamps

    # ---------------- 주기 점검 ----------------
    def on_tick(self, now: float) -> tuple[str, list[float] | None]:
        """('expire', None) = 끊김 → 0 속도 + move_stop. ('clamp', vel) = 명령 사이에 한계에 닿음 → vel·last_wz 재전송.
        ('', None) = 할 일 없음."""
        if not self.active:
            return "", None
        if now - self.last_rx > self.p.watchdog_s:
            self._zero()
            return "expire", None
        xyz = self.predicted_xyz(now)
        if xyz is None:
            # pose 가 끊겼는데 움직이는 중: 작업 영역을 모르니 멈춘다
            self._zero()
            return "expire", None
        v, ws = self._limit_workspace(xyz, self.last_vel)
        wz, yc = self._limit_yaw(now, self.last_wz)
        if ws or yc:
            self.last_vel, self.last_wz = v, wz  # 자른 값은 last_wz 로 함께 다시 보낸다
            return "clamp", v
        return "", None

    def _zero(self) -> None:
        self.active = False
        self.last_vel = [0.0, 0.0, 0.0]
        self.last_wz = 0.0

    def stop(self, stamp_now: float) -> None:
        """/voss/robot/stop: 이 시각 이전 stamp 는 버리고 새 stamp 부터 받는다(F-04 제안, 김학민)."""
        self.stop_stamp = stamp_now
        self._zero()
