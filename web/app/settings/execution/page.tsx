"use client";

import { useState } from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";

function SliderField({
  label,
  value,
  unit = "%",
  help,
  fillPercent,
}: {
  label: string;
  value: number;
  unit?: string;
  help?: string;
  fillPercent: number;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-text-primary">{label}</span>
        <span className="font-mono text-sm text-text-secondary">
          {value.toLocaleString()}
          {unit}
        </span>
      </div>
      <div className="relative h-2 w-full rounded-full bg-bg-2">
        <div
          className="absolute left-0 top-0 h-full rounded-full bg-accent-brand"
          style={{ width: `${fillPercent}%` }}
        />
        <div
          className="absolute top-1/2 h-3.5 w-3.5 -translate-y-1/2 rounded-full border-2 border-accent-brand bg-bg-0 shadow-[0_0_0_3px_rgba(0,255,136,0.15)]"
          style={{ left: `calc(${fillPercent}% - 7px)` }}
        />
      </div>
      {help && <p className="text-[11px] text-text-muted">{help}</p>}
    </div>
  );
}

export default function ExecutionSettingsPage() {
  const [liveMode, setLiveMode] = useState(false);
  const [autoExecute, setAutoExecute] = useState(true);

  return (
    <div className="space-y-6">
      {/* Danger banner: Live trading mode */}
      <div
        className={cn(
          "rounded-xl border-l-4 p-4",
          liveMode
            ? "border-l-danger bg-danger/10"
            : "border-l-danger bg-danger/5"
        )}
      >
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <span className="text-xl">🛡️</span>
            <div>
              <h3
                className={cn(
                  "text-sm font-semibold",
                  liveMode ? "text-danger" : "text-danger"
                )}
              >
                Live trading mode
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
              liveMode ? "bg-danger" : "bg-bg-3"
            )}
          >
            <span
              className={cn(
                "absolute top-1 h-4 w-4 rounded-full bg-white transition-transform",
                liveMode ? "left-6" : "left-1"
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
                autoExecute ? "bg-accent-brand" : "bg-bg-3"
              )}
            >
              <span
                className={cn(
                  "absolute top-1 h-4 w-4 rounded-full bg-white transition-transform",
                  autoExecute ? "left-6" : "left-1"
                )}
              />
            </button>
          </div>

          <SliderField
            label="Auto-execute confidence threshold"
            value={80}
            fillPercent={80}
            help="Range 70–95% · only signals above this confidence auto-execute"
          />
        </div>
      </div>

      {/* Card 2: OKX API keys */}
      <div className="rounded-xl border border-border-default bg-bg-1 p-4">
        <h3 className="text-sm font-semibold text-text-primary">
          OKX API keys
        </h3>
        <p className="mb-4 text-[11px] text-text-muted">
          create a key at okx.com → API Management · grant Read + Trade +
          Futures · NEVER grant Withdrawal
        </p>

        {/* Warning callout */}
        <div className="mb-4 rounded-lg border border-warning/30 bg-warning/5 p-3">
          <div className="flex items-start gap-2 text-[12px] text-warning">
            <span>⚠</span>
            <span>
              Security · API keys are stored encrypted in
              .streamlit/secrets.toml · this file is in .gitignore · never
              commit it.
            </span>
          </div>
        </div>

        {/* 3-col grid of password inputs */}
        <div className="mb-4 grid gap-3 md:grid-cols-3">
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-text-primary">
              API Key
            </label>
            <input
              type="password"
              placeholder="●●●● (saved)"
              className="min-h-[44px] w-full rounded-lg border border-border-default bg-bg-2 px-3 py-2 font-mono text-sm text-text-primary"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-text-primary">
              Secret
            </label>
            <input
              type="password"
              placeholder="●●●● (saved)"
              className="min-h-[44px] w-full rounded-lg border border-border-default bg-bg-2 px-3 py-2 font-mono text-sm text-text-primary"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-text-primary">
              Passphrase
            </label>
            <input
              type="password"
              placeholder="●●●● (saved)"
              className="min-h-[44px] w-full rounded-lg border border-border-default bg-bg-2 px-3 py-2 font-mono text-sm text-text-primary"
            />
          </div>
        </div>
        <p className="mb-4 text-[11px] text-text-muted">
          Leave a field blank to keep the currently saved value. Test the
          connection after saving.
        </p>

        {/* Default order type */}
        <div className="mb-4 max-w-[300px] space-y-1.5">
          <label className="text-sm font-medium text-text-primary">
            Default order type
          </label>
          <select className="min-h-[44px] w-full rounded-lg border border-border-default bg-bg-2 px-3 py-2 text-sm text-text-primary">
            <option>Market</option>
            <option>Limit</option>
          </select>
          <p className="text-[11px] text-text-muted">
            Market = immediate fill at current price · Limit = post-only at
            specified price
          </p>
        </div>

        {/* Button row */}
        <div className="flex flex-wrap gap-3">
          <button className="inline-flex min-h-[44px] items-center gap-2 rounded-lg bg-accent-brand px-5 py-2.5 text-sm font-semibold text-bg-0 transition-colors hover:bg-accent-brand/90">
            <span>💾</span>
            <span>Save Execution Config</span>
          </button>
          <button className="inline-flex min-h-[44px] items-center gap-2 rounded-lg border border-border-default bg-bg-2 px-5 py-2.5 text-sm font-medium text-text-primary transition-colors hover:bg-bg-3">
            <span>🔌</span>
            <span>Test OKX Connection</span>
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
