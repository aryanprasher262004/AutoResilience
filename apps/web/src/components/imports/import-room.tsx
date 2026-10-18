"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { type ReactNode, useId, useRef, useState } from "react";

import { applicationHref } from "@/components/applications/applications-view";
import { Badge } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/field";
import { PageHeader } from "@/components/ui/page-header";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { ApiError, api } from "@/lib/api/client";
import { queryKeys, useImport, useImportCapabilities } from "@/lib/api/queries";
import type { ImportRead, ImportWorkloadHealth } from "@/lib/api/types";
import { formatRelative } from "@/lib/format";
import { TOUR_TARGET } from "@/lib/help-content";
import { SOURCE_META, STATUS_META, isSettling } from "@/lib/imports";

import { FindingsView, PlanView, SpecView } from "./plan-view";

function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.unavailable ? error.message : `${error.status}: ${error.detail}`;
  return String(error);
}

const WORKLOAD_STATE: Record<string, { label: string; tone: "success" | "info" | "danger" | "warning" | "neutral" }> = {
  READY: { label: "Ready", tone: "success" },
  PROGRESSING: { label: "Starting", tone: "info" },
  IMAGE_PULL_FAILED: { label: "Image pull failed", tone: "danger" },
  CRASH_LOOP: { label: "Crash loop", tone: "danger" },
  CONFIG_ERROR: { label: "Cannot start", tone: "danger" },
  MISSING: { label: "Missing", tone: "warning" },
};

function useImportAction(imp: ImportRead) {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run(action: () => Promise<ImportRead | undefined>, after?: () => void) {
    setBusy(true);
    setError(null);
    try {
      const result = await action();
      if (result) queryClient.setQueryData(queryKeys.importItem(imp.id), result);
      void queryClient.invalidateQueries({ queryKey: queryKeys.imports, exact: true });
      void queryClient.invalidateQueries({ queryKey: queryKeys.applications });
      after?.();
      return true;
    } catch (e) {
      setError(errorText(e));
      return false;
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, run, clear: () => setError(null) };
}

function ConfirmDialog({
  trigger,
  title,
  children,
  confirmLabel,
  tone,
  onConfirm,
  busy,
  error,
  canConfirm = true,
}: {
  /** The button that opens the dialog. */
  trigger: { label: string; variant: "primary" | "danger"; disabled?: boolean; title?: string };
  title: string;
  children: ReactNode;
  confirmLabel: string;
  tone: "primary" | "danger";
  onConfirm: (close: () => void) => void;
  busy: boolean;
  error: string | null;
  canConfirm?: boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const close = () => dialog.current?.close();
  return (
    <>
      <Button
        variant={trigger.variant}
        onClick={() => dialog.current?.showModal()}
        disabled={trigger.disabled}
        title={trigger.title}
      >
        {trigger.label}
      </Button>
      <dialog
        ref={dialog}
        aria-labelledby={titleId}
        className="m-auto w-full max-w-lg rounded-lg border border-line-strong bg-surface p-0 text-fg backdrop:bg-black/60"
      >
        <div className="grid gap-4 p-5">
          <h2 id={titleId} className="text-base font-semibold">
            {title}
          </h2>
          <div className="grid gap-2 text-xs leading-relaxed text-muted">{children}</div>
          {error ? (
            <Callout tone="danger" title="Not done" role="alert">
              <span className="font-mono break-words">{error}</span>
            </Callout>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={close} disabled={busy}>
              Cancel
            </Button>
            <Button variant={tone} onClick={() => onConfirm(close)} disabled={busy || !canConfirm}>
              {busy ? "Working…" : confirmLabel}
            </Button>
          </div>
        </div>
      </dialog>
    </>
  );
}

function DeployControl({ imp, available, reason }: { imp: ImportRead; available: boolean; reason: string | null }) {
  const action = useImportAction(imp);
  const retry = imp.status === "FAILED";
  return (
    <ConfirmDialog
      trigger={{
        label: retry ? "Retry deployment" : "Deploy",
        variant: "primary",
        disabled: !available,
        title: available ? undefined : (reason ?? undefined),
      }}
      title={`${retry ? "Retry deploying" : "Deploy"} “${imp.name}” to ${imp.plan.namespace}?`}
      confirmLabel={retry ? "Retry deployment" : "Deploy this plan"}
      tone="primary"
      busy={action.busy}
      error={action.error}
      onConfirm={(close) => void action.run(() => api.deployImport(imp.id, imp.plan.digest), close)}
    >
      <p>This approves exactly the reviewed plan (digest <code className="font-mono">{imp.plan.digest.slice(0, 12)}</code>). It will:</p>
      <ul className="list-disc pl-4">
        {imp.plan.actions.map((a) => (
          <li key={a}>{a}</li>
        ))}
      </ul>
      <p>
        Images are pulled by the cluster node. No experiment starts: chaos still needs a reviewed, validated experiment. You can
        remove everything afterwards.
      </p>
    </ConfirmDialog>
  );
}

function RemoveControl({ imp, available }: { imp: ImportRead; available: boolean }) {
  const action = useImportAction(imp);
  const [typed, setTyped] = useState("");
  const inputId = useId();
  const deployed = !(imp.status === "PLANNED" && imp.deployment.attempts === 0);
  return (
    <ConfirmDialog
      trigger={{ label: deployed ? "Remove deployment" : "Discard", variant: "danger", disabled: deployed && !available }}
      title={deployed ? `Remove “${imp.name}” from the cluster?` : `Discard “${imp.name}”?`}
      confirmLabel={deployed ? "Remove" : "Discard"}
      tone="danger"
      busy={action.busy}
      error={action.error}
      canConfirm={typed === imp.name}
      onConfirm={(close) => void action.run(() => api.removeImport(imp.id, typed), close)}
    >
      {deployed ? (
        <p>
          Deletes namespace <code className="font-mono text-fg">{imp.namespace}</code> and everything in it, but only after the
          engine verifies that the namespace and every object it manages there carry this import&apos;s ownership labels. If
          anything else is found, nothing is deleted. The topology view is removed; experiment history is kept.
        </p>
      ) : (
        <p>It was never deployed, so nothing in the cluster changes; only the saved plan is discarded.</p>
      )}
      <Field id={inputId} label={`Type ${imp.name} to confirm`}>
        <Input id={inputId} value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
      </Field>
    </ConfirmDialog>
  );
}

function ForgetControl({ imp }: { imp: ImportRead }) {
  const router = useRouter();
  const action = useImportAction(imp);
  return (
    <Button
      variant="ghost"
      disabled={action.busy}
      onClick={() => void action.run(() => api.forgetImport(imp.id), () => router.push("/applications"))}
    >
      Forget record
    </Button>
  );
}

function WorkloadList({ workloads }: { workloads: ImportWorkloadHealth[] }) {
  if (!workloads.length) return <p className="text-xs text-muted">Waiting for the first health check…</p>;
  return (
    <ul className="grid gap-1.5">
      {workloads.map((w) => {
        const meta = WORKLOAD_STATE[w.state] ?? { label: w.state, tone: "neutral" as const };
        return (
          <li key={w.name} className="grid grid-cols-[minmax(0,1fr)] gap-1 text-xs sm:grid-cols-[12rem_8rem_minmax(0,1fr)] sm:items-baseline sm:gap-3">
            <span className="font-mono text-fg">
              {w.name} <span className="text-faint">{w.kind}</span>
            </span>
            <span>
              <Badge tone={meta.tone} dot>
                {meta.label} {w.ready}/{w.desired}
              </Badge>
            </span>
            <span className="break-words text-muted">{w.detail}</span>
          </li>
        );
      })}
    </ul>
  );
}

function StatusCard({ imp }: { imp: ImportRead }) {
  const d = imp.deployment;
  return (
    <Card>
      <CardHeader
        title="Deployment"
        description={STATUS_META[imp.status].description}
        actions={d.checked_at ? <span className="text-2xs text-faint">checked {formatRelative(d.checked_at)}</span> : null}
      />
      <CardBody className="grid gap-3" aria-live="polite">
        {imp.status === "FAILED" && d.error ? (
          <Callout tone="danger" title="The deployment did not become healthy" role="alert">
            <p className="font-mono break-words text-fg">{d.error}</p>
            {d.recovery ? <p className="mt-1">{d.recovery}</p> : null}
          </Callout>
        ) : null}
        {imp.status === "READY" ? (
          <Callout tone="success" title="Deployed and healthy" role="status">
            Its topology is onboarded as an application. Workloads marked <em>target</em> there can be used in experiments;
            safety validation still decides each run (for example, a single-replica workload is refused).
          </Callout>
        ) : null}
        {imp.status === "REMOVING" ? (
          <Callout tone="warning" title="Removing" role="status">
            Namespace <code className="font-mono">{imp.namespace}</code> is being deleted. This page updates when it is gone.
          </Callout>
        ) : null}
        {imp.status === "REMOVED" ? (
          <Callout tone="neutral" title="Removed" role="status">
            Nothing of this import is left in the cluster. Forget the record, or import the file again to redeploy it.
          </Callout>
        ) : null}
        {imp.deployment.removal && "refused" in imp.deployment.removal ? (
          <Callout tone="warning" title="Removal was refused" role="status">
            <span className="font-mono break-words">{String(imp.deployment.removal.refused)}</span>
          </Callout>
        ) : null}
        {imp.status === "DEPLOYING" || imp.status === "READY" || (imp.status === "FAILED" && d.workloads?.length) ? (
          <WorkloadList workloads={d.workloads ?? []} />
        ) : null}
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
          <div>
            <dt className="text-faint">Attempts</dt>
            <dd className="font-mono">{d.attempts}</dd>
          </div>
          <div>
            <dt className="text-faint">Started</dt>
            <dd>{d.started_at ? formatRelative(d.started_at) : "—"}</dd>
          </div>
          <div>
            <dt className="text-faint">Finished</dt>
            <dd>{d.finished_at ? formatRelative(d.finished_at) : "—"}</dd>
          </div>
          <div>
            <dt className="text-faint">Objects applied</dt>
            <dd className="font-mono">{d.applied?.length ?? 0}</dd>
          </div>
        </dl>
      </CardBody>
    </Card>
  );
}

export function ImportRoom({ id }: { id: string }) {
  const query = useImport(id);
  const caps = useImportCapabilities();

  if (query.isPending) return <Card><LoadingState rows={4} label="Loading import" /></Card>;
  if (query.isError) {
    const missing = query.error instanceof ApiError && query.error.status === 404;
    return (
      <Card>
        <ErrorState
          title={missing ? "Import not found" : "Could not load the import"}
          message={missing ? "It may have been forgotten in another tab." : query.error.message}
          onRetry={missing ? undefined : () => query.refetch()}
        />
      </Card>
    );
  }
  const imp = query.data;
  const available = !!caps.data?.provisioner.configured;
  const reason = caps.data && !available ? caps.data.provisioner.detail : null;
  const canDeploy = imp.status === "PLANNED" || imp.status === "FAILED";
  const canRemove = imp.status !== "REMOVED" && imp.status !== "REMOVING";

  return (
    <>
      <PageHeader
        title={imp.name}
        description={`Imported from ${SOURCE_META[imp.source].label.toLowerCase()}${imp.filename ? ` ${imp.filename}` : ""} · namespace ${imp.namespace}`}
        meta={
          <span data-tour={TOUR_TARGET.importStatus} className="inline-flex items-center gap-2">
            <Badge tone={STATUS_META[imp.status].tone} dot>
              {STATUS_META[imp.status].label}
            </Badge>
            {isSettling(imp.status) ? <span className="text-2xs text-faint">checking every few seconds</span> : null}
          </span>
        }
        actions={
          <span data-tour={TOUR_TARGET.importActions} className="flex flex-wrap items-center gap-2">
            {imp.status === "READY" && imp.application_id ? (
              <ButtonLink href={applicationHref(imp.application_id)} variant="primary">
                Open topology
              </ButtonLink>
            ) : null}
            {canDeploy ? <DeployControl imp={imp} available={available} reason={reason} /> : null}
            {canRemove ? <RemoveControl imp={imp} available={available} /> : null}
            {imp.status === "REMOVED" ? <ForgetControl imp={imp} /> : null}
          </span>
        }
      />
      <div className="grid gap-4">
        {canDeploy && caps.data && !available ? (
          <Callout tone="warning" title="Deployment is not available on this engine" role="status">
            {caps.data.provisioner.detail}
          </Callout>
        ) : null}
        <StatusCard imp={imp} />
        <PlanView plan={imp.plan} title={imp.status === "PLANNED" ? "Plan to approve" : "Reviewed plan"} />
        <SpecView spec={imp.spec} />
        <details className="rounded-lg border border-line bg-surface">
          <summary className="cursor-pointer px-4 py-2.5 text-sm font-medium">Security review ({imp.findings.length})</summary>
          <div className="border-t border-line p-3">
            <FindingsView findings={imp.findings} level={3} />
          </div>
        </details>
      </div>
    </>
  );
}
