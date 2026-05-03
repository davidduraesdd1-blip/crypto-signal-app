import { cn } from "@/lib/utils";

interface MacroItem {
  label: string;
  value: string;
  sub: string;
  subColor?: "default" | "warning" | "success" | "accent";
}

interface MacroStripProps {
  items: MacroItem[];
}

export function MacroStrip({ items }: MacroStripProps) {
  const subColorClasses = {
    default: "text-text-muted",
    warning: "text-warning",
    success: "text-success",
    accent: "text-accent-brand",
  };

  return (
    <div className="grid min-w-0 max-w-full grid-cols-2 rounded-xl border border-border-default bg-bg-1 md:grid-cols-3 lg:grid-cols-5">
      {items.map((item, index) => (
        <div
          key={item.label}
          className={cn(
            "min-w-0 p-3 md:p-3.5",
            index < items.length - 1 && "border-r border-border-default",
            // Handle mobile grid borders
            "max-md:border-b max-md:border-border-default",
            "max-md:last:border-b-0 max-md:[&:nth-last-child(2)]:border-b-0",
            // Hide right border on last item of each row on mobile
            "max-md:odd:border-r max-md:even:border-r-0"
          )}
        >
          <div className="text-[10.5px] uppercase tracking-wide text-text-muted">
            {item.label}
          </div>
          <div className="mt-0.5 font-mono text-[17px] font-semibold">
            {item.value}
          </div>
          <div
            className={cn(
              "mt-0.5 font-mono text-[11.5px]",
              subColorClasses[item.subColor || "default"]
            )}
          >
            {item.sub}
          </div>
        </div>
      ))}
    </div>
  );
}
