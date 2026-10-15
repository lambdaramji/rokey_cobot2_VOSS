"""레포 config/voss_config.yaml 의 현장 값(10/12 실기·10/13 게이트, S2-T21)이 sort_manager 에서 그대로 읽히는지.

로직 시험은 test/fixtures/voss_config_3x1.yaml 을 쓴다 — 여기만 레포 설정을 읽는다.
"""

import os

import yaml

from voss_manager import sort_fsm as f

REPO_CONFIG = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "config", "voss_config.yaml"
)


def raw_repo() -> dict:
    with open(REPO_CONFIG, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_repo_config_field_values() -> None:
    cfg = f.load_config(raw_repo())
    # A·B·C 3×2 × 2층 = 12칸(실제로 쓰는 것은 칸 0~6), 재확인·보류 2칸
    assert cfg.capacity == {"A": 12, "B": 12, "C": 12, "RECHECK": 2, "HOLD": 2}
    assert cfg.layer_cells == {"A": 6, "B": 6, "C": 6}
    # 1층은 +X 끝부터 2,5,1,4,0,3 — 7번째(n=6)는 2층 칸 6 = 칸 0 위
    for z in ("A", "B", "C"):
        assert [cfg.slot_at(z, n) for n in range(7)] == [2, 5, 1, 4, 0, 3, 6]
    assert cfg.pallet_ready is True  # zones.pallet.pose 교시됨


def test_repo_pallet_grid_has_no_order() -> None:
    """적재 순서는 pallet_plan.slot_order 상수 — zones.pallet.grid.order 는 지웠다(10/13 PL 결정 Q12)."""
    grid = raw_repo()["zones"]["pallet"]["grid"]
    assert "order" not in grid
    assert (grid["cols"], grid["rows"], grid["layers"]) == (4, 2, 2)
