"use client";

const steps = [
  { num: 1, name: "TICK", detail: "fires every interval_seconds" },
  { num: 2, name: "GATHER", detail: "composite signal + regime + position state" },
  { num: 3, name: "PRE-GATE", detail: "drawdown · daily P&L · concurrent · cooldown · emergency" },
  { num: 4, name: "CLAUDE", detail: "Sonnet 4.6 → APPROVE | REJECT | SKIP" },
  { num: 5, name: "POST-GATE", detail: "size cap · slippage · pair allowlist" },
  { num: 6, name: "EXECUTE", detail: "place order (or log-only in dry-run)" },
  { num: 7, name: "LOOP", detail: "sleep until next tick" },
];

export function PipelineDiagram() {
  return (
    <div className="rounded-xl border border-border-default bg-bg-1 p-4">
      {/* Horizontal flow diagram */}
      <div className="overflow-x-auto pb-2">
        <div className="flex min-w-max items-start gap-2">
          {steps.map((step, i) => (
            <div key={step.num} className="flex items-start">
              {/* Step box */}
              <div className="flex flex-col items-center">
                <div className="rounded-lg border border-accent-brand/30 bg-accent-brand/5 px-3 py-2 text-center">
                  <div className="text-[10px] font-medium uppercase tracking-wider text-text-muted">
                    {step.num}
                  </div>
                  <div className="font-mono text-xs font-semibold text-accent-brand">
                    {step.name}
                  </div>
                </div>
                <div className="mt-1.5 max-w-[100px] text-center text-[10px] leading-tight text-text-muted">
                  {step.detail}
                </div>
              </div>
              {/* Arrow between steps */}
              {i < steps.length - 1 && (
                <div className="flex h-10 items-center px-1 text-text-muted">
                  <span className="text-xs">→</span>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Footer comments - real stack */}
      <div className="mt-4 space-y-1 border-t border-border-default pt-4 font-mono text-[11px] text-text-muted">
        <p>{"// Crash safety: supervisor restarts process on uncaught exception"}</p>
        <p>{"// State: position state and config persist to alerts_config.json"}</p>
        <p>{"// Audit: every cycle decision written to agent_log.jsonl with rationale"}</p>
      </div>
    </div>
  );
}
