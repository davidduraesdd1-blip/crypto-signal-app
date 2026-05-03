interface PriceChartProps {
  dataSource?: string;
}

export function PriceChart({ dataSource = "yfinance · live" }: PriceChartProps) {
  return (
    <div className="flex h-full flex-col rounded-xl border border-border-default bg-bg-1 p-4">
      <div className="mb-2.5 flex items-baseline justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-text-muted">
          Price · last 90d
        </span>
        <span className="text-xs text-text-muted">{dataSource}</span>
      </div>

      {/* Chart placeholder with gradient */}
      <div className="relative h-[200px] overflow-hidden rounded-lg bg-gradient-to-b from-[color-mix(in_srgb,var(--accent)_10%,transparent)] to-transparent">
        <svg
          viewBox="0 0 600 200"
          preserveAspectRatio="none"
          className="h-full w-full"
        >
          <defs>
            <linearGradient id="chartGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.5" />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
            </linearGradient>
          </defs>
          <polyline
            fill="url(#chartGradient)"
            stroke="none"
            points="0,160 30,150 60,158 90,140 120,145 150,120 180,110 210,90 240,95 270,78 300,72 330,65 360,82 390,70 420,58 450,45 480,52 510,40 540,30 570,28 600,20 600,200 0,200"
          />
          <polyline
            fill="none"
            stroke="var(--accent)"
            strokeWidth="2"
            points="0,160 30,150 60,158 90,140 120,145 150,120 180,110 210,90 240,95 270,78 300,72 330,65 360,82 390,70 420,58 450,45 480,52 510,40 540,30 570,28 600,20"
          />
        </svg>
      </div>
    </div>
  );
}
