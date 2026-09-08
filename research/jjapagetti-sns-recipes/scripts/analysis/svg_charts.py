# -*- coding: utf-8 -*-
"""Inline-SVG chart helpers following the dataviz mark specs (thin marks, rounded data-ends,
2px surface gaps, hairline grid, text in text tokens, legend for >=2 series, hover tooltips via <title>)."""
import math
from html import escape

SERIES_VARS = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)"]  # blue, orange, aqua, yellow (validated order)


def _nice_max(v):
    if v <= 0:
        return 1
    exp = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 2.5, 5, 10):
        if v <= m * exp:
            return m * exp
    return 10 * exp


def _ticks(vmax, n=4):
    step = vmax / n
    return [round(step * i) for i in range(n + 1)]


def _rounded_bar_h(x, y, w, h, r=4):
    """Horizontal bar growing from x (baseline, square) to x+w (rounded end)."""
    if w <= 0:
        return ""
    r = min(r, w, h / 2)
    return (f"M{x:.1f},{y:.1f} H{x + w - r:.1f} a{r},{r} 0 0 1 {r},{r} V{y + h - r:.1f} "
            f"a{r},{r} 0 0 1 -{r},{r} H{x:.1f} Z")


def _rounded_bar_v(x, y, w, h, r=4):
    """Vertical column from baseline y+h (square) up to y (rounded cap)."""
    if h <= 0:
        return ""
    r = min(r, h, w / 2)
    return (f"M{x:.1f},{y + h:.1f} V{y + r:.1f} a{r},{r} 0 0 1 {r},-{r} H{x + w - r:.1f} "
            f"a{r},{r} 0 0 1 {r},{r} V{y + h:.1f} Z")


def hbar_chart(rows, title, value_label="건", width=760, bar_h=18, gap=8, label_w=230, top_n=None, color="var(--s1)"):
    """rows: list of (label, value[, sublabel]) sorted desc. Single series -> no legend."""
    if top_n:
        rows = rows[:top_n]
    n = len(rows)
    vmax = _nice_max(max((r[1] for r in rows), default=1))
    pad_l, pad_r, pad_t, pad_b = label_w, 56, 8, 26
    plot_w = width - pad_l - pad_r
    height = pad_t + n * (bar_h + gap) + pad_b
    out = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">']
    # grid
    for t in _ticks(vmax):
        x = pad_l + plot_w * t / vmax
        out.append(f'<line x1="{x:.1f}" y1="{pad_t}" x2="{x:.1f}" y2="{height - pad_b}" class="grid"/>')
        out.append(f'<text x="{x:.1f}" y="{height - 8}" class="tick" text-anchor="middle">{t:,}</text>')
    for i, r in enumerate(rows):
        label, val = r[0], r[1]
        y = pad_t + i * (bar_h + gap)
        w = plot_w * val / vmax
        out.append(f'<text x="{pad_l - 10}" y="{y + bar_h * 0.72:.1f}" class="lbl" text-anchor="end">{escape(str(label))}</text>')
        out.append(f'<path d="{_rounded_bar_h(pad_l, y, w, bar_h)}" fill="{color}"><title>{escape(str(label))}: {val:,}{value_label}</title></path>')
        out.append(f'<text x="{pad_l + w + 6:.1f}" y="{y + bar_h * 0.72:.1f}" class="val">{val:,}</text>')
    out.append(f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{height - pad_b}" class="axis"/>')
    out.append("</svg>")
    return "\n".join(out)


def grouped_hbar_chart(rows, series_names, title, width=760, bar_h=12, inner_gap=2, group_gap=12, label_w=230):
    """rows: list of (label, [v1, v2, ...]) ; up to 4 series."""
    n = len(rows)
    k = len(series_names)
    vmax = _nice_max(max((max(r[1]) for r in rows), default=1))
    pad_l, pad_r, pad_t, pad_b = label_w, 56, 30, 26
    plot_w = width - pad_l - pad_r
    group_h = k * bar_h + (k - 1) * inner_gap
    height = pad_t + n * (group_h + group_gap) + pad_b
    out = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">']
    # legend
    lx = pad_l
    for j, s in enumerate(series_names):
        out.append(f'<rect x="{lx}" y="6" width="12" height="12" rx="2" fill="{SERIES_VARS[j]}"/>')
        out.append(f'<text x="{lx + 17}" y="16" class="lbl">{escape(s)}</text>')
        lx += 17 + 9 * len(s) + 24
    for t in _ticks(vmax):
        x = pad_l + plot_w * t / vmax
        out.append(f'<line x1="{x:.1f}" y1="{pad_t}" x2="{x:.1f}" y2="{height - pad_b}" class="grid"/>')
        out.append(f'<text x="{x:.1f}" y="{height - 8}" class="tick" text-anchor="middle">{t:,}</text>')
    for i, (label, vals) in enumerate(rows):
        y0 = pad_t + i * (group_h + group_gap)
        out.append(f'<text x="{pad_l - 10}" y="{y0 + group_h / 2 + 4:.1f}" class="lbl" text-anchor="end">{escape(str(label))}</text>')
        for j, v in enumerate(vals):
            y = y0 + j * (bar_h + inner_gap)
            w = plot_w * v / vmax
            out.append(f'<path d="{_rounded_bar_h(pad_l, y, w, bar_h, r=3)}" fill="{SERIES_VARS[j]}"><title>{escape(str(label))} · {escape(series_names[j])}: {v:,}</title></path>')
            if j == 0 or v == max(vals):
                out.append(f'<text x="{pad_l + w + 5:.1f}" y="{y + bar_h * 0.8:.1f}" class="val small">{v:,}</text>')
    out.append(f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{height - pad_b}" class="axis"/>')
    out.append("</svg>")
    return "\n".join(out)


def line_chart(x_labels, series, title, width=760, height=280, label_every=2):
    """series: list of (name, [values]) ; <=4 series; legend + end labels; hover circles with <title>."""
    pad_l, pad_r, pad_t, pad_b = 44, 90, 30, 34
    plot_w, plot_h = width - pad_l - pad_r, height - pad_t - pad_b
    vmax = _nice_max(max(max(v) for _, v in series))
    n = len(x_labels)
    xs = [pad_l + plot_w * i / max(n - 1, 1) for i in range(n)]
    out = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">']
    lx = pad_l
    for j, (name, _) in enumerate(series):
        out.append(f'<line x1="{lx}" y1="12" x2="{lx + 14}" y2="12" stroke="{SERIES_VARS[j]}" stroke-width="2" stroke-linecap="round"/>')
        out.append(f'<text x="{lx + 19}" y="16" class="lbl">{escape(name)}</text>')
        lx += 19 + 9 * len(name) + 24
    for t in _ticks(vmax):
        y = pad_t + plot_h - plot_h * t / vmax
        out.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + plot_w}" y2="{y:.1f}" class="grid"/>')
        out.append(f'<text x="{pad_l - 8}" y="{y + 4:.1f}" class="tick" text-anchor="end">{t:,}</text>')
    for i, xl in enumerate(x_labels):
        if i % label_every == 0 or i == n - 1:
            out.append(f'<text x="{xs[i]:.1f}" y="{height - 10}" class="tick" text-anchor="middle">{escape(xl)}</text>')
    for j, (name, vals) in enumerate(series):
        pts = [(xs[i], pad_t + plot_h - plot_h * v / vmax) for i, v in enumerate(vals)]
        d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        area = d + f" L{pts[-1][0]:.1f},{pad_t + plot_h} L{pts[0][0]:.1f},{pad_t + plot_h} Z"
        out.append(f'<path d="{area}" fill="{SERIES_VARS[j]}" fill-opacity="0.08"/>')
        out.append(f'<path d="{d}" fill="none" stroke="{SERIES_VARS[j]}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')
        for i, (x, y) in enumerate(pts):
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{SERIES_VARS[j]}" stroke="var(--surface)" stroke-width="2" class="pt"><title>{escape(x_labels[i])} · {escape(name)}: {vals[i]:,}</title></circle>')
        out.append(f'<text x="{pts[-1][0] + 8:.1f}" y="{pts[-1][1] + 4:.1f}" class="val small">{escape(name)} {vals[-1]:,}</text>')
    out.append(f'<line x1="{pad_l}" y1="{pad_t + plot_h}" x2="{pad_l + plot_w}" y2="{pad_t + plot_h}" class="axis"/>')
    out.append("</svg>")
    return "\n".join(out)


def stacked_columns(x_labels, series, title, width=760, height=260, label_every=1):
    """Stacked columns (<=4 series) with 2px surface gaps; legend; per-segment <title>."""
    pad_l, pad_r, pad_t, pad_b = 44, 16, 30, 34
    plot_w, plot_h = width - pad_l - pad_r, height - pad_t - pad_b
    n = len(x_labels)
    totals = [sum(s[1][i] for s in series) for i in range(n)]
    vmax = _nice_max(max(totals) if totals else 1)
    slot = plot_w / n
    bw = min(24, slot * 0.6)
    out = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">']
    lx = pad_l
    for j, (name, _) in enumerate(series):
        out.append(f'<rect x="{lx}" y="6" width="12" height="12" rx="2" fill="{SERIES_VARS[j]}"/>')
        out.append(f'<text x="{lx + 17}" y="16" class="lbl">{escape(name)}</text>')
        lx += 17 + 9 * len(name) + 24
    for t in _ticks(vmax):
        y = pad_t + plot_h - plot_h * t / vmax
        out.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + plot_w}" y2="{y:.1f}" class="grid"/>')
        out.append(f'<text x="{pad_l - 8}" y="{y + 4:.1f}" class="tick" text-anchor="end">{t:,}</text>')
    for i, xl in enumerate(x_labels):
        x = pad_l + slot * i + (slot - bw) / 2
        ybase = pad_t + plot_h
        for j, (name, vals) in enumerate(series):
            v = vals[i]
            if v <= 0:
                continue
            h = plot_h * v / vmax
            top = ybase - h
            is_top = all(series[jj][1][i] <= 0 for jj in range(j + 1, len(series)))
            if is_top:
                out.append(f'<path d="{_rounded_bar_v(x, top, bw, h, r=3)}" fill="{SERIES_VARS[j]}"><title>{escape(xl)} · {escape(name)}: {v:,}</title></path>')
            else:
                out.append(f'<rect x="{x:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{max(h - 2, 0.5):.1f}" fill="{SERIES_VARS[j]}"><title>{escape(xl)} · {escape(name)}: {v:,}</title></rect>')
            ybase = top
        if totals[i] > 0:
            out.append(f'<text x="{x + bw / 2:.1f}" y="{ybase - 5:.1f}" class="val small" text-anchor="middle">{totals[i]:,}</text>')
        if i % label_every == 0:
            out.append(f'<text x="{x + bw / 2:.1f}" y="{height - 10}" class="tick" text-anchor="middle">{escape(xl)}</text>')
    out.append(f'<line x1="{pad_l}" y1="{pad_t + plot_h}" x2="{pad_l + plot_w}" y2="{pad_t + plot_h}" class="axis"/>')
    out.append("</svg>")
    return "\n".join(out)
