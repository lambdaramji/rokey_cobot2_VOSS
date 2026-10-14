"""pallet_gate — Sprint 2 게이트 팔레타이징 회차 기록표를 녹화에서 만든다 (S2-T13, docs/sprint2-gate.md §5).

- 입력: 게이트 녹화(sprint2-gate.md §3) 의 `/voss/pallet/state`·`/voss/pallet/result`·`/voss/voice/say`.
- 출력: §5 기록표와 **같은 12열** Markdown 표 + 회차마다 박스별 상세. run_id 하나 = 회차 하나.
- 자동으로 채우는 것: 시각(계획 발행), 경로, 박스 수, DONE, FAILED(원인), 명령한 칸 = 계획 칸(2층 수·#37 당겨 놓음),
  기대 pallet_log 행 수(싣지 않은 박스 포함), 박스당 최대 s(계획 → 첫 결과, 결과 → 다음 결과 — 녹화 수신 시각), 끝 안내.
- **사람이 채우는 것**: 입력 경로(음성·HMI·서비스), 실물이 그 칸에 놓였는지·2층 안정, 밀림, DB pallet_log 행(§3 5번 SQL).
  그래서 판정 열은 "완주 후보"까지만 낸다(§1 완주 정의의 나머지는 눈으로).
- 순수 함수(회차 나누기·집계·렌더)와 I/O(녹화 읽기·main)를 나눠 둔다 → test/test_pallet_gate.py.
  python3 -m voss_manager.pallet_gate ~/voss_data/1013/s2gate_pal [--out gate_rows.md]
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
NFR15_S = 30.0  # 박스당 사이클 (BRD v1.5 NFR-15)
LOADED = ("DONE", "FAILED")
FINISH = "팔레트 적재를 마쳤습니다"
TOPIC_STATE, TOPIC_RESULT, TOPIC_SAY = (
    "/voss/pallet/state",
    "/voss/pallet/result",
    "/voss/voice/say",
)
COLUMNS = ("회차", "시각", "입력", "경로", "박스 수", "DONE", "FAILED(원인)", "계획 칸대로(2층 포함)", "밀림",
           "pallet_log 행", "박스당 최대 s (NFR-15 ≤ 30)", "판정")  # fmt: skip


@dataclass(frozen=True)
class Ev:
    t: float  # 녹화 수신 시각(s, epoch)
    topic: str
    data: dict  # 메시지 필드 그대로 (say 는 {"data": 문장})


@dataclass(frozen=True)
class BoxRow:
    box_id: str
    dong: str
    planned_slot: int
    pallet_slot: int
    layer: int
    outcome: str
    reason: str
    attempts: int
    dt_s: float  # 앞 박스 결과(첫 박스는 계획) → 이 박스 결과


@dataclass(frozen=True)
class RunRow:
    run_id: str
    plan_t: float
    route: tuple[str, ...]
    total: int
    done: int
    failed: tuple[tuple[str, str], ...]  # (box_id, reason)
    slots_ok: int  # DONE 중 명령한 칸 = 계획 칸
    pulled: int  # DONE 중 #37 로 아래 칸에 놓은 박스
    layer2: int  # 2층에 놓은 DONE
    results: int  # PalletResult 수 = 기대 pallet_log 행 (OVERFLOW·EXCLUDED 포함)
    unloaded: int
    max_s: float
    finished: bool  # 마지막 PalletState.state == DONE
    finish_said: bool
    boxes: tuple[BoxRow, ...]

    @property
    def candidate(self) -> bool:
        """§1 완주 정의 중 녹화로 볼 수 있는 부분을 모두 만족."""
        return (self.finished and self.finish_said and not self.failed and self.done == self.total
                and self.total > 0 and self.slots_ok == self.done)  # fmt: skip


def split_runs(events: list[Ev]) -> dict[str, list[Ev]]:
    """run_id 별 사건(시간순). say 는 그 회차의 첫 사건 ~ 마지막 사건 + 10 s 안의 것을 붙인다. 실행 없음("")은 버린다."""
    evs = sorted(events, key=lambda e: e.t)
    runs: dict[str, list[Ev]] = {}
    for e in evs:
        rid = e.data.get("run_id", "") if e.topic != TOPIC_SAY else ""
        if rid:
            runs.setdefault(rid, []).append(e)
    for lst in runs.values():
        lo, hi = lst[0].t, lst[-1].t + 10.0
        lst.extend(e for e in evs if e.topic == TOPIC_SAY and lo <= e.t <= hi)
        lst.sort(key=lambda e: e.t)
    return dict(sorted(runs.items(), key=lambda kv: kv[1][0].t))


def summarize_run(run_id: str, evs: list[Ev]) -> RunRow:
    states = [e for e in evs if e.topic == TOPIC_STATE]
    plan = next((e for e in states if e.data.get("dongs")), None)
    plan_t = plan.t if plan else (evs[0].t if evs else 0.0)
    planned = {b: s for s, b in enumerate(plan.data["slot_box_id"]) if b} if plan else {}
    results = [e for e in evs if e.topic == TOPIC_RESULT]
    loaded = [e for e in results if e.data["outcome"] in LOADED]
    boxes, prev = [], plan_t
    for e in loaded:
        d = e.data
        boxes.append(BoxRow(d["box_id"], d["dong"], planned.get(d["box_id"], -1), d["pallet_slot"],
                            d["pallet_layer"], d["outcome"], d["reason"], d["attempts"], e.t - prev))  # fmt: skip
        prev = e.t
    done = [b for b in boxes if b.outcome == "DONE"]
    # 끝 안내는 마지막 결과 뒤(관측 복귀 뒤)에 나온다
    last_t = loaded[-1].t if loaded else plan_t
    said = [e.data.get("data", "") for e in evs if e.topic == TOPIC_SAY and e.t >= last_t]
    return RunRow(
        run_id=run_id,
        plan_t=plan_t,
        route=tuple(plan.data["route"]) if plan else (),
        total=int(plan.data["total"]) if plan else 0,
        done=len(done),
        failed=tuple((b.box_id, b.reason) for b in boxes if b.outcome == "FAILED"),
        slots_ok=sum(1 for b in done if b.pallet_slot == b.planned_slot),
        pulled=sum(1 for b in done if b.planned_slot >= 0 and b.pallet_slot == b.planned_slot - 2),
        layer2=sum(1 for b in done if b.layer == 2),
        results=len(results),
        unloaded=len(results) - len(loaded),
        max_s=max((b.dt_s for b in boxes), default=float("nan")),
        finished=bool(states) and states[-1].data.get("state") == "DONE",
        finish_said=any(s.startswith(FINISH) for s in said),
        boxes=tuple(boxes),
    )


def _short(box_id: str) -> str:
    return box_id.rsplit("-", 1)[-1]


def table_row(i: int, r: RunRow) -> list[str]:
    failed = "0" if not r.failed else (
        f"{len(r.failed)} (" + ", ".join(f"{_short(b)}번 {why or '?'}" for b, why in r.failed) + ")"
    )  # fmt: skip
    slots = f"명령 {r.slots_ok}/{r.done} (2층 {r.layer2})" + (
        f", 당겨 놓음 {r.pulled}" if r.pulled else ""
    )
    slots += " · 실물 눈 확인"
    rows = (
        f"기대 {r.results}" + (f"(미적재 {r.unloaded} 포함)" if r.unloaded else "") + " · DB 확인"
    )
    over = r.max_s > NFR15_S
    max_s = "-" if r.max_s != r.max_s else f"{r.max_s:.1f}" + (" ⚠" if over else "")
    if r.candidate:
        verdict = "완주 후보 — 실물·밀림·pallet_log 확인 뒤 완주"
    else:
        why = []
        if r.failed:
            why.append(f"FAILED {len(r.failed)}")
        if r.done + len(r.failed) < r.total:
            why.append(f"남은 박스 {r.total - r.done - len(r.failed)}")
        if r.slots_ok != r.done:
            why.append("칸이 계획과 다름")
        if not r.finished:
            why.append("DONE 상태 아님")
        if not r.finish_said:
            why.append("끝 안내 없음")
        verdict = "미완주 — " + ", ".join(why or ["확인 필요"])
    t = datetime.fromtimestamp(r.plan_t, KST).strftime("%H:%M:%S")
    return [
        str(i),
        t,
        "",
        " → ".join(r.route),
        str(r.total),
        str(r.done),
        failed,
        slots,
        "(눈)",
        rows,
        max_s,
        verdict,
    ]


def render(rows: list[RunRow]) -> str:
    """§5 기록표 + 회차별 박스 상세."""
    out = ["| " + " | ".join(COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    out += ["| " + " | ".join(table_row(i, r)) + " |" for i, r in enumerate(rows, 1)]
    for i, r in enumerate(rows, 1):
        out += ["", f"**회차 {i}** run_id `{r.run_id}`", "",
                "| 차례 | box_id | 동 | 계획 칸 | 놓은 칸 | 층 | 결과 | 사유 | 시도 | 앞에서 s |", "|" + "---|" * 10]  # fmt: skip
        for k, b in enumerate(r.boxes, 1):
            moved = (
                " (당겨 놓음)" if b.outcome == "DONE" and b.pallet_slot != b.planned_slot else ""
            )
            out.append(f"| {k} | {_short(b.box_id)} | {b.dong} | {b.planned_slot + 1} | {b.pallet_slot + 1}{moved} | "
                       f"{b.layer} | {b.outcome} | {b.reason} | {b.attempts} | {b.dt_s:.1f} |")  # fmt: skip
    out += ["", "칸 번호 = slot + 1(적재 순서, HMI 와 같다). 시간은 녹화 수신 시각."]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- I/O


def read_bag(path: Path) -> list[Ev]:  # pragma: no cover — 공용 PC 녹화
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from std_msgs.msg import String

    from voss_msgs.msg import PalletResult, PalletState

    types = {TOPIC_STATE: PalletState, TOPIC_RESULT: PalletResult, TOPIC_SAY: String}
    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=str(path.expanduser())), rosbag2_py.ConverterOptions("", "")
    )
    have = {t.name for t in reader.get_all_topics_and_types()}
    for name in (TOPIC_STATE, TOPIC_RESULT):
        if name not in have:
            sys.exit(f"{name} 없음 — sprint2-gate.md §3 녹화 토픽을 확인 ({sorted(have)})")
    if TOPIC_SAY not in have:
        print(
            f"주의: {TOPIC_SAY} 없음 — 끝 안내를 볼 수 없어 '끝 안내 없음'으로 나온다",
            file=sys.stderr,
        )
    out = []
    while reader.has_next():
        topic, data, t_ns = reader.read_next()
        if topic in types:
            m = deserialize_message(data, types[topic])
            fields = {k: getattr(m, k) for k in type(m).get_fields_and_field_types()}
            fields = {k: (list(v) if not isinstance(v, (str, int, float, bool)) and k != "stamp" else v)
                      for k, v in fields.items()}  # fmt: skip
            out.append(Ev(t_ns * 1e-9, topic, fields))
    return out


def main(argv: list[str] | None = None) -> None:  # pragma: no cover
    ap = argparse.ArgumentParser(
        description="Sprint 2 게이트 팔레타이징 기록표 (sprint2-gate.md §5)"
    )
    ap.add_argument("bags", type=Path, nargs="+")
    ap.add_argument("--out", type=Path, help="Markdown 으로 저장")
    args = ap.parse_args(argv)
    events = [e for bag in args.bags for e in read_bag(bag)]
    rows = [summarize_run(rid, evs) for rid, evs in split_runs(events).items()]
    text = (
        render(rows)
        if rows
        else "팔레타이징 회차 없음 (run_id 가 있는 PalletState·PalletResult 가 없다)\n"
    )
    print(text)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"저장 {args.out}")


if __name__ == "__main__":  # pragma: no cover
    main()
