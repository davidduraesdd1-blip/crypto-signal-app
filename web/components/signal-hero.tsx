import { cn } from "@/lib/utils";

export type SignalType = "buy" | "hold" | "sell";

interface SignalHeroProps {
  ticker: string;
  name: string;
  price: string;
  change24h: string;
  change30d: string;
  change1y: string;
  signal: SignalType;
  signalStrength: string;
  timeframe: string;
  regime: string;
  confidence: string;
  regimeAge: string;
}

const signalConfig: Record<SignalType, { icon: string; label: string; bgClass: string; textClass: string }> = {
  buy: { 
    icon: "▲", 
    label: "Buy", 
    bgClass: "bg-[color-mix(in_srgb,var(--success)_16%,transparent)]",
    textClass: "text-success"
  },
  hold: { 
    icon: "■", 
    label: "Hold", 
    bgClass: "bg-[color-mix(in_srgb,var(--warning)_16%,transparent)]",
    textClass: "text-warning"
  },
  sell: { 
    icon: "▼", 
    label: "Sell", 
    bgClass: "bg-[color-mix(in_srgb,var(--danger)_16%,transparent)]",
    textClass: "text-danger"
  },
};

export function SignalHero({
  ticker,
  name,
  price,
  change24h,
  change30d,
  change1y,
  signal,
  signalStrength,
  timeframe,
  regime,
  confidence,
  regimeAge,
}: SignalHeroProps) {
  const config = signalConfig[signal];
  const is24hPositive = change24h.startsWith("+");
  const is30dPositive = change30d.startsWith("+");
  const is1yPositive = change1y.startsWith("+");

  return (
    <div className="flex flex-col items-start justify-between gap-4 rounded-xl border border-border-default bg-bg-1 p-5 md:flex-row md:items-center md:p-6">
      <div className="min-w-0">
        <div className="text-sm font-medium text-text-secondary">
          {ticker} · {name}
        </div>
        <div className="mt-1.5 font-mono text-[34px] font-semibold leading-none tracking-tight md:text-[52px]">
          {price}
        </div>
        <div className="mt-1.5 font-mono text-sm">
          <span className={is24hPositive ? "text-success" : "text-danger"}>
            {change24h} · 24h
          </span>
          <span className="text-text-muted"> · </span>
          <span className={is30dPositive ? "text-success" : "text-danger"}>
            {change30d} · 30d
          </span>
          <span className="text-text-muted"> · </span>
          <span className={is1yPositive ? "text-success" : "text-danger"}>
            {change1y} · 1Y
          </span>
        </div>
      </div>

      <div className="flex flex-col items-start gap-1 md:items-end">
        <span
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full px-4 py-2.5 text-[15px] font-semibold tracking-wide",
            config.bgClass,
            config.textClass
          )}
        >
          {config.icon} {config.label} · {signalStrength} · {timeframe}
        </span>
        <div className="flex items-center gap-1.5 text-xs text-text-muted">
          <span className="h-1.5 w-1.5 rounded-full bg-accent-brand" />
          Regime: {regime} · {confidence} conf · stable {regimeAge}
        </div>
      </div>
    </div>
  );
}
