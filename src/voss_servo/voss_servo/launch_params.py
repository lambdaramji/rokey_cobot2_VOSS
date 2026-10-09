"""belt_servo 기동 파라미터 정리 (순수 모듈 — ROS 를 import 하지 않는다).

launch 파일(launch/belt_servo.launch.py·sim.launch.py)이 부르는 계산을 모두 여기 둔다 → pytest 로 확인.
- 설계: design/U3-dd.md 1절, pseudo 1절.
- 순서: params YAML → (overrides YAML) → log_dir → voss_config 키·지문 → 형 맞추기.
- null(미측정) 키는 노드에 넘기지 않는다 → 노드(params.py)가 "값 없음 = READY 거부" 로 판단.
- voss_config 값(belt·gripper·timing)은 voss_config 에서만 온다 (CLAUDE.md 규칙 5).
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Any

import yaml

from voss_servo.params import NULL_STRINGS, PARAM_SPECS  # 읽기만 (params.py 는 U5 담당 파일)

NODE_NAME = "belt_servo"  # YAML 최상위 키 = 노드 이름
CONFIG_PREFIXES = ("belt", "gripper", "timing")  # voss_config 에서만 오는 키 묶음
CONFIG_META_KEYS = ("config_version", "config_sha256")  # launch 가 만들어 넘기는 키
SPEC_KIND: dict[str, str] = {s.name: s.kind for s in PARAM_SPECS}  # 이름 → 종류(float 등)
# voss_config 에서 뽑을 키: PARAM_SPECS 중 첫 마디가 belt·gripper·timing 인 것 (U5 가 더하면 자동 포함)
CONFIG_KEYS: tuple[str, ...] = tuple(n for n in SPEC_KIND if n.split(".")[0] in CONFIG_PREFIXES)
SHA_LEN = 12  # 파일 지문 길이 — gateway config_params.load_config 와 같은 형식


class LaunchParamsError(ValueError):
    """launch 를 멈춰야 하는 설정 오류 (파일 없음·YAML 오류·규칙 5 위반)."""


@dataclass(frozen=True)
class BuildResult:
    """build_params 결과."""

    params: dict[str, Any]  # 노드에 넘길 값 (점 이름 → 값)
    dropped: list[str] = field(default_factory=list)  # null 이라 넘기지 않은 키
    warnings: list[str] = field(default_factory=list)  # launch 가 로그로 찍을 경고
    config_sha: str = ""  # voss_config 파일 지문 (12자리)
    sources: dict[str, str] = field(default_factory=dict)  # 읽은 파일 절대 경로


def expand(path: Any) -> str:
    """'~' 를 펼친 절대 경로. launch 인자 'params:=~/x' 는 셸이 펼치지 않는다."""
    return os.path.abspath(os.path.expanduser(str(path)))


def load_yaml(path: Any) -> dict[str, Any]:
    """YAML 파일을 dict 로 읽는다. 없음·문법 오류·최상위가 표가 아니면 LaunchParamsError."""
    p = expand(path)
    if not os.path.isfile(p):
        raise LaunchParamsError(f"파일 없음: {p} — 경로 확인")
    try:
        with open(p, encoding="utf-8") as f:
            doc = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        first = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        raise LaunchParamsError(f"YAML 오류: {p} — {first}") from exc
    if doc is None:
        return {}  # 빈 파일
    if not isinstance(doc, dict):
        raise LaunchParamsError(f"최상위가 표(dict)가 아님: {p}")
    return doc


def node_section(doc: dict[str, Any], node: str = NODE_NAME, where: str = "") -> dict[str, Any]:
    """doc[node]['ros__parameters'] 를 꺼낸다. 없거나 표가 아니면 LaunchParamsError."""
    top = doc.get(node)
    sec = top.get("ros__parameters") if isinstance(top, dict) else None  # 중간이 표가 아니어도 안전
    if not isinstance(sec, dict):
        raise LaunchParamsError(f"'{node}: ros__parameters:' 없음: {where}")
    return sec


def flatten(d: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """중첩 표를 점 이름으로 편다. {'a': {'b': 1}} → {'a.b': 1}. 목록은 잎으로 둔다."""
    out: dict[str, Any] = {}
    for key, value in d.items():
        name = f"{prefix}.{key}" if prefix else str(key)  # 맨 위는 점 없이
        if isinstance(value, dict):
            out.update(flatten(value, name))  # 더 들어간다
        else:
            out[name] = value  # 숫자·문자열·목록
    return out


def is_unset(v: Any) -> bool:
    """미측정 표시인가: None · 문자열 'null'/'~'(앞뒤 공백 무시, 대소문자 구분) · 빈 목록.

    0·False·'' 는 값으로 본다 (옳고 그름은 노드가 판단). 비교는 노드 params._is_null_string 과 같다.
    """
    if v is None:
        return True
    if isinstance(v, str):
        return v.strip() in NULL_STRINGS  # "null", " null ", "~"
    if isinstance(v, list | tuple):
        return len(v) == 0  # 빈 배열은 ROS 파라미터 형을 정할 수 없다
    return False


def drop_unset(flat: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """미측정 키를 뺀다 → (남은 값, 뺀 키 이름 정렬)."""
    kept = {k: v for k, v in flat.items() if not is_unset(v)}
    dropped = sorted(k for k, v in flat.items() if is_unset(v))
    return kept, dropped


def forbidden_keys(flat: dict[str, Any]) -> list[str]:
    """params·overrides 에 있으면 안 되는 키 (voss_config 몫과 launch 가 만드는 키)."""
    return sorted(k for k in flat if k.split(".")[0] in CONFIG_PREFIXES or k in CONFIG_META_KEYS)


def unknown_keys(flat: dict[str, Any]) -> list[str]:
    """노드가 선언하지 않는 키 (오타 등) — 노드는 조용히 무시하므로 launch 가 경고한다."""
    return sorted(k for k in flat if k not in SPEC_KIND)


def _is_num(v: Any) -> bool:
    """bool 을 뺀 int·float (True 를 1 로 치지 않는다)."""
    return isinstance(v, int | float) and not isinstance(v, bool)


def normalize(flat: dict[str, Any]) -> dict[str, Any]:
    """PARAM_SPECS 종류대로 형을 맞춘다 → 같은 설정이면 같은 params_sha256.

    90 과 90.0 은 노드 지문이 다르다 (U3 사전 실험). 틀린 형은 그대로 둔다 → 노드가 READY 거부.
    """
    out = dict(flat)
    for key, value in flat.items():
        kind = SPEC_KIND.get(key)
        if kind == "float" and _is_num(value):
            out[key] = float(value)  # 90 → 90.0
        elif kind == "float3" and isinstance(value, list | tuple) and all(map(_is_num, value)):
            out[key] = [float(x) for x in value]  # [1, 0, 0] → [1.0, 0.0, 0.0]
        elif kind == "int" and isinstance(value, float) and value.is_integer():
            out[key] = int(value)  # 1.0 → 1 (노드는 정수만 받는다)
    return out


def file_sha(path: Any) -> str:
    """파일 바이트 sha256 앞 12자리 (gateway 로그의 voss_config sha 와 대조용)."""
    p = expand(path)
    if not os.path.isfile(p):
        raise LaunchParamsError(f"파일 없음: {p} — 경로 확인")
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:SHA_LEN]


def config_values(cfg_doc: dict[str, Any], sha: str) -> dict[str, Any]:
    """voss_config 에서 belt_servo 가 쓰는 값 + config_version·config_sha256."""
    flat = flatten(cfg_doc)
    out = {k: flat[k] for k in CONFIG_KEYS if k in flat and not is_unset(flat[k])}
    version = cfg_doc.get("version")
    if not is_unset(version) and version != "":
        out["config_version"] = version  # 정수 또는 문자열 (params.py int_or_str)
    out["config_sha256"] = sha
    return out


def _section_from(path: Any) -> tuple[dict[str, Any], list[str]]:
    """belt_servo 파라미터 YAML 하나 → (넘길 값, null 이라 뺀 키)."""
    doc = load_yaml(path)
    flat = flatten(node_section(doc, NODE_NAME, expand(path)))
    return drop_unset(flat)


def build_params(
    params_path: Any,
    config_path: Any,
    overrides_path: Any = None,
    log_dir: Any = None,
) -> BuildResult:
    """노드에 넘길 파라미터를 만든다 (design/U3-dd.md 1.3 의 ①~⑦)."""
    if not params_path:
        raise LaunchParamsError("params 인자가 비었다 — params:=<belt_servo yaml 경로>")
    warnings: list[str] = []
    values, dropped = _section_from(params_path)  # ① 기본 파일
    if overrides_path:  # ② 덮어쓰기 파일
        over, over_dropped = _section_from(overrides_path)
        values.update(over)  # 같은 키는 덮어쓰고, 새 키는 더한다
        # 값을 받은 키는 뺀 키가 아니다
        dropped = sorted((set(dropped) | set(over_dropped)) - set(over))
    bad = forbidden_keys(values)  # ③ 규칙 5
    if bad:
        raise LaunchParamsError(
            f"params/overrides 에 voss_config 키가 있다(규칙 5): {bad} — 지우기"
        )
    if log_dir:  # ④ 로그 폴더
        values["log.dir"] = expand(log_dir)
    elif isinstance(values.get("log.dir"), str) and not os.path.isabs(values["log.dir"]):
        warnings.append(f"log.dir 상대 경로 — 실행 위치 기준: {values['log.dir']}")
    sha = file_sha(config_path)  # ⑤ voss_config 값·지문
    values.update(config_values(load_yaml(config_path), sha))
    values = normalize(values)  # ⑥ 형 맞추기
    unknown = unknown_keys(values)  # ⑦ 오타 경고
    if unknown:
        warnings.append(f"PARAM_SPECS 에 없는 키(노드가 무시): {unknown}")
    sources = {
        "params": expand(params_path),
        "overrides": expand(overrides_path) if overrides_path else "-",
        "config": expand(config_path),
    }
    return BuildResult(values, dropped, warnings, sha, sources)


def summary_line(result: BuildResult) -> str:
    """launch 가 찍는 요약 한 줄 (무엇을 읽어 무엇을 넘겼나)."""
    src = result.sources
    return (
        f"belt_servo launch: params={src.get('params')} overrides={src.get('overrides')} "
        f"config={src.get('config')} config_sha256={result.config_sha} "
        f"넘김 {len(result.params)}개, null 로 뺀 키 {len(result.dropped)}개 {result.dropped}"
    )
