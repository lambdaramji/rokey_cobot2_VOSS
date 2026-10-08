"""RG2 Modbus 래퍼 — 가짜 Modbus 클라이언트로 (ADR-0005 레지스터, BUSY·INVALID·TIMEOUT·COMM_ERROR)."""

import threading
import time

from voss_robot.rg2 import DryRunRg2, Rg2, validate


class Resp:
    def __init__(self, regs=None, err=False):
        self.registers = regs or [0]
        self._err = err

    def isError(self):  # noqa: N802 (pymodbus 이름)
        return self._err


class FakeModbus:
    """busy_reads 번 읽는 동안 busy, 그 뒤 목표 폭(또는 물체 폭)에서 멈춘다."""

    def __init__(self, busy_reads=2, object_mm=None, fail_write=False, connected=True):
        self.connected = connected
        self.busy_reads = busy_reads
        self.object_mm = object_mm
        self.fail_write = fail_write
        self.width10 = 1000
        self.writes = []
        self._left = 0
        self._grip = False

    def connect(self):
        return self.connected

    def write_registers(self, addr, values, slave=None):
        self.writes.append((addr, list(values), slave))
        if self.fail_write:
            return Resp(err=True)
        target = values[1]
        if self.object_mm is not None and target < self.object_mm * 10 < self.width10:
            self.width10, self._grip = int(self.object_mm * 10), True
        else:
            self.width10, self._grip = target, False
        self._left = self.busy_reads
        return Resp()

    def read_holding_registers(self, addr, count=1, slave=None):
        if addr == 268:
            busy = self._left > 0
            self._left = max(0, self._left - 1)
            return Resp([(1 if busy else 0) | (2 if self._grip and not busy else 0)])
        if addr == 267:
            return Resp([self.width10])
        return Resp([0])

    def close(self):
        pass


def test_validate_ranges():
    assert validate(39, 14) is None
    assert validate(-1, 14) and validate(111, 14)
    assert validate(39, 2) and validate(39, 41)


def test_writes_force_width_control_to_unit_65():
    c = FakeModbus()
    r = Rg2(c, poll_s=0.0).command(39.0, 14.0)
    assert c.writes == [(0, [140, 390, 16], 65)]
    assert r.ok and r.message == "OK" and r.width_actual == 39.0 and not r.grip_detected


def test_grip_detected_on_object():
    r = Rg2(FakeModbus(object_mm=40.2), poll_s=0.0).command(39.0, 14.0)
    assert r.ok and r.grip_detected and r.width_actual == 40.2


def test_invalid_does_not_write():
    c = FakeModbus()
    r = Rg2(c).command(200.0, 14.0)
    assert not r.ok and r.message.startswith("INVALID") and c.writes == []


def test_timeout_when_busy_never_clears():
    r = Rg2(FakeModbus(busy_reads=10**6), timeout_s=0.3, poll_s=0.01).command(39.0, 14.0)
    assert not r.ok and r.message == "TIMEOUT"


def test_comm_error_on_write_failure_and_no_connection():
    assert Rg2(FakeModbus(fail_write=True)).command(39, 14).message.startswith("COMM_ERROR")
    assert Rg2(FakeModbus(connected=False)).command(39, 14).message.startswith("COMM_ERROR")


def test_second_command_while_moving_is_busy():
    rg = Rg2(FakeModbus(busy_reads=20), poll_s=0.02)
    out = {}
    t = threading.Thread(target=lambda: out.update(first=rg.command(90.0, 14.0)))
    t.start()
    time.sleep(0.2)
    assert rg.command(39.0, 14.0).message == "BUSY"
    t.join()
    assert out["first"].ok


def test_dry_run_grips_object_between():
    g = DryRunRg2(width_mm=90.0, object_mm=40.2)
    r = g.command(39.0, 14.0)
    assert r.ok and r.grip_detected and r.width_actual == 40.2
    assert g.command(90.0, 14.0).width_actual == 90.0


def test_hold_blocks_external_command_and_allows_held():
    rg = Rg2(FakeModbus(), poll_s=0.0)
    assert rg.try_hold()
    assert rg.command(39.0, 14.0).message == "BUSY"  # MoveToZone 이 점유 중
    assert rg.command_held(90.0, 14.0).ok
    rg.release()
    assert rg.command(39.0, 14.0).ok
