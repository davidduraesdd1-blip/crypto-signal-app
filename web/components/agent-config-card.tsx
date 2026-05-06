"use client";

import { useId, useState } from "react";
import { cn } from "@/lib/utils";

interface SliderFieldProps {
  label: string;
  value: number;
  unit?: string;
  min: number;
  max: number;
  step?: number;
  help?: string;
  fillPercent: number;
  onChange?: (v: number) => void;
}

function SliderField({
  label,
  value,
  unit = "%",
  min,
  max,
  step = 1,
  help,
  fillPercent,
  onChange,
}: SliderFieldProps) {
  // AUDIT-2026-05-04 (H3 — keyboard a11y): the previous SliderField was
  // decorative <div>s with no real <input type="range">, so keyboard +
  // screen-reader users couldn't operate it. Replaced with a native
  // range input styled via background gradient. label↔input association
  // via useId so axe-core "label" rule passes too.
  const id = useId();
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label htmlFor={id} className="text-sm font-medium text-text-primary">{label}</label>
        <span className="font-mono text-sm text-text-secondary">
          {value.toLocaleString()}{unit}
        </span>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange?.(Number(e.target.value))}
        aria-label={label}
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={value}
        className="w-full"
        style={{
          background: `linear-gradient(to right, var(--accent-brand, #22d36f) 0%, var(--accent-brand, #22d36f) ${fillPercent}%, var(--bg-2, #1a1a22) ${fillPercent}%, var(--bg-2, #1a1a22) 100%)`,
          height: "8px",
          borderRadius: "9999px",
          appearance: "none",
        }}
      />
      {help && <p className="text-[11px] text-text-muted">{help}</p>}
    </div>
  );
}

interface InputFieldProps {
  label: string;
  value: string | number;
  help?: string;
}

function InputField({ label, value, help }: InputFieldProps) {
  // AUDIT-2026-05-04 (T4 a11y): label↔input association via useId so
  // Lighthouse axe-core "label" rule passes on every InputField instance.
  const id = useId();
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="text-sm font-medium text-text-primary">{label}</label>
      <input
        id={id}
        type="text"
        defaultValue={value}
        className="min-h-[44px] w-full rounded-lg border border-border-default bg-bg-2 px-3 py-2 font-mono text-sm text-text-primary"
      />
      {help && <p className="text-[11px] text-text-muted">{help}</p>}
    </div>
  );
}

interface ToggleFieldProps {
  label: string;
  checked: boolean;
  sublabel?: string;
}

function ToggleField({ label, checked, sublabel }: ToggleFieldProps) {
  const [on, setOn] = useState(checked);
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <span className="text-sm font-medium text-text-primary">{label}</span>
        {sublabel && <p className="text-[11px] text-text-muted">{sublabel}</p>}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={on}
        aria-label={`${label} — ${on ? "on" : "off"}`}
        onClick={() => setOn(!on)}
        className={cn(
          "relative h-6 w-11 shrink-0 rounded-full transition-colors",
          on ? "bg-accent-brand" : "bg-bg-2"
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

// AUDIT-2026-05-06 (W2 Tier 1 F-AI-1): pre-fix every SliderField was
// rendered with a `value` prop but NO parent `onChange` — the native
// <input type="range"> was effectively read-only because React kept
// re-rendering the same controlled value. The whole card looked
// broken. Fix: hoist each slider/input into local state so the
// controls move as the user drags. Persistence to the backend is
// still pending (no /agent/config endpoint), so the "Save Agent
// Config" button stays a local-only no-op for now.
function _pct(value: number, min: number, max: number): number {
  if (max <= min) return 0;
  return Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100));
}

export function AgentConfigCard() {
  const [minConfidence, setMinConfidence] = useState(75);
  const [maxTradeSize, setMaxTradeSize] = useState(10);
  const [cooldownLoss, setCooldownLoss] = useState(1800);
  const [dailyLossLimit, setDailyLossLimit] = useState(5);
  const [maxDrawdown, setMaxDrawdown] = useState(15);

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {/* Left: Cycle behavior */}
      <div className="rounded-xl border border-border-default bg-bg-1 p-4">
        <h3 className="text-sm font-semibold text-text-primary">Cycle behavior</h3>
        <p className="mb-4 text-[11px] text-text-muted">how often and when the agent acts</p>
        <div className="space-y-5">
          <ToggleField
            label="Dry Run mode"
            checked={true}
            sublabel="log decisions only · no real orders placed"
          />
          <InputField label="Cycle Interval" value={60} help="30 to 3600 · default 60s" />
          <SliderField
            label="Min Confidence to Act"
            value={minConfidence}
            min={50}
            max={99}
            onChange={setMinConfidence}
            fillPercent={_pct(minConfidence, 50, 99)}
            help="Composite confidence floor before agent considers acting · 50–99%"
          />
          <SliderField
            label="Max Trade Size"
            value={maxTradeSize}
            min={0}
            max={50}
            onChange={setMaxTradeSize}
            fillPercent={_pct(maxTradeSize, 0, 50)}
            help="Hard cap on any single trade as % of total portfolio equity"
          />
          <SliderField
            label="Cooldown After Loss"
            value={cooldownLoss}
            unit="s"
            min={0}
            max={86400}
            step={60}
            onChange={setCooldownLoss}
            fillPercent={_pct(cooldownLoss, 0, 86400)}
            help="Pause before next trade after a losing cycle · 0 to 86,400s"
          />
        </div>
      </div>

      {/* Right: Risk limits */}
      <div className="rounded-xl border border-border-default bg-bg-1 p-4">
        <h3 className="text-sm font-semibold text-text-primary">Risk limits</h3>
        <p className="mb-4 text-[11px] text-text-muted">portfolio-level guardrails</p>
        <div className="space-y-5">
          <InputField label="Portfolio Size USD" value="100,000" />
          <InputField
            label="Max Concurrent Positions"
            value={6}
            help="1 to 10 · agent will skip new entries when at cap"
          />
          <SliderField
            label="Daily Loss Limit"
            value={dailyLossLimit}
            min={0}
            max={50}
            onChange={setDailyLossLimit}
            fillPercent={_pct(dailyLossLimit, 0, 50)}
            help="Agent halts new entries when daily P&L drops below this"
          />
          <SliderField
            label="Max Drawdown from Peak"
            value={maxDrawdown}
            min={0}
            max={50}
            onChange={setMaxDrawdown}
            fillPercent={_pct(maxDrawdown, 0, 50)}
            help="Halts all entries if portfolio drawdown exceeds this from peak"
          />
          <button
            type="button"
            className="mt-2 inline-flex min-h-[44px] items-center gap-2 rounded-lg bg-accent-brand px-5 py-2.5 text-sm font-semibold text-bg-0 transition-colors hover:bg-accent-brand/90"
            title="Backend /agent/config endpoint not in V1 — persists locally only"
          >
            Save Agent Config
          </button>
          <p className="text-[11px] text-text-muted">
            Server-side persistence pending — values reset on reload.
          </p>
          <details className="rounded-lg border border-border-default bg-bg-2">
            <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-text-secondary">
              Active Limits
            </summary>
            <div className="border-t border-border-default px-4 py-3 text-xs text-text-muted">
              Current limits are enforced in real-time by the risk engine.
            </div>
          </details>
        </div>
      </div>
    </div>
  );
}
