"""06_erd — PostgreSQL 스키마 (docker/db/init/01_schema.sql + migrations/20261012_sprint2_pallet.sql). python3 gen_06_erd.py"""

import html

import cairosvg

from archlib import BG, FONT, GRID

TABLES = {
    "sort_log": (
        "SortResult 1건 = 1행 · writer voss_logger · reader voss_web",
        [
            ("box_id", "varchar(32)", "PK", "<session_id>-NNN (24자)"),
            ("session_id", "varchar(24)", "NN", "YYYYMMDDTHHMMSS-xxxx"),
            ("track_id", "integer", "", "BoxTrack.track_id (참고)"),
            ("code", "varchar(16)", "NN ''", "S07-01 · 02 · 03"),
            ("dong", "varchar(16)", "NN ''", "역삼동 · 대치동 · 청담동"),
            ("confidence", "real", "", "0~1"),
            ("decided_by", "varchar(8)", "NN CHECK", "OCR · RECHECK · OPERATOR · NONE"),
            ("zone", "varchar(8)", "NN CHECK", "A · B · C · RECHECK · HOLD · ''"),
            ("result", "varchar(8)", "NN CHECK", "PLACED · HELD · FAILED · PASSED"),
            ("reason", "varchar(24)", "NN ''", "LOW_CONF · NO_ANSWER · NON_TARGET · STOPPED · DEVICE_ERROR · …"),
            ("raw_text", "text", "NN ''", "OCR 원문"),
            ("second_region", "varchar(16)", "NN ''", "dong_alt (2위 후보)"),
            ("rule_version", "varchar(16)", "NN ''", "ZoneMap.version"),
            ("attempts", "smallint", "NN 0", "파지 시도 횟수"),
            ("retries", "smallint", "GENERATED", "GREATEST(attempts-1, 0) STORED"),
            ("started_at", "timestamptz", "", "첫 관측 (ROS Time 0 → NULL)"),
            ("finished_at", "timestamptz", "NN", "SortResult.stamp · cycle_s = finished_at − started_at"),
            ("inserted_at", "timestamptz", "NN now()", "트랜잭션 시작 시각"),
            ("slot", "smallint", "CHECK ≥0", "격자 칸 (Sprint 2 마이그레이션, −1 → NULL)"),
        ],
        "IDX (session_id, result) · IDX (finished_at)",
    ),
    "pallet_log": (
        "PalletResult 1건 = 1행 · Sprint 2 · PK (run_id, box_id)",
        [
            ("run_id", "varchar(24)", "PK", "팔레타이징 실행 ID"),
            ("box_id", "varchar(32)", "PK", "sort_log.box_id"),
            ("session_id", "varchar(24)", "NN", ""),
            ("dong", "varchar(16)", "NN ''", ""),
            ("route_index", "smallint", "NN −1~2", "0 = 첫 배송지 · −1 = EXCLUDED"),
            ("zone", "varchar(8)", "NN CHECK", "집은 구역 A · B · C"),
            ("slot", "smallint", "NN ≥0", "집은 칸"),
            ("pallet_slot", "smallint", "0~15", "(열−1)×4 + (층−1)×2 + (줄−1) · NULL = 미적재"),
            ("pallet_col", "smallint", "1~4", "1 = 트럭 머리(−X) · 4 = 문"),
            ("pallet_lane", "smallint", "1~2", ""),
            ("pallet_layer", "smallint", "1~2", "2 = +27 mm"),
            ("result", "varchar(8)", "NN CHECK", "DONE · FAILED · OVERFLOW · EXCLUDED"),
            ("reason", "varchar(24)", "NN ''", "GRIP_FAIL · DROPPED · STOPPED · DEVICE_ERROR"),
            ("attempts", "smallint", "NN 0", ""),
            ("finished_at", "timestamptz", "NN", "PalletResult.stamp"),
            ("inserted_at", "timestamptz", "NN now()", ""),
        ],
        "IDX (session_id, box_id)",
    ),
    "session_plan": (
        "Spring Boot 전용 · voss_web 읽기/쓰기",
        [
            ("session_id", "varchar(24)", "PK", "'next' → 첫 voss/state 수신 시 세션 ID 로"),
            ("planned", "integer", "NN 1~100", "투입 예정 수량 (HMI 스테퍼, 기본 10)"),
            ("updated_at", "timestamptz", "NN now()", ""),
        ],
        "",
    ),
}

GAP = 300
W = 60 + 2 * sum((210, 130, 110, 650)) + GAP + 60
ROW = 30
COLW = (210, 130, 110, 650)
TW = sum(COLW)
X = {"sort_log": 60, "pallet_log": 60 + TW + GAP, "session_plan": 60 + TW + GAP}
Y = {"sort_log": 110, "pallet_log": 110, "session_plan": 110 + (16 + 2) * ROW + ROW + 110}
H = Y["session_plan"] + 5 * ROW + 70

o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}">',
     f'<pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0 H0 V40" fill="none" stroke="{GRID}" stroke-width="1"/></pattern>',
     f'<rect width="{W}" height="{H}" fill="{BG}"/><rect width="{W}" height="{H}" fill="url(#grid)"/>',
     '<text x="40" y="46" font-size="26" font-weight="700" fill="#f8fafc">VOSS ERD — PostgreSQL 16 · 테이블 3 · 컬럼 38 (01_schema.sql + 20261012_sprint2_pallet.sql)</text>',
     '<text x="40" y="76" font-size="14" fill="#94a3b8">NN = NOT NULL · \'\' = DEFAULT \'\' · CHECK = 허용값 제약. sort_log → pallet_log 는 box_id 논리 참조(스풀 지연 때문에 FK 를 걸지 않음), session_plan → sort_log 는 session_id 논리 참조.</text>']


def esc(s):
    return html.escape(s, quote=True)


for name, (desc, cols, idx) in TABLES.items():
    x, y = X[name], Y[name]
    h = (len(cols) + 2) * ROW + (ROW if idx else 0)
    o.append(f'<rect x="{x}" y="{y}" width="{TW}" height="{h}" rx="10" fill="#0b1220" stroke="#a78bfa" stroke-width="2"/>')
    o.append(f'<rect x="{x}" y="{y}" width="{TW}" height="{ROW + 6}" rx="10" fill="#2b1a5c"/>')
    o.append(f'<text x="{x + 14}" y="{y + 24}" font-size="18" font-weight="700" fill="#f8fafc">⛁ {esc(name)}</text>')
    o.append(f'<text x="{x + TW - 14}" y="{y + 24}" font-size="12" fill="#c4b5fd" text-anchor="end">{esc(desc)}</text>')
    hy = y + ROW + 6
    o.append(f'<rect x="{x}" y="{hy}" width="{TW}" height="{ROW - 6}" fill="#111827"/>')
    cx = x
    for head, w in zip(("컬럼", "타입", "키·제약", "의미 · 허용값"), COLW):
        o.append(f'<text x="{cx + 10}" y="{hy + 17}" font-size="12" font-weight="700" fill="#94a3b8">{head}</text>')
        cx += w
    ry = hy + ROW - 6
    for i, (c, t, k, m) in enumerate(cols):
        fill = "#0f172a" if i % 2 else "#0b1220"
        o.append(f'<rect x="{x}" y="{ry}" width="{TW}" height="{ROW}" fill="{fill}"/>')
        kc = "#fcd34d" if "PK" in k else "#cbd5e1"
        cx = x
        for val, w, col, bold in ((c, COLW[0], "#f8fafc", "700" if "PK" in k else "500"), (t, COLW[1], "#7dd3fc", "400"), (k, COLW[2], kc, "400"), (m, COLW[3], "#cbd5e1", "400")):
            o.append(f'<text x="{cx + 10}" y="{ry + 20}" font-size="13" font-weight="{bold}" fill="{col}">{esc(val)}</text>')
            cx += w
        ry += ROW
    if idx:
        o.append(f'<text x="{x + 10}" y="{ry + 20}" font-size="12" fill="#94a3b8">{esc(idx)}</text>')

# 관계선 (crow's foot)
x1 = X["sort_log"] + TW
y1 = Y["sort_log"] + ROW + 6 + ROW - 6 + ROW / 2  # box_id 행
x2 = X["pallet_log"]
y2 = Y["pallet_log"] + ROW + 6 + ROW - 6 + ROW + ROW / 2  # box_id 행 (2번째)
mid = (x1 + x2) / 2 - 40
o.append(f'<path d="M{x1} {y1} L{mid} {y1} L{mid} {y2} L{x2 - 16} {y2}" fill="none" stroke="#a78bfa" stroke-width="2.5" stroke-dasharray="8 6"/>')
o.append(f'<path d="M{x2 - 16} {y2} L{x2} {y2 - 9} M{x2 - 16} {y2} L{x2} {y2} M{x2 - 16} {y2} L{x2} {y2 + 9}" stroke="#a78bfa" stroke-width="2.5" fill="none"/>')
o.append(f'<path d="M{x1 + 8} {y1 - 9} L{x1 + 8} {y1 + 9}" stroke="#a78bfa" stroke-width="2.5"/>')
o.append(f'<rect x="{mid - 120}" y="{(y1 + y2) / 2 + 30}" width="240" height="48" rx="6" fill="{BG}" stroke="#a78bfa" stroke-opacity="0.5"/>')
o.append(f'<text x="{mid}" y="{(y1 + y2) / 2 + 49}" font-size="13" fill="#c4b5fd" text-anchor="middle">1 : N (논리) box_id</text>')
o.append(f'<text x="{mid}" y="{(y1 + y2) / 2 + 68}" font-size="12" fill="#94a3b8" text-anchor="middle">세션 적재 기록 → 팔레트 이동</text>')
# session_plan → sort_log (session_id)
x3 = X["session_plan"]
y3 = Y["session_plan"] + ROW + 6 + ROW - 6 + ROW / 2
y4 = Y["sort_log"] + ROW + 6 + ROW - 6 + ROW + ROW / 2  # session_id 행
mid2 = mid + 80
o.append(f'<path d="M{x3} {y3} L{mid2} {y3} L{mid2} {y4} L{x1 + 16} {y4}" fill="none" stroke="#a78bfa" stroke-width="2.5" stroke-dasharray="8 6"/>')
o.append(f'<path d="M{x1 + 16} {y4} L{x1} {y4 - 9} M{x1 + 16} {y4} L{x1} {y4} M{x1 + 16} {y4} L{x1} {y4 + 9}" stroke="#a78bfa" stroke-width="2.5" fill="none"/>')
o.append(f'<rect x="{mid2 - 120}" y="{y3 - 90}" width="240" height="48" rx="6" fill="{BG}" stroke="#a78bfa" stroke-opacity="0.5"/>')
o.append(f'<text x="{mid2}" y="{y3 - 71}" font-size="13" fill="#c4b5fd" text-anchor="middle">1 : N (논리) session_id</text>')
o.append(f'<text x="{mid2}" y="{y3 - 52}" font-size="12" fill="#94a3b8" text-anchor="middle">next → 첫 state 수신 시 세션에 붙임</text>')
o.append(f'<text x="{W - 40}" y="{H - 20}" font-size="13" fill="#64748b" text-anchor="end">근거: docker/db/init/01_schema.sql · 02_roles.sh · migrations/20261012_sprint2_pallet.sql · docker/web/backend PlanRepository</text>')
o.append("</svg>")
svg = "\n".join(o)
open("06_erd.svg", "w").write(svg)
cairosvg.svg2png(bytestring=svg.encode(), write_to="06_erd.png", scale=2)
print("ok")
