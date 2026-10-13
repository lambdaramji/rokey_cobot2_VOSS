#!/usr/bin/env python3
"""VOSS 한 번에 기동·종료 (T22 #31) — g0-runbook 2절 T1~T8 + 음성 3노드 + hmi_bridge 를 순서대로 띄우고,
단계마다 "준비됨" 로그를 기다린 뒤 다음으로 간다. 실패하면 그 단계에서 멈춘다(이미 뜬 단계는 그대로 — 고친 뒤
같은 명령을 다시 하면 떠 있는 단계는 건너뛰고 실패한 단계부터).

**실행은 사람이 한다. --real 은 로봇이 움직일 수 있다 — 비상정지 옆에서(CLAUDE.md 규칙 6).**
운전 시작(start)은 이 스크립트가 보내지 않는다. 기동은 로봇을 움직이지 않고 IDLE 로 끝난다(TR-VOICE-12).

  scripts/voss_up.sh --real --print            # 계획만 출력 (아무것도 띄우지 않는다)
  scripts/voss_up.sh --real                     # 실기 (확인 질문에 yes). T1 은 VOSS_ROBOT_HOST 가 필요
  scripts/voss_up.sh --real --skip T1           # 두산 브링업은 이미 떠 있음(학민)
  scripts/voss_up.sh --dry --playback <bag>     # 로봇 없이 소프트웨어 전체 (도메인 30 거부)
  scripts/voss_down.sh                          # 역순 종료 (IDLE·PAUSED 에서만, belt_servo 를 gateway 보다 먼저)
  python3 scripts/voss_up.py status | logs T7

단계 명령의 인자는 voss_bringup/launch/voss_host.launch.py 의 host_plan() 에서 가져온다(값을 두 곳에 적지 않는다).
로그·상태는 레포 밖 `--run-dir`(기본 ~/voss_data/run) — 커밋하지 않는다(규칙 8). 로봇 컨트롤러 IP 는 환경 변수로만.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOST_LAUNCH = REPO / "src/voss_bringup/launch/voss_host.launch.py"
VISION_COMPOSE = REPO / "docker/vision"
OPERATING_DOMAIN = "30"
ACTIVE = ("RUNNING", "PICKING", "RECHECK", "ASKING", "PALLETIZING")  # 끄기 전에 멈춰야 하는 상태
CHILD_ENV = {
    "PYTHONUNBUFFERED": "1",
    "RCUTILS_COLORIZED_OUTPUT": "0",
    "RCUTILS_LOGGING_BUFFERED_STREAM": "0",
}


@dataclass(frozen=True)
class Step:
    """기동 단계 하나. ready 의 정규식이 모두 로그에 나오면(또는 check 명령이 성공하면) 준비."""

    id: str
    title: str
    cmd: str  # bash 한 줄
    ready: tuple[str, ...] = ()
    fail: str = ""  # 이 줄이 나오면 실패
    timeout_s: float = 30.0
    check: str = ""  # 로그 대신 2 s 마다 돌려 볼 명령(성공 = 준비)
    after: tuple[tuple[str, str, float], ...] = ()  # (다른 단계 id, 정규식, 초) — 못 보면 경고만
    needs_env: tuple[str, ...] = ()


@dataclass
class Opts:
    mode: str = "real"  # real | dry
    skip: set[str] = field(default_factory=set)
    only: set[str] = field(default_factory=set)
    vision: str = "container"  # container | host | skip
    gpu: bool = False
    voice: bool = True
    voice_mode: str = "mic"
    hmi: bool = True
    config_dir: str = ""
    servo_overrides: str = ""
    playback: str = ""
    servo: str = "mock"  # dry: mock | sim
    ocr_python: str = ""


# ---------------------------------------------------------------- 계획 (ROS 를 띄우지 않는다, pytest 대상)


def _q(v) -> str:
    """ros2 인자 값 — bool 은 true/false, float 는 소수점 유지(4600.0 = double)."""
    if isinstance(v, bool):
        return "true" if v else "false"
    return shlex.quote(str(v))


def launch_cmd(pkg: str, target: str, args: dict) -> str:
    kv = " ".join(f"{k}:={_q(v)}" for k, v in args.items() if v != "")
    return f"ros2 launch {pkg} {target} {kv}".rstrip()


def run_cmd(pkg: str, exe: str, name: str, params: dict | None, ns: str = "") -> str:
    out = f"ros2 run {pkg} {exe} --ros-args"
    if ns:  # 카메라: -r __ns:=/ 가 없으면 /camera/camera/color/image_raw 로 나가 box_tracker 가 영상 0 (10/13)
        out += f" -r __ns:={ns}"
    if name:
        out += f" -r __node:={name}"
    for k, v in (params or {}).items():
        out += f" -p {k}:={_q(v)}"
    return out


# host_plan 의 target → (id, 제목, 준비 줄, 실패 줄, 제한 s)
READY = {
    "robot_gateway.launch.py": ("T2", "robot_gateway", (r"robot_gateway started: real",), r"robot_gateway started: dry_run", 60),
    "realsense2_camera_node": ("T3", "카메라", (r"RealSense Node Is Up",), "", 60),
    "sort_logger": ("T4", "sort_logger", (r"DB 연결 성공",), "", 30),
    "voss_vision.launch.py": ("T5", "비전(호스트)", (r"OCR 엔진 준비 \S+ [0-9.]+ s",), r"OCR 엔진 준비 실패", 300),
    "belt_servo.launch.py": ("T7", "belt_servo", (r"\[belt_servo\]: READY$",), r"READY 거부", 60),
    "sort_manager.launch.py": ("T8", "sort_manager", (r"voss_config .* sha256",), "", 30),
    "speech_out": ("V1", "speech_out", (r"speech_out ready",), "", 30),
    "intent_parser": ("V2", "intent_parser", (r"intent_parser ready",), "", 30),
    "voice_listener": ("V3", "voice_listener", (r"voice_listener: (mic|text) 모드",), "", 60),
    "hmi_bridge": ("H1", "hmi_bridge", (r"MQTT connected",), "", 30),
}  # fmt: skip


def load_host_module():
    try:
        from launch.launch_description_sources.python_launch_file_utilities import (
            load_python_launch_file_as_module,
        )
    except ImportError as e:  # pragma: no cover - ROS 가 source 안 됨
        raise SystemExit("ROS 환경을 먼저 source 한다 (launch 모듈 없음)") from e
    return load_python_launch_file_as_module(str(HOST_LAUNCH))


def real_plan(o: Opts, env: dict[str, str], host=None) -> list[Step]:
    host = host or load_host_module()
    a = {n: d for n, d, _ in host.ARGS}
    # with_gateway=true: voss_host 단독 실기는 gateway(T2)를 런북대로 따로 띄우지만(1030f28), 여기서는 T2 가 자기 터미널의
    # 단계라 No-Go 줄·이동 높이 계산을 기다린 뒤 다음으로 가고, 내릴 때도 belt_servo 다음에 따로 내린다(런북 6·7절과 같다)
    a.update(dry_run="false", with_gateway="true", with_vision="true" if o.vision == "host" else "false",
             with_voice=_q(o.voice), with_hmi=_q(o.hmi), voice_mode=o.voice_mode,
             config_dir=o.config_dir or env.get("VOSS_CONFIG_DIR") or a["config_dir"],
             servo_overrides=o.servo_overrides, ocr_python=o.ocr_python or a["ocr_python"])  # fmt: skip
    steps = [
        Step(
            "T1",
            "두산 브링업",
            "ros2 launch m0609_rg2_bringup bringup.launch.py mode:=real host:=${VOSS_ROBOT_HOST} port:=12345 model:=m0609",
            check="ros2 service list | grep -q dsr_controller2/aux_control/get_current_tool_flange_posx",
            timeout_s=120,
            needs_env=("VOSS_ROBOT_HOST",),
        )
    ]
    for s in host.host_plan(a):
        sid, title, ready, fail, tmo = READY[s.target]
        if s.kind == "include":
            cmd = launch_cmd(s.pkg, s.target, s.args or {})
        else:
            cmd = run_cmd(s.pkg, s.target, s.name, s.args, getattr(s, "namespace", ""))
        extra: dict = {}
        if (
            sid == "T2"
        ):  # #153: 관측 자세 칸 미리 계산(BUSY PREWARM)이 끝난 뒤 T7·T8 (빌드가 #153 전이면 줄이 없다)
            extra["after"] = (("T2", r"이동 높이 미리 계산", 90.0),)
        if sid == "T4":
            extra["needs_env"] = ("VOSS_DB_LOGGER_PASSWORD",)
        if (
            sid == "T8" and o.vision != "skip"
        ):  # label_reader 는 zone_map(T8) 을 받아야 판독 준비 완료
            extra["after"] = (("T5", r"판독 준비 완료", 30.0),)
        if sid == "T7" and o.vision == "container":
            steps.append(vision_container_step(o))
        steps.append(Step(sid, title, cmd, ready, fail, float(tmo), **extra))
    return [s for s in steps if _wanted(s.id, o)]


def vision_container_step(o: Opts) -> Step:
    files = "-f compose.yml" + (" -f compose.gpu.yml" if o.gpu else "")
    return Step(
        "T5",
        "비전 컨테이너(box_tracker·label_reader)",
        f"cd {shlex.quote(str(VISION_COMPOSE))} && docker compose {files} up",
        (r"OCR 엔진 준비 \S+ [0-9.]+ s",),
        r"OCR 엔진 준비 실패",
        300.0,
    )


def dry_plan(o: Opts) -> list[Step]:
    if not o.playback:
        raise SystemExit("--dry 는 --playback <bag 폴더> 가 필요하다")
    args = {"playback": o.playback, "servo": o.servo, "ocr_python": o.ocr_python}
    return [
        Step(
            "D1",
            "dry_run 전체(가짜 로봇·녹화 재생)",
            launch_cmd("voss_bringup", "voss_dry_run.launch.py", args),
            (r"robot_gateway started: dry_run", r"voss_config .* sha256", r"판독 준비 완료"),
            r"robot_gateway started: real|voss_dry_run 거부",
            300.0,
        )
    ]


def _wanted(sid: str, o: Opts) -> bool:
    if o.only:
        return sid in o.only
    return sid not in o.skip


def guard(o: Opts, plan: list[Step], env: dict[str, str]) -> list[str]:
    """띄우기 전 거부 사유 (없으면 [])."""
    why = []
    domain = env.get("ROS_DOMAIN_ID", "0").strip()
    if o.mode == "dry" and domain == OPERATING_DOMAIN:
        why.append(
            "--dry 거부: ROS_DOMAIN_ID 30(운용 도메인) — export ROS_DOMAIN_ID=77 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST"
        )
    for s in plan:
        for k in s.needs_env:
            if not env.get(k):
                why.append(f"{s.id} {s.title}: 환경 변수 {k} 가 없다 (또는 --skip {s.id})")
    if (
        any(s.id == "T5" and "docker compose" in s.cmd for s in plan)
        and not (VISION_COMPOSE / "compose.yml").exists()
    ):
        why.append(
            "T5: docker/vision/compose.yml 없음(#159 머지 전) — --vision host 또는 --skip T5"
        )
    return why


def print_plan(plan: list[Step], o: Opts) -> None:
    print(f"# voss_up 계획 ({'실기' if o.mode == 'real' else 'dry_run'}) — 아무것도 띄우지 않았다")
    for s in plan:
        wait = f"check: {s.check}" if s.check else "준비: " + " · ".join(s.ready)
        print(f"[{s.id}] {s.title}  (≤ {s.timeout_s:.0f} s)\n    {s.cmd}\n    {wait}")
        if s.fail:
            print(f"    실패: {s.fail}")
        for sid, rx, t in s.after:
            print(f"    뒤에 확인({sid} 로그, {t:.0f} s, 못 보면 경고): {rx}")


# ---------------------------------------------------------------- 실행


def alive(pid: int) -> bool:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    return stat.rsplit(")", 1)[1].split()[0] != "Z"


class Runner:
    """단계마다 새 세션(프로세스 그룹)으로 띄우고 로그 파일에 쓴다. 상태는 run_dir/state.json."""

    def __init__(self, run_dir: Path, env_file: str = "", out=print) -> None:
        self.run_dir = Path(run_dir).expanduser()
        self.env_file = env_file
        self.out = out
        self.state_path = self.run_dir / "state.json"
        self.state = self._load()
        self.procs: dict[str, subprocess.Popen] = {}

    def _load(self) -> dict:
        try:
            return json.loads(self.state_path.read_text())
        except (OSError, ValueError):
            return {"steps": {}}

    def _save(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self.state, ensure_ascii=False, indent=1))

    def running(self, sid: str) -> bool:
        rec = self.state["steps"].get(sid)
        return bool(rec) and alive(rec["pid"])

    def start(self, s: Step) -> Path:
        logs = self.run_dir / datetime.now().strftime("%m%d")
        logs.mkdir(parents=True, exist_ok=True)
        log = logs / f"{s.id}_{datetime.now():%H%M%S}.log"
        src = f"source {shlex.quote(self.env_file)} >/dev/null && " if self.env_file else ""
        fh = open(log, "w")  # noqa: SIM115 - 자식이 쓰는 동안 열어 둔다
        # exec 를 붙이지 않는다(cd … && docker compose … 같은 묶음 명령). 끌 때는 프로세스 그룹째 보낸다
        p = subprocess.Popen(["bash", "-c", f"{src}{s.cmd}"], stdout=fh, stderr=subprocess.STDOUT,
                             start_new_session=True, env={**os.environ, **CHILD_ENV})  # fmt: skip
        fh.close()
        self.procs[s.id] = p
        self.state["steps"][s.id] = {"pid": p.pid, "log": str(log), "title": s.title, "cmd": s.cmd}
        self.state.setdefault("order", [])
        if s.id in self.state["order"]:
            self.state["order"].remove(s.id)
        self.state["order"].append(s.id)
        self._save()
        return log

    def log_text(self, sid: str) -> str:
        rec = self.state["steps"].get(sid)
        try:
            return Path(rec["log"]).read_text(errors="replace") if rec else ""
        except OSError:
            return ""

    def wait(self, s: Step, poll_s: float = 0.5) -> tuple[bool, str]:
        """준비·실패·시간 초과·프로세스 끝남."""
        t_end = time.monotonic() + s.timeout_s
        next_check = 0.0
        pid = self.state["steps"][s.id]["pid"]
        while time.monotonic() < t_end:
            text = self.log_text(s.id)
            if s.fail and re.search(s.fail, text, re.M):
                return False, f"실패 줄: {re.search(s.fail, text, re.M).group(0)}"
            if s.check:
                if time.monotonic() >= next_check:
                    next_check = time.monotonic() + 2.0
                    if subprocess.run(["bash", "-c", s.check], capture_output=True).returncode == 0:
                        return True, "check 성공"
            elif s.ready and all(re.search(rx, text, re.M) for rx in s.ready):
                return True, "준비 줄 확인"
            if not alive(pid):
                return False, "준비 전에 프로세스가 끝남"
            time.sleep(poll_s)
        return False, f"{s.timeout_s:.0f} s 안에 준비 줄 없음"

    def stop(self, sid: str, grace_s: float = 15.0) -> bool:
        rec = self.state["steps"].get(sid)
        if not rec:
            return True
        pid = rec["pid"]
        for sig, wait_s in ((signal.SIGINT, grace_s), (signal.SIGTERM, 5.0), (signal.SIGKILL, 2.0)):
            if not alive(pid):
                break
            try:
                os.killpg(pid, sig)
            except ProcessLookupError:
                break
            t_end = time.monotonic() + wait_s
            while alive(pid) and time.monotonic() < t_end:
                if sid in self.procs:
                    self.procs[sid].poll()  # 이 프로세스가 띄운 자식이면 좀비를 거둔다
                time.sleep(0.2)
        if sid in self.procs:
            self.procs[sid].poll()
        ok = not alive(pid)
        if ok:
            self.state["steps"].pop(sid, None)
            self.state["order"] = [x for x in self.state.get("order", []) if x != sid]
            self._save()
        return ok

    def tail(self, sid: str, n: int = 15) -> str:
        return "\n".join(self.log_text(sid).splitlines()[-n:])


def up(plan: list[Step], r: Runner) -> int:
    for s in plan:
        if r.running(s.id):
            r.out(f"[{s.id}] {s.title}: 이미 떠 있음 — 건너뜀")
            continue
        log = r.start(s)
        r.out(f"[{s.id}] {s.title}: 기동 … (로그 {log})")
        ok, why = r.wait(s)
        if not ok:
            r.out(f"[{s.id}] {s.title}: ✗ {why}\n--- 로그 끝 ---\n{r.tail(s.id)}\n---")
            r.stop(s.id)
            r.out(
                f"멈춤: {s.id} 를 고친 뒤 같은 명령을 다시 하면 떠 있는 단계는 건너뛰고 {s.id} 부터 한다"
            )
            return 1
        r.out(f"[{s.id}] {s.title}: ✓ {why}")
        for sid, rx, t in s.after:
            if not r.running(sid):
                r.out(f"    ⚠ {sid} 가 떠 있지 않아 '{rx}' 확인을 건너뜀")
                continue
            t_end = time.monotonic() + t
            while time.monotonic() < t_end and not re.search(rx, r.log_text(sid), re.M):
                time.sleep(0.5)
            seen = re.search(rx, r.log_text(sid), re.M)
            r.out(
                f"    {'✓' if seen else '⚠'} {sid} 로그 '{rx}' {'확인' if seen else f'{t:.0f} s 안에 없음 — 확인 필요'}"
            )
    r.out("기동 끝 — IDLE. 운전 시작은 사람이 따로(비상정지 옆에서): "
          "ros2 service call /voss/sort/command voss_msgs/srv/Command \"{command: start}\"")  # fmt: skip
    return 0


def read_sort_state(timeout_s: float = 4.0) -> str:
    """/voss/sort/state 한 번 읽기 (읽기만 한다). 못 읽으면 ""."""
    try:
        p = subprocess.run(["ros2", "topic", "echo", "--once", "/voss/sort/state"],
                           capture_output=True, text=True, timeout=timeout_s)  # fmt: skip
    except (OSError, subprocess.TimeoutExpired):
        return ""
    m = re.search(r"^state:\s*'?(\w+)", p.stdout, re.M)
    return m.group(1) if m else ""


def down(
    r: Runner, force: bool = False, keep: set[str] | None = None, state_reader=read_sort_state
) -> int:
    order = [x for x in r.state.get("order", []) if r.running(x)]
    if not order:
        r.out("띄운 단계가 없다")
        return 0
    state = state_reader() if "T8" in order or "D1" in order else ""
    if state in ACTIVE and not force:
        r.out(
            f"거부: sort_manager 가 {state} — 먼저 stop 으로 멈추고(PAUSED) 벨트 12 V 를 끈 뒤 다시 (TR-VOICE-14)"
        )
        return 1
    rc = 0
    for sid in reversed(order):  # 기동의 역순 = T8 → T7(belt_servo) → … → T2(gateway) → T1
        if keep and sid in keep:
            r.out(f"[{sid}] 남겨 둠")
            continue
        ok = r.stop(sid)
        r.out(f"[{sid}] {'끔' if ok else '✗ 안 꺼짐 — 직접 확인'}")
        rc |= 0 if ok else 1
    return rc


def effective_env(env_file: str) -> dict[str, str]:
    """env 파일을 source 한 뒤의 환경 (도메인·VOSS_CONFIG_DIR 판단용)."""
    if not env_file:
        return dict(os.environ)
    p = subprocess.run(["bash", "-c", f"source {shlex.quote(env_file)} >/dev/null 2>&1; env -0"],
                       capture_output=True)  # fmt: skip
    out = {}
    for item in p.stdout.split(b"\0"):
        k, _, v = item.decode(errors="replace").partition("=")
        if k:
            out[k] = v
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    pu = sub.add_parser("up", help="기동")
    g = pu.add_mutually_exclusive_group()
    g.add_argument(
        "--real",
        dest="mode",
        action="store_const",
        const="real",
        help="실기(로봇이 움직일 수 있다)",
    )
    g.add_argument(
        "--dry", dest="mode", action="store_const", const="dry", help="로봇 없이 녹화 재생"
    )
    pu.add_argument("--print", action="store_true", help="계획만 출력하고 아무것도 띄우지 않는다")
    pu.add_argument(
        "--yes",
        action="store_true",
        help="실기 확인 질문을 건너뜀 (voss_launcher 가 음성으로 확인했을 때만)",
    )
    pu.add_argument("--skip", default="", help="건너뛸 단계 (예 T1,V3)")
    pu.add_argument("--only", default="", help="이 단계만")
    pu.add_argument("--vision", choices=("container", "host", "skip"), default="container")
    pu.add_argument("--gpu", action="store_true", help="비전 컨테이너 GPU(compose.gpu.yml)")
    pu.add_argument("--no-voice", action="store_true")
    pu.add_argument("--voice-mode", choices=("mic", "text"), default="mic")
    pu.add_argument("--no-hmi", action="store_true")
    pu.add_argument("--config-dir", default="")
    pu.add_argument("--servo-overrides", default="", help="belt_servo 덮어쓸 YAML (첫 실기 kp0 등)")
    pu.add_argument("--ocr-python", default="")
    pu.add_argument("--playback", default="", help="--dry: box_tracker 녹화 bag 폴더")
    pu.add_argument(
        "--servo", choices=("mock", "sim"), default="mock", help="--dry: TrackAndGrasp 대역"
    )
    for p in (
        pu,
        sub.add_parser("down", help="역순 종료"),
        sub.add_parser("status"),
        sub.add_parser("logs"),
    ):
        p.add_argument("--run-dir", default=os.path.expanduser("~/voss_data/run"))
        p.add_argument(
            "--env", default="", help="단계마다 source 할 환경 파일 (실기 기본 ~/voss_g0_env.sh)"
        )
    pd = sub.choices["down"]
    pd.add_argument("--force", action="store_true", help="운전 중이어도 끈다 (비상 때만)")
    pd.add_argument("--keep", default="", help="남겨 둘 단계 (예 T1)")
    sub.choices["logs"].add_argument("step")
    a = ap.parse_args(argv)

    if a.cmd == "up":
        mode = a.mode or "real"
        env_file = a.env or (
            os.path.expanduser("~/voss_g0_env.sh")
            if mode == "real" and Path("~/voss_g0_env.sh").expanduser().exists()
            else ""
        )
        env = effective_env(env_file)
        o = Opts(mode=mode, skip=set(filter(None, a.skip.split(","))), only=set(filter(None, a.only.split(","))),
                 vision=a.vision, gpu=a.gpu, voice=not a.no_voice, voice_mode=a.voice_mode, hmi=not a.no_hmi,
                 config_dir=a.config_dir, servo_overrides=a.servo_overrides, playback=a.playback,
                 servo=a.servo, ocr_python=a.ocr_python)  # fmt: skip
        plan = real_plan(o, env) if mode == "real" else dry_plan(o)
        if a.print:
            print_plan(plan, o)
            return 0
        why = guard(o, plan, env)
        if why:
            print("\n".join(why), file=sys.stderr)
            return 2
        if mode == "real" and not a.yes:
            print("실기 기동: 로봇·RG2 가 연결되고 움직일 수 있는 상태가 된다(운전 시작은 따로).")
            if (
                input("비상정지 담당이 버튼 앞에 있고 작업 영역이 비었으면 yes: ").strip().lower()
                != "yes"
            ):
                print("취소")
                return 3
        return up(plan, Runner(Path(a.run_dir), env_file))
    r = Runner(Path(a.run_dir), a.env)
    if a.cmd == "down":
        return down(r, force=a.force, keep=set(filter(None, a.keep.split(","))))
    if a.cmd == "status":
        for sid in r.state.get("order", []):
            rec = r.state["steps"][sid]
            print(
                f"[{sid}] {rec['title']}: {'떠 있음' if alive(rec['pid']) else '꺼짐'}  pid {rec['pid']}  {rec['log']}"
            )
        return 0
    print(r.tail(a.step, 50))
    return 0


if __name__ == "__main__":
    sys.exit(main())
