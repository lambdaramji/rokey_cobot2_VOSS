"""voss_config.yaml → robot_gateway 파라미터 (ROS import 없음).

voss_config.md 값 규칙: 쓰는 노드는 sort_manager 뿐이고, 정적 값은 launch 가 읽어 파라미터로 넘긴다.
version·sha256 을 같이 넘겨 노드가 기동 때 로그로 남긴다(#53 MC-009). null = 미측정 → 그 키는
파라미터로 넘기지 않고, 노드는 필요한 값이 없으면 준비 안 됨으로 시작한다.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

ZONES = ("A", "B", "C", "RECHECK", "HOLD")  # MoveToZone zone 값(대문자). config 키는 대소문자 무시


def load_config(path: str | Path) -> tuple[dict[str, Any], str]:
    """YAML 을 읽어 (내용, sha256 앞 12자리) 를 돌려준다."""
    raw = Path(path).expanduser().read_bytes()
    return yaml.safe_load(raw) or {}, hashlib.sha256(raw).hexdigest()[:12]


def _floats(v: Any, n: int) -> list[float] | None:
    """길이 n 의 숫자 목록이면 float 목록, 아니면(null 포함) None."""
    if not isinstance(v, list) or len(v) != n:
        return None
    if not all(isinstance(x, int | float) and not isinstance(x, bool) for x in v):
        return None
    return [float(x) for x in v]


def gateway_params(cfg: dict[str, Any], sha: str) -> dict[str, Any]:
    """robot_gateway 에 넘길 파라미터. null·형식 오류인 키는 빠진다."""
    out: dict[str, Any] = {
        "config_version": str(cfg.get("version", "")),
        "config_sha256": sha,
    }
    tcp = _floats((cfg.get("robot") or {}).get("tcp_offset_mm"), 3)
    if tcp is not None:
        out["tcp_offset_mm"] = tcp
    obs = _floats(cfg.get("observe_pose"), 6)
    if obs is not None:
        out["observe_pose"] = obs
    zones = {str(k).upper(): v for k, v in (cfg.get("zones") or {}).items()}
    for z in ZONES:
        zc = zones.get(z) or {}
        pose = _floats(zc.get("pose"), 6)
        if pose is not None:
            out[f"zones.{z}.pose"] = pose
        grid = zc.get("grid") or {}
        if all(isinstance(grid.get(k), int | float) for k in ("cols", "rows", "pitch_mm")):
            off = grid.get("offset_mm", 0)  # 칸 줄 중심의 X 위치(트레이 중심 기준), 없으면 0
            out[f"zones.{z}.grid"] = [
                float(grid["cols"]),
                float(grid["rows"]),
                float(grid["pitch_mm"]),
                float(off) if isinstance(off, int | float) and not isinstance(off, bool) else 0.0,
            ]
        view = _floats(zc.get("view_pose"), 6)
        if view is not None:
            out[f"zones.{z}.view_pose"] = view
    g = cfg.get("gripper") or {}
    for k in ("pre_open_mm", "grasp_width_mm", "force_n"):
        if isinstance(g.get(k), int | float) and not isinstance(g.get(k), bool):
            out[f"gripper.{k}"] = float(g[k])
    return out
