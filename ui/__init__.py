"""ui/ — presentation layer for the 2026-05 redesign.

Modules:
    design_system   — tokens, theme injector, component helpers (copy of common/ui_design_system.py)
    sidebar         — render_sidebar() + render_top_bar() — sibling-family left rail + topbar
    overrides       — Streamlit widget CSS overrides that shadow the default Streamlit look
"""
from .design_system import inject_theme, tokens, ACCENTS, kpi_tile, signal_badge, data_source_badge
from .sidebar import (
    current_user_level,
    level_label,
    render_sidebar,
    render_top_bar,
    page_header,
    macro_strip,
    segmented_control,
    hero_signal_card_html,
    hero_signal_cards_row,
    watchlist_card,
    backtest_preview_card,
    regime_card_html,
    regime_cards_grid,
    coin_picker,
    signal_hero_detail_card,
    composite_score_card,
    indicator_card,
    signal_history_table,
    regime_state_bar,
    macro_regime_overlay_card,
    regime_weights_grid,
    backtest_controls_row,
    backtest_kpi_strip,
    optuna_top_card,
    recent_trades_card,
)
from .overrides import inject_streamlit_overrides
from .plotly_template import (
    register_default as register_plotly_template,
    template_for as plotly_template_for,
    apply as apply_plotly_template,
    colors as plotly_colors,
)

__all__ = [
    "inject_theme",
    "tokens",
    "ACCENTS",
    "kpi_tile",
    "signal_badge",
    "data_source_badge",
    "current_user_level",
    "level_label",
    "render_sidebar",
    "render_top_bar",
    "page_header",
    "macro_strip",
    "segmented_control",
    "hero_signal_card_html",
    "hero_signal_cards_row",
    "watchlist_card",
    "backtest_preview_card",
    "regime_card_html",
    "regime_cards_grid",
    "coin_picker",
    "signal_hero_detail_card",
    "composite_score_card",
    "indicator_card",
    "signal_history_table",
    "regime_state_bar",
    "macro_regime_overlay_card",
    "regime_weights_grid",
    "backtest_controls_row",
    "backtest_kpi_strip",
    "optuna_top_card",
    "recent_trades_card",
    "inject_streamlit_overrides",
    "register_plotly_template",
    "plotly_template_for",
    "apply_plotly_template",
    "plotly_colors",
]
