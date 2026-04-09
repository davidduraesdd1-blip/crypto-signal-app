"""
chart_component.py — TradingView Lightweight Charts HTML builder
Crypto Signal Model v5.9.13

Builds a self-contained HTML page with an embedded candlestick chart,
volume histogram, optional entry/stop/target price lines, and synchronized
RSI-14 + MACD(12,26,9) indicator panels.
Use with st.iframe(build_chart_html(...), height=560, scrolling=False).
"""

import html
import json
import math

_CDN = "https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"


# ── Indicator helpers (pure Python, no numpy required) ────────────────────

def _compute_rsi(time_close, period=14):
    """Wilder RSI-14. Returns [{time, value}] list."""
    if len(time_close) < period + 2:
        return []
    times  = [t for t, _ in time_close]
    prices = [p for _, p in time_close]
    diffs  = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains  = [max(d, 0.0) for d in diffs]
    losses = [max(-d, 0.0) for d in diffs]

    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period

    def _calc_rsi(g: float, l: float) -> float:
        # Wilder (1978): avg_l==0 and avg_g>0 → RSI=100 (all gains, no losses)
        # avg_g==0 and avg_l==0 → flat market → neutral RSI=50
        if l == 0:
            return 100.0 if g > 0 else 50.0
        return 100.0 - (100.0 / (1.0 + g / l))

    result = []
    _rsi = _calc_rsi(avg_g, avg_l)
    result.append({"time": times[period], "value": round(_rsi, 2)})

    for i in range(period, len(diffs)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
        _rsi = _calc_rsi(avg_g, avg_l)
        result.append({"time": times[i + 1], "value": round(_rsi, 2)})

    return result


def _ema(prices, period):
    """Exponential moving average list (same length offset as SMA seed)."""
    if len(prices) < period:
        return []
    k = 2.0 / (period + 1)
    ema = [sum(prices[:period]) / period]
    for p in prices[period:]:
        ema.append(ema[-1] + k * (p - ema[-1]))
    return ema


def _compute_macd(time_close, fast=12, slow=26, signal=9):
    """MACD(12,26,9). Returns (macd_data, signal_data, hist_data) as [{time,value}] lists."""
    if len(time_close) < slow + signal:
        return [], [], []
    times  = [t for t, _ in time_close]
    prices = [p for _, p in time_close]

    ema_fast = _ema(prices, fast)   # len = N-fast+1, starts at prices[fast-1]
    ema_slow = _ema(prices, slow)   # len = N-slow+1, starts at prices[slow-1]

    fast_offset = slow - fast       # align both to prices[slow-1]
    macd_line   = [f - s for f, s in zip(ema_fast[fast_offset:], ema_slow)]
    macd_times  = times[slow - 1:]

    sig_line    = _ema(macd_line, signal)
    sig_offset  = signal - 1
    sig_times   = macd_times[sig_offset:]

    hist = [m - s for m, s in zip(macd_line[sig_offset:], sig_line)]

    macd_data   = [{"time": t, "value": round(m, 8)} for t, m in zip(sig_times, macd_line[sig_offset:])]
    signal_data = [{"time": t, "value": round(s, 8)} for t, s in zip(sig_times, sig_line)]
    hist_data   = [
        {"time": t, "value": round(h, 8),
         "color": "rgba(0,212,170,0.65)" if h >= 0 else "rgba(255,75,75,0.65)"}
        for t, h in zip(sig_times, hist)
    ]
    return macd_data, signal_data, hist_data


def build_chart_html(
    ohlcv: list,
    pair: str,
    tf: str,
    entry: float = None,
    stop: float = None,
    target: float = None,
    height: int = 300,
) -> str:
    """
    Build a self-contained HTML page with a TradingView Lightweight Chart
    plus synchronized RSI-14 and MACD(12,26,9) indicator panels.

    Args:
        ohlcv:  ccxt-format OHLCV list — [[ts_ms, open, high, low, close, volume], ...]
        pair:   Trading pair label, e.g. 'BTC/USDT'
        tf:     Timeframe string, e.g. '1h'
        entry:  Entry price (dashed teal line)
        stop:   Stop loss price (dashed red line)
        target: Exit target price (dashed blue line)
        height: Main candlestick canvas height in pixels (indicator panel adds ~180 px)

    Returns:
        HTML string for use with st.iframe(html, height=560, scrolling=False).
    """
    # Escape for safe HTML/JS embedding (pair names like BTC/USDT are benign in
    # practice but escaping is correct defensively)
    pair_h = html.escape(pair)
    tf_h   = html.escape(tf)
    # JS-safe versions (escape single quotes for string literals in JS)
    pair_j = pair.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "\\r")
    tf_j   = tf.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "\\r")

    if not ohlcv:
        return (
            f"<div style='color:#888;font-family:monospace;padding:14px'>"
            f"No OHLCV data returned for {pair_h} {tf_h}</div>"
        )

    # ── Convert ccxt bars → lightweight-charts format ──────────────────────
    seen: set = set()
    candles: list = []
    volumes: list = []

    # CHART-02/03: filter bars with None fields before conversion to prevent TypeError
    valid_bars = [
        b for b in ohlcv
        if isinstance(b, (list, tuple)) and len(b) >= 5
        and b[0] is not None
        and all(x is not None for x in b[1:5])
    ]
    for bar in sorted(valid_bars, key=lambda b: b[0]):
        try:
            ts_ms = int(bar[0])
        except (TypeError, ValueError):
            continue
        if ts_ms in seen:
            continue
        seen.add(ts_ms)

        try:
            o = float(bar[1])
            h = float(bar[2])
            l = float(bar[3])
            c = float(bar[4])
            v = float(bar[5]) if len(bar) > 5 else 0.0
        except (TypeError, ValueError):
            continue
        t = ts_ms // 1000  # ms → seconds

        candles.append({"time": t, "open": o, "high": h, "low": l, "close": c})
        volumes.append({
            "time": t,
            "value": v,
            "color": "rgba(0,212,170,0.22)" if c >= o else "rgba(255,75,75,0.22)",
        })

    candles_json = json.dumps(candles)
    volumes_json = json.dumps(volumes)

    # ── Compute RSI + MACD from processed candle data ─────────────────────
    time_close  = [(c["time"], c["close"]) for c in candles]
    rsi_data    = _compute_rsi(time_close)
    macd_data, signal_data, hist_data = _compute_macd(time_close)

    rsi_json  = json.dumps(rsi_data)
    macd_json = json.dumps(macd_data)
    sig_json  = json.dumps(signal_data)
    hist_json = json.dumps(hist_data)

    # ── Price lines ─────────────────────────────────────────────────────────
    # LineStyle enum: 0=Solid, 1=Dotted, 2=Dashed, 3=LargeDashed, 4=SparseDotted
    price_lines_js = ""
    legend_parts: list = []

    def _safe_price(val) -> float | None:
        """Return a valid positive finite float, or None if unusable."""
        try:
            v = float(val)
        except (TypeError, ValueError):
            return None
        if math.isnan(v) or math.isinf(v) or v <= 0 or v > 1e12:
            return None
        return v

    _entry  = _safe_price(entry)
    _target = _safe_price(target)
    _stop   = _safe_price(stop)

    if _entry is not None:
        price_lines_js += f"""
  candleSeries.createPriceLine({{
    price: {_entry:.8f},
    color: '#00d4aa',
    lineWidth: 1,
    lineStyle: 2,
    title: 'Entry',
    axisLabelVisible: true,
  }});"""
        legend_parts.append('<span style="color:#00d4aa">&#9135; Entry</span>')

    if _target is not None:
        price_lines_js += f"""
  candleSeries.createPriceLine({{
    price: {_target:.8f},
    color: '#636EFA',
    lineWidth: 1,
    lineStyle: 2,
    title: 'Target',
    axisLabelVisible: true,
  }});"""
        legend_parts.append('<span style="color:#636EFA">&#9135; Target</span>')

    if _stop is not None:
        price_lines_js += f"""
  candleSeries.createPriceLine({{
    price: {_stop:.8f},
    color: '#ff4b4b',
    lineWidth: 1,
    lineStyle: 2,
    title: 'Stop',
    axisLabelVisible: true,
  }});"""
        legend_parts.append('<span style="color:#ff4b4b">&#9135; Stop</span>')

    legend_html  = "&nbsp;&nbsp;&nbsp;".join(legend_parts)
    ind_height   = 160   # fixed indicator panel height
    total_height = height + 46 + 22 + ind_height  # header + main + ind-bar + indicator

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #0e1117; font-family: monospace; overflow: hidden; }}
  #hdr {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 7px 10px 5px 10px;
    border-bottom: 1px solid #1a1d23;
  }}
  #title {{ color: #00d4aa; font-size: 13px; font-weight: bold; letter-spacing: 0.03em; }}
  #legend {{ font-size: 11px; color: #aaa; display: flex; gap: 14px; }}
  #chart {{ width: 100%; }}
  #ind-bar {{
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 2px 10px;
    border-top: 1px solid #1a1d23;
    background: #0e1117;
  }}
  #ind-bar span {{ font-size: 9px; letter-spacing: 0.04em; }}
  #indicators {{ width: 100%; }}
</style>
</head>
<body>
<div id="hdr">
  <span id="title">{pair_h} &middot; {tf_h}</span>
  <span id="legend">{legend_html}</span>
</div>
<div id="chart"></div>
<div id="ind-bar">
  <span style="color:#f5a623">RSI 14</span>
  <span style="color:#00d4aa">MACD 12,26</span>
  <span style="color:#ff6b6b">Signal 9</span>
</div>
<div id="indicators"></div>
<script src="{_CDN}"></script>
<script>
(function() {{
  var el  = document.getElementById('chart');
  var el2 = document.getElementById('indicators');

  // ── Main chart ──────────────────────────────────────────────
  var chart = LightweightCharts.createChart(el, {{
    width:  el.offsetWidth || 820,
    height: {height},
    layout: {{
      background: {{ color: '#0e1117' }},
      textColor:  '#e0e0e0',
    }},
    grid: {{
      vertLines: {{ color: '#1a1d23' }},
      horzLines: {{ color: '#1a1d23' }},
    }},
    crosshair: {{ mode: 1 }},
    rightPriceScale: {{
      borderColor: '#2a2d35',
      scaleMargins: {{ top: 0.05, bottom: 0.22 }},
    }},
    timeScale: {{
      borderColor: '#2a2d35',
      timeVisible: true,
      secondsVisible: false,
    }},
  }});

  // ── Candlestick series ──────────────────────────────────────
  var candleSeries = chart.addCandlestickSeries({{
    upColor:         '#00d4aa',
    downColor:       '#ff4b4b',
    borderUpColor:   '#00d4aa',
    borderDownColor: '#ff4b4b',
    wickUpColor:     '#00d4aa',
    wickDownColor:   '#ff4b4b',
  }});
  candleSeries.setData({candles_json});

  // ── Volume histogram ────────────────────────────────────────
  var volSeries = chart.addHistogramSeries({{
    priceFormat:  {{ type: 'volume' }},
    priceScaleId: 'vol',
    lastValueVisible: false,
    priceLineVisible: false,
  }});
  chart.priceScale('vol').applyOptions({{
    scaleMargins: {{ top: 0.82, bottom: 0.00 }},
  }});
  volSeries.setData({volumes_json});

  // ── Price lines ─────────────────────────────────────────────
  {price_lines_js}

  // ── Indicator chart ─────────────────────────────────────────
  var chart2 = LightweightCharts.createChart(el2, {{
    width:  el2.offsetWidth || 820,
    height: {ind_height},
    layout: {{
      background: {{ color: '#0e1117' }},
      textColor:  '#e0e0e0',
    }},
    grid: {{
      vertLines: {{ color: '#1a1d23' }},
      horzLines: {{ color: '#1a1d23' }},
    }},
    crosshair: {{ mode: 1 }},
    rightPriceScale: {{ borderColor: '#2a2d35' }},
    timeScale: {{
      borderColor: '#2a2d35',
      timeVisible: true,
      secondsVisible: false,
    }},
    handleScroll: {{ mouseWheel: false, pressedMouseMove: false }},
    handleScale:  {{ mouseWheel: false, pinch: false, axisDoubleClickReset: false }},
  }});

  // RSI line — top half of indicator panel
  var rsiSeries = chart2.addLineSeries({{
    color:            '#f5a623',
    lineWidth:        1,
    priceScaleId:     'rsi',
    lastValueVisible: true,
    priceLineVisible: false,
    crosshairMarkerVisible: true,
  }});
  chart2.priceScale('rsi').applyOptions({{
    scaleMargins: {{ top: 0.04, bottom: 0.54 }},
    borderColor: '#2a2d35',
  }});
  rsiSeries.setData({rsi_json});
  // Overbought / oversold reference lines
  rsiSeries.createPriceLine({{ price: 70, color: '#3a3a3a', lineWidth: 1, lineStyle: 1, title: '' }});
  rsiSeries.createPriceLine({{ price: 30, color: '#3a3a3a', lineWidth: 1, lineStyle: 1, title: '' }});

  // MACD histogram — bottom half
  var macdHist = chart2.addHistogramSeries({{
    priceScaleId:     'macd',
    lastValueVisible: false,
    priceLineVisible: false,
  }});
  chart2.priceScale('macd').applyOptions({{
    scaleMargins: {{ top: 0.56, bottom: 0.02 }},
    borderColor: '#2a2d35',
  }});
  macdHist.setData({hist_json});

  // MACD signal line (red)
  var macdSignal = chart2.addLineSeries({{
    color:            '#ff6b6b',
    lineWidth:        1,
    priceScaleId:     'macd',
    lastValueVisible: false,
    priceLineVisible: false,
  }});
  macdSignal.setData({sig_json});

  // MACD line (blue)
  var macdLine = chart2.addLineSeries({{
    color:            '#636EFA',
    lineWidth:        1,
    priceScaleId:     'macd',
    lastValueVisible: false,
    priceLineVisible: false,
  }});
  macdLine.setData({macd_json});

  // ── Sync time scales (mutual, with re-entrancy guard) ───────
  var _syncing = false;
  chart.timeScale().subscribeVisibleLogicalRangeChange(function(range) {{
    if (_syncing || !range) return;
    _syncing = true;
    chart2.timeScale().setVisibleLogicalRange(range);
    _syncing = false;
  }});
  chart2.timeScale().subscribeVisibleLogicalRangeChange(function(range) {{
    if (_syncing || !range) return;
    _syncing = true;
    chart.timeScale().setVisibleLogicalRange(range);
    _syncing = false;
  }});

  chart.timeScale().fitContent();

  // ── Responsive resize ───────────────────────────────────────
  new ResizeObserver(function() {{
    chart.applyOptions({{ width: el.offsetWidth }});
    chart2.applyOptions({{ width: el2.offsetWidth }});
  }}).observe(el);

  // ── Crosshair tooltip ───────────────────────────────────────
  chart.subscribeCrosshairMove(function(param) {{
    if (!param || !param.seriesData) return;
    var bar = param.seriesData.get(candleSeries);
    if (!bar) return;
    document.getElementById('title').textContent =
      '{pair_j} \u00b7 {tf_j}' +
      '  O:' + bar.open.toFixed(4) +
      '  H:' + bar.high.toFixed(4) +
      '  L:' + bar.low.toFixed(4) +
      '  C:' + bar.close.toFixed(4);
  }});
}})();
</script>
</body>
</html>"""
