"""
alerts.py — Alert system for Crypto Signal Model v5.9.13
Handles Email notifications for scan results.

Telegram + Discord channels were removed 2026-04-18 after repeated bot-token /
webhook-URL leaks in git history. If demand resurfaces, reintroduce them with
env-var-only config (never persisted to disk, never shipped via UI).
"""
from __future__ import annotations

import json
import logging
import os
import re
import smtplib
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

# PERF: reuse TCP connections for any outbound HTTPS call (e.g. generic webhook).
_SESSION = requests.Session()
_SESSION.headers.update({"Accept-Encoding": "gzip, deflate", "Connection": "keep-alive"})

_ALERTS_CONFIG_FILE = "alerts_config.json"

# ── Alert deduplication — 4-hour cooldown per pair+direction ─────────────────
# Prevents the same high-confidence signal from firing an alert every 15 minutes.
# Key: (pair, direction), Value: unix timestamp of last alert sent.
_ALERT_COOLDOWN_SECS = 4 * 3600   # 4 hours
_alert_last_sent: dict = {}        # in-memory; resets on process restart (acceptable)
_alert_dedup_lock = threading.Lock()


def _is_new_signal(pair: str, direction: str) -> bool:
    """Return True only if this pair+direction hasn't been alerted in the last 4 hours."""
    key = (pair, direction)
    now = time.time()
    with _alert_dedup_lock:
        last = _alert_last_sent.get(key, 0)
        if now - last < _ALERT_COOLDOWN_SECS:
            return False
        _alert_last_sent[key] = now
        return True


def _deduplicate_results(results: list) -> list:
    """Filter scan results to only those with new signals (4h cooldown)."""
    return [r for r in results if _is_new_signal(
        r.get("pair", ""), r.get("direction", "")
    )]


# ──────────────────────────────────────────────
# CONFIG PERSISTENCE
# ──────────────────────────────────────────────

_DEFAULTS = {
    "min_confidence": 70,
    "autoscan_enabled": False,
    "autoscan_interval_minutes": 60,
    "autoscan_quiet_hours_enabled": False,
    "autoscan_quiet_start": "22:00",
    "autoscan_quiet_end": "06:00",
    "email_enabled": False,
    "email_to": "",
    "email_from": "",
    "email_pass": "",
    "email_min_confidence": 70,
    # Telegram + Discord channels removed 2026-04-18 (see module docstring).
    # Paid/free API keys (stubs — add key to activate)
    "lunarcrush_key": "",
    "coinglass_key": "",
    "cryptoquant_key": "",
    "glassnode_key": "",
    "cryptopanic_key": "",   # Free — sign up at cryptopanic.com
    # FastAPI REST server
    "api_key": "",
    "api_host": "0.0.0.0",
    "api_port": 8000,
    # Live execution (OKX ccxt)
    "live_trading_enabled":          False,
    "auto_execute_enabled":          False,
    "auto_execute_min_confidence":   80,
    "okx_api_key":                   "",
    "okx_secret":                    "",
    "okx_passphrase":                "",
    "default_order_type":            "market",
    # Autonomous AI trading agent
    "agent_enabled":                 False,
    "agent_dry_run":                 True,
    "agent_interval_seconds":        60,
    "agent_min_confidence":          80.0,
    "agent_max_concurrent_positions": 3,
    "agent_daily_loss_limit_pct":    5.0,
    "agent_portfolio_size_usd":      10_000.0,
    # Watchlist alert rules: list of {name, pair, condition, min_confidence, enabled}
    # condition options: "BUY", "SELL", "STRONG BUY", "STRONG SELL", "ANY"
    "watchlist": [],
}


def load_alerts_config():
    """Load alert config from disk, merged with defaults for any missing keys."""
    config = dict(_DEFAULTS)
    if os.path.exists(_ALERTS_CONFIG_FILE):
        try:
            with open(_ALERTS_CONFIG_FILE, "r", encoding="utf-8") as f:
                config.update(json.load(f))
        except Exception as e:
            logging.error("[alerts] Failed to load config from %s: %s", _ALERTS_CONFIG_FILE, e)
    return config


def save_alerts_config(config: dict):
    """Persist alert config to disk atomically (BUG-M08: avoids corrupt file on crash)."""
    import os, tempfile
    try:
        # Write to a temp file in the same directory, then atomically rename
        dir_ = os.path.dirname(os.path.abspath(_ALERTS_CONFIG_FILE)) or "."
        with tempfile.NamedTemporaryFile("w", dir=dir_, suffix=".tmp", delete=False, encoding="utf-8") as tmp:
            json.dump(config, tmp, indent=2)
            tmp_path = tmp.name
        # BUG-ALERTS01: restrict permissions before rename so API keys aren't
        # world-readable in the temp file even briefly (chmod is no-op on Windows).
        try:
            os.chmod(tmp_path, 0o600)
        except Exception:
            pass
        os.replace(tmp_path, _ALERTS_CONFIG_FILE)
    except Exception as e:
        logging.error("[alerts] Failed to save config: %s", e)


# Telegram sender removed 2026-04-18 (see module docstring).

def _fmt_price(val) -> str:
    """Format a price with auto-precision based on magnitude."""
    if val is None:
        return "—"
    try:
        v = float(val)
        if v >= 1000:
            return f"${v:,.2f}"
        elif v >= 1:
            return f"${v:,.4f}"
        else:
            return f"${v:,.6f}"
    except (TypeError, ValueError):
        return "—"


def _signal_emoji(direction: str) -> str:
    # ALERTS-01: guard against None direction (key exists but value is None)
    if not direction:
        return "🟡"
    if "STRONG BUY" in direction:   return "🟢🟢"
    if "BUY" in direction:           return "🟢"
    if "STRONG SELL" in direction:  return "🔴🔴"
    if "SELL" in direction:         return "🔴"
    return "🟡"


def _extract_signal_fields(r: dict) -> dict:
    """Extract common display fields from a scan result dict.
    Shared by format_email_body (and formerly format_scan_alert /
    format_discord_message before those channels were removed 2026-04-18).
    """
    lev_rec = r.get("leverage_rec") or {}
    return {
        "pair":      r.get("pair", "?"),
        "conf":      r.get("confidence_avg_pct", 0),
        "direction": r.get("direction", "—"),
        "price":     r.get("price_usd"),
        "entry":     r.get("entry"),
        "stop":      r.get("stop_loss"),
        "tp1":       r.get("tp1"),
        "tp2":       r.get("tp2"),
        "tp3":       r.get("tp3"),
        "mtf":       r.get("mtf_alignment", 0),
        "mtf_conf":  r.get("mtf_confirmed", True),
        "lev_label": lev_rec.get("label", "—"),
        "lev_basis": lev_rec.get("basis", ""),
        "pos_pct":   r.get("position_size_pct"),
        "regime":    r.get("risk_mode", r.get("regime", "")),
        "rr":        r.get("rr_ratios") or {},
        "high_conf": r.get("high_conf", False),
    }


# format_scan_alert (Telegram HTML formatter) + send_scan_alerts (Telegram
# dispatcher) removed 2026-04-18 along with the send_telegram sender above.


# ──────────────────────────────────────────────
# EMAIL (SMTP via Gmail)
# ──────────────────────────────────────────────

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _is_valid_email(addr: str) -> bool:
    return bool(addr and _EMAIL_RE.match(addr.strip()))


def _strip_crlf(s: str, max_len: int = 200) -> str:
    """Strip CR/LF from a string and truncate — used on anything that might
    end up in an SMTP header (subject line, rule name, etc.) to block
    header-injection (R1h HIGH #3)."""
    return re.sub(r"[\r\n]", " ", str(s))[:max_len]


def send_email_alert(
    sender: str, app_password: str, recipient: str,
    subject: str, body_text: str
) -> tuple[bool, str | None]:
    """
    Send an email via Gmail SMTP (TLS port 587).
    Requires a Gmail App Password (not your account password).
    Returns (success: bool, error: str | None).
    """
    if not sender or not app_password or not recipient:
        return False, "Sender, app password, or recipient not configured"
    # Audit R1h HIGH #2: port _is_valid_email from DeFi/RWA. Without this
    # a malformed recipient goes straight to SMTP and the error response
    # can echo the submitted address + local server state.
    if not _is_valid_email(sender) or not _is_valid_email(recipient):
        return False, "Sender or recipient email format is invalid — check both fields."
    # Audit R1h HIGH #3: scrub CRLF from subject (SMTP header-injection vector).
    subject = _strip_crlf(subject, max_len=200)
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = recipient
        msg.attach(MIMEText(body_text, "plain", "utf-8"))

        with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as server:  # FIX-503: reduced from 15s to stay under health-check deadline
            server.ehlo()
            server.starttls()
            server.login(sender, app_password)
            server.sendmail(sender, recipient, msg.as_string())
        return True, None
    except smtplib.SMTPAuthenticationError:
        return False, "Authentication failed — check your Gmail App Password"
    except Exception as e:
        # Audit R1f: don't raw-dump exception — type only.
        logger.warning("[alerts] send_email_alert failed: %s", type(e).__name__)
        return False, "Send failed — check your email settings and network, then try again."


def format_email_body(results: list, min_confidence: float = 70) -> str | None:
    """
    Build a plain-text email body from scan results.
    Includes TP1/TP2/TP3, leverage recommendation, and MTF confirmation.
    Returns None if no eligible signals.
    """
    if not results:
        return None
    from datetime import datetime, timezone
    eligible = [r for r in results if r.get("confidence_avg_pct", 0) >= min_confidence]
    if not eligible:
        return None
    eligible_sorted = sorted(eligible, key=lambda x: x.get("confidence_avg_pct", 0), reverse=True)
    scan_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    SEP = "─" * 44

    lines = [
        "📡 Crypto Signal Alert",
        f"{len(results)} pairs scanned · {len(eligible)} signal(s) >= {int(min_confidence)}% · {scan_utc}",
        "",
    ]
    for r in eligible_sorted:
        f = _extract_signal_fields(r)
        hc_tag  = " [HIGH CONF ⚡]" if f["high_conf"] else ""
        mtf_tag = " [MTF DOWNGRADED ⚠️]" if not f["mtf_conf"] else ""

        lines.append(SEP)
        lines.append(f"{f['pair']}{hc_tag}  |  {f['direction']}{mtf_tag}  |  {f['conf']}% conf  |  MTF {f['mtf']}%")
        lines.append(f"  Price: {_fmt_price(f['price'])}")
        lines.append("")
        if f["entry"]:
            lines.append(f"  Entry:  {_fmt_price(f['entry'])}")
        if f["stop"] and f["entry"]:
            try:
                _entry_f = float(f["entry"])
                stop_pct = abs(_entry_f - float(f["stop"])) / _entry_f * 100 if _entry_f != 0 else 0
                lines.append(f"  Stop:   {_fmt_price(f['stop'])}  (-{stop_pct:.1f}% risk)")
            except Exception:
                lines.append(f"  Stop:   {_fmt_price(f['stop'])}")
        if f["tp1"]:
            lines.append(f"  TP1:    {_fmt_price(f['tp1'])}  (R:R {f['rr'].get('tp1','1.5:1')}) — exit 40%")
        if f["tp2"]:
            lines.append(f"  TP2:    {_fmt_price(f['tp2'])}  (R:R {f['rr'].get('tp2','2.5:1')}) — exit 40%")
        if f["tp3"]:
            lines.append(f"  TP3:    {_fmt_price(f['tp3'])}  (R:R {f['rr'].get('tp3','4.0:1')}) — hold 20%")
        lines.append("")
        lev_line = f"  Leverage: {f['lev_label']}"
        if f["lev_basis"]:
            lev_line += f"  ({f['lev_basis']})"
        if f["pos_pct"]:
            lev_line += f"   Position: {f['pos_pct']}% of account"
        lines.append(lev_line)
        if f["regime"]:
            lines.append(f"  Regime: {str(f['regime']).replace('Regime: ', '')}")
        if not f["mtf_conf"]:
            lines.append("  ⚠️  STRONG signal was downgraded — higher timeframe disagrees")
        lines.append("")

    lines.append(SEP)
    return "\n".join(lines).rstrip()


def send_scan_email_alerts(results: list, config: dict | None = None) -> tuple[bool, str | None]:
    """Send email alert for completed scan if email alerts are enabled (4h dedup)."""
    if config is None:
        config = load_alerts_config()

    if not config.get("email_enabled"):
        return False, "Email alerts disabled"

    sender     = config.get("email_from", "").strip()
    app_pass   = config.get("email_pass", "")
    recipient  = config.get("email_to", "").strip()
    try:
        min_conf = float(config.get("email_min_confidence", 70) or 70)
    except (ValueError, TypeError):
        min_conf = 70.0

    new_results = _deduplicate_results(results)
    if not new_results:
        return False, "All signals already emailed within the last 4 hours — skipping"

    body = format_email_body(new_results, min_conf)
    if body is None:
        return False, f"No new signals above {int(min_conf)}% threshold — no email sent"

    subject = f"Crypto Signal Alert — {len([r for r in new_results if r.get('confidence_avg_pct', 0) >= min_conf])} new signal(s)"
    return send_email_alert(sender, app_pass, recipient, subject, body)


# Discord sender + formatter + dispatcher removed 2026-04-18 (see module docstring).


# ──────────────────────────────────────────────
# WATCHLIST ALERTS
# ──────────────────────────────────────────────

def _watchlist_condition_matches(rule: dict, result: dict) -> bool:
    """Return True if a scan result satisfies a watchlist rule's condition."""
    condition = rule.get("condition", "ANY").upper().strip()
    direction = result.get("direction", "").upper().strip()
    conf      = float(result.get("confidence_avg_pct", 0) or 0)
    min_conf  = float(rule.get("min_confidence", 0) or 0)

    if conf < min_conf:
        return False
    if condition == "ANY":
        return True
    return condition in direction


def check_watchlist_alerts(scan_results: list, config: dict | None = None) -> list[dict]:
    """
    Check scan results against watchlist rules and fire alerts for any matches.
    Returns list of triggered rule dicts (for UI display).

    Each rule in config["watchlist"]:
        {
            "name": str,          # user-defined label
            "pair": str,          # e.g. "BTC/USDT" or "ALL"
            "condition": str,     # "ANY"|"BUY"|"SELL"|"STRONG BUY"|"STRONG SELL"
            "min_confidence": float,
            "enabled": bool,
        }
    """
    if config is None:
        config = load_alerts_config()

    rules    = config.get("watchlist", [])
    results  = {r.get("pair", ""): r for r in scan_results if r.get("pair")}
    triggered = []

    for rule in rules:
        if not rule.get("enabled", True):
            continue
        target_pair = rule.get("pair", "ALL").strip()

        # Determine which scan results to check
        if target_pair == "ALL":
            candidates = list(results.values())
        else:
            candidates = [results[target_pair]] if target_pair in results else []

        for scan_r in candidates:
            if not _watchlist_condition_matches(rule, scan_r):
                continue

            pair      = scan_r.get("pair", "")
            direction = scan_r.get("direction", "")
            conf      = float(scan_r.get("confidence_avg_pct", 0) or 0)
            entry     = scan_r.get("entry")
            stop      = scan_r.get("stop_loss")

            msg = (
                f"🔔 Watchlist Alert: {rule.get('name', 'Unnamed')}\n"
                f"{_signal_emoji(direction)} {pair} — {direction} ({conf:.0f}% confidence)\n"
            )
            if entry:
                msg += f"Entry: {_fmt_price(entry)}  |  Stop: {_fmt_price(stop)}"

            # PERF: fire all enabled channels concurrently. Telegram + Discord
            # channels were removed 2026-04-18; only email remains. Keeping
            # the ThreadPoolExecutor pattern so reintroducing another
            # channel later is a single append.
            _send_tasks = []
            if config.get("email_enabled"):
                # Audit R1h HIGH #3: rule name is user-supplied free text;
                # CRLF-strip before interpolation to block SMTP header
                # injection via the subject line.
                _rule_name = _strip_crlf(rule.get("name", pair), max_len=80)
                _send_tasks.append(("email", lambda _msg=msg, _rn=_rule_name: send_email_alert(
                    sender       = config.get("email_from", ""),
                    app_password = config.get("email_pass", ""),
                    recipient    = config.get("email_to", ""),
                    subject      = f"Watchlist Alert: {_rn}",
                    body_text    = _msg,
                )))

            if _send_tasks:
                with ThreadPoolExecutor(max_workers=len(_send_tasks)) as _alert_ex:
                    _futs = {name: _alert_ex.submit(fn) for name, fn in _send_tasks}
                    for name, fut in _futs.items():
                        try:
                            fut.result()
                        except Exception as e:
                            logging.warning("[watchlist] %s fire failed: %s", name, e)

            triggered.append({
                "rule_name":  rule.get("name", ""),
                "pair":       pair,
                "direction":  direction,
                "confidence": conf,
            })

    return triggered
