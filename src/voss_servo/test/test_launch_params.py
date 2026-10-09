"""launch_params.py 시험 (ROS 없이) — design/U3-dd.md 8절 T-L1~T-L13."""

import hashlib
from pathlib import Path

import pytest
import yaml
from voss_servo.params import check_params

from voss_servo import launch_params as lp

PKG = Path(__file__).resolve().parents[1]  # src/voss_servo
REPO = PKG.parents[1]  # 레포 루트
BASE_YAML = PKG / "config" / "belt_servo.yaml"
EXAMPLE_YAML = PKG / "config" / "belt_servo_real.yaml.example"
SIM_YAML = PKG / "config" / "belt_servo_sim.yaml"
VOSS_CONFIG = REPO / "config" / "voss_config.yaml"
# U5 PR #131 이 belt_servo.yaml·PARAM_SPECS 에 더하는 필수 키. example·sim 에 미리 넣었다 → U3·U5 어느 쪽이 먼저
# 머지돼도 T-L12 와 sim READY 가 깨지지 않는다. #131 머지 뒤에는 base 가 이 키를 가지므로 지워도 된다.
U5_PENDING_KEYS = {"grasp.close_time_max_s", "grasp.room_margin_mm", "gripper_timeout_s"}


def write_params(tmp_path: Path, name: str, body: dict) -> Path:
    """belt_servo: ros__parameters: 아래에 body 를 넣은 YAML 파일을 만든다."""
    path = tmp_path / name
    path.write_text(yaml.safe_dump({"belt_servo": {"ros__parameters": body}}), encoding="utf-8")
    return path


def write_config(tmp_path: Path, body: dict) -> Path:
    """가짜 voss_config.yaml 을 만든다."""
    path = tmp_path / "voss_config.yaml"
    path.write_text(yaml.safe_dump(body), encoding="utf-8")
    return path


def small_config(tmp_path: Path) -> Path:
    """시험용 voss_config (정수 값이 섞인 실제 파일과 같은 모양)."""
    return write_config(
        tmp_path,
        {
            "version": 1,
            "belt": {"speed_cmps": 4.8, "direction_base": [1, 0, 0]},
            "gripper": {"pre_open_mm": 90, "grasp_width_mm": 39, "force_n": 14.0},
            "timing": {"latency_offset_ms": 0},
            "zones": {"A": {"pose": [1, 2, 3]}},  # belt_servo 가 안 쓰는 키
        },
    )


def flat_keys(path: Path) -> set[str]:
    """belt_servo YAML 의 평탄화 키 집합."""
    return set(lp.flatten(lp.node_section(lp.load_yaml(path))))


def test_flatten_nested_names_and_list_leaf() -> None:
    """T-L1: 중첩 → 점 이름, 목록은 잎."""
    flat = lp.flatten({"a": {"b": {"c": 1}, "d": [1, 2]}, "e": "x"})
    assert flat == {"a.b.c": 1, "a.d": [1, 2], "e": "x"}


def test_drop_unset_matches_node_null_rule() -> None:
    """T-L2: None·'null'·' null '·'~'·[] 는 지우고 0·False·''·'NULL' 은 남긴다 (노드와 같은 규칙)."""
    flat = {
        "n": None,
        "s": "null",
        "sp": " null ",
        "t": "~",
        "e": [],
        "z": 0,
        "f": False,
        "b": "",
        "u": "NULL",
    }
    kept, dropped = lp.drop_unset(flat)
    assert dropped == ["e", "n", "s", "sp", "t"]  # 정렬됨
    assert kept == {"z": 0, "f": False, "b": "", "u": "NULL"}


def test_overrides_replace_add_and_clear_dropped(tmp_path: Path) -> None:
    """T-L3: overrides 가 같은 키를 덮어쓰고 새 키를 더하며, 값을 준 키는 dropped 에서 빠진다."""
    base = write_params(tmp_path, "p.yaml", {"control": {"kp_per_s": None}, "rate_hz": 30.0})
    over = write_params(tmp_path, "o.yaml", {"control": {"kp_per_s": 2.0}, "zero_hold_s": 0.5})
    res = lp.build_params(base, small_config(tmp_path), overrides_path=over)
    assert res.params["control.kp_per_s"] == 2.0
    assert res.params["rate_hz"] == 30.0 and res.params["zero_hold_s"] == 0.5
    assert "control.kp_per_s" not in res.dropped


@pytest.mark.parametrize("bad", [{"belt": {"speed_cmps": 5.0}}, {"config_version": 2}])
def test_voss_config_keys_in_params_rejected(tmp_path: Path, bad: dict) -> None:
    """T-L4: params 에 voss_config 몫 키가 있으면 launch 를 멈춘다 (규칙 5)."""
    path = write_params(tmp_path, "p.yaml", {"rate_hz": 30.0, **bad})
    with pytest.raises(lp.LaunchParamsError, match="규칙 5"):
        lp.build_params(path, small_config(tmp_path))


def test_unknown_key_warns_and_passes(tmp_path: Path) -> None:
    """T-L5: PARAM_SPECS 에 없는 키 → 경고 1줄, 값은 그대로 넘긴다."""
    path = write_params(tmp_path, "p.yaml", {"rate_hz": 30.0, "contrl": {"kp": 1.0}})
    res = lp.build_params(path, small_config(tmp_path), log_dir=str(tmp_path))
    assert res.params["contrl.kp"] == 1.0
    assert [w for w in res.warnings if "contrl.kp" in w]


def test_normalize_by_spec_kind() -> None:
    """T-L6: float 종류 90 → 90.0, float3 정수 목록 → float, bool 그대로, int 종류 1.0 → 1."""
    out = lp.normalize(
        {
            "gripper.pre_open_mm": 90,
            "belt.direction_base": [1, 0, 0],
            "rate_hz": True,  # 틀린 형은 그대로 (노드가 거부)
            "retry.max_attempts": 1.0,
            "log.dir": "x",
        }
    )
    assert out["gripper.pre_open_mm"] == 90.0 and isinstance(out["gripper.pre_open_mm"], float)
    assert out["belt.direction_base"] == [1.0, 0.0, 0.0]
    assert all(isinstance(x, float) for x in out["belt.direction_base"])
    assert out["rate_hz"] is True
    assert out["retry.max_attempts"] == 1 and isinstance(out["retry.max_attempts"], int)
    assert out["log.dir"] == "x"


def test_config_values_extracts_six_keys_and_version(tmp_path: Path) -> None:
    """T-L7: voss_config 에서 6키 + version → config_version, null 은 뺀다, 안 쓰는 키는 안 가져온다."""
    assert len(lp.CONFIG_KEYS) == 6  # 지금 PARAM_SPECS 기준 (U5 가 더하면 이 숫자를 고친다)
    doc = lp.load_yaml(small_config(tmp_path))
    doc["timing"]["latency_offset_ms"] = None  # null 이면 빠진다
    out = lp.config_values(doc, "abc123abc123")
    assert set(out) == set(lp.CONFIG_KEYS) - {"timing.latency_offset_ms"} | {
        "config_version",
        "config_sha256",
    }
    assert out["config_version"] == 1 and out["config_sha256"] == "abc123abc123"


def test_file_sha_matches_gateway_format(tmp_path: Path) -> None:
    """T-L8: 길이 12, 같은 파일 같은 값, 한 바이트 바뀌면 다름, gateway 방식(sha256 앞 12)과 같음."""
    path = tmp_path / "c.yaml"
    path.write_bytes(b"version: 1\n")
    sha = lp.file_sha(path)
    assert len(sha) == 12 and sha == lp.file_sha(path)
    assert (
        sha == hashlib.sha256(b"version: 1\n").hexdigest()[:12]
    )  # config_params.load_config 와 같은 식
    path.write_bytes(b"version: 2\n")
    assert lp.file_sha(path) != sha


def test_bad_files_raise_with_path(tmp_path: Path) -> None:
    """T-L9: 파일 없음·깨진 YAML·ros__parameters 없음 → LaunchParamsError (메시지에 경로)."""
    missing = tmp_path / "none.yaml"
    with pytest.raises(lp.LaunchParamsError, match="none.yaml"):
        lp.load_yaml(missing)
    broken = tmp_path / "broken.yaml"
    broken.write_text("a: [1, 2\n", encoding="utf-8")
    with pytest.raises(lp.LaunchParamsError, match="YAML 오류"):
        lp.load_yaml(broken)
    wrong = tmp_path / "wrong.yaml"
    wrong.write_text("other_node:\n  ros__parameters: {a: 1}\n", encoding="utf-8")
    with pytest.raises(lp.LaunchParamsError, match="wrong.yaml"):
        lp.build_params(wrong, small_config(tmp_path))
    with pytest.raises(lp.LaunchParamsError, match="params 인자가 비었다"):
        lp.build_params("", small_config(tmp_path))


def test_log_dir_expands_and_relative_warns(tmp_path: Path) -> None:
    """T-L10: log_dir '~/x' → 절대 경로로 log.dir 덮어씀. log_dir 없고 상대 경로면 경고."""
    path = write_params(tmp_path, "p.yaml", {"log": {"dir": "data/servo"}})
    res = lp.build_params(path, small_config(tmp_path), log_dir="~/voss_logs")
    assert res.params["log.dir"] == str(Path.home() / "voss_logs")
    assert not [w for w in res.warnings if "상대 경로" in w]
    res2 = lp.build_params(path, small_config(tmp_path))
    assert res2.params["log.dir"] == "data/servo"
    assert [w for w in res2.warnings if "상대 경로" in w]


def test_build_with_repo_files() -> None:
    """T-L11: 레포 belt_servo.yaml + 레포 voss_config → null 은 빠지고 voss_config 6키·지문이 들어간다."""
    res = lp.build_params(BASE_YAML, VOSS_CONFIG)
    assert "control.kp_per_s" in res.dropped  # main 의 미측정 값
    for key in lp.CONFIG_KEYS:
        assert key in res.params
    assert res.params["config_sha256"] == lp.file_sha(VOSS_CONFIG)
    assert isinstance(res.params["gripper.pre_open_mm"], float)  # voss_config 의 90 → 90.0
    assert all("상대 경로" in w for w in res.warnings)  # main 의 log.dir 상대 경로 경고만
    assert not lp.unknown_keys(res.params)  # 모르는 키 없음
    assert all(not lp.is_unset(v) for v in res.params.values())  # null 은 하나도 안 넘어감


def test_three_yaml_files_have_same_keys() -> None:
    """T-L12: example = sim = belt_servo.yaml ∪ U5 대기 키 (평탄화 키 집합). 키가 새로 생기면 여기서 알람."""
    want = flat_keys(BASE_YAML) | U5_PENDING_KEYS  # #131 머지 전후 모두 같은 집합
    assert flat_keys(EXAMPLE_YAML) == want
    assert flat_keys(SIM_YAML) == want
    assert not lp.forbidden_keys(dict.fromkeys(want))  # voss_config 몫은 셋 다 없다
    # gripper_timeout_s 는 voss_config gripper.* 묶음이 아니다 (첫 마디가 "gripper" 가 아님)
    assert not lp.forbidden_keys({"gripper_timeout_s": 3.0})


def test_sim_yaml_is_ready() -> None:
    """T-L13: sim yaml + 레포 voss_config → 노드 기동 검사(params.check_params)가 READY."""
    res = lp.build_params(SIM_YAML, VOSS_CONFIG)
    assert res.dropped == []  # sim 은 전부 채웠다
    report = check_params(res.params)
    assert report.ready, (report.missing, report.invalid)
