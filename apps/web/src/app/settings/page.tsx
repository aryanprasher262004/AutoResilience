import type { Metadata } from "next";

import { GuideControls } from "@/components/settings/guide-controls";
import { LocalEnvironment, StackCommands } from "@/components/settings/local-environment";
import { PreferencesForm } from "@/components/settings/preferences-form";
import { StackControls } from "@/components/settings/stack-controls";
import { ApiStatus } from "@/components/shell/api-status";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { DescriptionList } from "@/components/ui/description-list";
import { PageHeader } from "@/components/ui/page-header";
import { PlannedState } from "@/components/ui/states";
import { API_BASE_PATH } from "@/lib/api/client";
import { RUNTIME_MODE, RUNTIME_MODES, type RuntimeMode } from "@/lib/runtime";

export const metadata: Metadata = { title: "Settings" };

export default function SettingsPage() {
  // The rewrite target baked in at build time (next.config.ts), i.e. where requests really go.
  const upstream = process.env.AUTORESILIENCE_API_PROXY_TARGET ?? "unknown";
  return (
    <>
      <PageHeader title="Settings" description="Console preferences and how this console reaches the engine." />
      <div className="grid gap-4">
        <PreferencesForm />

        <Card>
          <CardHeader title="Getting-started guide" description="Stored in this browser." />
          <CardBody>
            <GuideControls />
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="API connection" description="Fixed when the console is built." />
          <CardBody>
            <DescriptionList
              items={[
                { label: "Browser endpoint", value: <code className="font-mono">{API_BASE_PATH}</code> },
                {
                  label: "Proxied to (AUTORESILIENCE_API_URL at build time)",
                  value: <code className="font-mono">{upstream}</code>,
                },
                { label: "Status (GET /ready)", value: <ApiStatus detailed /> },
              ]}
            />
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Runtime mode" description="Where the engine and this console run." />
          <ul className="divide-y divide-line">
            {(Object.keys(RUNTIME_MODES) as RuntimeMode[]).map((mode) => {
              const meta = RUNTIME_MODES[mode];
              return (
                <li key={mode} className="flex flex-wrap items-start justify-between gap-3 px-4 py-3">
                  <div className="min-w-0">
                    <p className="text-sm text-fg">
                      {meta.label}
                      {mode === RUNTIME_MODE ? <span className="ml-2 text-xs text-accent">this console</span> : null}
                    </p>
                    <p className="mt-0.5 text-xs text-muted">{meta.summary}</p>
                  </div>
                  <Badge tone={meta.status === "available" ? "success" : "warning"} dot>
                    {meta.status === "available" ? "Available" : "Planned"}
                  </Badge>
                </li>
              );
            })}
          </ul>
        </Card>

        <LocalEnvironment />

        <StackControls />

        <StackCommands />

        <PlannedState milestone="Not in the browser" title="What stays out of the console">
          <p>
            Installing, upgrading, restoring and uninstalling the stack, and granting the engine access to further
            clusters (<code className="font-mono">ar cluster import</code>), provision or delete resources and run only
            from a terminal. The engine&apos;s clusters are fixed when it starts (
            <code className="font-mono">KUBE_CONTEXT</code>, <code className="font-mono">DISCOVERY_CLUSTERS</code>).
          </p>
          <p>
            Safety policies, timeouts and limits are configured in the engine (code and environment variables) and
            are deliberately not editable from the browser.
          </p>
        </PlannedState>
      </div>
    </>
  );
}
