"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";

const activePairs = [
  "BTC/USDT",
  "ETH/USDT",
  "XRP/USDT",
  "SOL/USDT",
  "AVAX/USDT",
  "LINK/USDT",
  "NEAR/USDT",
  "DOT/USDT",
];

const timeframes = [
  { label: "1m", active: false },
  { label: "5m", active: true },
  { label: "15m", active: true },
  { label: "30m", active: true },
  { label: "1h", active: true },
  { label: "4h", active: true },
  { label: "1d", active: true },
  { label: "1w", active: false },
];

export default function TradingSettingsPage() {
  const [pairs, setPairs] = useState(activePairs);
  const [tfs, setTfs] = useState(timeframes);

  const toggleTf = (idx: number) => {
    setTfs((prev) =>
      prev.map((tf, i) => (i === idx ? { ...tf, active: !tf.active } : tf))
    );
  };

  const removePair = (pair: string) => {
    setPairs((prev) => prev.filter((p) => p !== pair));
  };

  const activeCount = tfs.filter((t) => t.active).length;

  return (
    <div className="space-y-6">
      {/* Beginner quick-panel */}
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
            Stored encrypted · OKX recommended for live trading
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
                >
                  ×
                </button>
              </span>
            ))}
            <button className="inline-flex items-center gap-1 rounded-md border border-dashed border-border-default px-2.5 py-1.5 text-xs text-text-muted hover:border-accent-brand hover:text-accent-brand">
              + Add pair
            </button>
          </div>
          <p className="mb-4 text-[11px] text-text-muted">
            {pairs.length} of 33 pairs active · click + Add pair for the
            dropdown
          </p>

          <div className="space-y-1.5">
            <label className="text-sm font-medium text-text-primary">
              Custom pair (advanced)
            </label>
            <input
              type="text"
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
            {tfs.map((tf, idx) => (
              <button
                key={tf.label}
                onClick={() => toggleTf(idx)}
                className={cn(
                  "min-h-[36px] rounded-md px-3 py-1.5 font-mono text-xs font-medium transition-colors",
                  tf.active
                    ? "bg-accent-brand text-bg-0"
                    : "bg-bg-2 text-text-muted hover:bg-bg-3"
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
            <select className="min-h-[44px] w-full rounded-lg border border-border-default bg-bg-2 px-3 py-2 text-sm text-text-primary">
              <option>OKX (primary · highest free quality)</option>
              <option>Kraken</option>
              <option>CoinGecko (daily-only fallback)</option>
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
            defaultOn={false}
          />
          <ToggleRow
            label="Compact watchlist mode"
            sublabel="Removes sparkline column to fit more pairs in a single view on smaller laptops"
            defaultOn={false}
          />
        </div>
      </div>

      {/* Button row */}
      <div className="flex flex-wrap gap-3">
        <button className="inline-flex min-h-[44px] items-center gap-2 rounded-lg bg-accent-brand px-5 py-2.5 text-sm font-semibold text-bg-0 transition-colors hover:bg-accent-brand/90">
          <span>💾</span>
          <span>Save Trading Config</span>
        </button>
        <button className="inline-flex min-h-[44px] items-center gap-2 rounded-lg border border-border-default bg-bg-2 px-5 py-2.5 text-sm font-medium text-text-primary transition-colors hover:bg-bg-3">
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
  defaultOn,
}: {
  label: string;
  sublabel: string;
  defaultOn: boolean;
}) {
  const [on, setOn] = useState(defaultOn);
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border-default pb-4 last:border-0 last:pb-0">
      <div className="min-w-0">
        <div className="text-sm font-medium text-text-primary">{label}</div>
        <div className="mt-0.5 text-[11px] text-text-muted">{sublabel}</div>
      </div>
      <button
        onClick={() => setOn(!on)}
        className={cn(
          "relative h-6 w-11 shrink-0 rounded-full transition-colors",
          on ? "bg-accent-brand" : "bg-bg-3"
        )}
      >
        <span
          className={cn(
            "absolute top-1 h-4 w-4 rounded-full bg-white transition-transform",
            on ? "left-6" : "left-1"
          )}
        />
      </button>
    </div>
  );
}
