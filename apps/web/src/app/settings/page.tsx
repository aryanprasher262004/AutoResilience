import type { Metadata } from "next";

import { ApiStatus } from "@/components/shell/api-status";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { DescriptionList } from "@/components/ui/description-list";
import { PageHeader } from "@/components/ui/page-header";
import { PlannedState } from "@/components/ui/states";
import { API_BASE_PATH } from "@/lib/api/client";

export const metadata: Metadata = { title: "Settings" };

// Read per request so the page reports the server's actual configuration.
export const dynamic = "force-dynamic";

export default function SettingsPage() {
  const upstream = process.env.AUTORESILIENCE_API_URL ?? "http://localhost:8000 (default)";
  return (
    <>
      <PageHeader title="Settings" description="How this console reaches the AutoResilience API." />
      <div className="grid gap-4">
        <Card>
          <CardHeader title="API connection" />
          <CardBody>
            <DescriptionList
              items={[
                { label: "Browser endpoint", value: <code className="font-mono">{API_BASE_PATH}</code> },
                {
                  label: "Proxied to (AUTORESILIENCE_API_URL)",
                  value: <code className="font-mono">{upstream}</code>,
                },
                { label: "Status", value: <ApiStatus /> },
              ]}
            />
          </CardBody>
        </Card>
        <PlannedState milestone="Not configurable here" title="Platform settings">
          <p>
            Safety policies, timeouts and the target cluster are configured on the backend (code
            and environment variables) and are deliberately not editable from the browser.
          </p>
        </PlannedState>
      </div>
    </>
  );
}
