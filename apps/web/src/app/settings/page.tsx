import type { Metadata } from "next";

import { GuideControls } from "@/components/settings/guide-controls";
import { LocalEnvironment, StackCommands } from "@/components/settings/local-environment";
import { PreferencesForm } from "@/components/settings/preferences-form";
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

        <StackCommands />

        <PlannedState milestone="Planned" title="Managing the stack from the console">
          <p>
            Starting and stopping the stack, reviewing the engine&apos;s granted permissions, backups and a cleanup
            preview need a local service-manager endpoint, which does not exist yet; use the commands above. The
            cluster context is fixed when the engine starts (<code className="font-mono">KUBE_CONTEXT</code>).
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
