"use client";

import type { ReactNode } from "react";

import { newExperimentHref, serviceHref } from "@/components/services/health-badge";
import { Badge } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import type { Topology, TopologyNode } from "@/lib/api/types";
import { formatRelative } from "@/lib/format";
import { EDGE_META, HEALTH_SOURCE, KIND_META, NODE_HEALTH_META, UNKNOWN_META, relationsOf, unknownsOf } from "@/lib/topology";

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="border-t border-line px-4 py-3">
      <h3 className="text-2xs font-medium tracking-wide text-faint uppercase">{title}</h3>
      {hint ? <p className="mt-0.5 text-2xs leading-relaxed text-faint">{hint}</p> : null}
      <div className="mt-2">{children}</div>
    </section>
  );
}

function Rows({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[8rem_1fr] gap-x-3 gap-y-1 text-xs">
      {rows.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="text-muted">{label}</dt>
          <dd className="min-w-0 font-mono break-all text-fg">{value ?? <span className="text-faint">No data</span>}</dd>
        </div>
      ))}
    </dl>
  );
}

function details(node: TopologyNode): [string, ReactNode][] {
  if (node.replicas) {
    const r = node.replicas;
    return [
      ["Ready / desired", `${r.ready}/${r.desired}`],
      ["Available", r.available],
      ["Current", r.current],
      ["Updated", r.updated],
      ["Selector", r.selector],
      ...(node.kind === "ReplicaSet" ? ([["Revision", r.revision]] as [string, ReactNode][]) : []),
    ];
  }
  if (node.pod) {
    const p = node.pod;
    return [
      ["Phase", p.terminating ? `${p.phase} (terminating)` : p.phase],
      ["Ready", p.ready ? "yes" : "no"],
      ["Restarts", p.restarts],
      ["Node", p.node_name],
      ["Pod IP", p.pod_ip],
      ["Started", p.start_time ? formatRelative(p.start_time) : null],
    ];
  }
  if (node.service) {
    const s = node.service;
    return [
      ["Type", s.type],
      ["Cluster IP", s.cluster_ip],
      ["Ports", s.ports.length ? s.ports.map((p) => `${p.name ? `${p.name} ` : ""}${p.port}→${p.target_port ?? "?"}/${p.protocol}`).join(", ") : null],
      ["Selector", s.selector ? Object.entries(s.selector).map(([k, v]) => `${k}=${v}`).join(",") : null],
    ];
  }
  if (node.endpoint_slice) {
    const e = node.endpoint_slice;
    return [
      ["Ready / endpoints", `${e.ready}/${e.endpoints}`],
      ["Address type", e.address_type],
      ["Ports", e.ports.length ? e.ports.map((p) => `${p.port}/${p.protocol}`).join(", ") : null],
    ];
  }
  if (node.node) {
    const n = node.node;
    return [
      ["Ready condition", n.ready],
      ["Roles", n.roles.length ? n.roles.join(", ") : null],
      ["Schedulable", n.unschedulable ? "no (cordoned)" : "yes"],
      ["Kubelet", n.kubelet_version],
      ["OS image", n.os_image],
      ["Architecture", n.architecture],
    ];
  }
  return [];
}

/** Everything the snapshot holds about one node; values are shown as returned, never derived. */
export function Inspector({
  topology,
  node,
  onSelect,
  onClear,
}: {
  topology: Topology;
  node: TopologyNode;
  onSelect: (id: string) => void;
  onClear?: () => void;
}) {
  const health = NODE_HEALTH_META[node.health];
  const relations = relationsOf(topology, node.id);
  const unknowns = unknownsOf(topology, node.id);
  const target = node.experiment_target;
  const workload = { namespace: node.namespace ?? "", kind: node.kind, name: node.name };

  return (
    <div aria-label={`${node.kind} ${node.name}`} className="text-sm">
      <header className="px-4 py-3">
        <div className="flex items-start justify-between gap-2">
          <p className="text-2xs tracking-wide text-faint uppercase">{KIND_META[node.kind].label}</p>
          {onClear ? (
            <Button size="sm" variant="ghost" className="-mt-1 -mr-2 h-6 px-2 text-2xs" onClick={onClear}>
              Clear selection
            </Button>
          ) : null}
        </div>
        <h2 className="mt-0.5 font-mono text-sm font-semibold break-all text-fg">{node.name}</h2>
        <p className="mt-0.5 text-xs text-muted">{node.namespace ? `namespace ${node.namespace}` : "cluster-scoped"}</p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Badge tone={health.tone} dot>
            {health.label}
          </Badge>
          <span className="text-xs text-muted">{node.health_reason || "No status reported"}</span>
        </div>
        <p className="mt-2 text-2xs leading-relaxed text-faint">
          {KIND_META[node.kind].description} {HEALTH_SOURCE[node.kind]}
        </p>
      </header>

      {target ? (
        <Section
          title="Experiment target"
          hint={target.supported ? "New experiment opens the builder with this workload filled in." : "Experiments run only on the execution cluster."}
        >
          <p className="text-xs leading-relaxed text-muted">{target.reason}</p>
          {target.supported ? (
            <div className="mt-2 flex flex-wrap gap-2">
              <ButtonLink href={newExperimentHref(workload)} variant="primary" size="sm">
                New experiment
              </ButtonLink>
              <ButtonLink href={serviceHref(workload)} size="sm">
                Service history
              </ButtonLink>
            </div>
          ) : null}
        </Section>
      ) : null}

      {details(node).length ? (
        <Section title="Status" hint="As the Kubernetes API returned it; nothing is estimated.">
          <Rows rows={details(node)} />
        </Section>
      ) : null}

      {node.pod?.containers.length ? (
        <Section title="Containers">
          <ul className="grid gap-1.5 text-xs">
            {node.pod.containers.map((c) => (
              <li key={c.name} className="rounded border border-line px-2 py-1.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-fg">{c.name}</span>
                  <Badge tone={c.ready ? "success" : "warning"}>{c.ready ? "ready" : (c.reason ?? c.state ?? "not ready")}</Badge>
                </div>
                <p className="mt-0.5 font-mono text-2xs break-all text-faint">
                  {c.image} · {c.restart_count} restarts
                </p>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      <Section
        title={`Relationships (${relations.length})`}
        hint="References Kubernetes records, each with where it was read and how it was verified. Not measured traffic."
      >
        {relations.length ? (
          <ul className="grid gap-2 text-xs">
            {relations.map(({ edge, direction, other }) => (
              <li key={edge.id}>
                <p>
                  <span className="text-muted">{direction === "out" ? EDGE_META[edge.type].label : `${EDGE_META[edge.type].label} by`}</span>{" "}
                  {other ? (
                    <button type="button" onClick={() => onSelect(other.id)} className="font-mono text-fg hover:text-accent">
                      {other.kind} {other.name}
                    </button>
                  ) : (
                    <span className="font-mono text-faint">{direction === "out" ? edge.target : edge.source}</span>
                  )}
                  {edge.type === "endpoint" && edge.attributes.ready === false ? (
                    <Badge tone="warning" className="ml-1.5">not ready</Badge>
                  ) : null}
                </p>
                <p className="text-2xs text-faint">
                  <span className="font-mono">{edge.provenance.source}</span>: {edge.provenance.detail}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-faint">No verified relationships.</p>
        )}
      </Section>

      {unknowns.length ? (
        <Section title="Not verified" hint="Reported instead of guessed.">
          <ul className="grid gap-1.5 text-xs text-muted">
            {unknowns.map((u, i) => (
              <li key={i}>
                <span className="font-mono text-2xs text-warning">{u.type}</span> {u.detail}
                <p className="text-2xs text-faint">{UNKNOWN_META[u.type]}</p>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      <Section title={`Events (${node.events.length})`} hint="The newest 10 the cluster still retains for this object.">
        {node.events.length ? (
          <ul className="grid gap-1.5 text-xs">
            {node.events.map((e, i) => (
              <li key={i}>
                <p>
                  <Badge tone={e.type === "Warning" ? "warning" : "neutral"}>{e.reason || e.type}</Badge>{" "}
                  <span className="text-faint">
                    ×{e.count}
                    {e.last_seen ? ` · ${formatRelative(e.last_seen)}` : ""}
                  </span>
                </p>
                <p className="mt-0.5 text-muted">{e.message}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-faint">No events retained by the cluster for this object.</p>
        )}
      </Section>

      <Section title="Metadata">
        <Rows
          rows={[
            ["ID", node.id],
            ["UID", node.uid],
            ["Created", node.created_at ? formatRelative(node.created_at) : null],
          ]}
        />
        {Object.keys(node.labels).length ? (
          <ul className="mt-2 flex flex-wrap gap-1" aria-label="Labels">
            {Object.entries(node.labels).map(([k, v]) => (
              <li key={k} className="rounded bg-surface-3 px-1.5 py-0.5 font-mono text-2xs break-all text-muted">
                {k}={v}
              </li>
            ))}
          </ul>
        ) : null}
      </Section>
    </div>
  );
}
