"use client";

import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { DescriptionList } from "@/components/ui/description-list";
import type { Experiment } from "@/lib/api/types";
import { MODE_HELP } from "@/lib/experiment-options";

export function ReviewStep({
  experiment,
  runError,
  busy,
  onBack,
  onRun,
}: {
  experiment: Experiment;
  runError: string | null;
  busy: boolean;
  onBack: () => void;
  onRun: () => void;
}) {
  const [confirmed, setConfirmed] = useState(false);
  const checkboxId = useId();
  const force = experiment.pod_delete_mode === "FORCE";
  const target = `${experiment.target.kind} ${experiment.target.namespace}/${experiment.target.name}`;
  const pods = `${experiment.affected_replicas} pod${experiment.affected_replicas === 1 ? "" : "s"}`;

  return (
    <div className="grid gap-4">
      <Card>
        <CardHeader
          title="Configuration"
          description="Exactly what the server stored and will run (from the created experiment)"
        />
        <CardBody>
          <DescriptionList
            items={[
              { label: "Name", value: experiment.name },
              { label: "Target", value: <span className="font-mono text-xs">{target}</span> },
              { label: "Fault", value: experiment.fault_type },
              { label: "Deletion mode", value: experiment.pod_delete_mode },
              { label: "Affected replicas", value: experiment.affected_replicas },
              { label: "Duration", value: `${experiment.duration_seconds}s` },
              {
                label: "Safety policy",
                value: (experiment.validation_result?.policy as { name?: string } | undefined)?.name ?? "—",
              },
              { label: "Description", value: experiment.description || "—" },
              { label: "Experiment id", value: <span className="font-mono text-xs">{experiment.id}</span> },
            ]}
          />
        </CardBody>
      </Card>

      <Callout tone={force ? "danger" : "warning"} title={force ? "FORCE mode: immediate pod kill" : "This injects a real fault"}>
        <p>
          Starting will capture a baseline and then delete {pods} of{" "}
          <span className="font-mono">{target}</span> through LitmusChaos.{" "}
          {force ? MODE_HELP.FORCE : MODE_HELP.GRACEFUL} Clients of this workload may see errors
          until a replacement is ready.
        </p>
        <p className="mt-1">
          The cluster is re-checked right before injection, and the run can be aborted from the
          experiment page.
        </p>
      </Callout>

      <label
        htmlFor={checkboxId}
        className="flex cursor-pointer items-start gap-2 text-sm text-fg"
      >
        <input
          id={checkboxId}
          type="checkbox"
          className="mt-0.5 size-4 accent-[var(--color-accent)]"
          checked={confirmed}
          disabled={busy}
          onChange={(e) => setConfirmed(e.target.checked)}
        />
        <span>
          I understand this will delete {pods} of <span className="font-mono">{experiment.target.namespace}/{experiment.target.name}</span>
          {force ? " without graceful shutdown" : ""}.
        </span>
      </label>

      {runError ? (
        <Callout tone="danger" title="The experiment was not started" role="alert">
          <span className="font-mono">{runError}</span>
        </Callout>
      ) : null}

      <div className="flex items-center justify-between gap-3">
        <Button variant="ghost" onClick={onBack} disabled={busy}>
          Back to safety check
        </Button>
        <Button variant={force ? "danger" : "primary"} onClick={onRun} disabled={!confirmed || busy}>
          {busy ? "Starting…" : "Start experiment"}
        </Button>
      </div>
    </div>
  );
}
