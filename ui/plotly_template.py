"""
ui/plotly_template.py — central Plotly theming for the 2026-05 redesign.

Exposes one registered Plotly template ("signal_dark" / "signal_light") that
mirrors the design-system tokens defined in ui/design_system.py — same
backgrounds, same Inter / JetBrains Mono fonts, same accent + semantic
colorway, same gridline color.

Usage at app startup:

    from ui.plotly_template import register_default
    register_default(theme="dark")  # or "light"

After this call, every Plotly figure created in the process inherits the
signal template by default. Per-chart `update_layout(...)` calls still win
over template defaults, so existing inline overrides keep working.

To rebuild the template (e.g., on theme toggle), call register_default again
with the new theme — `pio.templates.default` flips and new figures pick it up.
"""
from __future__ import annotations

from typing import Literal

try:
    import plotly.graph_objects as go
    import plotly.io as pio
except ImportError:  # pragma: no cover — plotly is a runtime dep
    go = None  # type: ignore
    pio = None  # type: ignore


# ── Token snapshot ─────────────────────────────────────────────────────
# Mirrors ui.design_system.SIBLING_DARK / SIBLING_LIGHT + the per-app accent
# from ACCENTS["crypto-signal-app"]. Kept in this module rather than imported
# so the file is self-contained and the surface for charts is one tiny dict
# per theme — easy to read in diffs, easy to swap if the design tokens move.
_FONT_UI = "Inter, system-ui, -apple-system, sans-serif"
_FONT_MONO = "JetBrains Mono, ui-monospace, monospace"

_TOKENS: dict[str, dict[str, str]] = {
    "dark": {
        "bg_0":           "#0a0a0f",
        "bg_1":           "#121218",
        "bg_2":           "#1a1a22",
        "text_primary":   "#e8e8f0",
        "text_secondary": "#8a8a9d",
        "text_muted":     "#5d5d6e",
        "border":         "#2a2a34",
        "border_strong":  "#3d3d4a",
        "accent":         "#22d36f",   # crypto-signal accent (signal-green)
        "success":        "#22c55e",
        "danger":         "#ef4444",
        "warning":        "#f59e0b",
        "info":           "#3b82f6",
    },
    "light": {
        "bg_0":           "#fafafb",
        "bg_1":           "#ffffff",
        "bg_2":           "#f5f5f7",
        "text_primary":   "#0f1014",
        "text_secondary": "#545660",
        "text_muted":     "#8b8d96",
        "border":         "#e8e9ed",
        "border_strong":  "#d1d3d9",
        "accent":         "#22d36f",
        "success":        "#22c55e",
        "danger":         "#ef4444",
        "warning":        "#f59e0b",
        "info":           "#3b82f6",
    },
}


def _build_layout(theme: Literal["dark", "light"]) -> "go.Layout":
    """Build the Plotly Layout object for the requested theme."""
    if go is None:
        raise RuntimeError("plotly is required to build the signal template")
    t = _TOKENS.get(theme, _TOKENS["dark"])

    # Transparent paper/plot bg: charts sit inside .ds-card containers that
    # already have the design-system background, so making the chart bg
    # transparent lets the card fill show through (no double-layer mismatch
    # when toggling themes).
    return go.Layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(
            family=_FONT_UI,
            color=t["text_secondary"],
            size=12,
        ),
        title=dict(
            font=dict(
                family=_FONT_UI,
                color=t["text_primary"],
                size=14,
            ),
            x=0.0, xanchor="left",
            y=0.98, yanchor="top",
        ),
        xaxis=dict(
            gridcolor=t["border"],
            linecolor=t["border"],
            zerolinecolor=t["border"],
            tickfont=dict(
                family=_FONT_MONO,
                color=t["text_muted"],
                size=11,
            ),
            title=dict(font=dict(family=_FONT_UI, color=t["text_muted"], size=11)),
        ),
        yaxis=dict(
            gridcolor=t["border"],
            linecolor=t["border"],
            zerolinecolor=t["border"],
            tickfont=dict(
                family=_FONT_MONO,
                color=t["text_muted"],
                size=11,
            ),
            title=dict(font=dict(family=_FONT_UI, color=t["text_muted"], size=11)),
        ),
        legend=dict(
            font=dict(family=_FONT_UI, color=t["text_secondary"], size=11),
            bgcolor="rgba(0,0,0,0)",
            bordercolor=t["border"],
            borderwidth=0,
        ),
        # Colorway ordered: accent → info → warning → danger → success →
        # secondary text. Charts that need explicit semantic colors should
        # still pass them inline (e.g., red for sell, green for buy); this
        # ordering is for unspecified series.
        colorway=[
            t["accent"],
            t["info"],
            t["warning"],
            t["danger"],
            t["success"],
            t["text_secondary"],
        ],
        margin=dict(l=8, r=8, t=24, b=8),
        hoverlabel=dict(
            bgcolor=t["bg_2"],
            bordercolor=t["border"],
            font=dict(family=_FONT_MONO, color=t["text_primary"], size=11),
        ),
    )


def template_for(theme: Literal["dark", "light"] = "dark") -> str:
    """Lazily build + register the signal_<theme> Plotly template.

    Returns the template name. Subsequent calls are cheap (idempotent).
    """
    if pio is None:
        return "plotly_dark"  # graceful fallback — keeps callers working
    name = f"signal_{theme}"
    if name not in pio.templates:
        pio.templates[name] = go.layout.Template(layout=_build_layout(theme))
    return name


def register_default(theme: Literal["dark", "light"] = "dark") -> str:
    """Register the signal template and set it as the Plotly default.

    Call once at app startup, and again whenever the theme toggles.
    Every figure created after the call inherits the template; explicit
    `update_layout(...)` calls per chart still override.
    """
    name = template_for(theme)
    if pio is not None:
        pio.templates.default = name
    return name


def apply(fig: "go.Figure", theme: Literal["dark", "light"] = "dark") -> "go.Figure":
    """Apply the signal template to an existing figure (additive).

    Useful for charts already built before register_default() ran.
    """
    fig.update_layout(template=template_for(theme))
    return fig


def colors(theme: Literal["dark", "light"] = "dark") -> dict[str, str]:
    """Return the token dict for the given theme — handy when a chart needs
    a specific accent / success / danger color from inline code."""
    return dict(_TOKENS.get(theme, _TOKENS["dark"]))


__all__ = [
    "template_for",
    "register_default",
    "apply",
    "colors",
]
