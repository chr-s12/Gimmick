"""Self-contained SVG bar charts for the usage reports (AC-07.3).

Built on the server so the app works offline (SRS 1.4.1), and styled inline so
a downloaded chart looks the same as on screen.
"""
from html import escape
from typing import Iterable, List, Sequence

WIDTH, HEIGHT = 720, 300
LEFT, RIGHT, TOP, BOTTOM = 48, 16, 36, 64
BAR, PEAK, GRID, TEXT, MUTED = "#9CA3AF", "#DC2626", "#E5E7EB", "#111827", "#4B5563"


def _niceMax(value: float) -> int:
    if value <= 5:
        return 5
    step = 10 ** (len(str(int(value))) - 1)
    for m in (1, 2, 2.5, 5, 10):
        if value <= m * step:
            return int(m * step)
    return int(value)


def barChart(title: str, labels: Sequence[str], values: Sequence[int], highlight: Iterable[int] = (),
             yLabel: str = "Visits") -> str:
    highlight = set(highlight)
    top = _niceMax(max(values, default=0))
    plotW, plotH = WIDTH - LEFT - RIGHT, HEIGHT - TOP - BOTTOM
    n = max(len(values), 1)
    slot = plotW / n
    barW = max(2.0, min(40.0, slot * 0.7))
    every = max(1, round(n / 14))   # thin out labels so they never overlap
    out: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}" '
        f'role="img" aria-label="{escape(title)}" font-family="Segoe UI, Arial, sans-serif">',
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#FFFFFF"/>',
        f'<text x="{LEFT}" y="22" font-size="15" font-weight="600" fill="{TEXT}">{escape(title)}</text>',
    ]
    for i in range(5):
        value = top * i / 4
        y = TOP + plotH - plotH * i / 4
        out.append(f'<line x1="{LEFT}" y1="{y:.1f}" x2="{WIDTH - RIGHT}" y2="{y:.1f}" stroke="{GRID}"/>')
        out.append(f'<text x="{LEFT - 8}" y="{y + 4:.1f}" font-size="11" text-anchor="end" fill="{MUTED}">'
                   f'{value:g}</text>')
    for i, (label, value) in enumerate(zip(labels, values)):
        h = plotH * value / top if top else 0
        x = LEFT + slot * i + (slot - barW) / 2
        y = TOP + plotH - h
        colour = PEAK if i in highlight else BAR
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{barW:.1f}" height="{h:.1f}" rx="2" fill="{colour}">'
                   f'<title>{escape(label)}: {value}</title></rect>')
        if i % every == 0:
            cx = x + barW / 2
            out.append(f'<text x="{cx:.1f}" y="{TOP + plotH + 16}" font-size="11" text-anchor="end" fill="{MUTED}" '
                       f'transform="rotate(-35 {cx:.1f} {TOP + plotH + 16})">{escape(label)}</text>')
    out.append(f'<text x="14" y="{TOP + plotH / 2:.1f}" font-size="11" fill="{MUTED}" text-anchor="middle" '
               f'transform="rotate(-90 14 {TOP + plotH / 2:.1f})">{escape(yLabel)}</text>')
    if highlight:
        out.append(f'<rect x="{WIDTH - 150}" y="12" width="10" height="10" fill="{PEAK}"/>'
                   f'<text x="{WIDTH - 135}" y="21" font-size="11" fill="{MUTED}">Busiest</text>')
    out.append("</svg>")
    return "".join(out)
