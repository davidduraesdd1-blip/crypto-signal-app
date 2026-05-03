"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { useSettings, useSaveSettings } from "@/hooks/use-settings";

const DEFAULT_PAIRS = [
  "BTC/USDT",
  "ETH/USDT",
  "XRP/USDT",
  "SOL/USDT",
  "AVAX/USDT",
  "LINK/USDT",
  "NEAR/USDT",
  "DOT/USDT",
];

const ALL_TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"];
const DEFAULT_ACTIVE_TFS = ["5m", "15m", "30m", "1h", "4h", "1d"];

// AUDIT-2026-05-03 (D4c): Trading settings page wired:
// - Initial values hydrated from useSettings() (trading group)
// - Save button → useSaveSettings({ group: "trading", patch })
// - rejected[] from the response surfaces as inline error block
// Portfolio Size + Risk per trade + API Key are quick-setup
// shortcuts that route to /signal-risk / dev-tools — those mutate
// in their own sub-pages. Here they stay local-state visual only
// with TODO(D-ext) to consolidate the quick-panel into a single
// PUT batch.

export default function TradingSettingsPage() {
  const settingsQuery = useSettings();
  const saveMutation = useSaveSettings();

  // Form state — initialized from API data when available
  const [pairs, setPairs] = useState<string[]>(DEFAULT_PAIRS);
  const [activeTfs, setActiveTfs] = useState<string[]>(DEFAULT_ACTIVE_TFS);
  const [taExchange, setTaExchange] = useState("OKX");
  const [customPair, setCustomPair] = useState("");
  const [regionalColors, setRegionalColors] = useState(false);
  const [compactWatchlist, setCompactWatchlist] = useState(false);

  // Hydrate from API on first load
  useEffect(() => {
    const t = settingsQuery.data?.trading;
    if (!t) return;
    if (Array.isArray(t.trading_pairs) && t.trading_pairs.length > 0) {
      setPairs(t.trading_pairs as string[]);
    }
    if (Array.isArray(t.active_timeframes) && t.active_timeframes.length > 0) {
      setActiveTfs(t.active_timeframes as string[]);
    }
    if (typeof t.ta_exchange === "string") setTaExchange(t.ta_exchange);
    if (typeof t.custom_pair === "string") setCustomPair(t.custom_pair);
    if (typeof t.regional_color_convention === "boolean")
      setRegionalColors(t.regional_color_convention);
    if (typeof t.compact_watchlist_mode === "boolean")
      setCompactWatchlist(t.compact_watchlist_mode);
  }, [settingsQuery.data]);

  const toggleTf = (label: string) => {
    setActiveTfs((prev) =>
      prev.includes(label) ? prev.filter((t) => t !== label) : [...prev, label],
    );
  };

  const removePair = (pair: string) => {
    setPairs((prev) => prev.filter((p) => p !== pair));
  };

  const handleSave = () => {
    saveMutation.mutate({
      group: "trading",
      patch: {
        trading_pairs: pairs,
        active_timeframes: activeTfs,
        ta_exchange: taExchange,
        custom_pair: customPair,
        regional_color_convention: regionalColors,
        compact_watchlist_mode: compactWatchlist,
      },
    });
  };

  const handleRevert = () => {
    setPairs(DEFAULT_PAIRS);
    setActiveTfs(DEFAULT_ACTIVE_TFS);
    setTaExchange("OKX");
    setCustomPair("");
    setRegionalColors(false);
    setCompactWatchlist(false);
  };

  const tfsForRender = ALL_TIMEFRAMES.map((label) => ({
    label,
    active: activeTfs.includes(label),
  }));
  const activeCount = activeTfs.length;

  // Mutation feedback — saved status, error message, rejected fields
  const saveStatus = saveMutation.data?.status;
  const rejected = saveMutation.data?.rejected ?? [];

  return (
    <div className="space-y-6">
      {/* Beginner quick-panel — visual only; TODO(D-ext): consolidate
          into one PUT spanning trading + signal-risk + dev-tools */}
      <div className="rounded-xl border border-info/30 bg-info/5 p-4">
        <div className="mb-3 flex items-center gap-2">
          <span className="text-lg">📖</span>
          <h3 className="text-sm font-semibold text-text-primary">
            Quick Setup · Beginner shortcut
          </h3>
        </div>
        <p className="mb-4 text-[12px] text-text-secondary">
          3 most-touched controls · the full tab stack lives below for when you
          need it
        </p>
        <div className="mb-4 grid gap-4 md:grid-cols-2">
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-text-primary">
              Portfolio Size USD
            </label>
            <input
              type="text"
              defaultValue="10000"
              className="min-h-[44px] w-full rounded-lg border border-border-strong bg-bg-0 px-3 py-2 font-mono text-base text-text-primary"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-text-primary">
              Risk per trade %
            </label>
            <input
              type="text"
              defaultValue="2"
              className="min-h-[44px] w-full rounded-lg border border-border-strong bg-bg-0 px-3 py-2 font-mono text-base text-text-primary"
            />
          </div>
        </div>
        <div className="space-y-1.5">
          <label className="text-sm font-medium text-text-primary">
            API Key
          </label>
          <input
            type="password"
            placeholder="●●●● (saved)"
            className="min-h-[44px] w-full rounded-lg border border-border-strong bg-bg-0 px-3 py-2 font-mono text-base text-text-primary"
          />
          <p className="text-[11px] text-text-muted">
            Stored encrypted via Render env vars · OKX recommended for live trading
          </p>
        </div>
        <div className="mt-4 border-t border-dashed border-border-default pt-3 text-center text-[11px] text-text-muted">
          More settings ↓ · full tab stack below
        </div>
      </div>

      {/* Two-column grid */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Card 1: Trading pairs */}
        <div className="rounded-xl border border-border-default bg-bg-1 p-4">
          <h3 className="text-sm font-semibold text-text-primary">
            Trading pairs
          </h3>
          <p className="mb-4 text-[11px] text-text-muted">
            universe scanned every cycle · validated against TIER1 ∪ TIER2
            allowlist
          </p>

          <div className="mb-3 flex flex-wrap gap-2">
            {pairs.map((pair) => (
              <span
                key={pair}
                className="inline-flex items-center gap-1.5 rounded-md bg-accent-brand/10 px-2.5 py-1.5 font-mono text-xs text-text-primary"
              >
                {pair}
                <button
                  onClick={() => removePair(pair)}
                  className="ml-0.5 text-text-muted hover:text-text-primary"
                  aria-label={`Remove ${pair}`}
                >
                  ×
                </button>
              </span>
            ))}
            <button
              type="button"
              onClick={() => {
                if (customPair && !pairs.includes(customPair)) {
                  setPairs((p) => [...p, customPair]);
                  setCustomPair("");
                }
              }}
              className="inline-flex items-center gap-1 rounded-md border border-dashed border-border-default px-2.5 py-1.5 text-xs text-text-muted hover:border-accent-brand hover:text-accent-brand"
            >
              + Add pair
            </button>
          </div>
          <p className="mb-4 text-[11px] text-text-muted">
            {pairs.length} pairs active
          </p>

          <div className="space-y-1.5">
            <label className="text-sm font-medium text-text-primary">
              Custom pair (advanced)
            </label>
            <input
              type="text"
              value={customPair}
              onChange={(e) => setCustomPair(e.target.value)}
              placeholder="e.g. ARB/USDT — must exist on the configured TA exchange"
              className="min-h-[44px] w-full rounded-lg border border-border-default bg-bg-2 px-3 py-2 text-sm text-text-primary placeholder:text-text-muted"
            />
          </div>
        </div>

        {/* Card 2: Timeframes & data */}
        <div className="rounded-xl border border-border-default bg-bg-1 p-4">
          <h3 className="text-sm font-semibold text-text-primary">
            Timeframes & data
          </h3>
          <p className="mb-4 text-[11px] text-text-muted">
            candle resolutions used in the multi-timeframe alignment check
          </p>

          <div className="mb-2 text-sm font-medium text-text-primary">
            Active timeframes
          </div>
          <div className="mb-3 flex flex-wrap gap-1">
            {tfsForRender.map((tf) => (
              <button
                key={tf.label}
                onClick={() => toggleTf(tf.label)}
                className={cn(
                  "min-h-[36px] rounded-md px-3 py-1.5 font-mono text-xs font-medium transition-colors",
                  tf.active
                    ? "bg-accent-brand text-bg-0"
                    : "bg-bg-2 text-text-muted hover:bg-bg-3",
                )}
              >
                {tf.label}
              </button>
            ))}
          </div>
          <p className="mb-4 text-[11px] text-text-muted">
            {activeCount} of 8 selected · 1m and 1w off by default (noise / lag)
          </p>

          <div className="space-y-1.5">
            <label className="text-sm font-medium text-text-primary">
              TA exchange (OHLCV source)
            </label>
            <select
              value={taExchange}
              onChange={(e) => setTaExchange(e.target.value)}
              className="min-h-[44px] w-full rounded-lg border border-border-default bg-bg-2 px-3 py-2 text-sm text-text-primary"
            >
              <option>OKX</option>
              <option>Kraken</option>
              <option>CoinGecko</option>
            </select>
            <p className="text-[11px] text-text-muted">
              Fallback chain: OKX → Kraken → CoinGecko per master template §10
            </p>
          </div>
        </div>
      </div>

      {/* Full-width card 3: Display preferences */}
      <div className="rounded-xl border border-border-default bg-bg-1 p-4">
        <h3 className="text-sm font-semibold text-text-primary">
          Display preferences
        </h3>
        <p className="mb-4 text-[11px] text-text-muted">
          visual settings that don&apos;t affect signal logic
        </p>

        <div className="space-y-4">
          <ToggleRow
            label="Regional color convention"
            sublabel="Red = up / Green = down (East-Asia convention) — flips price + chart colors but keeps semantic colors (success/danger) untouched"
            on={regionalColors}
            onToggle={() => setRegionalColors((v) => !v)}
          />
          <ToggleRow
            label="Compact watchlist mode"
            sublabel="Removes sparkline column to fit more pairs in a single view on smaller laptops"
            on={compactWatchlist}
            onToggle={() => setCompactWatchlist((v) => !v)}
          />
        </div>
      </div>

      {/* Save status / rejected fields */}
      {saveMutation.isError && (
        <div className="rounded-lg border border-danger/30 bg-danger/5 p-3 text-sm text-danger">
          Save failed — {String(saveMutation.error?.message ?? "unknown error")}
        </div>
      )}
      {saveStatus === "ok" && saveMutation.isSuccess && rejected.length === 0 && (
        <div className="rounded-lg border border-success/30 bg-success/5 p-3 text-sm text-success">
          Saved · all values applied to alerts_config.json
        </div>
      )}
      {saveStatus === "partial" && rejected.length > 0 && (
        <div className="rounded-lg border border-warning/30 bg-warning/5 p-3 text-sm">
          <div className="mb-1 font-medium text-warning">
            Partial save — {rejected.length} field{rejected.length === 1 ? "" : "s"} rejected
          </div>
          <ul className="space-y-0.5 font-mono text-[11px] text-text-muted">
            {rejected.map((r) => (
              <li key={r.key}>
                <span className="text-text-secondary">{r.key}</span>: {r.reason}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Button row */}
      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={handleSave}
          disabled={saveMutation.isPending}
          className="inline-flex min-h-[44px] items-center gap-2 rounded-lg bg-accent-brand px-5 py-2.5 text-sm font-semibold text-bg-0 transition-colors hover:bg-accent-brand/90 disabled:opacity-60 disabled:cursor-wait"
        >
          <span className={cn(saveMutation.isPending && "animate-spin")}>💾</span>
          <span>{saveMutation.isPending ? "Saving…" : "Save Trading Config"}</span>
        </button>
        <button
          type="button"
          onClick={handleRevert}
          className="inline-flex min-h-[44px] items-center gap-2 rounded-lg border border-border-default bg-bg-2 px-5 py-2.5 text-sm font-medium text-text-primary transition-colors hover:bg-bg-3"
        >
          <span>↺</span>
          <span>Revert to defaults</span>
        </button>
      </div>
    </div>
  );
}

function ToggleRow({
  label,
  sublabel,
  on,
  onToggle,
}: {
  label: string;
  sublabel: string;
  on: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border-default pb-4 last:border-0 last:pb-0">
      <div className="min-w-0">
        <div className="text-sm font-medium text-text-primary">{label}</div>
        <div className="mt-0.5 text-[11px] text-text-muted">{sublabel}</div>
      </div>
      <button
        onClick={onToggle}
        className={cn(
          "relative h-6 w-11 shrink-0 rounded-full transition-colors",
          on ? "bg-accent-brand" : "bg-bg-3",
        )}
      >
        <span
          className={cn(
            "absolute top-1 h-4 w-4 rounded-full bg-white transition-transform",
            on ? "left-6" : "left-1",
          )}
        />
      </button>
    </div>
  );
}
