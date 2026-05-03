"use client";

interface EquityCurveProps {
  dateRange: string;
}

export function EquityCurve({ dateRange }: EquityCurveProps) {
  return (
    <div className="rounded-xl border border-border bg-bg-1 p-4">
      <div className="mb-2.5 flex items-baseline justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-text-muted">
          Equity curve - signal vs BTC
        </span>
        <span className="text-xs text-text-muted">{dateRange}</span>
      </div>
      <div className="relative h-[200px] overflow-hidden rounded-lg bg-gradient-to-b from-success/10 to-transparent md:h-[280px]">
        <svg
          viewBox="0 0 900 280"
          preserveAspectRatio="none"
          className="h-full w-full"
        >
          <defs>
            <linearGradient id="equity-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--success)" stopOpacity="0.35" />
              <stop offset="100%" stopColor="var(--success)" stopOpacity="0" />
            </linearGradient>
          </defs>
          {/* Signal equity fill */}
          <polyline
            fill="url(#equity-fill)"
            stroke="none"
            points="0,240 50,235 100,210 150,220 200,180 250,170 300,195 350,140 400,125 450,105 500,90 550,130 600,85 650,60 700,78 750,45 800,30 850,28 900,20 900,280 0,280"
          />
          {/* Signal equity line */}
          <polyline
            fill="none"
            stroke="var(--success)"
            strokeWidth="2"
            points="0,240 50,235 100,210 150,220 200,180 250,170 300,195 350,140 400,125 450,105 500,90 550,130 600,85 650,60 700,78 750,45 800,30 850,28 900,20"
          />
          {/* BTC buy-and-hold dashed */}
          <polyline
            fill="none"
            stroke="var(--gray-6)"
            strokeWidth="1.5"
            strokeDasharray="4,3"
            points="0,240 50,230 100,225 150,245 200,225 250,220 300,240 350,210 400,200 450,190 500,175 550,215 600,180 650,160 700,170 750,145 800,130 850,140 900,125"
          />
        </svg>
      </div>
      <div className="mt-3 flex gap-5 text-xs">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-3.5 bg-success" />
          Composite signal
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-3.5 border-t-2 border-dashed border-gray-6" />
          BTC buy-and-hold
        </span>
      </div>
    </div>
  );
}
