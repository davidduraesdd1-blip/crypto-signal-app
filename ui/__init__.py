"""ui/ — presentation layer for the 2026-05 redesign.

Modules:
    design_system   — tokens, theme injector, component helpers (copy of common/ui_design_system.py)
    sidebar         — render_sidebar() + render_top_bar() — sibling-family left rail + topbar
    overrides       — Streamlit widget CSS overrides that shadow the default Streamlit look
"""
from .design_system import inject_theme, tokens, ACCENTS, kpi_tile, signal_badge, data_source_badge
from .sidebar import (
    render_sidebar,
    render_top_bar,
    page_header,
    macro_strip,
    hero_signal_card_html,
    hero_signal_cards_row,
    watchlist_card,
    backtest_preview_card,
    regime_card_html,
    regime_cards_grid,
)
from .overrides import inject_streamlit_overrides

__all__ = [
    "inject_theme",
    "tokens",
    "ACCENTS",
    "kpi_tile",
    "signal_badge",
    "data_source_badge",
    "render_sidebar",
    "render_top_bar",
    "page_header",
    "macro_strip",
    "hero_signal_card_html",
    "hero_signal_cards_row",
    "watchlist_card",
    "backtest_preview_card",
    "regime_card_html",
    "regime_cards_grid",
    "inject_streamlit_overrides",
]
