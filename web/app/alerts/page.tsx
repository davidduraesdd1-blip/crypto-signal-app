"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { SegmentedControl } from "@/components/segmented-control";
import { AlertTypeCard } from "@/components/alert-type-card";
import { ChannelRow } from "@/components/channel-row";
import { ToggleSwitch } from "@/components/toggle-switch";
import { BeginnerHint } from "@/components/beginner-hint";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAlertConfig, useUpdateAlertConfig } from "@/hooks/use-alerts-config";

// AUDIT-2026-05-06 (Everything-Live, item 6): hardcoded alertTypes +
// channels arrays removed — pulled live from /alerts/config and
// persisted via PUT /alerts/config.

export default function AlertsPage() {
  const router = useRouter();
  const configQuery = useAlertConfig();
  const updateConfig = useUpdateAlertConfig();

  const [emailEnabled, setEmailEnabled] = useState(false);
  const [emailAddress, setEmailAddress] = useState("");
  const [threshold, setThreshold] = useState(75);
  const [typesState, setTypesState] = useState<Record<string, boolean>>({});

  // Sync local state with persisted config when it loads
  useEffect(() => {
    const data = configQuery.data;
    if (!data) return;
    setEmailEnabled(Boolean(data.email_enabled));
    setEmailAddress(data.email_address ?? "");
    setThreshold(typeof data.confidence_threshold === "number" ? data.confidence_threshold : 75);
    setTypesState(Object.fromEntries((data.alert_types ?? []).map((t) => [t.id, t.enabled])));
  }, [configQuery.data]);

  const types = (configQuery.data?.alert_types ?? []).map((t) => ({
    ...t,
    enabled: typesState[t.id] ?? t.enabled,
  }));
  const channels = configQuery.data?.channels ?? [];

  const toggleType = (id: string) => {
    const next = !(typesState[id] ?? types.find((t) => t.id === id)?.enabled ?? false);
    setTypesState((prev) => ({ ...prev, [id]: next }));
    updateConfig.mutate({ alert_types: { [id]: next } });
  };

  const toggleEmail = () => {
    const next = !emailEnabled;
    setEmailEnabled(next);
    updateConfig.mutate({ email_enabled: next });
  };

  const handleEmailBlur = (value: string) => {
    if (value !== emailAddress) {
      setEmailAddress(value);
      updateConfig.mutate({ email_address: value });
    }
  };

  const handleThresholdChange = (next: number) => {
    setThreshold(next);
    updateConfig.mutate({ confidence_threshold: next });
  };

  return (
    <AppShell crumbs="Account" currentPage="Alerts">
      <PageHeader
        title="Alerts"
        subtitle="Get notified when signals change, regimes shift, on-chain divergences fire, or funding spikes break threshold. Sent via the channels you've connected."
      />

      {/* AUDIT-2026-05-06 (W2 Tier 6 F-LEVEL-1): Beginner gloss */}
      <BeginnerHint title="When should you set up alerts?">
        Alerts are how the model gets your attention without you
        having to keep checking. Most people start with two:
        <strong className="text-text-primary"> high-confidence
        signal changes </strong>
        (so you know when the model rotates from Hold to Buy or
        Sell) and
        <strong className="text-text-primary"> regime shifts </strong>
        (so you know when conditions change for the whole market).
        Add more once you&rsquo;ve seen what feels useful and what
        feels noisy.
      </BeginnerHint>

      {/* Tab navigation */}
      <div className="mb-5">
        <SegmentedControl
          options={[
            { label: "Configure", value: "configure" },
            { label: "History", value: "history" },
          ]}
          value="configure"
          onChange={(v) => {
            // AUDIT-2026-05-03 (D4 audit, MEDIUM): router.push instead
            // of full page reload — preserves TanStack Query cache.
            if (v === "history") router.push("/alerts/history");
          }}
        />
      </div>

      {/* 2-column layout */}
      <div className="mb-5 grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Email notifications card */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-[13px] font-semibold">
              Email notifications
            </CardTitle>
            <p className="text-[12px] text-text-muted">
              SMTP-based, sent immediately when an event fires
            </p>
          </CardHeader>
          <CardContent className="space-y-4">
            <ToggleSwitch
              label="Enable email alerts"
              sublabel="master switch · turn off without losing config"
              enabled={emailEnabled}
              onToggle={toggleEmail}
            />

            <div className="space-y-1.5">
              <label className="text-[11.5px] font-medium uppercase tracking-[0.05em] text-text-muted">
                Recipient
              </label>
              <Input
                type="email"
                value={emailAddress}
                onChange={(e) => setEmailAddress(e.target.value)}
                onBlur={(e) => handleEmailBlur(e.target.value)}
                placeholder="alerts@your-domain.com"
                className="h-9 text-[13px]"
              />
              <p className="text-[11.5px] text-text-muted">
                Comma-separated for multiple recipients · saves on blur
              </p>
            </div>

            <div className="space-y-1.5">
              <label className="text-[11.5px] font-medium uppercase tracking-[0.05em] text-text-muted">
                Sender (SMTP)
              </label>
              <Input
                type="email"
                defaultValue="alerts@cryptosignal.app"
                className="h-9 text-[13px]"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-[11.5px] font-medium uppercase tracking-[0.05em] text-text-muted">
                SMTP Password
              </label>
              <Input
                type="password"
                placeholder="never pre-filled · leave blank to keep stored value"
                className="h-9 text-[13px]"
              />
              <p className="text-[11.5px] text-text-muted">
                Stored encrypted via Render env vars (production) or
                <code className="mx-1 rounded bg-bg-2 px-1 font-mono">.env.local</code>
                (local dev). Never written to git.
              </p>
            </div>

            <div className="space-y-2">
              <div className="flex items-baseline justify-between">
                <label className="text-[11.5px] font-medium uppercase tracking-[0.05em] text-text-muted">
                  High-confidence threshold
                </label>
                <span className="font-mono text-[14px] font-semibold text-accent-brand">
                  {threshold}%
                </span>
              </div>
              <input
                type="range"
                min={50}
                max={95}
                step={1}
                value={threshold}
                onChange={(e) => setThreshold(Number(e.target.value))}
                onMouseUp={() => handleThresholdChange(threshold)}
                onTouchEnd={() => handleThresholdChange(threshold)}
                className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-bg-3 accent-accent-brand"
              />
              <p className="text-[11.5px] text-text-muted">
                Alerts fire when composite signal confidence ≥ this threshold
              </p>
            </div>

            <div className="flex flex-wrap gap-2.5 pt-2">
              <Button className="h-9 px-4 text-[13px]">Save Config</Button>
              <Button variant="outline" className="h-9 px-4 text-[13px]">
                Send Test Email
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Alert types card */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-[13px] font-semibold">
              Alert types
            </CardTitle>
            <p className="text-[12px] text-text-muted">
              choose which events trigger an alert
            </p>
          </CardHeader>
          <CardContent>
            <div className="space-y-2.5">
              {types.map((t) => (
                <AlertTypeCard
                  key={t.id}
                  name={t.name}
                  description={t.description}
                  enabled={t.enabled}
                  onToggle={() => toggleType(t.id)}
                />
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Delivery channels card */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-[13px] font-semibold">
            Delivery channels
          </CardTitle>
          <p className="text-[12px] text-text-muted">
            where alerts get sent · email is required, others optional
          </p>
        </CardHeader>
        <CardContent>
          <div className="space-y-2.5">
            {channels.length === 0 && configQuery.isLoading ? (
              <div className="text-center text-xs text-text-muted">Loading channels…</div>
            ) : channels.length === 0 ? (
              <div className="text-center text-xs text-text-muted">
                No channels configured — set email above or paste a Slack/Telegram webhook to enable.
              </div>
            ) : (
              channels.map((ch) => (
                <ChannelRow
                  key={ch.id ?? ch.name}
                  icon={ch.icon}
                  name={ch.name}
                  status={ch.status}
                  connected={ch.connected}
                />
              ))
            )}
          </div>
        </CardContent>
      </Card>
    </AppShell>
  );
}
