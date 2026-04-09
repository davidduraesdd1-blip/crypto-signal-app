"""
Convert page_config() 5 expanders → 5 sub-tabs.
Also: add Alerts tab with full alert config (moved from sidebar).
"""
import re

with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

# ── Boundaries:
# page_config starts at L3693
# 5 expanders at L3758, 3821, 4061, 4199, 4287
# page_config ends at L4629 (before page_backtest at L4630)

lines = content.split("\n")
L = lambda n: n - 1

# Extract the section of page_config that uses expanders (after beginner return)
# beginner return is around line 3754 (return statement after beginner block)
# Expanders start at 3758

# ── Find exact positions
expander_1 = 3758   # Trading Parameters
expander_2 = 3821   # Signal & Risk
expander_3 = 4061   # Notifications
expander_4 = 4199   # Developer Tools
expander_5 = 4287   # Live Execution
func_end    = 4607  # exclusive: page_config ends at 4606; _backtest_progress starts at 4608 (module-level)

# New tabs header (to replace the first expander header line)
# We need to also handle the _settings_tab auto-select from sidebar "Configure Alerts" button
TABS_HEADER = '''    # ── Auto-jump to Alerts tab when navigated from sidebar
    _cfg_initial_tab = 0
    _st_tab_override = st.session_state.pop("_settings_tab", None)
    _cfg_tab_names = ["📊 Trading", "⚡ Signal & Risk", "🔔 Alerts", "🛠️ Dev Tools", "⚙️ Execution"]
    if _st_tab_override and _st_tab_override in _cfg_tab_names:
        _cfg_initial_tab = _cfg_tab_names.index(_st_tab_override)

    _cfg_t1, _cfg_t2, _cfg_t3, _cfg_t4, _cfg_t5 = st.tabs(_cfg_tab_names)

    # ── ALERTS TAB content definition (full config moved from sidebar)
    def _render_alerts_tab():
        """Full alert configuration — Telegram, Email, Discord."""
        _at_cfg = _cached_alerts_config()

        with st.expander("🔔 Telegram Alerts", expanded=_at_cfg.get("telegram_enabled", False)):
            _at_cfg2 = _at_cfg.copy()
            tg_enabled = st.toggle("Enable Telegram", value=_at_cfg2.get("telegram_enabled", False), key="cfg_tg_enabled")
            tg_token   = st.text_input("Bot Token", value=_at_cfg2.get("telegram_token", ""), type="password",
                                       placeholder="123456:ABC-DEF...", key="cfg_tg_token", disabled=not tg_enabled)
            tg_chat_id = st.text_input("Chat ID", value=_at_cfg2.get("telegram_chat_id", ""),
                                       placeholder="-1001234567890", key="cfg_tg_chat", disabled=not tg_enabled)
            tg_min_conf = st.slider("Alert threshold (%)", 50, 95, int(_at_cfg2.get("min_confidence", 70)),
                                    step=5, key="cfg_tg_thresh", disabled=not tg_enabled)
            cst, ctest = st.columns(2)
            with cst:
                if st.button("Save Telegram", key="cfg_tg_save", width="stretch"):
                    _at_cfg2.update({"telegram_enabled": tg_enabled, "telegram_token": tg_token.strip(),
                                     "telegram_chat_id": tg_chat_id.strip(), "min_confidence": tg_min_conf})
                    _save_alerts_config_and_clear(_at_cfg2)
                    st.success("Saved!")
            with ctest:
                if st.button("Test", key="cfg_tg_test", width="stretch", disabled=not tg_enabled):
                    ok, err = _alerts.send_telegram(tg_token.strip(), tg_chat_id.strip(),
                                                    "\\u2705 Telegram test — connection successful!")
                    st.success("Message sent!") if ok else st.error(f"Failed: {err}")
            st.caption("Get bot token from @BotFather · Chat ID from @userinfobot")

        with st.expander("📧 Email Alerts", expanded=_at_cfg.get("email_enabled", False)):
            _at_em = _at_cfg.copy()
            em_on   = st.toggle("Enable Email", value=_at_em.get("email_enabled", False), key="cfg_em_on")
            em_to   = st.text_input("Recipient", value=_at_em.get("email_to", ""), placeholder="you@example.com",
                                    key="cfg_em_to", disabled=not em_on)
            em_from = st.text_input("Sender (Gmail)", value=_at_em.get("email_from", ""),
                                    placeholder="yourbot@gmail.com", key="cfg_em_from", disabled=not em_on)
            em_pass = st.text_input("App Password", value=_at_em.get("email_pass", ""), type="password",
                                    key="cfg_em_pass", disabled=not em_on)
            em_min  = st.slider("Alert threshold (%)", 50, 95, int(_at_em.get("email_min_confidence", 70)),
                                step=5, key="cfg_em_thresh", disabled=not em_on)
            cse, cte = st.columns(2)
            with cse:
                if st.button("Save Email", key="cfg_em_save", width="stretch"):
                    _at_em.update({"email_enabled": em_on, "email_to": em_to.strip(),
                                   "email_from": em_from.strip(), "email_pass": em_pass,
                                   "email_min_confidence": em_min})
                    _save_alerts_config_and_clear(_at_em)
                    st.success("Saved!")
            with cte:
                if st.button("Test", key="cfg_em_test", width="stretch", disabled=not em_on):
                    ok, err = _alerts.send_email_alert(em_from.strip(), em_pass, em_to.strip(),
                                                       "Crypto Signal Model — Test Alert",
                                                       "\\u2705 Email alert test successful.")
                    st.success("Email sent!") if ok else st.error(f"Failed: {err}")
            st.caption("Use a Gmail App Password (Settings → Security → 2FA → App passwords)")

        with st.expander("💬 Discord Alerts", expanded=_at_cfg.get("discord_enabled", False)):
            _at_dc = _at_cfg.copy()
            dc_on  = st.toggle("Enable Discord", value=_at_dc.get("discord_enabled", False), key="cfg_dc_on")
            dc_wh  = st.text_input("Webhook URL", value=_at_dc.get("discord_webhook_url", ""), type="password",
                                   placeholder="https://discord.com/api/webhooks/...",
                                   key="cfg_dc_wh", disabled=not dc_on)
            dc_min = st.slider("Alert threshold (%)", 50, 95, int(_at_dc.get("discord_min_confidence", 70)),
                               step=5, key="cfg_dc_thresh", disabled=not dc_on)
            csd, ctd = st.columns(2)
            with csd:
                if st.button("Save Discord", key="cfg_dc_save", width="stretch"):
                    _at_dc.update({"discord_enabled": dc_on, "discord_webhook_url": dc_wh.strip(),
                                   "discord_min_confidence": dc_min})
                    _save_alerts_config_and_clear(_at_dc)
                    st.success("Saved!")
            with ctd:
                if st.button("Test", key="cfg_dc_test", width="stretch", disabled=not dc_on):
                    ok, err = _alerts.send_discord(dc_wh.strip(),
                                                   "\\u2705 **Crypto Signal Model** — Discord test!")
                    st.success("Message sent!") if ok else st.error(f"Failed: {err}")
            st.caption("Create webhook: Channel → Edit → Integrations → Webhooks → New")

    # ── Tab 1: Trading Parameters
    with _cfg_t1:
'''

# ── Old line 3758: `    with st.expander("📊 Trading Parameters", expanded=True):`
# We need to replace this with the new tab structure

# The code between expanders:
# Block A: expander_1 (3758) to expander_2 (3821) → goes into _cfg_t1
# Block B: expander_2 (3821) to expander_3 (4061) → goes into _cfg_t2
# Block C: expander_3 (4061) to expander_4 (4199) → goes into _cfg_t3 (after alert config)
# Block D: expander_4 (4199) to expander_5 (4287) → goes into _cfg_t4
# Block E: expander_5 (4287) to func_end (4629)   → goes into _cfg_t5

def extract_expander_body(start_line, end_line):
    """Extract lines inside an expander block (skip the with st.expander line itself)."""
    body = lines[L(start_line)+1 : L(end_line)]
    # De-indent by 4 spaces (the expander adds one extra level)
    result = []
    for ln in body:
        if ln.startswith("        "):  # 8 spaces → 4 spaces
            result.append("    " + ln[8:])
        elif ln.startswith("    "):    # 4 spaces → keep (it was the base indent)
            result.append(ln[4:])
        else:
            result.append(ln)
    return "\n".join(result)


body_a = extract_expander_body(expander_1, expander_2)
body_b = extract_expander_body(expander_2, expander_3)
body_c = extract_expander_body(expander_3, expander_4)
body_d = extract_expander_body(expander_4, expander_5)
body_e = extract_expander_body(expander_5, func_end)

# Re-indent bodies to 8 spaces (they'll be inside `with _cfg_tN:` at 4-space indent)
def reindent_block(text, extra=4):
    pad = " " * extra
    out = []
    for ln in text.split("\n"):
        if ln.strip() == "":
            out.append("")
        else:
            out.append(pad + ln)
    return "\n".join(out)

body_a = reindent_block(body_a)
body_b = reindent_block(body_b)
body_c = reindent_block(body_c)
body_d = reindent_block(body_d)
body_e = reindent_block(body_e)

new_tabs_section = (
    TABS_HEADER
    + body_a
    + "\n\n    # ── Tab 2: Signal & Risk\n    with _cfg_t2:\n"
    + body_b
    + "\n\n    # ── Tab 3: Alerts (full config + notifications)\n    with _cfg_t3:\n"
    + "        _render_alerts_tab()\n"
    + "        st.markdown('---')\n"
    + "        st.markdown('#### Notifications & Scheduler')\n"
    + body_c
    + "\n\n    # ── Tab 4: Dev Tools\n    with _cfg_t4:\n"
    + body_d
    + "\n\n    # ── Tab 5: Live Execution\n    with _cfg_t5:\n"
    + body_e
)

# ── Find the exact text to replace in content
# From the start of expander_1 line to end of expander_5 body
old_section_start = "\n".join(lines[L(expander_1):L(func_end)])

# Replace
new_content = content.replace(old_section_start, new_tabs_section, 1)

if new_content == content:
    print("WARNING: No replacement made — check line numbers")
else:
    with open("app_cfg_restructured.py", "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"Written app_cfg_restructured.py — {len(new_content.splitlines())} lines")
    print("Run: py -3 -m py_compile app_cfg_restructured.py")
