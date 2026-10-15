"""10/15 U14 실기 뒤 추가 — + 쪽 큰 각은 반대 방향(flip_above), 회전 중 LOST 기준(rotate.lost_timeout_s)."""

import math
from types import SimpleNamespace

from test_rotate import D, cfg, inputs
from test_rotate_hooks import invalid_keys, on_values

from voss_servo import rotate as rt
from voss_servo.belt_servo import BeltServoNode
from voss_servo.params import params_digest, rot_cfg_from_values, rotate_line


def _decide(box_deg: float, **kw) -> tuple[str, float | None]:
    c = cfg(max_rot=D(110), flip_above=D(70), **kw)
    return rt.decide(rt.aggregate([D(box_deg)] * 5), inputs(), c)


# ---------------------------------------------------------------- decide


def test_flip_turns_large_plus_into_minus() -> None:
    """+70 넘는 Δ 는 Δ − 180 (−110 ~ −90), 그 밖은 그대로."""
    for box, want in ((80, -100), (89, -91), (90, -90), (71, -109), (70, 70), (45, 45), (-85, -85)):
        cause, delta = _decide(box)
        assert cause == ""
        assert math.isclose(math.degrees(delta), want, abs_tol=1e-6), (box, math.degrees(delta))


def test_flip_off_keeps_old_rule() -> None:
    """flip 없으면 예전과 같다 — +80 은 max 45 밖, +80 은 + 쪽."""
    c = cfg()
    assert rt.decide(rt.aggregate([D(80)] * 5), inputs(), c)[0] == rt.OUT_OF_RANGE
    c = cfg(max_rot=D(90))
    cause, delta = rt.decide(rt.aggregate([D(80)] * 5), inputs(), c)
    assert cause == "" and math.isclose(math.degrees(delta), 80, abs_tol=1e-6)


def test_flip_respects_max_and_small() -> None:
    """뒤집은 뒤에도 상한·작은 각 판정은 |Δ| 로."""
    cause, _ = rt.decide(rt.aggregate([D(75)] * 5), inputs(), cfg(max_rot=D(100), flip_above=D(70)))
    assert cause == rt.OUT_OF_RANGE  # 75 → −105, |−105| > 100
    cause, _ = rt.decide(rt.aggregate([D(5)] * 5), inputs(), cfg(max_rot=D(110), flip_above=D(70)))
    assert cause == rt.SMALL


def test_flip_rotation_goes_minus_and_returns() -> None:
    """−100 목표: 첫 지령이 − 방향, 되돌리기 지령은 + 방향(감은 각 ±180 넘지 않음)."""
    c = cfg(max_rot=D(110), flip_above=D(70))
    rs = rt.RotState(rt.COLLECT, t_goal=0.0, home=rt.HOME if hasattr(rt, "HOME") else D(-88.72))
    rs, w, _ = rt._collect(rs, inputs(yaws=[D(80)] * 5), c)
    assert rs.state == rt.ROTATING and w is not None and w < 0
    assert math.isclose(math.degrees(rt.wrap_pi(rs.target - D(-88.72))), -100, abs_tol=1e-6)
    psi = rt.wrap_pi(D(-88.72) - D(100))  # 다 돈 자세 (+171.28°)
    w_back = rt._law_to(rs.home, inputs(psi_raw=psi, psi_est=psi), rs, c)
    assert w_back > 0  # 풀어서 돌아온다 (반대로 260° 돌지 않음)


# ---------------------------------------------------------------- params


def test_params_flip_allows_max_up_to_180_minus_flip() -> None:
    assert "rotate.min_deg" in invalid_keys(on_values(**{"rotate.max_deg": 110}))  # flip 없으면 ≤ 90
    ok = on_values(**{"rotate.max_deg": 110, "rotate.flip_above_deg": 70})
    assert invalid_keys(ok) == []
    assert "rotate.min_deg" in invalid_keys(on_values(**{"rotate.max_deg": 111, "rotate.flip_above_deg": 70}))
    assert "rotate.flip_above_deg" in invalid_keys(on_values(**{"rotate.flip_above_deg": 8}))  # ≤ min 10
    assert "rotate.flip_above_deg" in invalid_keys(on_values(**{"rotate.flip_above_deg": 95}))


def test_params_rotate_lost_timeout_not_below_input() -> None:
    v = on_values(**{"rotate.lost_timeout_s": 1.2})
    assert invalid_keys(v) == []
    low = on_values(**{"rotate.lost_timeout_s": v["input.lost_timeout_s"] / 2})
    assert "rotate.lost_timeout_s" in invalid_keys(low)


def test_params_new_keys_cfg_line_and_sha() -> None:
    v = on_values(**{"rotate.max_deg": 110, "rotate.flip_above_deg": 70, "rotate.lost_timeout_s": 1.2})
    c = rot_cfg_from_values(v, (1.0, 0.0, 0.0))
    assert math.isclose(c.flip_above, D(70))
    assert rot_cfg_from_values(on_values(), (1.0, 0.0, 0.0)).flip_above is None
    line = rotate_line(v)
    assert "flip >70 → −" in line and "lost(회전) 1.2 s" in line
    # 회전 끔이면 새 키도 지문에서 빠진다
    off = {**v, "rotate.enable": False}
    base = {k: val for k, val in off.items() if not k.startswith("rotate.") or k == "rotate.enable"}
    assert params_digest(off) == params_digest(base)


# ---------------------------------------------------------------- belt_servo LOST 기준


def _node(rot_on: bool, rot_lost):
    values = {"input.lost_timeout_s": 0.5, "rotate.lost_timeout_s": rot_lost}
    return SimpleNamespace(values=values, _rot_on=rot_on, _p=values.__getitem__,
                           _ROT_LOST_STATES=BeltServoNode._ROT_LOST_STATES)  # fmt: skip


def _ctx(rot_state, phase):
    rot = None if rot_state is None else rt.RotState(rot_state, t_goal=0.0)
    return SimpleNamespace(rot=rot, state=SimpleNamespace(phase=phase))


def test_lost_timeout_extends_only_while_rotated_before_descend() -> None:
    f = BeltServoNode._lost_timeout
    n = _node(True, 1.2)
    for st in (rt.ROTATING, rt.SETTLING, rt.DONE, rt.STOPPING, rt.FALLBACK):
        assert f(n, _ctx(st, "TRACK")) == 1.2
        assert f(n, _ctx(st, "PREPARE")) == 1.2
        assert f(n, _ctx(st, "DESCEND")) == 0.5  # 하강부터는 원래 기준
    for st in (rt.COLLECT, rt.SKIP, None):
        assert f(n, _ctx(st, "TRACK")) == 0.5  # 회전을 안 쓰는 goal
    assert f(_node(True, None), _ctx(rt.ROTATING, "TRACK")) == 0.5  # 키 없으면 그대로
    assert f(_node(False, 1.2), _ctx(rt.ROTATING, "TRACK")) == 0.5  # 회전 끔
