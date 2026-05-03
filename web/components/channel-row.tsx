"use client";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

interface ChannelRowProps {
  icon: string;
  name: string;
  status: string;
  connected: boolean;
  onAction?: () => void;
}

export function ChannelRow({
  icon,
  name,
  status,
  connected,
  onAction,
}: ChannelRowProps) {
  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-lg border bg-bg-2 px-3.5 py-3",
        connected ? "border-accent-brand" : "border-border"
      )}
    >
      <div className="grid h-8 w-8 flex-shrink-0 place-items-center rounded-lg bg-bg-1 text-[16px]">
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-[13px] font-medium">{name}</div>
        <div
          className={cn(
            "mt-0.5 text-[11.5px]",
            connected ? "text-success" : "text-text-muted"
          )}
        >
          {connected && <span className="mr-1">●</span>}
          {status}
        </div>
      </div>
      <Button
        variant="outline"
        size="sm"
        onClick={onAction}
        className="h-8 px-2.5 text-[12px]"
      >
        {connected ? "Edit" : "Connect"}
      </Button>
    </div>
  );
}
