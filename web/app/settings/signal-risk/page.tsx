"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { useSettings, useSaveSettings } from "@/hooks/use-settings";

// AUDIT-2026-05-03 (D4c): Signal-Risk page wired:
// - useSettings() hydrates min_confidence_threshold + high_conf_threshold +
//   min_alert_confidence + max_drawdown_pct + position_size_pct
// - useSaveSettings({group: "signal-risk", patch}) on Save
// - rejected[] surfaces inline as before
// Position-sizing fields (Portfolio size USD / Max exposure / Max
// position cap USD / Max open per pair) stay as visual mock — those
// keys aren't in the _SIGNAL_RISK_KEYS allowlist on the FastAPI
// side; they're either dev-tools (portfolio_size_usd lives in
// agent_portfolio_size_usd) or future settings groups.

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
        className="w-full"
        style={{
          // Show the same gradient track via background-image so the
          // styled track stays visible underneath the native input.
          background: `linear-gradient(to right, var(--accent-brand, #00d4aa) 0%, var(--accent-brand, #00d4aa) ${fillPercent}%, var(--bg-2, #1a1a22) ${fillPercent}%, var(--bg-2, #1a1a22) 100%)`,
          height: "8px",
          borderRadius: "9999px",
          appearance: "none",
        }}
      />
      {help && <p className="text-[11px] text-text-muted">{help}</p>}
    </div>
  );
}

function InputField({
  label,
  value,
  help,
  onChange,
  type = "text",
}: {
  label: string;
  value: string | number;
  help?: string;
  onChange?: (v: string) => void;
  type?: string;
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium text-text-primary">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange?.(e.target.value)}
        className="min-h-[44px] w-full rounded-lg border border-border-default bg-bg-2 px-3 py-2 font-mono text-sm text-text-primary"
      />
      {help && <p className="text-[11px] text-text-muted">{help}</p>}
    </div>
  );
}

const compositeWeights = [
  // Visual reference — actual weights live in alerts_config under
  // composite_layer_weights and adjust per regime via Optuna.
  { layer: "Layer 1 · Technical", weight: "0.30" },
  { layer: "Layer 2 · Macro", weight: "0.15" },
  { layer: "Layer 3 · Sentiment", weight: "0.20" },
  { layer: "Layer 4 · On-chain", weight: "0.35" },
];

export default function SignalRiskSettingsPage() {
  const settingsQuery = useSettings();
  const saveMutation = useSaveSettings();

  // Form state — persisted keys (per _SIGNAL_RISK_KEYS in routers/settings.py)
  const [minConfidence, setMinConfidence] = useState(60);
  const [highConfThreshold, setHighConfThreshold] = useState(75);
  const [minAlertConfidence, setMinAlertConfidence] = useState(70);
  const [maxDrawdownPct, setMaxDrawdownPct] = useState(15);
  const [positionSizePct, setPositionSizePct] = useState(2);

  // Visual-only fields (no API contract today)
  const [portfolioSizeUsd, setPortfolioSizeUsd] = useState("100000");
  const [maxPositionCapUsd, setMaxPositionCapUsd] = useState("25000");
  const [maxOpenPerPair, setMaxOpenPerPair] = useState("1");
  const [maxExposure, setMaxExposure] = useState(35);
  const [mtfAlignment, setMtfAlignment] = useState(60);
  const [regimeConfidence, setRegimeConfidence] = useState(55);

  // Hydrate from API
  useEffect(() => {
    const sr = settingsQuery.data?.signal_risk;
    if (!sr) return;
    if (typeof sr.min_confidence_threshold === "number") setMinConfidence(sr.min_confidence_threshold);
    if (typeof sr.high_conf_threshold === "number") setHighConfThreshold(sr.high_conf_threshold);
    if (typeof sr.min_alert_confidence === "number") setMinAlertConfidence(sr.min_alert_confidence);
    if (typeof sr.max_drawdown_pct === "number") setMaxDrawdownPct(sr.max_drawdown_pct);
    if (typeof sr.position_size_pct === "number") setPositionSizePct(sr.position_size_pct);
  }, [settingsQuery.data]);

  const handleSave = () => {
    saveMutation.mutate({
      group: "signal-risk",
      patch: {
        min_confidence_threshold: minConfidence,
        high_conf_threshold: highConfThreshold,
        min_alert_confidence: minAlertConfidence,
        max_drawdown_pct: maxDrawdownPct,
        position_size_pct: positionSizePct,
      },
    });
  };

  const handleRevert = () => {
    setMinConfidence(60);
    setHighConfThreshold(75);
    setMinAlertConfidence(70);
    setMaxDrawdownPct(15);
    setPositionSizePct(2);
  };

  const saveStatus = saveMutation.data?.status;
  const rejected = saveMutation.data?.rejected ?? [];

  return (
    <div className="space-y-6">
      {/* Two-column grid */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Card 1: Position sizing */}
        <div className="rounded-xl border border-border-default bg-bg-1 p-4">
          <h3 className="text-sm font-semibold text-text-primary">
            Position sizing
          </h3>
          <p className="mb-4 text-[11px] text-text-muted">
            how much capital each signal commits
          </p>

          <div className="space-y-5">
            <InputField
              label="Portfolio size USD"
              value={portfolioSizeUsd}
              onChange={setPortfolioSizeUsd}
              help="TODO(D-ext): persists via dev-tools group · agent_portfolio_size_usd"
            />
            <SliderField
              label="Risk per trade"
              value={positionSizePct}
              max={10}
              step={0.5}
              onChange={setPositionSizePct}
              help="Max loss per trade as % of portfolio · 0.5% to 10% · persists as position_size_pct"
            />
            <SliderField
              label="Max exposure"
              value={maxExposure}
              onChange={setMaxExposure}
              help="Total open-position equity as % of portfolio · TODO(D-ext): no FastAPI key today"
            />
            <InputField
              label="Max position cap USD"
              value={maxPositionCapUsd}
              onChange={setMaxPositionCapUsd}
              help="TODO(D-ext): persists via execution group · max_order_size_usd"
            />
            <InputField
              label="Max open per pair"
              value={maxOpenPerPair}
              onChange={setMaxOpenPerPair}
              help="TODO(D-ext): no FastAPI key today"
            />
          </div>
        </div>

        {/* Card 2: Signal thresholds */}
        <div className="rounded-xl border border-border-default bg-bg-1 p-4">
          <h3 className="text-sm font-semibold text-text-primary">
            Signal thresholds
          </h3>
          <p className="mb-4 text-[11px] text-text-muted">
            composite-score floors that gate signal action
          </p>

          <div className="space-y-5">
            <SliderField
              label="Min confidence (entry)"
              value={minConfidence}
              onChange={setMinConfidence}
              help="Below this, signal is 'watch only' · persists as min_confidence_threshold"
            />
            <SliderField
              label="High-confidence threshold"
              value={highConfThreshold}
              onChange={setHighConfThreshold}
              help="Above this, signal becomes 'high conf' (UI badge) · persists as high_conf_threshold"
            />
            <SliderField
              label="Min alert confidence"
              value={minAlertConfidence}
              onChange={setMinAlertConfidence}
              help="Email / push alerts only fire above this floor · persists as min_alert_confidence"
            />
            <SliderField
              label="Max drawdown (halt)"
              value={maxDrawdownPct}
              onChange={setMaxDrawdownPct}
              max={50}
              help="Cumulative drawdown that trips the agent's circuit-breaker · persists as max_drawdown_pct"
            />
            <SliderField
              label="MTF alignment threshold"
              value={mtfAlignment}
              onChange={setMtfAlignment}
              help="% of active timeframes that must agree · TODO(D-ext): no FastAPI key today"
            />
            <SliderField
              label="Regime-confidence floor"
              value={regimeConfidence}
              onChange={setRegimeConfidence}
              help="HMM regime must report ≥ this confidence · TODO(D-ext): no FastAPI key today"
            />

            {/* Composite layer weights — visual reference */}
            <div className="space-y-2">
              <label className="text-sm font-medium text-text-primary">
                Composite layer weights
              </label>
              <div className="rounded-lg bg-bg-2 p-3">
                <div className="grid grid-cols-2 gap-2 font-mono text-xs">
                  {compositeWeights.map((w) => (
                    <div
                      key={w.layer}
                      className="flex items-center justify-between"
                    >
                      <span className="text-text-secondary">{w.layer}</span>
                      <span className="text-text-primary">{w.weight}</span>
                    </div>
                  ))}
                </div>
              </div>
              <p className="text-[11px] text-text-muted">
                Auto-adjusted per regime · Bull bias on-chain, Distribution bias
                macro · edit per-regime in Advanced
              </p>
            </div>
          </div>
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
          <span>{saveMutation.isPending ? "Saving…" : "Save Signal & Risk Config"}</span>
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
