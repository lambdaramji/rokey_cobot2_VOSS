"""sort_fsm — G0 최소 경로, stop·resume·reset_zone, 실패 분기, 구역 가득, 설정 검사."""

import os
from datetime import datetime

import pytest
import yaml

from voss_manager import sort_fsm as f

REPO_CONFIG = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "config", "voss_config.yaml"
)
SID = "20261010T143012-a3f9"
MS = 1_000_000


def raw_config() -> dict:
    with open(REPO_CONFIG, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.fixture
def cfg() -> f.Config:
    return f.load_config(raw_config())


def run(ctx: f.Ctx, *events) -> tuple[f.Ctx, list, list]:
    """이벤트를 차례로 넣고 (ctx, 액션 전부, 응답 전부)."""
    acts, replies = [], []
    for ev in events:
        out = f.step(ctx, ev)
        ctx = out.ctx
        acts += list(out.actions)
        replies.append(out.reply)
    return ctx, acts, replies


def of(acts: list, kind: type) -> list:
    return [a for a in acts if isinstance(a, kind)]


def start(t: int = 0, not_ready: tuple = ()) -> f.Command:
    return f.Command("start", "", t, not_ready, SID)


def cmd(c: str, arg: str = "", t: int = 0, not_ready: tuple = ()) -> f.Command:
    return f.Command(c, arg, t, not_ready)


def label(
    track: int,
    code: str = "S07-02",
    dong: str = "대치동",
    conf: float = 0.9,
    t: int = 2000 * MS,
    **kw,
) -> f.LabelSeen:
    base = dict(
        stage=1,
        stamp_ns=t,
        raw_text=f"{code}\n{dong}",
        dong_alt="",
        now_ns=t + 50 * MS,
        started_at_ns=t - 300 * MS,
    )
    base.update(kw)
    return f.LabelSeen(track, code, dong, conf, **base)


def running(cfg: f.Config) -> f.Ctx:
    """start → OBSERVE 도착(1 s) 까지 마친 RUNNING."""
    ctx, _, _ = run(f.new_ctx(cfg), start(0), f.MoveDone(True, "OK", 0, 1000 * MS))
    assert ctx.state == f.RUNNING and ctx.phase == f.PH_NONE and ctx.stage_start_ns == 1000 * MS
    return ctx


def placed(ctx: f.Ctx, track: int, t: int = 2000 * MS, **kw) -> tuple[f.Ctx, list]:
    """판독 → 파지 OK → 적재 OK 한 박스."""
    ctx, acts, _ = run(
        ctx,
        label(track, t=t, **kw),
        f.GoalDone(True, True, "OK", 1, t + 5000 * MS),
        f.MoveDone(True, "OK", t + 9000 * MS, t + 12000 * MS),
    )
    return ctx, acts


# ---------------------------------------------------------------- 설정·ID


def test_load_repo_config(cfg: f.Config) -> None:
    assert cfg.zone_map == {"역삼동": "A", "대치동": "B", "청담동": "C"}
    assert cfg.capacity == {"A": 3, "B": 3, "C": 3, "RECHECK": 2, "HOLD": 2}
    assert cfg.confidence_min == 0.6 and cfg.version == "1"
    assert ("대치동", "B", "S07-02", ["대치", "대치동"]) in f.zone_map_entries(cfg)


@pytest.mark.parametrize(
    "patch, msg",
    [
        ({"zone_map": {"역삼동": "D"}}, "A/B/C"),
        ({"ocr": {"confidence_min": 0.6, "codes": {"S07-09": "논현동"}}}, "zone_map 에 없음"),
        ({"ocr": {"confidence_min": 0, "codes": {"S07-01": "역삼동"}}}, "confidence_min"),
        ({"zones": {"A": {"grid": {"cols": 3, "rows": 1}}}}, "grid"),
        ({"version": "x" * 17}, "16자"),
    ],
)
def test_load_config_rejects(patch: dict, msg: str) -> None:
    raw = {**raw_config(), **patch}
    with pytest.raises(ValueError, match=msg):
        f.load_config(raw)


def test_ids() -> None:
    sid = f.make_session_id(datetime(2026, 10, 10, 14, 30, 12), "a3f9")
    assert sid == SID and len(sid) == 20
    bid = f.make_box_id(sid, 7)
    assert bid == SID + "-007" and len(bid) == 24


def test_resolve_label(cfg: f.Config) -> None:
    assert f.resolve_label("S07-02", "대치동", 0.9, cfg) == ("대치동", "B", "")
    assert f.resolve_label("S07-02", "", 0.9, cfg) == ("대치동", "B", "")  # 코드만
    assert f.resolve_label("", "청담", 0.9, cfg) == ("청담동", "C", "")  # 별칭
    assert f.resolve_label("S07-02", "역삼동", 0.9, cfg)[2] == "CODE_DONG_MISMATCH"
    assert f.resolve_label("S07-02", "대치동", 0.5, cfg) == ("대치동", "B", "LOW_CONF")
    assert f.resolve_label("", "", 0.9, cfg)[2] == "UNKNOWN"


def test_intent_to_command() -> None:
    assert f.intent_to_command("start", "", "", "") == ("start", "")
    assert f.intent_to_command("priority", "역삼동", "", "") == ("priority", "역삼동")
    assert f.intent_to_command("answer", "", "HOLD", SID + "-001") == ("answer", SID + "-001|HOLD")
    assert f.intent_to_command("update_zone_map", "대치동", "C", "") is None


# ---------------------------------------------------------------- G0 최소 경로


def test_g0_happy_path(cfg: f.Config) -> None:
    ctx = f.new_ctx(cfg)
    ctx, acts, rep = run(ctx, start(0, not_ready=("LOG",)))
    assert rep == [(False, "준비 안 됨: LOG")] and ctx.state == f.IDLE

    ctx, acts, rep = run(ctx, start(0))
    assert rep[0][0] and ctx.state == f.RUNNING and ctx.phase == f.PH_HOME and ctx.session_id == SID
    assert of(acts, f.CallMove) == [f.CallMove("OBSERVE", 0, "")]
    ctx, acts, _ = run(ctx, label(5))  # OBSERVE 도착 전 판독은 받지 않는다
    assert ctx.state == f.RUNNING and not of(acts, f.SendGoal)

    ctx, _, _ = run(ctx, f.MoveDone(True, "OK", 0, 1000 * MS))
    ctx, acts, _ = run(ctx, label(5, t=900 * MS))  # 관측 시작 전 촬영
    assert ctx.state == f.RUNNING and not of(acts, f.SendGoal)

    ctx, acts, _ = run(ctx, label(5))
    assert ctx.state == f.PICKING and of(acts, f.SendGoal) == [f.SendGoal(5)]
    assert ctx.box.box_id == SID + "-001" and ctx.box.zone == "B" and ctx.box.slot == 0
    ctx, acts, _ = run(ctx, label(5), label(6))  # PICKING 중 다른 판독은 무시
    assert not acts and ctx.box.track_id == 5

    ctx, acts, _ = run(ctx, f.GoalDone(True, True, "OK", 1, 7000 * MS))
    assert of(acts, f.CallMove) == [f.CallMove("B", 0, "")] and ctx.phase == f.PH_PLACE

    ctx, acts, _ = run(ctx, f.MoveDone(True, "OK", 11000 * MS, 14000 * MS))
    (res,) = of(acts, f.Result)
    assert (res.outcome, res.zone, res.reason, res.decided_by, res.attempts) == (
        "PLACED",
        "B",
        "",
        "OCR",
        1,
    )
    assert res.stamp_ns == 11000 * MS and res.started_at_ns == 1700 * MS and res.rule_version == "1"
    assert res.session_id == SID and res.track_id == 5 and res.code == "S07-02"
    assert ctx.state == f.RUNNING and ctx.slots["B"] == 1 and ctx.box is None
    assert ctx.stage_start_ns == 14000 * MS  # OBSERVE 복귀 뒤 새로 관측

    ctx, acts, _ = run(ctx, label(5, t=15000 * MS))  # 처리한 트랙은 다시 집지 않는다
    assert not of(acts, f.SendGoal)
    ctx, acts = placed(ctx, 9, t=15000 * MS)
    assert of(acts, f.Result)[0].box_id == SID + "-002" and ctx.slots["B"] == 2


def test_start_without_home(cfg: f.Config) -> None:
    ctx, acts, _ = run(f.new_ctx(cfg, home_first=False), start(500 * MS))
    assert ctx.state == f.RUNNING and ctx.phase == f.PH_NONE and not of(acts, f.CallMove)
    assert ctx.stage_start_ns == 500 * MS


def test_low_conf_waits_then_confident_label_picks(cfg: f.Config) -> None:
    ctx = running(cfg)
    ctx, acts, _ = run(ctx, label(3, conf=0.4), label(3, code="S07-01", dong="대치동"))
    assert ctx.state == f.RUNNING and not of(acts, f.SendGoal) and 3 not in ctx.decided
    ctx, acts, _ = run(ctx, label(3, conf=0.8))
    assert ctx.state == f.PICKING and of(acts, f.SendGoal) == [f.SendGoal(3)]


def test_waiting_log_once_per_track_and_reason(cfg: f.Config) -> None:
    ctx = running(cfg)
    ctx, acts, _ = run(
        ctx, label(3, conf=0.4), label(3, conf=0.4), label(3, conf=0.3), label(4, conf=0.4)
    )
    assert len(of(acts, f.Log)) == 2  # track 3 LOW_CONF 한 번, track 4 한 번


def test_label_ignored_when_box_gone_or_not_stage1(cfg: f.Config) -> None:
    ctx = running(cfg)
    ctx, acts, _ = run(ctx, label(3, track_fresh=False), label(3, stage=2))
    assert ctx.state == f.RUNNING and not of(acts, f.SendGoal) and not ctx.decided


def test_not_ready_robot_skips_box(cfg: f.Config) -> None:
    ctx = running(cfg)
    ctx, acts, _ = run(ctx, label(3, not_ready=("SERVO",)))
    assert ctx.state == f.RUNNING and not of(acts, f.SendGoal) and 3 not in ctx.decided
    ctx, acts, _ = run(ctx, label(3, not_ready=("LOG", "OCR")))  # 운전 중 LOG·OCR 은 막지 않는다
    assert ctx.state == f.PICKING


def test_priority_passes_non_target(cfg: f.Config) -> None:
    ctx, _, rep = run(f.new_ctx(cfg), cmd("priority", "역삼"))  # IDLE 에서 저장, 별칭 허용
    assert rep == [(True, "우선 역삼동")] and ctx.priority == "역삼동"
    ctx, _, _ = run(ctx, start(0), f.MoveDone(True, "OK", 0, 1000 * MS))
    assert ctx.priority == "역삼동"  # IDLE 에서 저장한 우선은 start 뒤에도 유지

    ctx, acts, _ = run(ctx, label(4))  # 대치동 = 비대상
    (res,) = of(acts, f.Result)
    assert (res.outcome, res.zone, res.reason, res.attempts) == ("PASSED", "", "NON_TARGET", 0)
    assert not of(acts, f.SendGoal) and ctx.state == f.RUNNING and res.stamp_ns > 0

    ctx, acts, _ = run(ctx, label(5, code="S07-01", dong="역삼동"))
    assert of(acts, f.SendGoal) == [f.SendGoal(5)] and ctx.box.box_id == SID + "-002"

    ctx, _, rep = run(ctx, start(0))  # 운전 중 start = 전체 분류로 전환
    assert rep[0][0] and ctx.priority == ""


# ---------------------------------------------------------------- 구역 가득·reset_zone


def test_zone_full_pauses_until_reset(cfg: f.Config) -> None:
    ctx = running(cfg)
    for i in range(3):
        ctx, _ = placed(ctx, 10 + i, t=(20 + i * 20) * 1000 * MS)
    assert ctx.slots["B"] == 3

    ctx, acts, _ = run(ctx, label(20, t=100_000 * MS))
    assert ctx.state == f.PAUSED and ctx.full_zone == "B" and not of(acts, f.SendGoal)
    assert of(acts, f.Say) and not of(acts, f.Result)

    ctx, _, rep = run(ctx, cmd("resume"))
    assert not rep[0][0] and "reset_zone" in rep[0][1]
    ctx, _, rep = run(ctx, cmd("reset_zone", "b"))
    assert rep[0][0] and ctx.slots["B"] == 0 and ctx.full_zone == ""
    ctx, acts, rep = run(ctx, cmd("resume", t=200_000 * MS))
    assert (
        rep[0][0]
        and ctx.state == f.RUNNING
        and of(acts, f.CallMove) == [f.CallMove("OBSERVE", 0, "")]
    )


def test_reset_zone_only_when_paused(cfg: f.Config) -> None:
    ctx = running(cfg)
    _, _, rep = run(ctx, cmd("reset_zone", "A"))
    assert rep == [(False, "reset_zone 은 PAUSED 에서만")]
    _, _, rep = run(ctx, cmd("stop"), cmd("reset_zone", "Z"))
    assert rep[1] == (False, "모르는 구역: Z")


# ---------------------------------------------------------------- stop·resume


def test_stop_while_grasping_cancels_and_records_stopped(cfg: f.Config) -> None:
    ctx = running(cfg)
    ctx, _, _ = run(ctx, label(5))
    ctx, acts, rep = run(ctx, cmd("stop"))
    assert rep == [(True, "stop 접수")] and ctx.state == f.PAUSED
    assert acts[:2] == [f.CallStop(), f.CancelGoal()]  # stop 이 먼저, 그다음 취소
    ctx, _, rep = run(ctx, cmd("resume"))
    assert not rep[0][0] and "응답 대기" in rep[0][1]  # goal 결과 전에는 resume 거부

    ctx, acts, _ = run(
        ctx, f.StopDone(True, "", 0), f.GoalDone(True, False, "CANCELED", 1, 9000 * MS)
    )
    (res,) = of(acts, f.Result)
    assert (res.outcome, res.reason, res.attempts, res.zone) == ("FAILED", "STOPPED", 1, "")
    assert ctx.state == f.PAUSED and ctx.box is None and not of(acts, f.CallMove)

    ctx, acts, rep = run(ctx, cmd("resume"))
    assert rep[0][0] and of(acts, f.CallMove) == [f.CallMove("OBSERVE", 0, "")]


def test_stop_race_grasped_is_not_placed(cfg: f.Config) -> None:
    ctx = running(cfg)
    ctx, acts, _ = run(ctx, label(5), cmd("stop"), f.GoalDone(True, True, "OK", 1, 9000 * MS))
    (res,) = of(acts, f.Result)
    assert (res.outcome, res.reason) == ("FAILED", "STOPPED")
    assert not [
        m for m in of(acts, f.CallMove) if m.zone != "OBSERVE"
    ]  # 정지 뒤 자동 적재·개방 없음


def test_stop_during_place(cfg: f.Config) -> None:
    ctx = running(cfg)
    ctx, _, _ = run(ctx, label(5), f.GoalDone(True, True, "OK", 2, 5000 * MS))
    ctx, acts, _ = run(ctx, cmd("stop"))
    assert of(acts, f.CallStop) and not of(acts, f.CancelGoal) and ctx.state == f.PAUSED
    ctx, acts, _ = run(ctx, f.MoveDone(False, "TIMEOUT", 8000 * MS, 9000 * MS))  # 개방은 했다
    (res,) = of(acts, f.Result)
    assert (res.outcome, res.zone, res.reason, res.attempts) == ("PLACED", "B", "STOPPED", 2)
    assert ctx.slots["B"] == 1 and ctx.state == f.PAUSED


def test_stop_failure_blocks_resume_until_stop_succeeds(cfg: f.Config) -> None:
    ctx = running(cfg)
    ctx, _, _ = run(ctx, cmd("stop"), f.StopDone(False, "TIMEOUT", 0))
    assert ctx.stop_failed and f.not_ready_items(ctx, []) == ["ROBOT"]
    _, _, rep = run(ctx, cmd("resume"))
    assert not rep[0][0] and "stop" in rep[0][1]
    ctx, acts, _ = run(ctx, cmd("stop"))
    assert of(acts, f.CallStop) and ctx.state == f.PAUSED  # PAUSED 에서도 stop 을 다시 보낸다(멱등)
    ctx, _, rep = run(ctx, f.StopDone(True, "", 0), cmd("resume"))
    assert rep[1][0] and ctx.state == f.RUNNING


def test_stop_in_idle_stays_idle(cfg: f.Config) -> None:
    ctx, acts, rep = run(f.new_ctx(cfg), cmd("stop"))
    assert ctx.state == f.IDLE and of(acts, f.CallStop) and rep[0][0]


def test_stop_during_home_then_resume(cfg: f.Config) -> None:
    ctx, _, _ = run(f.new_ctx(cfg), start(0), cmd("stop"))
    assert ctx.state == f.PAUSED and ctx.phase == f.PH_HOME
    ctx, _, _ = run(ctx, f.MoveDone(False, "STOPPED", 0, 1000 * MS))
    assert ctx.state == f.PAUSED and ctx.phase == f.PH_NONE
    ctx, _, rep = run(ctx, cmd("resume"), f.MoveDone(True, "OK", 0, 3000 * MS))
    assert rep[0][0] and ctx.state == f.RUNNING and ctx.stage_start_ns == 3000 * MS


# ---------------------------------------------------------------- 장비 실패


@pytest.mark.parametrize(
    "reason", ["GRASP_FAILED", "LOST", "OUT_OF_REACH", "STALE_INPUT", "DEVICE_ERROR"]
)
def test_grasp_failure_records_reason_and_pauses(cfg: f.Config, reason: str) -> None:
    ctx = running(cfg)
    ctx, acts, _ = run(ctx, label(5), f.GoalDone(True, False, reason, 3, 9000 * MS))
    (res,) = of(acts, f.Result)
    assert (res.outcome, res.reason, res.attempts, res.zone) == ("FAILED", reason, 3, "")
    assert ctx.state == f.PAUSED and ctx.box is None
    assert not [m for m in of(acts, f.CallMove)]  # 실패 뒤 자동 이동·개방 없음 (G0 임시 규칙)


def test_goal_rejected_is_device_error(cfg: f.Config) -> None:
    ctx = running(cfg)
    ctx, acts, _ = run(ctx, label(5), f.GoalDone(False, False, "", 0, 3000 * MS))
    (res,) = of(acts, f.Result)
    assert (res.outcome, res.reason, res.attempts) == ("FAILED", "DEVICE_ERROR", 0)
    assert ctx.state == f.PAUSED


def test_place_return_failed_counts_slot(cfg: f.Config) -> None:
    ctx = running(cfg)
    ctx, _, _ = run(ctx, label(5), f.GoalDone(True, True, "OK", 1, 5000 * MS))
    ctx, acts, _ = run(ctx, f.MoveDone(False, "RETURN_FAILED", 8000 * MS, 20000 * MS))
    (res,) = of(acts, f.Result)
    assert (res.outcome, res.zone, res.reason, res.stamp_ns) == (
        "PLACED",
        "B",
        "DEVICE_ERROR",
        8000 * MS,
    )
    assert ctx.slots["B"] == 1 and ctx.state == f.PAUSED


def test_place_fail_before_open_reuses_slot(cfg: f.Config) -> None:
    ctx = running(cfg)
    ctx, _, _ = run(ctx, label(5), f.GoalDone(True, True, "OK", 1, 5000 * MS))
    ctx, acts, _ = run(ctx, f.MoveDone(False, "GRIP_FAIL", 0, 9000 * MS))
    (res,) = of(acts, f.Result)
    assert (res.outcome, res.zone, res.reason, res.stamp_ns) == (
        "FAILED",
        "",
        "DEVICE_ERROR",
        9000 * MS,
    )
    assert ctx.slots["B"] == 0 and ctx.state == f.PAUSED
    ctx, _, _ = run(
        ctx, cmd("resume"), f.MoveDone(True, "OK", 0, 30000 * MS), label(8, t=31000 * MS)
    )
    assert ctx.box.slot == 0  # 같은 칸 재사용


def test_home_failure_pauses(cfg: f.Config) -> None:
    ctx, acts, _ = run(f.new_ctx(cfg), start(0), f.MoveDone(False, "NO_SERVICE", 0, 100 * MS))
    assert ctx.state == f.PAUSED and ctx.session_id == SID and of(acts, f.Say)


# ---------------------------------------------------------------- 명령 규칙


def test_command_rules(cfg: f.Config) -> None:
    ctx = f.new_ctx(cfg)
    assert run(ctx, cmd("resume"))[2][0] == (False, "IDLE 에서는 resume 불가")
    assert run(ctx, cmd("answer", SID + "-001|대치동"))[2][0][0] is False
    assert run(ctx, cmd("priority", "논현동"))[2][0][0] is False
    assert run(ctx, cmd("start", "B"))[2][0][0] is False
    assert run(ctx, cmd("dance"))[2][0][0] is False
    assert run(ctx, f.Command("start", "ALL", 0, ()))[2][0] == (False, "세션 ID 없음")

    paused, _, _ = run(running(cfg), cmd("stop"))
    assert run(paused, start(0))[2][0] == (False, "PAUSED 에서는 resume")
    assert run(paused, cmd("priority", "역삼동"))[2][0][0] is False


def test_new_session_resets_slots_and_ids(cfg: f.Config) -> None:
    """IDLE 에서 start 할 때만 칸·순번을 0 으로 (MC-018). PAUSED 를 지나도 세션은 유지."""
    ctx = running(cfg)
    ctx, _ = placed(ctx, 5)
    ctx, _, _ = run(
        ctx,
        cmd("stop"),
        f.StopDone(True, "", 0),
        cmd("resume"),
        f.MoveDone(True, "OK", 0, 30000 * MS),
    )
    assert ctx.session_id == SID and ctx.slots["B"] == 1 and ctx.seq == 1


def test_every_box_id_gets_one_result(cfg: f.Config) -> None:
    """발급한 box_id 마다 SortResult 정확히 1건 (DB 유일키)."""
    ctx = running(cfg)
    events = [
        label(1),
        f.GoalDone(True, True, "OK", 1, 5000 * MS),
        f.MoveDone(True, "OK", 8000 * MS, 9000 * MS),
        label(2, t=10000 * MS),
        f.GoalDone(True, False, "LOST", 1, 12000 * MS),
        cmd("resume"),
        f.MoveDone(True, "OK", 0, 13000 * MS),
        label(3, t=14000 * MS),
        cmd("stop"),
        f.GoalDone(True, False, "CANCELED", 1, 15000 * MS),
    ]
    ctx, acts, _ = run(ctx, *events)
    ids = [r.box_id for r in of(acts, f.Result)]
    assert ids == [f.make_box_id(SID, i) for i in (1, 2, 3)] and ctx.seq == 3
    assert all(r.stamp_ns > 0 for r in of(acts, f.Result))
