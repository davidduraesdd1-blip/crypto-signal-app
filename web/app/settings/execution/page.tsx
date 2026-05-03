"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { useSettings, useSaveSettings } from "@/hooks/use-settings";
import { useTestExchangeConnection } from "@/hooks/use-exchange";

// AUDIT-2026-05-03 (D4c): Execution settings page wired:
// - useSettings() hydrates live_trading_enabled / auto_execute /
//   exchange / max_order_size_usd / default_order_type /
//   slippage_tolerance_pct
// - useSaveSettings({group: "execution"}) on Save button
// - useTestExchangeConnection() on the Test OKX Connection button —
//   surfaces the {ok, balance_usdt, error} response inline

function SliderField({
  label,
  value,
  unit = "%",
  help,
  min = 0,
  max = 100,
  step = 1,
  onChange,
}: {
  label: string;
  value: number;
  unit?: string;
  help?: string;
  min?: number;
  max?: number;
  step?: number;
  onChange?: (v: number) => void;
}) {
  const fillPercent = Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100));
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-text-primary">{label}</span>
        <span className="font-mono text-sm text-text-secondary">
          {value.toLocaleString()}
          {unit}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange?.(Number(e.target.value))}
        style={{
          background: `linear-gradient(to right, var(--accent-brand, #00d4aa) 0%, var(--accent-brand, #00d4aa) ${fillPercent}%, var(--bg-2, #1a1a22) ${fillPercent}%, var(--bg-2, #1a1a22) 100%)`,
          height: "8px",
          borderRadius: "9999px",
          appearance: "none",
        }}
        className="w-full"
      />
      {help && <p className="text-[11px] text-text-muted">{help}</p>}
    </div>
  );
}

export default function ExecutionSettingsPage() {
  const settingsQuery = useSettings();
  const saveMutation = useSaveSettings();
  const testConnectionMutation = useTestExchangeConnection();

  const [liveMode, setLiveMode] = useState(false);
  const [autoExecute, setAutoExecute] = useState(true);
  const [exchange, setExchange] = useState("OKX");
  const [maxOrderSizeUsd, setMaxOrderSizeUsd] = useState(1000);
  const [defaultOrderType, setDefaultOrderType] = useState("market");
  const [slippageTolerance, setSlippageTolerance] = useState(0.5);
  const [autoExecConfidence, setAutoExecConfidence] = useState(80);

  // Hydrate from API
  useEffect(() => {
    const e = settingsQuery.data?.execution;
    if (!e) return;
    if (typeof e.live_trading_enabled === "boolean") setLiveMode(e.live_trading_enabled);
    if (typeof e.auto_execute === "boolean") setAutoExecute(e.auto_execute);
    if (typeof e.exchange === "string") setExchange(e.exchange);
    if (typeof e.max_order_size_usd === "number") setMaxOrderSizeUsd(e.max_order_size_usd);
    if (typeof e.default_order_type === "string") setDefaultOrderType(e.default_order_type);
    if (typeof e.slippage_tolerance_pct === "number") setSlippageTolerance(e.slippage_tolerance_pct);
  }, [settingsQuery.data]);

  const handleSave = () => {
    saveMutation.mutate({
      group: "execution",
      patch: {
        live_trading_enabled: liveMode,
        auto_execute: autoExecute,
        exchange,
        max_order_size_usd: maxOrderSizeUsd,
        default_order_type: defaultOrderType,
        slippage_tolerance_pct: slippageTolerance,
      },
    });
  };

  const saveStatus = saveMutation.data?.status;
  const rejected = saveMutation.data?.rejected ?? [];
  const testResult = testConnectionMutation.data;

  return (
    <div className="space-y-6">
      {/* Danger banner: Live trading mode */}
      <div
        className={cn(
          "rounded-xl border-l-4 p-4",
          liveMode
            ? "border-l-danger bg-danger/10"
            : "border-l-danger bg-danger/5",
        )}
      >
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <span className="text-xl">🛡️</span>
            <div>
              <h3 className="text-sm font-semibold text-danger">
                Live trading mode {liveMode ? "· ON" : "· OFF"}
              </h3>
              <p className="mt-0.5 text-[12px] text-text-secondary">
                OFF = paper simulation only · ON = real orders sent to OKX with
                real funds. The 7-gate circuit breaker still applies.
              </p>
            </div>
          </div>
          <button
            onClick={() => setLiveMode(!liveMode)}
            className={cn(
              "relative h-6 w-11 shrink-0 rounded-full transition-colors",
              liveMode ? "bg-danger" : "bg-bg-3",
            )}
            aria-label="Toggle live trading mode"
          >
            <span
              className={cn(
                "absolute top-1 h-4 w-4 rounded-full bg-white transition-transform",
                liveMode ? "left-6" : "left-1",
              )}
            />
          </button>
        </div>
      </div>

      {/* Card 1: Auto-execute on scan */}
      <div className="rounded-xl border border-border-default bg-bg-1 p-4">
        <h3 className="text-sm font-semibold text-text-primary">
          Auto-execute on scan
        </h3>
        <p className="mb-4 text-[11px] text-text-muted">
          automatically place orders for HIGH_CONF signals after each scan ·
          respects the live/paper toggle above
        </p>

        <div className="space-y-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-sm font-medium text-text-primary">
                Enable auto-execute
              </div>
              <p className="mt-0.5 text-[11px] text-text-muted">
                when ON, signals above the confidence threshold trigger orders
                without manual review
              </p>
            </div>
            <button
              onClick={() => setAutoExecute(!autoExecute)}
              className={cn(
                "relative h-6 w-11 shrink-0 rounded-full transition-colors",
                autoExecute ? "bg-accent-brand" : "bg-bg-3",
              )}
            >
              <span
                className={cn(
                  "absolute top-1 h-4 w-4 rounded-full bg-white transition-transform",
                  autoExecute ? "left-6" : "left-1",
                )}
              />
            </button>
          </div>

          <SliderField
            label="Auto-execute confidence threshold"
            value={autoExecConfidence}
            min={70}
            max={95}
            onChange={setAutoExecConfidence}
            help="TODO(D-ext): no FastAPI key today; persists locally only"
          />
        </div>
      </div>

      {/* Card 2: OKX API keys + Execution settings */}
      <div className="rounded-xl border border-border-default bg-bg-1 p-4">
        <h3 className="text-sm font-semibold text-text-primary">
          OKX API keys + execution config
        </h3>
        <p className="mb-4 text-[11px] text-text-muted">
          create a key at okx.com → API Management · grant Read + Trade +
          Futures · NEVER grant Withdrawal
        </p>

        {/* Warning callout — copy now matches Phase D secrets architecture */}
        <div className="mb-4 rounded-lg border border-warning/30 bg-warning/5 p-3">
          <div className="flex items-start gap-2 text-[12px] text-warning">
            <span>⚠</span>
            <span>
              Security · OKX keys live in Render env vars (production) or
              <code className="mx-1 rounded bg-bg-1 px-1 font-mono">.env.local</code>
              (local dev). Never written to git.
            </span>
          </div>
        </div>

        {/* 3-col grid of password inputs — read-only since we read keys
            from env on the FastAPI side */}
        <div className="mb-4 grid gap-3 md:grid-cols-3">
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-text-primary">
              API Key
            </label>
            <input
              type="password"
              placeholder="●●●● (set via OKX_API_KEY env var)"
              disabled
              className="min-h-[44px] w-full rounded-lg border border-border-default bg-bg-2 px-3 py-2 font-mono text-sm text-text-primary disabled:opacity-60"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-text-primary">
              Secret
            </label>
            <input
              type="password"
              placeholder="●●●● (set via OKX_API_SECRET env var)"
              disabled
              className="min-h-[44px] w-full rounded-lg border border-border-default bg-bg-2 px-3 py-2 font-mono text-sm text-text-primary disabled:opacity-60"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-text-primary">
              Passphrase
            </label>
            <input
              type="password"
              placeholder="●●●● (set via OKX_PASSPHRASE env var)"
              disabled
              className="min-h-[44px] w-full rounded-lg border border-border-default bg-bg-2 px-3 py-2 font-mono text-sm text-text-primary disabled:opacity-60"
            />
          </div>
        </div>
        <p className="mb-4 text-[11px] text-text-muted">
          Set these in the Render dashboard. Test the connection after saving.
        </p>

        {/* Exchange + Default order type + Max order size + Slippage */}
        <div className="mb-4 grid gap-4 md:grid-cols-2">
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-text-primary">
              Exchange
            </label>
            <select
              value={exchange}
              onChange={(e) => setExchange(e.target.value)}
              className="min-h-[44px] w-full rounded-lg border border-border-default bg-bg-2 px-3 py-2 text-sm text-text-primary"
            >
              <option>OKX</option>
              <option>Binance</option>
              <option>Kraken</option>
              <option>Bybit</option>
            </select>
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-text-primary">
              Default order type
            </label>
            <select
              value={defaultOrderType}
              onChange={(e) => setDefaultOrderType(e.target.value)}
              className="min-h-[44px] w-full rounded-lg border border-border-default bg-bg-2 px-3 py-2 text-sm text-text-primary"
            >
              <option value="market">Market</option>
              <option value="limit">Limit</option>
            </select>
            <p className="text-[11px] text-text-muted">
              Market = immediate fill · Limit = post-only at specified price
            </p>
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-text-primary">
              Max order size USD
            </label>
            <input
              type="number"
              value={maxOrderSizeUsd}
              onChange={(e) => setMaxOrderSizeUsd(Number(e.target.value))}
              min={0}
              className="min-h-[44px] w-full rounded-lg border border-border-default bg-bg-2 px-3 py-2 font-mono text-sm text-text-primary"
            />
            <p className="text-[11px] text-text-muted">
              Per-order ceiling enforced by execution.place_order (P4-C-3)
            </p>
          </div>
          <div className="space-y-1.5">
            <SliderField
              label="Slippage tolerance"
              value={slippageTolerance}
              max={5}
              step={0.1}
              onChange={setSlippageTolerance}
              help="Max %% deviation from quote at fill · trades exceeding this are rejected"
            />
          </div>
        </div>

        {/* Test connection result */}
        {testResult && (
          <div
            className={cn(
              "mb-4 rounded-lg border p-3 text-sm",
              testResult.ok
                ? "border-success/30 bg-success/5 text-success"
                : "border-danger/30 bg-danger/5 text-danger",
            )}
          >
            {testResult.ok ? (
              <>
                ✓ Connected · USDT balance:{" "}
                {testResult.balance_usdt.toLocaleString("en-US", {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </>
            ) : (
              <>✗ {testResult.error ?? "connection failed"}</>
            )}
          </div>
        )}
        {testConnectionMutation.isError && (
          <div className="mb-4 rounded-lg border border-danger/30 bg-danger/5 p-3 text-sm text-danger">
            Test failed — {String(testConnectionMutation.error?.message ?? "unknown error")}
          </div>
        )}

        {/* Save status / rejected fields */}
        {saveMutation.isError && (
          <div className="mb-4 rounded-lg border border-danger/30 bg-danger/5 p-3 text-sm text-danger">
            Save failed — {String(saveMutation.error?.message ?? "unknown error")}
          </div>
        )}
        {saveStatus === "ok" && saveMutation.isSuccess && rejected.length === 0 && (
          <div className="mb-4 rounded-lg border border-success/30 bg-success/5 p-3 text-sm text-success">
            Saved · all values applied to alerts_config.json
          </div>
        )}
        {saveStatus === "partial" && rejected.length > 0 && (
          <div className="mb-4 rounded-lg border border-warning/30 bg-warning/5 p-3 text-sm">
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
            <span>{saveMutation.isPending ? "Saving…" : "Save Execution Config"}</span>
          </button>
          <button
            type="button"
            onClick={() => testConnectionMutation.mutate()}
            disabled={testConnectionMutation.isPending}
            className="inline-flex min-h-[44px] items-center gap-2 rounded-lg border border-border-default bg-bg-2 px-5 py-2.5 text-sm font-medium text-text-primary transition-colors hover:bg-bg-3 disabled:opacity-60 disabled:cursor-wait"
          >
            <span className={cn(testConnectionMutation.isPending && "animate-spin")}>🔌</span>
            <span>{testConnectionMutation.isPending ? "Testing…" : "Test OKX Connection"}</span>
          </button>
        </div>
      </div>

      {/* Cross-link card */}
      <div className="rounded-xl border border-dashed border-border-default bg-bg-2 p-4">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div className="flex items-start gap-3">
            <span className="text-xl">🤖</span>
            <div>
              <h3 className="text-sm font-semibold text-text-primary">
                Looking for autonomous agent settings?
              </h3>
              <p className="mt-0.5 text-[12px] text-text-secondary">
                Agent enable/dry-run, cycle interval, min confidence, position
                caps, daily-loss limit, and emergency stop now live on the AI
                Assistant page (Account → AI Assistant).
              </p>
            </div>
          </div>
          <Link
            href="/ai-assistant"
            className="inline-flex min-h-[44px] shrink-0 items-center gap-2 rounded-lg border border-accent-brand px-4 py-2 text-sm font-medium text-accent-brand transition-colors hover:bg-accent-brand/10"
          >
            Open AI Assistant →
          </Link>
        </div>
      </div>
    </div>
  );
}
