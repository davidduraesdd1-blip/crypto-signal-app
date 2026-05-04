"use client";

import { useId, useState } from "react";
import { cn } from "@/lib/utils";

interface SliderFieldProps {
  label: string;
  value: number;
  unit?: string;
  min: number;
  max: number;
  help?: string;
  fillPercent: number;
}

function SliderField({ label, value, unit = "%", min, max, help, fillPercent }: SliderFieldProps) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-text-primary">{label}</span>
        <span className="font-mono text-sm text-text-secondary">
          {value.toLocaleString()}{unit}
        </span>
      </div>
      <div className="relative h-2 w-full rounded-full bg-bg-2">
        <div
          className="absolute left-0 top-0 h-full rounded-full bg-accent-brand"
          style={{ width: `${fillPercent}%` }}
        />
        {/* Thumb */}
        <div
          className="absolute top-1/2 h-3.5 w-3.5 -translate-y-1/2 rounded-full border-2 border-accent-brand bg-bg-0 shadow-[0_0_0_3px_rgba(0,255,136,0.15)]"
          style={{ left: `calc(${fillPercent}% - 7px)` }}
        />
      </div>
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

export function AgentConfigCard() {
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
            value={75}
            min={50}
            max={99}
            fillPercent={50}
            help="Composite confidence floor before agent considers acting · 50–99%"
          />
          <SliderField
            label="Max Trade Size"
            value={10}
            min={0}
            max={50}
            fillPercent={20}
            help="Hard cap on any single trade as % of total portfolio equity"
          />
          <SliderField
            label="Cooldown After Loss"
            value={1800}
            unit="s"
            min={0}
            max={86400}
            fillPercent={30}
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
            value={5}
            min={0}
            max={50}
            fillPercent={10}
            help="Agent halts new entries when daily P&L drops below this"
          />
          <SliderField
            label="Max Drawdown from Peak"
            value={15}
            min={0}
            max={50}
            fillPercent={25}
            help="Halts all entries if portfolio drawdown exceeds this from peak"
          />
          <button className="mt-2 inline-flex min-h-[44px] items-center gap-2 rounded-lg bg-accent-brand px-5 py-2.5 text-sm font-semibold text-bg-0 transition-colors hover:bg-accent-brand/90">
            Save Agent Config
          </button>
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
