"use client";

interface EquityCurveProps {
  dateRange: string;
  /** Equity series, in % units (100 = start). When absent or empty,
   * renders an empty-state hint instead of fake data.
   * AUDIT-2026-05-06 (Everything-Live, item 9). */
  points?: number[];
}

const _W = 900;
const _H = 280;

function _toPolyline(values: number[], width = _W, height = _H, padTop = 20, padBot = 20): string {
  if (!values || values.length < 2) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const usable = height - padTop - padBot;
  const stepX = width / (values.length - 1);
  return values
    .map((v, i) => {
      const x = (i * stepX).toFixed(1);
      // Invert Y so higher equity is higher on screen
      const y = (padTop + (1 - (v - min) / range) * usable).toFixed(1);
      return `${x},${y}`;
    })
    .join(" ");
}

export function EquityCurve({ dateRange, points }: EquityCurveProps) {
  const havePoints = Array.isArray(points) && points.length >= 2;
  const polyline = havePoints ? _toPolyline(points!) : "";
  const fillPolyline = havePoints
    ? `${polyline} ${_W},${_H} 0,${_H}`
    : "";

  return (
    <div className="rounded-xl border border-border bg-bg-1 p-4">
      <div className="mb-2.5 flex items-baseline justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-text-muted">
          Equity curve · composite signal (cumulative)
        </span>
        <span className="text-xs text-text-muted">{dateRange}</span>
      </div>
      <div className="relative h-[200px] overflow-hidden rounded-lg bg-gradient-to-b from-success/10 to-transparent md:h-[280px]">
        {havePoints ? (
          <svg
            viewBox={`0 0 ${_W} ${_H}`}
            preserveAspectRatio="none"
            className="h-full w-full"
          >
            <defs>
              <linearGradient id="equity-fill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--success)" stopOpacity="0.35" />
                <stop offset="100%" stopColor="var(--success)" stopOpacity="0" />
              </linearGradient>
            </defs>
            <polyline fill="url(#equity-fill)" stroke="none" points={fillPolyline} />
            <polyline fill="none" stroke="var(--success)" strokeWidth="2" points={polyline} />
          </svg>
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-text-muted">
            No backtest trades yet — run a backtest to populate the equity curve.
          </div>
        )}
      </div>
      <div className="mt-3 flex gap-5 text-xs">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-3.5 bg-success" />
          Composite signal
        </span>
      </div>
    </div>
  );
}
