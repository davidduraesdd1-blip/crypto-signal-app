"""
pdf_export.py — PDF report generation for Crypto Signal Model v5.9.13
Uses reportlab to build scan and backtest PDF reports.
"""

import io
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)


# ── Color palette (matches dark theme) ──
TEAL   = colors.HexColor("#00d4aa")
DARK   = colors.HexColor("#0d0e14")
MID    = colors.HexColor("#111827")
TEXT   = colors.HexColor("#f8fafc")
GREEN  = colors.HexColor("#22c55e")
RED    = colors.HexColor("#ef4444")
ORANGE = colors.HexColor("#f59e0b")
GREY   = colors.HexColor("#94a3b8")
WHITE  = colors.white
BLACK  = colors.black


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title", parent=base["Title"],
            fontSize=18, textColor=TEAL, spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "subtitle", parent=base["Normal"],
            fontSize=10, textColor=GREY, spaceAfter=12,
        ),
        "section": ParagraphStyle(
            "section", parent=base["Heading2"],
            fontSize=13, textColor=TEAL, spaceBefore=14, spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body", parent=base["Normal"],
            fontSize=9, textColor=BLACK, spaceAfter=4,
        ),
        "footer": ParagraphStyle(
            "footer", parent=base["Normal"],
            fontSize=7, textColor=GREY,
        ),
    }


def _signal_table_style(num_rows):
    """TableStyle for the main signal table."""
    style = [
        # Header row
        ("BACKGROUND", (0, 0), (-1, 0), TEAL),
        ("TEXTCOLOR",  (0, 0), (-1, 0), BLACK),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, 0), 8),
        ("ALIGN",      (0, 0), (-1, 0), "CENTER"),
        # Body rows
        ("FONTSIZE",   (0, 1), (-1, -1), 7.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f8fafc"), WHITE]),
        ("ALIGN",      (1, 1), (-1, -1), "CENTER"),
        ("ALIGN",      (0, 1), (0, -1), "LEFT"),
        # Grid
        ("GRID",       (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
    ]
    return TableStyle(style)


def _direction_label(direction: str) -> str:
    mapping = {
        "STRONG BUY": "STR BUY",
        "BUY":        "BUY",
        "STRONG SELL":"STR SELL",
        "SELL":       "SELL",
        "NEUTRAL":    "NEUTRAL",
    }
    if not isinstance(direction, str):
        return "—"
    for k, v in mapping.items():
        if k in direction:
            return v
    return direction[:8]


def generate_scan_pdf(results: list, scan_timestamp: str = None) -> bytes:
    """
    Build a PDF report from scan results.
    Returns raw PDF bytes suitable for st.download_button().
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
    )
    styles = _styles()
    story = []

    # ── Title ──
    ts = scan_timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    story.append(Paragraph("Crypto Signal Model v5.9.13 — Scan Report", styles["title"]))
    story.append(Paragraph(f"Generated: {ts}  |  Pairs scanned: {len(results)}", styles["subtitle"]))
    story.append(HRFlowable(width="100%", thickness=1, color=TEAL, spaceAfter=10))

    if not results:
        story.append(Paragraph("No scan results available.", styles["body"]))
        doc.build(story)
        return buf.getvalue()

    # ── Summary metrics ──
    story.append(Paragraph("Summary", styles["section"]))
    hc      = [r for r in results if r.get("high_conf")]
    buys    = [r for r in results if "BUY"  in r.get("direction", "")]
    sells   = [r for r in results if "SELL" in r.get("direction", "")]
    avg_conf = round(sum((r.get("confidence_avg_pct") or 0) for r in results) / len(results), 1)

    summary_data = [
        ["Metric", "Value"],
        ["Pairs Scanned",       str(len(results))],
        ["High-Confidence",     str(len(hc))],
        ["Buy Signals",         str(len(buys))],
        ["Sell Signals",        str(len(sells))],
        ["Average Confidence",  f"{avg_conf}%"],
    ]
    tbl = Table(summary_data, colWidths=[6 * cm, 4 * cm])
    tbl.setStyle(_signal_table_style(len(summary_data)))
    story.append(tbl)
    story.append(Spacer(1, 10))

    # ── High-confidence alerts ──
    if hc:
        pairs_str = ", ".join(r.get("pair", "?") for r in hc)
        story.append(Paragraph(f"HIGH-CONFIDENCE SIGNALS: {pairs_str}", styles["body"]))
        story.append(Spacer(1, 6))

    # ── Signal table ──
    story.append(Paragraph("All Signals", styles["section"]))

    headers = ["Pair", "Conf%", "Direction", "MTF%", "Price", "Entry", "Target", "Stop", "Strategy", "Regime", "HC"]
    col_w   = [3.0, 1.5, 2.2, 1.5, 2.8, 2.8, 2.8, 2.8, 2.8, 2.5, 1.0]
    col_w_cm = [w * cm for w in col_w]

    rows = [headers]
    # Sort: high-conf first, then by confidence descending
    sorted_results = sorted(results, key=lambda r: (r.get("high_conf", False), r.get("confidence_avg_pct", 0)), reverse=True)

    for r in sorted_results:
        price    = r.get("price_usd")
        entry    = r.get("entry")
        exit_tgt = r.get("exit")
        stop     = r.get("stop_loss")
        rows.append([
            r.get("pair", "?"),
            f"{r.get('confidence_avg_pct', 0)}%",
            _direction_label(r.get("direction", "—")),
            f"{r.get('mtf_alignment', 0)}%",
            f"${price:,.4f}"    if price    is not None else "—",
            f"${entry:,.4f}"   if entry    is not None else "—",
            f"${exit_tgt:,.4f}" if exit_tgt is not None else "—",
            f"${stop:,.4f}"    if stop     is not None else "—",
            (r.get("strategy_bias") or "—")[:10],
            (r.get("regime") or "—")[:10],
            "YES" if r.get("high_conf") else "",
        ])

    tbl2 = Table(rows, colWidths=col_w_cm)
    style2 = _signal_table_style(len(rows))

    # Color direction cells (column 2, rows 1+)
    _DIR_COLORS = {
        "STRONG BUY":  "#d1fae5",
        "BUY":         "#d1fae5",
        "STRONG SELL": "#fecaca",
        "SELL":        "#fee2e2",
        "NEUTRAL":     "#f8fafc",  # explicit neutral — no tint
    }
    for i, r in enumerate(sorted_results, start=1):
        direction = r.get("direction", "")
        bg = None
        for key, hex_color in _DIR_COLORS.items():
            if key in direction:
                bg = hex_color
                break
        if bg is None:
            bg = "#f1f5f9"  # fallback for NO DATA / LOW VOL / unknown
        style2.add("BACKGROUND", (2, i), (2, i), colors.HexColor(bg))
        # High-conf row highlight
        if r.get("high_conf"):
            style2.add("FONTNAME", (0, i), (-1, i), "Helvetica-Bold")

    tbl2.setStyle(style2)
    story.append(tbl2)

    # ── Footer ──
    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=0.5, color=GREY))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Crypto Signal Model v5.9.13 — For informational purposes only. Not financial advice.",
        styles["footer"]
    ))

    doc.build(story)
    return buf.getvalue()


def generate_backtest_pdf(metrics: dict, trades_df, scan_timestamp: str = None) -> bytes:
    """
    Build a PDF report from backtest metrics and trade log.
    Returns raw PDF bytes suitable for st.download_button().
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
    )
    styles = _styles()
    story = []

    ts = scan_timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    story.append(Paragraph("Crypto Signal Model v5.9.13 — Backtest Report", styles["title"]))
    story.append(Paragraph(f"Generated: {ts}", styles["subtitle"]))
    story.append(HRFlowable(width="100%", thickness=1, color=TEAL, spaceAfter=10))

    # ── Metrics table ──
    if metrics:
        story.append(Paragraph("Performance Metrics", styles["section"]))
        metric_rows = [["Metric", "Value"]]
        metric_map = [
            ("Total Trades",       "total_trades"),
            ("Win Rate",           "win_rate",    "%"),
            ("Avg PnL/Trade",      "avg_pnl",     "%"),
            ("Total Return",       "total_return", "%"),
            ("Profit Factor",      "profit_factor"),
            ("Sharpe Ratio",       "sharpe"),
            ("Sortino Ratio",      "sortino"),
            ("Calmar Ratio",       "calmar"),
            ("Max Drawdown",       "max_drawdown", "%"),
            ("Max Consec Losses",  "max_consec_losses"),
            ("Expectancy/Trade",   "expectancy",  "%"),
            ("VaR (95%)",          "var_95",      "%"),
            ("CVaR (95%)",         "cvar_95",     "%"),
        ]
        for entry in metric_map:
            label = entry[0]
            key   = entry[1]
            suffix = entry[2] if len(entry) > 2 else ""
            val = metrics.get(key, "—")
            # BUG-R27: val can be Python None (not "N/A") when the metric was not computed.
            # f"{None}%" renders as "None%" in the PDF — use explicit check instead.
            if val is None or val == "N/A" or val == "":  # BUG-PDF01: empty string renders as "%" in PDF
                metric_rows.append([label, "N/A"])
            else:
                metric_rows.append([label, f"{val}{suffix}"])

        tbl_m = Table(metric_rows, colWidths=[7 * cm, 4 * cm])
        tbl_m.setStyle(_signal_table_style(len(metric_rows)))
        story.append(tbl_m)
        story.append(Spacer(1, 10))

    # ── Trade log table ──
    if trades_df is not None and not trades_df.empty:
        story.append(Paragraph("Trade Log", styles["section"]))

        cols_to_show = [c for c in ["pair", "direction", "entry", "exit",
                                     "pnl_pct", "pnl_usd", "exit_reason"] if c in trades_df.columns]
        if cols_to_show:
            header_labels = {
                "pair": "Pair", "direction": "Direction",
                "entry": "Entry", "exit": "Exit",
                "pnl_pct": "PnL %", "pnl_usd": "PnL USD",
                "exit_reason": "Exit Reason",
            }
            trade_rows = [[header_labels.get(c, c) for c in cols_to_show]]
            for _, row in trades_df.head(60).iterrows():   # cap at 60 rows to avoid huge PDFs
                trade_rows.append([str(row.get(c, "")) for c in cols_to_show])

            col_w2 = [max(3.5, 28 / len(cols_to_show)) * cm] * len(cols_to_show)
            tbl_t = Table(trade_rows, colWidths=col_w2)
            style_t = _signal_table_style(len(trade_rows))

            # Color PnL column
            if "pnl_pct" in cols_to_show:
                pnl_col = cols_to_show.index("pnl_pct")
                for i, (_, row) in enumerate(trades_df.head(60).iterrows(), start=1):
                    try:
                        # BUG-R21: pandas Series.get() returns None for missing keys,
                        # not the default 0.  float(None) would raise TypeError caught
                        # silently, disabling PnL coloring for the whole column.
                        v = float(row.get("pnl_pct") or 0)
                        style_t.add("TEXTCOLOR", (pnl_col, i), (pnl_col, i),
                                    GREEN if v > 0 else RED)
                    except Exception as _pnl_color_err:
                        logger.debug("[PDF] PnL color styling failed at row %d: %s", i, _pnl_color_err)

            tbl_t.setStyle(style_t)
            story.append(tbl_t)

            if len(trades_df) > 60:
                story.append(Spacer(1, 4))
                story.append(Paragraph(
                    f"(Showing first 60 of {len(trades_df)} trades — download CSV for full log)",
                    styles["footer"]
                ))

    # ── Footer ──
    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=0.5, color=GREY))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Crypto Signal Model v5.9.13 — For informational purposes only. Not financial advice.",
        styles["footer"]
    ))

    doc.build(story)
    return buf.getvalue()
