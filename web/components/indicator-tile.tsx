import { cn } from "@/lib/utils";

interface IndicatorTileProps {
  label: string;
  value: string;
  subtext?: string;
  variant?: "default" | "success" | "warning" | "danger";
}

export function IndicatorTile({ label, value, subtext, variant = "default" }: IndicatorTileProps) {
  return (
    <div className="min-w-0 overflow-hidden rounded-lg bg-bg-2 p-3">
      <div className="truncate text-[11px] font-medium uppercase tracking-wider text-text-muted">
        {label}
      </div>
      <div
        className={cn(
          "mt-1 truncate font-mono text-base font-semibold",
          variant === "default" && "text-text-primary",
          variant === "success" && "text-success",
          variant === "warning" && "text-warning",
          variant === "danger" && "text-danger"
        )}
      >
        {value}
      </div>
      {subtext && (
        <div className="mt-0.5 truncate font-mono text-[11.5px] text-text-muted">
          {subtext}
        </div>
      )}
    </div>
  );
}

interface IndicatorGridProps {
  children: React.ReactNode;
  columns?: 2 | 4 | 5;
}

export function IndicatorGrid({ children, columns = 4 }: IndicatorGridProps) {
  return (
    <div
      className={cn(
        "grid gap-3",
        columns === 2 && "grid-cols-1 md:grid-cols-2",
        columns === 4 && "grid-cols-1 md:grid-cols-2 lg:grid-cols-4",
        columns === 5 && "grid-cols-2 md:grid-cols-3 lg:grid-cols-5"
      )}
    >
      {children}
    </div>
  );
}
