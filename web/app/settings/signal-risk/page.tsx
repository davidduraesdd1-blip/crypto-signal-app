"use client";

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

function InputField({
  label,
  value,
  help,
}: {
  label: string;
  value: string | number;
  help?: string;
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium text-text-primary">{label}</label>
      <input
        type="text"
        defaultValue={value}
        className="min-h-[44px] w-full rounded-lg border border-border-default bg-bg-2 px-3 py-2 font-mono text-sm text-text-primary"
      />
      {help && <p className="text-[11px] text-text-muted">{help}</p>}
    </div>
  );
}

const compositeWeights = [
  { layer: "Layer 1 · Technical", weight: "0.30" },
  { layer: "Layer 2 · Macro", weight: "0.15" },
  { layer: "Layer 3 · Sentiment", weight: "0.20" },
  { layer: "Layer 4 · On-chain", weight: "0.35" },
];

export default function SignalRiskSettingsPage() {
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
              value="100,000"
              help="Used to compute position sizes when exchange balance is unreachable"
            />
            <SliderField
              label="Risk per trade"
              value={2.0}
              fillPercent={20}
              help="Max loss per trade as % of portfolio · 0.5% to 10%"
            />
            <SliderField
              label="Max exposure"
              value={35}
              fillPercent={35}
              help="Total open-position equity as % of portfolio · sums all concurrent trades"
            />
            <InputField
              label="Max position cap USD"
              value="25,000"
              help="Hard ceiling per single position · trades larger than this are rejected at post-gate"
            />
            <InputField
              label="Max open per pair"
              value="1"
              help="1 = single concurrent position per pair · 2+ enables ladder entries"
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
              label="High-confidence threshold"
              value={75}
              fillPercent={75}
              help="Below this, signal is 'watch only' · above, signal becomes actionable (BUY/SELL)"
            />
            <SliderField
              label="MTF alignment threshold"
              value={60}
              fillPercent={60}
              help="% of active timeframes that must agree before signal fires · 60% = 4 of 6 default"
            />
            <SliderField
              label="Regime-confidence floor"
              value={55}
              fillPercent={55}
              help="HMM regime must report ≥ this confidence to weight regime-adjusted scoring"
            />

            {/* Composite layer weights */}
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

      {/* Button row */}
      <div className="flex flex-wrap gap-3">
        <button className="inline-flex min-h-[44px] items-center gap-2 rounded-lg bg-accent-brand px-5 py-2.5 text-sm font-semibold text-bg-0 transition-colors hover:bg-accent-brand/90">
          <span>💾</span>
          <span>Save Signal & Risk Config</span>
        </button>
        <button className="inline-flex min-h-[44px] items-center gap-2 rounded-lg border border-border-default bg-bg-2 px-5 py-2.5 text-sm font-medium text-text-primary transition-colors hover:bg-bg-3">
          <span>↺</span>
          <span>Revert to defaults</span>
        </button>
      </div>
    </div>
  );
}
