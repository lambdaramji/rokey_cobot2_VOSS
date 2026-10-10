"""RG2 그리퍼 — Compute Box Modbus TCP 직접 제어 (ADR-0005). ROS import 없음.

레지스터(OnRobot RG, unit 65, scripts/measure_1006/rg2_check.py 와 같은 값):
0 목표 힘(0.1 N) · 1 목표 폭(0.1 mm) · 2 제어(16 = grip_w_offset) · 267 폭(0.1 mm) · 268 상태(bit0 busy,
bit1 grip_detected, bit6 safety_err). 폭은 RG2 보고값(실제 간격 ≈ 보고값 − 10 mm, measurements #8).
응답은 busy 가 풀린(동작 완료) 뒤 돌려준다(voss_msgs.md Gripper, #53 MC-012·013).
한 번에 한 명령만 — 동작 중 두 번째 명령은 BUSY(topics.md 자원 규칙). 판정(grip_detected 주, 폭 보조)은
호출자(belt_servo) 몫이고 여기서는 보고만 한다.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

UNIT = 65
REG_FORCE, REG_WIDTH, REG_CTRL = 0, 1, 2
REG_ACT_WIDTH, REG_STATUS = 267, 268
CTRL_GRIP_W_OFFSET = 16
BIT_BUSY, BIT_GRIP, BIT_SAFETY = 0, 1, 6
WIDTH_RANGE_MM = (0.0, 110.0)  # RG2 보고 폭 범위
FORCE_RANGE_N = (3.0, 40.0)  # RG2 힘 범위 (measurements #8: 3 N 은 놓침)


@dataclass
class GripResult:
    ok: bool
    width_actual: float = 0.0  # mm (RG2 보고값)
    grip_detected: bool = False
    message: str = "OK"  # OK | TIMEOUT | INVALID | BUSY | COMM_ERROR


def validate(width_mm: float, force_n: float) -> str | None:
    """요청이 범위 밖이면 사유 문자열, 아니면 None."""
    lo, hi = WIDTH_RANGE_MM
    if not lo <= width_mm <= hi:
        return f"width {width_mm} mm 는 {lo:.0f}~{hi:.0f}"
    flo, fhi = FORCE_RANGE_N
    if not flo <= force_n <= fhi:
        return f"force {force_n} N 은 {flo:.0f}~{fhi:.0f}"
    return None


class Rg2:
    """Modbus 클라이언트를 감싼 RG2. client 는 pymodbus ModbusTcpClient 와 같은 메서드를 가진 것(시험 때 가짜)."""

    def __init__(self, client, timeout_s: float = 6.0, poll_s: float = 0.05) -> None:
        self._c = client
        self._timeout = timeout_s
        self._poll = poll_s
        self._busy = threading.Lock()  # RG2 자원: 동시에 하나
        self._io = threading.Lock()  # Modbus 소켓은 한 스레드씩 (상태 읽기와 명령이 겹치지 않게)
        self._kw = self._unit_kw()

    def _unit_kw(self) -> dict:
        import inspect

        try:
            params = inspect.signature(self._c.read_holding_registers).parameters
        except (TypeError, ValueError):
            return {"slave": UNIT}
        return (
            {"device_id": UNIT} if "device_id" in params else {"slave": UNIT}
        )  # pymodbus 3.9+ / 3.6

    def _connected(self) -> bool:
        with self._io:
            if getattr(self._c, "connected", True):
                return True
            return bool(self._c.connect())

    def _read(self, addr: int) -> int:
        with self._io:
            r = self._c.read_holding_registers(addr, count=1, **self._kw)
        if r is None or r.isError():
            raise OSError(f"레지스터 {addr} 읽기 실패: {r}")
        return r.registers[0]

    @property
    def busy(self) -> bool:
        """명령 실행 중 (RobotState action GRIPPER)."""
        return self._busy.locked()

    def status(self) -> tuple[float, bool, bool, bool]:
        """(폭 mm, busy, grip_detected, safety_err). 읽기만."""
        word = self._read(REG_STATUS)
        width = self._read(REG_ACT_WIDTH) / 10.0
        return (
            width,
            bool(word >> BIT_BUSY & 1),
            bool(word >> BIT_GRIP & 1),
            bool(word >> BIT_SAFETY & 1),
        )

    def try_hold(self) -> bool:
        """RG2 자원을 잡는다(MoveToZone PLACE·PICK 이 모션과 함께 점유 — 그동안 외부 Gripper 는 BUSY)."""
        return self._busy.acquire(blocking=False)

    def release(self) -> None:
        self._busy.release()

    def command(self, width_mm: float, force_n: float) -> GripResult:
        """폭·힘으로 움직이고 busy 가 풀린 뒤 결과를 돌려준다. 동작 중이면 바로 BUSY."""
        if (why := validate(width_mm, force_n)) is not None:
            return GripResult(False, message=f"INVALID: {why}")
        if not self.try_hold():
            return GripResult(False, message="BUSY")
        try:
            return self.command_held(width_mm, force_n)
        finally:
            self.release()

    def command_held(self, width_mm: float, force_n: float) -> GripResult:
        """try_hold 로 자원을 이미 잡은 호출자용."""
        if (why := validate(width_mm, force_n)) is not None:
            return GripResult(False, message=f"INVALID: {why}")
        try:
            if not self._connected():
                return GripResult(False, message="COMM_ERROR: 연결 안 됨")
            with self._io:
                w = self._c.write_registers(
                    REG_FORCE,
                    [round(force_n * 10), round(width_mm * 10), CTRL_GRIP_W_OFFSET],
                    **self._kw,
                )
            if w.isError():
                return GripResult(False, message=f"COMM_ERROR: 쓰기 실패 {w}")
            t0 = time.monotonic()
            time.sleep(0.15)  # busy 비트가 올라올 시간 (rg2_check.py 와 같음)
            while True:
                width, busy, grip, safety = self.status()
                if safety:
                    return GripResult(False, width, grip, "COMM_ERROR: RG2 safety_err")
                if not busy:
                    return GripResult(True, width, grip, "OK")
                if time.monotonic() - t0 > self._timeout:
                    return GripResult(False, width, grip, "TIMEOUT")
                time.sleep(self._poll)
        except Exception as e:  # 소켓 오류·pymodbus 예외(ConnectionException 등)
            return GripResult(False, message=f"COMM_ERROR: {e}")

    def close(self) -> None:
        with self._io:
            self._c.close()


class DryRunRg2:
    """가짜 RG2: 목표 폭으로 0.3 s 뒤 도착. object_mm 를 주면 그 폭에서 멈추고 grip_detected."""

    def __init__(self, width_mm: float = 100.0, object_mm: float | None = None) -> None:
        self.width = width_mm
        self.object_mm = object_mm
        self._busy = threading.Lock()

    @property
    def busy(self) -> bool:
        return self._busy.locked()

    def status(self) -> tuple[float, bool, bool, bool]:
        return self.width, False, False, False

    def try_hold(self) -> bool:
        return self._busy.acquire(blocking=False)

    def release(self) -> None:
        self._busy.release()

    def command(self, width_mm: float, force_n: float) -> GripResult:
        if (why := validate(width_mm, force_n)) is not None:
            return GripResult(False, message=f"INVALID: {why}")
        if not self.try_hold():
            return GripResult(False, message="BUSY")
        try:
            return self.command_held(width_mm, force_n)
        finally:
            self.release()

    def command_held(self, width_mm: float, force_n: float) -> GripResult:
        if (why := validate(width_mm, force_n)) is not None:
            return GripResult(False, message=f"INVALID: {why}")
        time.sleep(0.3)
        # 이미 물체 폭에서 멈춘 채 다시 닫아도(belt_servo VERIFY 재닫기) 쥔 상태 유지 → <= (#41 박병후)
        grip = self.object_mm is not None and width_mm < self.object_mm <= self.width
        self.width = self.object_mm if grip else width_mm
        return GripResult(True, self.width, grip, "OK")

    def close(self) -> None:
        pass
