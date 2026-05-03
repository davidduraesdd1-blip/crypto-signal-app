import { cn } from "@/lib/utils";

interface KpiCardProps {
  label: string;
  value: string;
  subtitle?: string;
  valueColor?: "default" | "success" | "danger" | "accent";
  subtitleDirection?: "up" | "down" | "neutral";
}

export function KpiCard({
  label,
  value,
  subtitle,
  valueColor = "default",
  subtitleDirection = "neutral",
}: KpiCardProps) {
  return (
    <div className="rounded-xl border border-border bg-bg-1 p-4">
      <div className="text-[11px] font-medium uppercase tracking-wider text-text-muted">
        {label}
      </div>
      <div
        className={cn(
          "mt-1 font-mono text-[22px] font-semibold leading-tight",
          valueColor === "success" && "text-success",
          valueColor === "danger" && "text-danger",
          valueColor === "accent" && "text-accent-brand"
        )}
      >
        {value}
      </div>
      {subtitle && (
        <div
          className={cn(
            "mt-1 font-mono text-[11.5px]",
            subtitleDirection === "up" && "text-success",
            subtitleDirection === "down" && "text-danger",
            subtitleDirection === "neutral" && "text-text-muted"
          )}
        >
          {subtitle}
        </div>
      )}
    </div>
  );
}
