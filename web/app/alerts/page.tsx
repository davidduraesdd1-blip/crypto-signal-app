"use client";

import { useState } from "react";
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

// Mock data
const alertTypes = [
  {
    id: "buy-sell",
    name: "▲ Buy / ▼ Sell crossings",
    description:
      "Composite signal crosses BUY (≥ 70) or SELL (≤ 30) threshold for any tracked pair on the configured timeframes.",
    enabled: true,
  },
  {
    id: "regime",
    name: "◈ Regime transitions",
    description:
      "HMM regime state changes (Bull → Transition → Accumulation → Distribution → Bear). Per-pair, with confidence threshold.",
    enabled: true,
  },
  {
    id: "onchain",
    name: "⬡ On-chain divergences",
    description:
      "MVRV-Z, SOPR, or exchange reserve flow flips direction relative to spot price for ≥ 2 consecutive days.",
    enabled: true,
  },
  {
    id: "funding",
    name: "⚡ Funding rate spikes",
    description:
      "Perpetual funding ≥ +0.05% or ≤ −0.05% for 8h. Often signals over-leveraged positioning before a flush.",
    enabled: false,
  },
  {
    id: "unlock",
    name: "🔓 Token unlock proximity",
    description:
      "CryptoRank-tracked unlocks within 7 days for any pair in the watchlist. Flags forward sell-pressure events.",
    enabled: false,
  },
];

const channels = [
  {
    icon: "📧",
    name: "Email",
    status: "Connected · david.duraes.dd1@gmail.com",
    connected: true,
  },
  {
    icon: "💬",
    name: "Slack webhook",
    status: "Not connected · paste a webhook URL to enable",
    connected: false,
  },
  {
    icon: "📨",
    name: "Telegram bot",
    status: "Not connected · @YourBotName + chat ID",
    connected: false,
  },
  {
    icon: "🔔",
    name: "Browser push",
    status: "Not connected · works only when app tab is open",
    connected: false,
  },
];

export default function AlertsPage() {
  const router = useRouter();
  const [emailEnabled, setEmailEnabled] = useState(true);
  const [threshold, setThreshold] = useState(75);
  const [types, setTypes] = useState(alertTypes);

  const toggleType = (id: string) => {
    setTypes((prev) =>
      prev.map((t) => (t.id === id ? { ...t, enabled: !t.enabled } : t))
    );
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
              onToggle={() => setEmailEnabled(!emailEnabled)}
            />

            <div className="space-y-1.5">
              <label className="text-[11.5px] font-medium uppercase tracking-[0.05em] text-text-muted">
                Recipient
              </label>
              <Input
                type="email"
                defaultValue="david.duraes.dd1@gmail.com"
                className="h-9 text-[13px]"
              />
              <p className="text-[11.5px] text-text-muted">
                Comma-separated for multiple recipients
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
              <div className="relative h-1.5 rounded-full bg-bg-3">
                <div
                  className="absolute left-0 top-0 h-full rounded-full bg-accent-brand"
                  style={{ width: `${threshold}%` }}
                />
                <div
                  className="absolute top-1/2 h-3.5 w-3.5 -translate-y-1/2 rounded-full bg-accent-brand shadow-[0_0_0_3px_rgba(34,211,111,0.2)]"
                  style={{ left: `${threshold}%`, transform: "translate(-50%, -50%)" }}
                />
              </div>
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
            {channels.map((ch) => (
              <ChannelRow
                key={ch.name}
                icon={ch.icon}
                name={ch.name}
                status={ch.status}
                connected={ch.connected}
              />
            ))}
          </div>
        </CardContent>
      </Card>
    </AppShell>
  );
}
