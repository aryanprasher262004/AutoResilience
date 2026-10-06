"use client";

import { Badge, type Tone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { DescriptionList } from "@/components/ui/description-list";
import { ErrorState } from "@/components/ui/states";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import type { Experiment, ValidationResult } from "@/lib/api/types";

const CHECK_TONE: Record<string, Tone> = {
  PASSED: "success",
  FAILED: "danger",
  ERROR: "warning",
  SKIPPED: "neutral",
};

type Check = ValidationResult["static_checks"][number];

function ChecksTable({ title, description, checks }: { title: string; description: string; checks: Check[] }) {
  return (
    <Card>
      <CardHeader title={title} description={description} />
      <Table>
        <THead>
          <tr>
            <TH className="w-28">Result</TH>
            <TH className="w-64">Check</TH>
            <TH>Server message</TH>
          </tr>
        </THead>
        <TBody>
          {checks.map((check) => (
            <TR key={check.name}>
              <TD>
                <Badge tone={CHECK_TONE[check.status] ?? "neutral"} dot>
                  {check.status}
                </Badge>
              </TD>
              <TD className="font-mono text-xs">{check.name}</TD>
              <TD className="text-xs text-muted">{check.message}</TD>
            </TR>
          ))}
        </TBody>
      </Table>
    </Card>
  );
}

export function SafetyStep({
  experiment,
  validationError,
  busy,
  onRetryValidation,
  onEdit,
  onContinue,
}: {
  experiment: Experiment;
  validationError: string | null;
  busy: boolean;
  onRetryValidation: () => void;
  onEdit: () => void;
  onContinue: () => void;
}) {
  const result = experiment.validation_result;
  if (!result) {
    return (
      <Card>
        {validationError ? (
          <ErrorState
            title="Safety validation did not complete"
            message={validationError}
            onRetry={busy ? undefined : onRetryValidation}
          />
        ) : (
          <CardBody>
            <p className="text-sm text-muted">Waiting for the server&apos;s validation result…</p>
          </CardBody>
        )}
        <div className="flex justify-start border-t border-line px-4 py-3">
          <Button variant="ghost" onClick={onEdit} disabled={busy}>
            Back to configuration
          </Button>
        </div>
      </Card>
    );
  }

  const policy = result.policy as { name?: string; description?: string; min_healthy_replicas?: number };
  const selection = result.policy_selection;
  return (
    <div className="grid gap-4">
      {result.passed ? (
        <Callout tone="success" title="All safety checks passed" role="status">
          The server validated this target under the “{policy.name}” policy. Review the
          configuration before starting.
        </Callout>
      ) : (
        <Callout tone="danger" title="Blocked by safety validation" role="alert">
          The server refused this experiment; it was recorded as Validation failed and nothing
          was injected. Adjust the configuration and check again.
        </Callout>
      )}

      <Card>
        <CardHeader title="Target and policy" description="As evaluated by the server" />
        <CardBody>
          <DescriptionList
            items={[
              {
                label: "Target",
                value: (
                  <span className="font-mono text-xs">
                    {experiment.target.kind} {experiment.target.namespace}/{experiment.target.name}
                  </span>
                ),
              },
              { label: "Safety policy", value: policy.name ?? "—" },
              { label: "Why this policy", value: selection?.rule ?? "—" },
              {
                label: "Min healthy replicas",
                value: policy.min_healthy_replicas ?? "—",
              },
              {
                label: "Experiment id",
                value: <span className="font-mono text-xs">{experiment.id}</span>,
              },
            ]}
          />
        </CardBody>
      </Card>

      <ChecksTable
        title="Static checks"
        description="Configuration against the safety policy"
        checks={result.static_checks}
      />
      <ChecksTable
        title="Cluster checks"
        description="Live Kubernetes state of the target"
        checks={result.cluster_checks}
      />

      <div className="flex items-center justify-between gap-3">
        <Button variant="ghost" onClick={onEdit} disabled={busy}>
          Back to configuration
        </Button>
        {result.passed ? (
          <Button variant="primary" onClick={onContinue} disabled={busy}>
            Continue to review
          </Button>
        ) : null}
      </div>
    </div>
  );
}
