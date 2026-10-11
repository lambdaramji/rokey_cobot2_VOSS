"""gate_summary.py 시험 (ROS 없이) — 시도 로그 → G1 회차 기록표·요약."""

import json
import re
from pathlib import Path

import pytest

from voss_servo import gate_summary as gs
from voss_servo import log_schema as ls

T0 = 1791608400.0  # 2026-10-10 14:00:00 KST 의 ROS 시각 (epoch 초)
PSHA = "a" * 64  # belt_servo 파라미터 sha 예
CSHA = "b1c2d3e4f5a6"  # voss_config sha 예 (12자리)


def attempt_row(event: str, goal_id: str, t: float, **kw) -> dict:
    """스키마(log_schema)로 만든 시도 로그 한 행. 스키마가 바뀌면 여기서 깨진다."""
    values = {k: None for k in ls.TICK_FIELDS if k != "kind"}  # 틱 키 전부
    values.update(goal_id=goal_id, track_id=7, attempt=1, phase="VERIFY", terminal=True)
    values.update(t_calc_s=t, reason="OK", cause="", grasped=True, belt_speed_mps=0.0477)
    values.update(config_version=1, config_sha256=CSHA, params_sha256=PSHA)
    values.update(kw)  # 사례별로 덮어쓴다
    row = ls.to_attempt(ls.make_tick(**values), event)  # 노드와 같은 길로 시도 행을 만든다
    assert tuple(row) == ls.ATTEMPT_FIELDS  # 시도 키만 남는다
    return row


def ok_goal(goal_id: str, t: float) -> list[dict]:
    """최초 시도 성공 goal."""
    return [attempt_row(ls.GOAL_END, goal_id, t)]


def retry_ok_goal(goal_id: str, t: float) -> list[dict]:
    """1회 실패(NOT_DETECTED) 뒤 재시도 성공 goal."""
    fail = attempt_row(
        ls.ATTEMPT_END, goal_id, t - 3, phase="PREPARE", reason=None, cause="NOT_DETECTED"
    )
    fail.update(grasped=False, terminal=False)
    return [fail, attempt_row(ls.GOAL_END, goal_id, t, attempt=2)]


def fail_goal(goal_id: str, t: float, reason: str, cause: str, attempt: int = 0) -> list[dict]:
    """실패 goal."""
    return [
        attempt_row(
            ls.GOAL_END, goal_id, t, reason=reason, cause=cause, grasped=False, attempt=attempt
        )
    ]


def write_jsonl(path: Path, rows: list[dict], extra_lines: tuple[str, ...] = ()) -> Path:
    """행들을 jsonl 로 쓴다 (깨진 줄을 끼워 넣을 수 있게)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [ls.to_json_line(r) for r in rows] + list(extra_lines)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def summarize(rows, since_s=None, exclude=(), limit=20):
    """순수 함수 연결: 행 → (줄, 집계)."""
    cases, _ = gs.collect_cases(rows)
    excluded, _ = gs.match_excludes(cases, exclude)
    table_rows, practice = gs.classify(cases, since_s, excluded, limit)
    return table_rows, gs.count_stats(table_rows, practice)


def test_ok_fail_retry_counts() -> None:
    rows = ok_goal("aa01", T0) + retry_ok_goal("aa02", T0 + 60)
    rows += fail_goal("aa03", T0 + 120, "GRASP_FAILED", "WIDTH_OUT", attempt=1)
    rows += fail_goal("aa04", T0 + 180, "LOST", "BOX_MISSING")
    table_rows, stats = summarize(rows)
    assert [r.label for r in table_rows] == ["1", "2", "3", "4"]  # 끝난 시각 순서
    assert (stats.counted, stats.success, stats.first_try) == (4, 2, 1)
    assert table_rows[1].case.attempts == 2 and table_rows[1].case.retry_causes == ("NOT_DETECTED",)
    assert stats.reasons == {"OK": 2, "GRASP_FAILED": 1, "LOST": 1}
    assert stats.hints == {"G": 1, "L": 1}  # 실패만 힌트 분포에


def test_since_filter_is_practice() -> None:
    rows = ok_goal("bb01", T0) + ok_goal("bb02", T0 + 100) + ok_goal("bb03", T0 + 200)
    since = gs.parse_since("2026-10-10T14:01:00")  # 시간대 없음 → KST
    table_rows, stats = summarize(rows, since_s=since)
    assert since == pytest.approx(T0 + 60.0)  # KST 로 읽었나
    assert [r.case.goal_id for r in table_rows] == ["bb02", "bb03"]
    assert stats.practice == 1 and stats.counted == 2 and stats.invalid == 0


def test_exclude_does_not_use_a_slot() -> None:
    rows = ok_goal("cc01aaaa", T0) + ok_goal("cc02bbbb", T0 + 60) + ok_goal("cc03cccc", T0 + 120)
    table_rows, stats = summarize(rows, exclude=["cc02"], limit=2)
    assert [r.label for r in table_rows] == ["1", "무효", "2"]  # 무효는 분모 칸을 쓰지 않는다
    assert stats.invalid == 1 and stats.counted == 2 and stats.over == 0
    cases, _ = gs.collect_cases(rows)
    chosen, warnings = gs.match_excludes(cases, ["cc0", "zz"])
    assert chosen == set() and len(warnings) == 2  # 겹치는 앞자리·없는 앞자리 → 경고


def test_limit_marks_over() -> None:
    rows = [r for i in range(4) for r in ok_goal(f"dd0{i}", T0 + i * 60)]
    table_rows, stats = summarize(rows, limit=3)
    assert [r.label for r in table_rows] == ["1", "2", "3", "초과"]
    assert stats.counted == 3 and stats.over == 1 and stats.success == 3


def test_first_try_uses_attempt_and_fallback() -> None:
    rows = retry_ok_goal("ee01", T0)  # attempt 2 → 최초 시도 성공 아님
    no_attempt = retry_ok_goal("ee02", T0 + 60)
    no_attempt[-1]["attempt"] = None  # GOAL_END 에 attempt 가 없으면
    cases, warnings = gs.collect_cases(rows + no_attempt + ok_goal("ee03", T0 + 120))
    assert [c.attempts for c in cases] == [2, 2, 1]  # ATTEMPT_END 1행 + 1 = 2 로 추정
    assert cases[1].attempts_estimated and any("추정" in w for w in warnings)
    assert [gs.is_first_try_success(c) for c in cases] == [False, False, True]
    assert all(gs.is_success(c) for c in cases)
    not_grasped = fail_goal("ee04", T0, "OK", "", attempt=1)  # OK 인데 grasped false
    case = gs.collect_cases(not_grasped)[0][0]
    assert not gs.is_success(case) and gs.row_hint(case)[0] == "?"


def test_empty_file(tmp_path, capsys) -> None:
    path = tmp_path / "attempts" / "servo_attempts_20261010_140000.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("", encoding="utf-8")
    assert gs.main([str(tmp_path), "--main", "abc1234"]) == 0  # log.dir 을 줘도 찾는다
    out = capsys.readouterr()
    assert "| 합계 |" in out.out and "0사례 중 0회 성공(__ %)" in out.out
    assert "GOAL_END 행이 없다" in out.err


def test_no_input_file_exit_2(tmp_path, capsys) -> None:
    assert gs.main([str(tmp_path / "없음"), "--main", "abc1234"]) == 2
    assert "파일 없음" in capsys.readouterr().err


def test_broken_lines_skipped_with_warning(tmp_path, capsys) -> None:
    path = write_jsonl(
        tmp_path / "servo_attempts_20261010_140000.jsonl",
        ok_goal("ff01", T0) + ok_goal("ff02", T0 + 60),
        extra_lines=('{"kind": "attempt", "event": "GOAL_E', "[1, 2]"),  # 쓰다 끊긴 줄·목록 줄
    )
    rows, warnings = gs.read_rows([path])
    assert len(rows) == 2 and len(warnings) == 2
    assert "깨진 줄 무시" in warnings[0] and ":3 " in warnings[0]  # 파일:줄 번호
    assert gs.main([str(path), "--main", "abc1234"]) == 0
    assert "깨진 줄 무시" in capsys.readouterr().err


def _g1_table_header() -> list[str] | None:
    """docs/g1-gate.md 3절 표 머리 칸 (레포 밖에서 돌면 None)."""
    for parent in Path(__file__).resolve().parents:
        doc = parent / "docs" / "g1-gate.md"
        if doc.is_file():
            for line in doc.read_text(encoding="utf-8").splitlines():
                if line.startswith("| # | 시각"):
                    return [c.strip() for c in line.strip().strip("|").split("|")]
    return None


def _cells(line: str) -> list[str]:
    """Markdown 표 한 줄 → 칸 (이스케이프된 | 는 칸 나눔이 아님)."""
    return [c.strip() for c in re.split(r"(?<!\\)\|", line.strip())[1:-1]]


def test_table_columns_match_g1_gate() -> None:
    header = _g1_table_header()
    if header is not None:
        assert tuple(header) == gs.GATE_COLUMNS  # 문서 표와 같은 열·같은 순서
    assert len(gs.GATE_COLUMNS) == 11
    rows = ok_goal("gg01", T0) + fail_goal("gg02", T0 + 60, "DEVICE_ERROR", "STOP_FAILED_a|b")
    table_rows, stats = summarize(rows)
    text = gs.render_gate_table(table_rows, stats, 20)
    lines = text.splitlines()
    assert len(lines) == 2 + 2 + 1  # 머리·구분선 + 사례 2 + 합계
    assert all(len(_cells(line)) == len(gs.GATE_COLUMNS) for line in lines)  # | 이스케이프 포함
    first = _cells(lines[2])
    assert first[1] == "14:00:00" and first[3] == "7" and first[6:8] == ["○", "○"]
    assert first[8] == "" and first[2] == "" and first[9] == ""  # 원인·박스·bag 시각은 사람이
    assert _cells(lines[-1])[6:8] == ["1/20", "1/20"] and _cells(lines[-1])[10] == "무효 0회"
    hint = gs.render_hint_table(table_rows, None).splitlines()
    assert all(len(_cells(line)) == len(gs.HINT_COLUMNS) for line in hint)


def test_summary_sentence() -> None:
    rows = [r for i in range(14) for r in ok_goal(f"hh{i:02d}", T0 + i * 60)]
    rows += retry_ok_goal("hh14", T0 + 14 * 60)
    rows += [
        r
        for i in range(15, 20)
        for r in fail_goal(f"hh{i:02d}", T0 + i * 60, "OUT_OF_REACH", "REACH_X_MAX")
    ]
    rows += ok_goal("hh99", T0 + 30 * 60)
    table_rows, stats = summarize(rows, exclude=["hh99"])
    meta = gs.Meta("s1", 20, "280f786", "h250", None)
    lines = gs.summary_lines([r.case for r in table_rows], stats, meta)
    assert lines[0] == (
        "- 측정: 20사례 중 15회 성공(75 %), 최초 시도 성공 14회, 무효 1회. "
        "벨트 h250(4.77 cm/s), main 280f786, belt_servo 파라미터 sha aaaaaaaaaaaa "
        "(measurements-1010 #__)"
    )
    assert "R 5" in lines[2]  # 자동 힌트 분포
    assert f"config_sha256 {CSHA}" in lines[5] and f"params_sha256 {PSHA}" in lines[5]


def test_auto_hint_codes() -> None:
    assert gs.auto_hint("LOST", "BOX_MISSING")[0] == "L"
    assert gs.auto_hint("STALE_INPUT", "POSE_MISSING")[0] == "L"
    assert gs.auto_hint("OUT_OF_REACH", "REACH_GRASP_ROOM")[0] == "R"
    assert gs.auto_hint("GRASP_FAILED", "NOT_DETECTED")[0] == "G"
    assert gs.auto_hint("DEVICE_ERROR", "GRIPPER_TIMEOUT")[0] == "D"
    assert gs.auto_hint("DEVICE_ERROR", "NODE_SHUTDOWN")[0] == "X"
    assert gs.auto_hint("CANCELED", "STOP_OK")[0] == "?"
    assert gs.auto_hint("OK", "") == ("", "")


def test_tick_summary() -> None:
    def tick(t, phase, err=None, cause=""):
        return {"kind": "tick", "goal_id": "ii01", "t_calc_s": t, "phase": phase,
                "error_m": err, "cause": cause}  # fmt: skip

    rows = [tick(T0, "PREPARE"), tick(T0 + 0.1, "TRACK"), tick(T0 + 1.1, "TRACK")]
    rows += [
        tick(T0 + 1.6, "DESCEND", [0.003, 0.004, 0.0]),
        tick(T0 + 1.7, "DESCEND", [0, 0.002, 0]),
    ]
    rows += [tick(T0 + 2.0, "GRASP"), tick(T0 + 3.0, "TRACK", cause="ZERO_HOLD")]  # 0 유지는 뺀다
    rows.append({"kind": "tick", "goal_id": "other", "t_calc_s": T0, "phase": "TRACK"})
    summary = gs.summarize_ticks(rows, {"ii01"})
    assert set(summary) == {"ii01"}
    s = summary["ii01"]
    assert s.n_ticks == 6 and s.track_s == pytest.approx(1.5)  # 0.1→1.1→1.6
    assert s.descend_max_err_mm == pytest.approx(5.0)


def test_main_md_append_and_ticks(tmp_path, capsys) -> None:
    log_dir = tmp_path / "servo"
    write_jsonl(log_dir / "attempts" / "servo_attempts_20261010_140000.jsonl", ok_goal("jj01", T0))
    tick = {"kind": "tick", "goal_id": "jj01", "t_calc_s": T0 - 2, "phase": "TRACK", "cause": ""}
    end = dict(tick, t_calc_s=T0, phase="VERIFY")
    (log_dir / "ticks").mkdir()
    (log_dir / "ticks" / "servo_ticks_20261010_140000.jsonl").write_text(
        json.dumps(tick) + "\n" + json.dumps(end) + "\n", encoding="utf-8"
    )
    md = tmp_path / "measurements-1010.md"
    md.write_text("# 10/10 실측\n", encoding="utf-8")
    argv = [str(log_dir), "--main", "abc1234", "--md", str(md), "--ticks", str(log_dir)]
    assert gs.main(argv) == 0
    text = md.read_text(encoding="utf-8")
    assert text.startswith("# 10/10 실측\n\n### G1 회차 기록")  # 기존 내용은 그대로, 끝에 붙임
    assert "| 1 | jj01 | OK |" in text and "| 2.00 |" in text  # 틱 요약 (추종 2 s)
    assert "main abc1234" in capsys.readouterr().out
