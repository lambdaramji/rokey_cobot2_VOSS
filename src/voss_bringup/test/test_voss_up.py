"""scripts/voss_up.py (T22 #31) — ros2·docker 를 부르지 않고 시험한다.

- 계획: host_plan 에서 만든 단계 순서·인자(런북 T1~T8), 옵션, 로봇 IP 를 적지 않음
- 거부: --dry 도메인 30, 필요한 환경 변수, --print 는 아무것도 띄우지 않음
- 실행 기계: 가짜 단계(python3 -c)로 준비 줄 대기·실패 줄·시간 초과·먼저 끝남·다시 하면 건너뜀·역순 종료·운전 중 종료 거부
"""

import importlib.util
import re
import sys
from pathlib import Path

import pytest
from launch.launch_description_sources.python_launch_file_utilities import (
    load_python_launch_file_as_module,
)

PKG = Path(__file__).resolve().parents[1]
REPO = PKG.parents[1]
spec = importlib.util.spec_from_file_location("voss_up", REPO / "scripts/voss_up.py")
vu = importlib.util.module_from_spec(spec)
sys.modules["voss_up"] = vu  # dataclass 가 모듈을 찾을 수 있게
spec.loader.exec_module(vu)
HOST = load_python_launch_file_as_module(str(PKG / "launch/voss_host.launch.py"))
ENV = {"VOSS_CONFIG_DIR": "/cfg", "VOSS_ROBOT_HOST": "x", "VOSS_DB_LOGGER_PASSWORD": "x"}


def plan(**kw) -> list:
    return vu.real_plan(vu.Opts(**kw), dict(ENV), HOST)


def by_id(steps) -> dict:
    return {s.id: s for s in steps}


# ---------------------------------------------------------------- 계획


def test_real_plan_follows_runbook_order_and_args() -> None:
    steps = plan()
    assert [s.id for s in steps] == [
        "T1",
        "T2",
        "T3",
        "T4",
        "T5",
        "T7",
        "T8",
        "V1",
        "V2",
        "V3",
        "H1",
    ]
    s = by_id(steps)
    assert "${VOSS_ROBOT_HOST}" in s["T1"].cmd and s["T1"].check  # IP 는 환경 변수로만
    t2 = s["T2"].cmd
    assert (
        "dry_run:=false" in t2
        and "pose_source:=joint_states" in t2
        and "config:=/cfg/voss_config.yaml" in t2
    )
    assert s["T2"].fail == r"robot_gateway started: dry_run"  # 실기를 원했는데 가짜로 뜨면 실패
    t3 = s["T3"].cmd
    for part in ("-r __node:=camera", "-p enable_depth:=false", "-p rgb_camera.exposure:=60",
                 "-p rgb_camera.white_balance:=4600.0", "-p rgb_camera.color_profile:=1920x1080x30"):  # fmt: skip
        assert part in t3
    assert s["T5"].cmd.endswith("docker compose -f compose.yml up")
    assert "params:=/cfg/belt_servo_real.yaml" in s["T7"].cmd and s["T7"].fail == "READY 거부"
    assert ("T5", r"판독 준비 완료", 30.0) in s[
        "T8"
    ].after  # label_reader 는 zone_map(T8) 뒤에 준비
    assert s["T2"].after[0][1] == r"이동 높이 미리 계산"  # #153 미리 계산 끝 → T7·T8
    assert s["T4"].needs_env == ("VOSS_DB_LOGGER_PASSWORD",)


def test_plan_options() -> None:
    s = by_id(plan(vision="host", ocr_python="/venv/bin/python"))
    assert (
        s["T5"].cmd.startswith("ros2 launch voss_bringup voss_vision.launch.py")
        and "python:=/venv/bin/python" in s["T5"].cmd
    )
    assert "compose.gpu.yml" in by_id(plan(gpu=True))["T5"].cmd
    assert "T5" not in by_id(plan(vision="skip")) and not by_id(plan(vision="skip"))["T8"].after
    ids = [x.id for x in plan(voice=False, hmi=False, skip={"T1"})]
    assert ids == ["T2", "T3", "T4", "T5", "T7", "T8"]
    assert "V3" not in by_id(plan(voice_mode="text"))  # text 는 stdin 이 필요해 따로
    assert [x.id for x in plan(only={"T7"})] == ["T7"]
    assert (
        "overrides:=/k/belt_servo_kp0.yaml"
        in by_id(plan(servo_overrides="/k/belt_servo_kp0.yaml"))["T7"].cmd
    )


def test_each_ready_rule_matches_real_log_line() -> None:
    """준비·실패 정규식이 코드가 실제로 찍는 줄과 맞는지 (문구가 바뀌면 여기서 잡는다)."""
    lines = {
        "T2": "[robot_gateway-1] [INFO] [1] [robot_gateway]: robot_gateway started: real, pose 50 Hz, servo watchdog 0.2 s",
        "T3": "[INFO] [1] [camera]: RealSense Node Is Up!",
        "T4": "[INFO] [1] [sort_logger]: DB 연결 성공",
        "T5": "label_reader-2  | [INFO] [1] [label_reader]: OCR 엔진 준비 cpu 12.3 s",
        "T7": "[belt_servo-1] [INFO] [1] [belt_servo]: READY",
        "T8": "[sort_manager-1] [INFO] [1] [sort_manager]: voss_config /c/voss_config.yaml version 1 sha256 abcdef123456, 구역 칸",
        "V1": "[INFO] [1] [speech_out]: speech_out ready: OpenAI TTS",
        "V2": "[INFO] [1] [intent_parser]: intent_parser ready (zone_map 대기 중)",
        "V3": "[INFO] [1] [voice_listener]: voice_listener: mic 모드 — '헬로, 로키' 뒤에 말하세요",
        "H1": "[INFO] [1] [hmi_bridge]: MQTT connected",
    }  # fmt: skip
    for sid, s in by_id(plan()).items():
        if sid in lines:
            assert all(re.search(rx, lines[sid], re.M) for rx in s.ready), sid
    refused = (
        "[belt_servo-1] [WARN] [1] [belt_servo]: READY 거부: missing=[belt.speed_cmps] invalid=[]"
    )
    t7 = by_id(plan())["T7"]
    assert re.search(t7.fail, refused) and not re.search(t7.ready[0], refused, re.M)
    assert not re.search(by_id(plan())["T5"].ready[0], "OCR 엔진 준비 실패 (cpu): boom")


def test_dry_plan_and_guards() -> None:
    with pytest.raises(SystemExit, match="playback"):
        vu.dry_plan(vu.Opts(mode="dry"))
    o = vu.Opts(mode="dry", playback="/bag")
    (d,) = vu.dry_plan(o)
    assert "voss_dry_run.launch.py playback:=/bag servo:=mock" in d.cmd and len(d.ready) == 3
    assert any("도메인" in w or "30" in w for w in vu.guard(o, [d], {"ROS_DOMAIN_ID": "30"}))
    assert vu.guard(o, [d], {"ROS_DOMAIN_ID": "77"}) == []
    real = vu.Opts()
    why = vu.guard(real, plan(), {"VOSS_CONFIG_DIR": "/cfg"})
    assert any("VOSS_ROBOT_HOST" in w for w in why) and any(
        "VOSS_DB_LOGGER_PASSWORD" in w for w in why
    )
    compose_missing = not (REPO / "docker/vision/compose.yml").exists()
    assert any(w.startswith("T5") for w in vu.guard(real, plan(), ENV)) == compose_missing


def test_print_and_refusals_start_nothing(tmp_path, monkeypatch, capsys) -> None:
    def boom(*_a, **_k):
        raise AssertionError("띄우면 안 된다")

    monkeypatch.setattr(vu.Runner, "start", boom)
    assert vu.main(["up", "--real", "--print", "--run-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "아무것도 띄우지 않았다" in out and "${VOSS_ROBOT_HOST}" in out
    assert not re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", out)  # IP 가 출력에 없다
    monkeypatch.setenv("ROS_DOMAIN_ID", "30")
    assert vu.main(["up", "--dry", "--playback", "/b", "--run-dir", str(tmp_path)]) == 2
    monkeypatch.delenv("VOSS_ROBOT_HOST", raising=False)
    monkeypatch.setenv("ROS_DOMAIN_ID", "77")
    assert (
        vu.main(["up", "--real", "--run-dir", str(tmp_path)]) == 2
    )  # 환경 변수 없음 → 확인 질문 전에 거부
    assert not (tmp_path / "state.json").exists()


# ---------------------------------------------------------------- 실행 기계 (가짜 단계)


def fake(sid: str, lines: list[str], hold_s: float = 30.0, **kw) -> "vu.Step":
    code = "import time\n" + "".join(
        f"print({ln!r}, flush=True)\ntime.sleep(0.2)\n" for ln in lines
    )
    code += f"time.sleep({hold_s})\n"
    kw.setdefault("timeout_s", 5.0)
    return vu.Step(sid, f"가짜 {sid}", f"python3 -c {vu.shlex.quote(code)}", **kw)


@pytest.fixture
def runner(tmp_path):
    out: list[str] = []
    r = vu.Runner(tmp_path, out=out.append)
    r.lines = out
    yield r
    for sid in list(r.state["steps"]):
        r.stop(sid, grace_s=2.0)


def test_up_waits_stops_failed_step_and_resumes(runner) -> None:
    s1 = fake("S1", ["시작", "준비 완료"], ready=("준비 완료",))
    bad = fake("S2", ["READY 거부: missing=[x]"], ready=(r"READY$",), fail="READY 거부")
    assert vu.up([s1, bad], runner) == 1
    assert runner.running("S1") and "S2" not in runner.state["steps"]  # 실패한 단계만 끈다
    assert any("S2 를 고친 뒤" in x for x in runner.lines)
    good = fake("S2", ["READY"], ready=(r"READY$",), fail="READY 거부")
    runner.lines.clear()
    assert vu.up([s1, good], runner) == 0
    assert "이미 떠 있음" in runner.lines[0] and runner.running("S2")
    runner.lines.clear()
    assert vu.down(runner, state_reader=lambda: "PAUSED") == 0
    assert runner.lines == ["[S2] 끔", "[S1] 끔"]  # 기동의 역순
    assert not runner.running("S1") and not runner.running("S2")


def test_timeout_early_exit_and_check(runner) -> None:
    ok, why = (lambda s: (runner.start(s), runner.wait(s))[1])(
        fake("E", ["안녕"], hold_s=0, ready=("준비",))
    )
    assert not ok and "프로세스가 끝남" in why
    ok, why = (lambda s: (runner.start(s), runner.wait(s))[1])(
        fake("W", ["..."], ready=("준비",), timeout_s=1.0)
    )
    assert not ok and "준비 줄 없음" in why
    ok, why = (lambda s: (runner.start(s), runner.wait(s))[1])(fake("C", [], check="true"))
    assert ok and why == "check 성공"


def test_after_check_warns_only(runner) -> None:
    s = fake("A", ["준비"], ready=("준비",), after=(("A", "미리 계산", 1.0), ("Z", "판독", 1.0)))
    assert vu.up([s], runner) == 0
    assert any("⚠ A 로그 '미리 계산'" in x for x in runner.lines)
    assert any("Z 가 떠 있지 않아" in x for x in runner.lines)


def test_down_refuses_while_running(runner) -> None:
    t8 = fake("T8", ["voss_config x sha256 y"], ready=("sha256",))
    assert vu.up([t8], runner) == 0
    assert vu.down(runner, state_reader=lambda: "RUNNING") == 1 and runner.running("T8")
    assert "먼저 stop" in runner.lines[-1]
    assert vu.down(runner, force=True, state_reader=lambda: "RUNNING") == 0 and not runner.running(
        "T8"
    )
