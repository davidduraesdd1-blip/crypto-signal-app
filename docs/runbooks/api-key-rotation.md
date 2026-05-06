# API key rotation runbook

**Last rotation:** 2026-05-05 (P0-1 of Phase 0.9 audit — leaked value scrubbed from `docs/redesign/`)

## When to rotate

- Key value committed to git or shared in chat / email / screenshot
- Suspected unauthorized access (look for unexpected /scan/trigger or /execute/order in agent_log)
- Quarterly cadence (target every 90 days)
- Before handing the repo to a new collaborator

## Procedure (5 minutes, zero downtime)

### 1. Generate new key
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
# copy the 43-char output
```

### 2. Set on Render BEFORE rotating Vercel
- Render dashboard → service `crypto-signal-app` → Environment
- Update `CRYPTO_SIGNAL_API_KEY` to the new value
- Click **Save Changes** — Render rolls a new deploy (~2 min)
- Verify: `curl -H "X-API-Key: $NEW_KEY" https://crypto-signal-app-1fsi.onrender.com/signals` → 200

### 3. Set on Vercel
- Vercel dashboard → project → Settings → Environment Variables
- Update `NEXT_PUBLIC_API_KEY` to the same new value
- **Sensitive flag MUST be OFF** (Sensitive blocks `NEXT_PUBLIC_*` inlining — known pitfall, see `docs/audits/2026-05-05_cross-platform-connectivity.md`)
- Apply to all 3 envs: Production, Preview, Development
- Trigger a redeploy with **build cache UNCHECKED** so the new value is inlined into the JS bundles

### 4. Verify both ends agree
```bash
# Should return 200
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "X-API-Key: $NEW_KEY" \
  https://crypto-signal-app-1fsi.onrender.com/signals

# Browser: hard-refresh https://v0-davidduraesdd1-blip-crypto-signa.vercel.app/signals
# Verify Network tab shows /signals → 200, not 401
```

### 5. Old key is automatically dead
Render's `require_api_key` does `hmac.compare_digest()` against the env value.
Once Render's env updates, the old key returns 401 immediately.
No grace period, no allow-list, no double-key window.

## Post-rotation: scrub committed plaintext

If the leaked value is in git history (not just HEAD):

**Option A (recommended for solo / family repo):** accept that the rotated key invalidates the leak. The string in old commits is now useless.

**Option B (if compliance / public repo):** rewrite history with `git filter-repo` or BFG. **Destructive.** Coordinate with anyone who has the repo cloned.

## Don't

- Don't paste the literal value into Claude / chat / Slack / Notion. Reference it as `$CRYPTO_SIGNAL_API_KEY` from your shell.
- Don't commit `web/.env.local` (gitignored, but worth re-checking).
- Don't add the key to a hardcoded test fixture.
