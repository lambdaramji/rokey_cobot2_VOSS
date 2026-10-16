"""VOSS 아키텍처 도면용 SVG 생성기 (Archify 다크 프리셋과 같은 시각 언어).

노드·존·엣지를 좌표로 적어 SVG 를 만들고 cairosvg 로 PNG 를 낸다.
글꼴은 Noto Sans CJK KR 하나만 쓴다 (cairo 폰트 폴백이 한글 mono 를 못 찾는다).
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field

FONT = "Noto Sans CJK KR, Noto Sans KR, sans-serif"
BG = "#020617"
GRID = "#0b1220"

KIND = {  # fill, stroke, 아이콘 글리프
    "ros": ("#06241f", "#34d399", "‹›"),
    "core": ("#0a2d26", "#6ee7b7", "‹›"),
    "front": ("#0b2545", "#38bdf8", "▭"),
    "db": ("#2b1a5c", "#a78bfa", "⛁"),
    "broker": ("#3b2a12", "#f59e0b", "≡"),
    "safety": ("#4a1631", "#f472b6", "⛨"),
    "ext": ("#111827", "#94a3b8", "⧉"),
    "hw": ("#1f2937", "#cbd5e1", "⚙"),
    "ai": ("#2a1f4f", "#c084fc", "✦"),
    "ctn": ("#0f1f2e", "#60a5fa", "▣"),
}

EDGE = {  # stroke, dash, 라벨 글자색
    "topic": ("#94a3b8", "", "#cbd5e1"),
    "srv": ("#34d399", "", "#6ee7b7"),
    "action": ("#34d399", "", "#6ee7b7"),
    "stop": ("#f472b6", "8 6", "#f9a8d4"),
    "http": ("#38bdf8", "2 5", "#7dd3fc"),
    "mqtt": ("#f59e0b", "", "#fcd34d"),
    "sql": ("#a78bfa", "", "#c4b5fd"),
    "bus": ("#cbd5e1", "", "#e2e8f0"),
    "ghost": ("#475569", "4 6", "#94a3b8"),
}


@dataclass
class Node:
    id: str
    x: float
    y: float
    w: float
    h: float
    title: str
    sub: str = ""
    kind: str = "ros"
    lines: list[str] = field(default_factory=list)  # 작은 글씨 추가 줄

    @property
    def cx(self):
        return self.x + self.w / 2

    @property
    def cy(self):
        return self.y + self.h / 2

    def port(self, side: str, t: float = 0.5):
        """side: l r t b, t: 0~1 위치."""
        if side == "l":
            return (self.x, self.y + self.h * t)
        if side == "r":
            return (self.x + self.w, self.y + self.h * t)
        if side == "t":
            return (self.x + self.w * t, self.y)
        return (self.x + self.w * t, self.y + self.h)


@dataclass
class Zone:
    x: float
    y: float
    w: float
    h: float
    label: str
    color: str = "#f5c542"


@dataclass
class Edge:
    pts: list[tuple[float, float]]
    label: str = ""
    kind: str = "topic"
    lab_at: tuple[float, float] | None = None  # 라벨 중심 (없으면 가장 긴 선분 중앙)
    both: bool = False
    width: float = 2.0
    anchor: str = "middle"


def esc(s):
    return html.escape(s, quote=True)


def _lab_pos(pts):
    best = None
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        L = abs(x2 - x1) + abs(y2 - y1)
        if best is None or L > best[0]:
            best = (L, ((x1 + x2) / 2, (y1 + y2) / 2))
    return best[1]


def text_w(s, size):
    """대략적인 글자 폭 (한글 1.0em, 영문 0.56em)."""
    w = 0
    for ch in s:
        w += size * (1.0 if ord(ch) > 0x2E7F else 0.56)
    return w


def render(width, height, title, nodes, zones, edges, legend, notes=None, out="out", yoff=70):
    o = []
    o.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" font-family="{FONT}">'
    )
    o.append("<defs>")
    for k, (stroke, dash, _) in EDGE.items():
        o.append(
            f'<marker id="arr-{k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto-start-reverse">'
            f'<path d="M1 1 L9 5 L1 9 z" fill="{stroke}"/></marker>'
        )
    o.append(
        f'<pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0 H0 V40" fill="none" stroke="{GRID}" stroke-width="1"/></pattern>'
    )
    o.append("</defs>")
    o.append(f'<rect width="{width}" height="{height}" fill="{BG}"/>')
    o.append(f'<rect width="{width}" height="{height}" fill="url(#grid)"/>')
    # title
    o.append(f'<text x="40" y="46" font-size="26" font-weight="700" fill="#f8fafc">{esc(title)}</text>')
    o.append(f'<g transform="translate(0,{yoff})">')
    # zones
    for z in zones:
        o.append(
            f'<rect x="{z.x}" y="{z.y}" width="{z.w}" height="{z.h}" rx="18" fill="{z.color}" fill-opacity="0.035" stroke="{z.color}" stroke-width="2" stroke-dasharray="10 7"/>'
        )
        tw = text_w(z.label, 16) + 24
        o.append(
            f'<rect x="{z.x + 14}" y="{z.y - 14}" width="{tw}" height="28" rx="6" fill="{BG}" stroke="{z.color}" stroke-width="1.2"/>'
        )
        o.append(
            f'<text x="{z.x + 26}" y="{z.y + 5}" font-size="16" font-weight="700" fill="{z.color}">{esc(z.label)}</text>'
        )
    # edges
    for e in edges:
        stroke, dash, lcol = EDGE[e.kind]
        d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in e.pts)
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        mk = f' marker-end="url(#arr-{e.kind})"' + (f' marker-start="url(#arr-{e.kind})"' if e.both else "")
        o.append(
            f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="{e.width}" stroke-linejoin="round"{dash_attr}{mk}/>'
        )
    # edge labels (위에 그려야 선이 글자를 안 가림)
    for e in edges:
        if not e.label:
            continue
        stroke, dash, lcol = EDGE[e.kind]
        lx, ly = e.lab_at or _lab_pos(e.pts)
        lines = e.label.split("\n")
        fs = 13
        tw = max(text_w(s, fs) for s in lines) + 16
        th = len(lines) * (fs + 4) + 6
        if e.anchor == "start":
            bx = lx
        elif e.anchor == "end":
            bx = lx - tw
        else:
            bx = lx - tw / 2
        o.append(
            f'<rect x="{bx:.1f}" y="{ly - th / 2:.1f}" width="{tw:.1f}" height="{th}" rx="5" fill="{BG}" fill-opacity="0.93" stroke="{stroke}" stroke-opacity="0.45" stroke-width="1"/>'
        )
        for i, s in enumerate(lines):
            ty = ly - th / 2 + 3 + (i + 1) * (fs + 4) - 4
            tx = bx + 8
            o.append(f'<text x="{tx:.1f}" y="{ty:.1f}" font-size="{fs}" fill="{lcol}">{esc(s)}</text>')
    # nodes
    for n in nodes:
        fill, stroke, glyph = KIND[n.kind]
        o.append(
            f'<rect x="{n.x}" y="{n.y}" width="{n.w}" height="{n.h}" rx="12" fill="{fill}" stroke="{stroke}" stroke-width="2.2"/>'
        )
        o.append(f'<text x="{n.x + 12}" y="{n.y + 22}" font-size="15" fill="{stroke}">{esc(glyph)}</text>')
        ty = n.y + (n.h / 2 if not n.lines else 36)
        if n.lines:
            ty = n.y + 34
        elif n.sub:
            ty = n.y + n.h / 2 - 2
        o.append(
            f'<text x="{n.cx}" y="{ty}" font-size="19" font-weight="700" fill="#f8fafc" text-anchor="middle">{esc(n.title)}</text>'
        )
        if n.sub:
            o.append(
                f'<text x="{n.cx}" y="{ty + 22}" font-size="13.5" fill="#cbd5e1" text-anchor="middle">{esc(n.sub)}</text>'
            )
        for i, s in enumerate(n.lines):
            o.append(
                f'<text x="{n.cx}" y="{ty + 22 + (i + 1) * 17}" font-size="12.5" fill="#94a3b8" text-anchor="middle">{esc(s)}</text>'
            )
    o.append('</g>')
    # legend
    lx, ly = 40, height - 24 - 24 * ((len(legend) + 5) // 6)
    o.append(f'<text x="{lx}" y="{ly - 10}" font-size="15" font-weight="700" fill="#f8fafc">Legend</text>')
    cx = lx
    cy = ly + 8
    for i, (kind, label, is_edge) in enumerate(legend):
        if i and i % 6 == 0:
            cx = lx
            cy += 24
        if is_edge:
            stroke, dash, _ = EDGE[kind]
            dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
            o.append(f'<path d="M{cx} {cy} L{cx + 34} {cy}" stroke="{stroke}" stroke-width="2.5"{dash_attr}/>')
        else:
            fill, stroke, _ = KIND[kind]
            o.append(
                f'<rect x="{cx}" y="{cy - 8}" width="34" height="16" rx="4" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
            )
        o.append(f'<text x="{cx + 42}" y="{cy + 5}" font-size="14" fill="#cbd5e1">{esc(label)}</text>')
        cx += 42 + text_w(label, 14) + 36
    if notes:
        for i, s in enumerate(notes):
            o.append(
                f'<text x="{width - 40}" y="{height - 24 - (len(notes) - 1 - i) * 20}" font-size="13" fill="#64748b" text-anchor="end">{esc(s)}</text>'
            )
    o.append("</svg>")
    svg = "\n".join(o)
    with open(out + ".svg", "w") as f:
        f.write(svg)
    import cairosvg

    cairosvg.svg2png(bytestring=svg.encode(), write_to=out + ".png", scale=2)
    return svg
