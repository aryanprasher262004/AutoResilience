"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { type ReactNode, useId, useRef, useState } from "react";

import { newExperimentHref } from "@/components/services/health-badge";
import { Badge } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/field";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { Stepper } from "@/components/ui/stepper";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { ApiError, api } from "@/lib/api/client";
import { queryKeys, useClusters, useNamespaces, useTopologyPreview } from "@/lib/api/queries";
import type { ClusterRef, Topology } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { NODE_HEALTH_META, workloadRows } from "@/lib/topology";

import { applicationHref } from "./applications-view";
import { ClusterRoleBadge, contextLabel } from "./cluster-badge";

const STEPS = [
  { id: "cluster", label: "Cluster" },
  { id: "namespaces", label: "Namespaces" },
  { id: "review", label: "Workloads & save" },
];
type StepId = "cluster" | "namespaces" | "review";

const AR = "python3 tools/ar/ar.py";

function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.unavailable ? error.message : `${error.status}: ${error.detail}`;
  return String(error);
}

/**
 * Onboarding: choose an authorized cluster, the namespaces the application runs in,
 * inspect what is there, save. Read-only on the cluster; the server checks every choice.
 */
export function Onboarding() {
  const [step, setStep] = useState<StepId>("cluster");
  const [cluster, setCluster] = useState<ClusterRef | null>(null);
  const [namespaces, setNamespaces] = useState<string[]>([]);

  return (
    <div className="grid gap-4">
      <Stepper steps={STEPS} current={step} />
      {step === "cluster" ? (
        <ClusterStep
          selected={cluster}
          onNext={(c) => {
            if (c.context !== cluster?.context) setNamespaces([]);
            setCluster(c);
            setStep("namespaces");
          }}
        />
      ) : step === "namespaces" && cluster ? (
        <NamespaceStep
          cluster={cluster}
          selected={namespaces}
          onChange={setNamespaces}
          onBack={() => setStep("cluster")}
          onNext={() => setStep("review")}
        />
      ) : cluster ? (
        <ReviewStep cluster={cluster} namespaces={namespaces} onBack={() => setStep("namespaces")} />
      ) : null}
    </div>
  );
}

function Choice({
  checked,
  disabled,
  onChange,
  type,
  name,
  children,
}: {
  checked: boolean;
  disabled?: boolean;
  onChange: () => void;
  type: "radio" | "checkbox";
  name: string;
  children: ReactNode;
}) {
  return (
    <label
      className={cn(
        "flex cursor-pointer items-start gap-3 rounded-md border px-3 py-2.5",
        checked ? "border-accent/60 bg-accent/5" : "border-line hover:border-line-strong",
        disabled && "cursor-not-allowed opacity-60",
      )}
    >
      <input type={type} name={name} checked={checked} disabled={disabled} onChange={onChange} className="mt-0.5 accent-[var(--color-accent)]" />
      <div className="min-w-0 flex-1">{children}</div>
    </label>
  );
}

function ClusterStep({ selected, onNext }: { selected: ClusterRef | null; onNext: (c: ClusterRef) => void }) {
  const { data, isPending, isError, error, refetch } = useClusters();
  const [choice, setChoice] = useState<ClusterRef | null>(selected);
  const current = choice ?? data?.items[0] ?? null;

  return (
    <Card>
      <CardHeader
        title="Choose a cluster"
        description="Only contexts the engine was configured with are offered; they cannot be added from the browser."
      />
      {isPending ? (
        <LoadingState rows={2} label="Loading clusters" />
      ) : isError ? (
        <ErrorState title="Could not load clusters" message={error.message} onRetry={() => refetch()} />
      ) : (
        <CardBody className="grid gap-3">
          <div className="grid gap-2" role="radiogroup" aria-label="Cluster">
            {data.items.map((c) => (
              <Choice
                key={c.context ?? ""}
                type="radio"
                name="cluster"
                checked={current?.context === c.context}
                onChange={() => setChoice(c)}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-sm text-fg">{contextLabel(c.context)}</span>
                  <ClusterRoleBadge cluster={c} />
                </div>
                <p className="mt-1 text-xs text-muted">
                  {c.role === "execution"
                    ? "Every namespace outside the system namespaces. Experiments run only on this cluster, and only after safety validation."
                    : `Read-only, limited to: ${c.namespaces?.join(", ")}. Topology and readiness only; no chaos execution is granted here.`}
                </p>
              </Choice>
            ))}
          </div>
          <p className="text-xs leading-relaxed text-muted [&_code]:font-mono [&_code]:text-fg">
            To add another cluster with read-only access, run{" "}
            <code>{AR} cluster import --context NAME --namespace NS</code> in a terminal. It creates a ServiceAccount there
            that can only read the namespaces you name, shows its plan and asks first.
          </p>
          <div className="flex justify-end">
            <Button variant="primary" disabled={!current} onClick={() => current && onNext(current)}>
              Continue
            </Button>
          </div>
        </CardBody>
      )}
    </Card>
  );
}

function NamespaceStep({
  cluster,
  selected,
  onChange,
  onBack,
  onNext,
}: {
  cluster: ClusterRef;
  selected: string[];
  onChange: (namespaces: string[]) => void;
  onBack: () => void;
  onNext: () => void;
}) {
  const { data, isPending, isError, error, refetch } = useNamespaces(cluster.context);
  const toggle = (name: string) =>
    onChange(selected.includes(name) ? selected.filter((n) => n !== name) : [...selected, name].sort());

  return (
    <Card>
      <CardHeader
        title="Choose the application's namespaces"
        description={`In ${contextLabel(cluster.context)}. Workload counts come from the engine's own read access.`}
      />
      {isPending ? (
        <LoadingState rows={4} label="Reading namespaces" />
      ) : isError ? (
        <ErrorState title="Could not read namespaces" message={error.message} onRetry={() => refetch()} />
      ) : (
        <CardBody className="grid gap-3">
          {data.source === "workloads" ? (
            <Callout tone="warning" title="Namespaces derived from workloads">
              The engine may not list namespaces (its access predates the topology view; <code className="font-mono">ar install</code> updates
              it). Only namespaces that contain workloads are shown.
            </Callout>
          ) : null}
          {data.items.length ? (
            <div className="grid gap-2 sm:grid-cols-2" role="group" aria-label="Namespaces">
              {data.items.map((n) => (
                <Choice
                  key={n.name}
                  type="checkbox"
                  name="namespace"
                  checked={selected.includes(n.name)}
                  disabled={n.access !== "readable"}
                  onChange={() => toggle(n.name)}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-sm text-fg">{n.name}</span>
                    {n.access === "readable" ? (
                      <span className="text-xs text-muted">{n.workloads} workloads</span>
                    ) : (
                      <Badge tone={n.access === "forbidden" ? "danger" : "warning"}>{n.access}</Badge>
                    )}
                  </div>
                  {n.access !== "readable" ? <p className="mt-1 font-mono text-2xs break-all text-faint">{n.detail}</p> : null}
                </Choice>
              ))}
            </div>
          ) : (
            <EmptyState title="No namespaces available" description="Every namespace in this cluster is a system namespace." />
          )}
          <p className="text-2xs text-faint">System namespaces are never offered: {data.excluded_namespaces.join(", ")}.</p>
          <div className="flex justify-between">
            <Button variant="ghost" onClick={onBack}>
              Back
            </Button>
            <Button variant="primary" disabled={!selected.length} onClick={onNext}>
              Discover workloads
            </Button>
          </div>
        </CardBody>
      )}
    </Card>
  );
}

function ReviewStep({ cluster, namespaces, onBack }: { cluster: ClusterRef; namespaces: string[]; onBack: () => void }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const preview = useTopologyPreview(cluster.context, namespaces);
  const [name, setName] = useState(namespaces.length === 1 ? namespaces[0] : "");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const inFlight = useRef(false);
  const nameId = useId();

  async function save() {
    if (!name.trim() || inFlight.current) return;
    inFlight.current = true;
    setSaving(true);
    setErrors({});
    setFailure(null);
    try {
      const app = await api.createApplication({ name: name.trim(), context: cluster.context, namespaces });
      void queryClient.invalidateQueries({ queryKey: queryKeys.applications });
      router.push(applicationHref(app.id));
    } catch (e) {
      const fields = e instanceof ApiError ? e.fieldErrors() : {};
      if (Object.keys(fields).length) setErrors(fields);
      else setFailure(errorText(e));
    } finally {
      inFlight.current = false;
      setSaving(false);
    }
  }

  return (
    <div className="grid gap-4">
      <Card>
        <CardHeader
          title="Discovered workloads"
          description={`${namespaces.join(", ")} in ${contextLabel(cluster.context)}: readiness as the controllers report it, Pods and Services linked by verified relationships.`}
          actions={
            <Button size="sm" onClick={() => preview.refetch()} disabled={preview.isFetching}>
              {preview.isFetching ? "Reading…" : "Re-read"}
            </Button>
          }
        />
        {preview.isPending ? (
          <LoadingState rows={4} label="Discovering workloads" />
        ) : preview.isError ? (
          <ErrorState title="Could not discover workloads" message={errorText(preview.error)} onRetry={() => preview.refetch()} />
        ) : (
          <WorkloadTable topology={preview.data} />
        )}
      </Card>

      <Card>
        <CardHeader title="Save the application" description="Stores the cluster and namespaces as a named view. Nothing is written to the cluster." />
        <CardBody className="grid gap-3">
          <form
            className="grid gap-3 sm:max-w-md"
            onSubmit={(e) => {
              e.preventDefault();
              void save();
            }}
          >
            <Field id={nameId} label="Application name" error={errors.name} hint="1–100 characters, unique">
              <Input id={nameId} value={name} maxLength={100} required aria-invalid={!!errors.name} onChange={(e) => setName(e.target.value)} />
            </Field>
            {errors.namespaces || errors.context ? (
              <Callout tone="danger" title="The engine rejected this scope" role="alert">
                {errors.context ?? errors.namespaces}
              </Callout>
            ) : null}
            {failure ? (
              <Callout tone="danger" title="Not saved" role="alert">
                <span className="font-mono">{failure}</span>
              </Callout>
            ) : null}
            <div className="flex justify-between gap-2">
              <Button variant="ghost" onClick={onBack} disabled={saving}>
                Back
              </Button>
              <Button type="submit" variant="primary" disabled={saving || !name.trim()}>
                {saving ? "Saving…" : "Save and open topology"}
              </Button>
            </div>
          </form>
        </CardBody>
      </Card>
    </div>
  );
}

export function WorkloadTable({ topology }: { topology: Topology }) {
  const rows = workloadRows(topology);
  if (!rows.length)
    return (
      <EmptyState
        title="No Deployments or StatefulSets found"
        description="The namespaces can be saved anyway; workloads appear in the topology once they exist."
      />
    );
  return (
    <>
      <Table>
        <THead>
          <tr>
            <TH>Workload</TH>
            <TH>Health</TH>
            <TH className="text-right">Ready</TH>
            <TH className="text-right">Pods</TH>
            <TH>Services</TH>
            <TH className="text-right">Warnings</TH>
            <TH>
              <span className="sr-only">Experiment</span>
            </TH>
          </tr>
        </THead>
        <TBody>
          {rows.map(({ node, pods, services, warnings }) => {
            const health = NODE_HEALTH_META[node.health];
            return (
              <TR key={node.id}>
                <TD>
                  <span className="font-mono text-xs font-medium">{node.name}</span>
                  <div className="text-2xs text-faint">
                    {node.kind} · {node.namespace}
                  </div>
                </TD>
                <TD>
                  <Badge tone={health.tone} dot title={node.health_reason}>
                    {health.label}
                  </Badge>
                </TD>
                <TD className="text-right font-mono text-xs tabular-nums">
                  {node.replicas ? `${node.replicas.ready}/${node.replicas.desired}` : "—"}
                </TD>
                <TD className="text-right font-mono text-xs tabular-nums">
                  {pods.filter((p) => p.health === "HEALTHY").length}/{pods.length}
                </TD>
                <TD className="font-mono text-xs text-muted">{services.map((s) => s.name).join(", ") || <span className="text-faint">none</span>}</TD>
                <TD className={cn("text-right font-mono text-xs tabular-nums", warnings ? "text-warning" : "text-faint")}>{warnings}</TD>
                <TD className="text-right">
                  {node.experiment_target?.supported ? (
                    <ButtonLink
                      href={newExperimentHref({ namespace: node.namespace ?? "", kind: node.kind, name: node.name })}
                      size="sm"
                      variant="ghost"
                    >
                      New experiment
                    </ButtonLink>
                  ) : (
                    <span className="text-2xs text-faint" title={node.experiment_target?.reason}>
                      read-only
                    </span>
                  )}
                </TD>
              </TR>
            );
          })}
        </TBody>
      </Table>
      <p className="border-t border-line px-4 py-2 text-2xs text-faint">
        Pods: ready / owned · Services: those whose selector matches the workload&apos;s Pods ·{" "}
        {topology.unknowns.length} items could not be verified (listed in the topology).
      </p>
    </>
  );
}
