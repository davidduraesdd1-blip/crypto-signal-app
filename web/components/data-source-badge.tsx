import { cn } from "@/lib/utils";

type Status = "live" | "cached" | "down";

interface DataSourceBadgeProps {
  name: string;
  status: Status;
  statusLabel?: string;
}

export function DataSourceBadge({
  name,
  status,
  statusLabel,
}: DataSourceBadgeProps) {
  const statusConfig = {
    live: {
      dotClass: "bg-success",
      defaultLabel: "live",
    },
    cached: {
      dotClass: "bg-warning",
      defaultLabel: "cached",
    },
    down: {
      dotClass: "bg-danger",
      defaultLabel: "down",
    },
  };

  const config = statusConfig[status];

  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-border-default bg-bg-2 px-2 py-0.5 text-[11.5px] text-text-secondary">
      <span className={cn("h-1.5 w-1.5 rounded-full", config.dotClass)} />
      {name} · {statusLabel || config.defaultLabel}
    </span>
  );
}

interface DataSourceRowProps {
  sources: DataSourceBadgeProps[];
}

export function DataSourceRow({ sources }: DataSourceRowProps) {
  return (
    <div className="flex max-w-full flex-wrap items-center gap-2.5">
      {sources.map((source) => (
        <DataSourceBadge key={source.name} {...source} />
      ))}
    </div>
  );
}
