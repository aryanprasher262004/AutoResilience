"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { useImportCapabilities } from "@/lib/api/queries";
import { TOUR_TARGET } from "@/lib/help-content";

/** Whether this engine can deploy imported applications, and with which identity. Read-only. */
export function ImportSettings() {
  const { data, isPending, isError, error, refetch } = useImportCapabilities();
  return (
    <Card data-tour={TOUR_TARGET.settingsImports}>
      <CardHeader
        level={3}
        title="Application imports"
        description="Deploying imported applications uses a separate provisioner identity, never the engine's experiment identity."
        actions={
          data ? (
            <Badge tone={data.provisioner.configured ? "success" : "warning"} dot>
              {data.provisioner.configured ? "Deployment available" : "Review only"}
            </Badge>
          ) : null
        }
      />
      {isPending ? (
        <LoadingState rows={2} label="Checking the provisioner" />
      ) : isError ? (
        <ErrorState title="Could not check imports" message={error.message} onRetry={() => refetch()} />
      ) : (
        <CardBody className="grid gap-2 text-xs leading-relaxed text-muted [&_code]:font-mono [&_code]:text-fg">
          <p className="text-fg">{data.provisioner.detail}</p>
          <ul className="grid list-disc gap-1 pl-4">
            <li>
              Imports go to the execution cluster (<code>{data.execution_context ?? "current context"}</code>), each in its own{" "}
              <code>{data.namespace_prefix}&lt;name&gt;</code> namespace; an admission policy rejects any write by the provisioner
              elsewhere.
            </li>
            <li>
              Limits: files up to {data.max_bytes / 1024} KiB and {data.max_documents} documents, {data.max_workloads} workloads,{" "}
              {data.max_replicas} replicas each, CPU and memory capped per container and per namespace.
            </li>
            <li>Removing an import deletes only its namespace, after the engine verifies it owns everything managed there.</li>
          </ul>
          <p>
            Enabling it is terminal-only: in the local stack <code>python3 tools/ar/ar.py install</code> creates the identity; in
            development run <code>./scripts/dev-provisioner.sh</code> and start the API with the <code>PROVISIONER_KUBECONFIG</code>{" "}
            it prints.
          </p>
        </CardBody>
      )}
    </Card>
  );
}
