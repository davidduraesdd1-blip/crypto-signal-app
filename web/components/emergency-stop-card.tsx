"use client";

interface EmergencyStopCardProps {
  active?: boolean;
  onActivate?: () => void;
}

export function EmergencyStopCard({ active = false, onActivate }: EmergencyStopCardProps) {
  return (
    <div className="rounded-xl border border-l-[3px] border-danger/30 border-l-danger bg-danger/5 p-4">
      <h3 className="text-sm font-semibold text-danger">🚨 Emergency Stop</h3>
      <p className="mb-4 text-[11px] text-text-muted">
        halts all new entries immediately · existing positions stay open · clear to resume
      </p>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2 text-sm">
          <span className="inline-block h-2 w-2 rounded-full bg-text-muted" />
          <span className="text-text-secondary">No emergency stop · agent operating normally</span>
        </div>
        <button
          onClick={onActivate}
          className="inline-flex min-h-[44px] items-center gap-2 rounded-lg border border-danger bg-danger/10 px-4 py-2 text-sm font-semibold text-danger transition-colors hover:bg-danger/20"
        >
          <span>🚨</span>
          <span>Activate Emergency Stop</span>
        </button>
      </div>
    </div>
  );
}
