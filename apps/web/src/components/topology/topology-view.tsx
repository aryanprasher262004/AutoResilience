"use client";

import { type ReactNode, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/field";
import { EmptyState } from "@/components/ui/states";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { Tooltip } from "@/components/ui/tooltip";
import type { EdgeType, ImportOverlay, NodeKind, Topology } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatRelative } from "@/lib/format";
import { TOUR_TARGET } from "@/lib/help-content";
import { SOURCE_META, importHref } from "@/lib/imports";
import {
  DEFAULT_FILTER,
  EDGE_META,
  EDGE_TYPES,
  KINDS,
  KIND_META,
  NODE_HEALTH_META,
  type TopologyFilter,
  UNKNOWN_META,
  applyFilter,
  matchesSearch,
} from "@/lib/topology";

import { Inspector } from "./inspector";
import { TopologyLegend } from "./legend";
import { TopologyGraph } from "./topology-graph";

function Toggle({
  pressed,
  onClick,
  children,
  hint,
}: {
  pressed: boolean;
  onClick: () => void;
  children: ReactNode;
  /** Explanation shown on hover and focus, and announced as the toggle's description. */
  hint?: ReactNode;
}) {
  const button = (describedBy?: string) => (
    <button
      type="button"
      aria-pressed={pressed}
      aria-describedby={describedBy}
      onClick={onClick}
      className={cn(
        "h-7 rounded-md border px-2 text-2xs font-medium transition-colors",
        pressed ? "border-accent/50 bg-accent/10 text-fg" : "border-line text-faint hover:text-muted",
      )}
    >
      {children}
    </button>
  );
  return hint ? <Tooltip content={hint}>{button}</Tooltip> : button();
}

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

/**
 * A topology snapshot: interactive graph (or an equivalent table), filters and an
 * inspector. `refreshError` set with data present means the shown snapshot is stale.
 */
export function TopologyView({
  topology,
  refreshError,
  refreshing,
  onRefresh,
}: {
  topology: Topology;
  refreshError?: string | null;
  refreshing?: boolean;
  onRefresh?: () => void;
}) {
  const [filter, setFilter] = useState<TopologyFilter>(DEFAULT_FILTER);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mode, setMode] = useState<"graph" | "list">("graph");
  const set = (patch: Partial<TopologyFilter>) => setFilter((f) => ({ ...f, ...patch }));

  const namespaces = useMemo(
    () => [...new Set(topology.nodes.flatMap((n) => (n.namespace ? [n.namespace] : [])))].sort(),
    [topology],
  );
  const { nodes, edges } = useMemo(() => applyFilter(topology, filter), [topology, filter]);
  const matches = useMemo(
    () => (filter.search.trim() ? new Set(nodes.filter((n) => matchesSearch(n, filter.search)).map((n) => n.id)) : null),
    [nodes, filter.search],
  );
  // A node that disappeared from a refreshed snapshot is simply no longer selected.
  const selected = topology.nodes.find((n) => n.id === selectedId) ?? null;
  const present = new Set(topology.nodes.map((n) => n.kind));
  const listed = matches ? nodes.filter((n) => matches.has(n.id)) : nodes;
  const hiddenKinds = KINDS.filter((k) => present.has(k) && !filter.kinds.includes(k)).length;
  const hiddenEdges = EDGE_TYPES.length - filter.edges.length;
  const relationCount = selected ? topology.edges.filter((e) => e.source === selected.id || e.target === selected.id).length : 0;

  return (
    <div className="grid gap-4">
      {refreshError ? (
        <Callout tone="warning" title="Showing an earlier snapshot" role="status">
          Refreshing failed: <span className="font-mono">{refreshError}</span>. The view below is the cluster as it was{" "}
          {formatRelative(topology.observed_at)}.
        </Callout>
      ) : null}

      <Card>
        <div className="flex flex-wrap items-end gap-2 border-b border-line px-4 py-3">
          <div className="w-full sm:w-56">
            <label htmlFor="topology-q" className="sr-only">
              Search resources
            </label>
            <Input
              id="topology-q"
              type="search"
              placeholder="Search name or namespace"
              value={filter.search}
              onChange={(e) => set({ search: e.target.value })}
            />
          </div>
          {namespaces.length > 1 ? (
            <div className="w-44">
              <label htmlFor="topology-ns" className="mb-1 block text-2xs font-medium tracking-wide text-faint uppercase">
                Namespace
              </label>
              <Select id="topology-ns" value={filter.namespace} onChange={(e) => set({ namespace: e.target.value })} className="h-7 text-xs">
                <option value="">All namespaces</option>
                {namespaces.map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </Select>
            </div>
          ) : null}
          <div className="ml-auto flex items-center gap-2">
            <span className="text-2xs text-faint" title={topology.observed_at}>
              observed {formatRelative(topology.observed_at)}
            </span>
            {onRefresh ? (
              <Button size="sm" onClick={onRefresh} disabled={refreshing}>
                {refreshing ? "Refreshing…" : "Refresh"}
              </Button>
            ) : null}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-line px-4 py-2">
          <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Resource kinds" data-tour={TOUR_TARGET.topologyKinds}>
            <span className="text-2xs text-faint">Show</span>
            {KINDS.filter((k) => present.has(k)).map((kind: NodeKind) => (
              <Toggle
                key={kind}
                pressed={filter.kinds.includes(kind)}
                onClick={() => set({ kinds: toggle(filter.kinds, kind) })}
                hint={KIND_META[kind].description}
              >
                {KIND_META[kind].plural} <span className="text-faint">{topology.counts[kind] ?? 0}</span>
              </Toggle>
            ))}
            {present.has("ReplicaSet") ? (
              <Toggle
                pressed={filter.inactiveReplicaSets}
                onClick={() => set({ inactiveReplicaSets: !filter.inactiveReplicaSets })}
                hint="ReplicaSets scaled to 0: earlier Deployment revisions, kept by Kubernetes for rollbacks. Hidden by default."
              >
                Inactive ReplicaSets
              </Toggle>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Relationship types" data-tour={TOUR_TARGET.topologyEdges}>
            <span className="text-2xs text-faint">Relationships</span>
            {EDGE_TYPES.map((type: EdgeType) => (
              <Toggle
                key={type}
                pressed={filter.edges.includes(type)}
                onClick={() => set({ edges: toggle(filter.edges, type) })}
                hint={
                  <>
                    {EDGE_META[type].description}. {EDGE_META[type].verified} A Kubernetes relationship, not traffic.
                  </>
                }
              >
                {EDGE_META[type].label}
              </Toggle>
            ))}
          </div>
          <div className="ml-auto flex gap-1" role="group" aria-label="View" data-tour={TOUR_TARGET.topologyView}>
            <Toggle pressed={mode === "graph"} onClick={() => setMode("graph")}>
              Graph
            </Toggle>
            <Toggle pressed={mode === "list"} onClick={() => setMode("list")}>
              List
            </Toggle>
          </div>
        </div>

        <TopologyLegend kinds={[...present]} />

        <div className="grid min-w-0 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <div className="min-w-0">
            {!nodes.length ? (
              <EmptyState
                title={topology.nodes.length ? "No resources match these filters" : "No resources in this scope"}
                description={
                  topology.nodes.length
                    ? [
                        hiddenKinds ? `${hiddenKinds} resource kind${hiddenKinds === 1 ? " is" : "s are"} hidden` : null,
                        hiddenEdges ? `${hiddenEdges} relationship type${hiddenEdges === 1 ? " is" : "s are"} hidden` : null,
                        filter.namespace ? `only namespace ${filter.namespace} is shown` : null,
                      ]
                        .filter(Boolean)
                        .join(", ") || "The current filters hide every resource."
                    : "The namespaces exist but hold no Deployments, StatefulSets, Pods or Services the engine could read. Resources it may not list appear under Not verified."
                }
                action={
                  topology.nodes.length ? (
                    <Button size="sm" onClick={() => setFilter(DEFAULT_FILTER)}>
                      Reset filters
                    </Button>
                  ) : undefined
                }
              />
            ) : mode === "graph" ? (
              <div className="h-[60vh] min-h-[360px]" aria-label="Topology graph" role="region" data-tour={TOUR_TARGET.topologyGraph}>
                <TopologyGraph nodes={nodes} edges={edges} selected={selected?.id ?? null} matches={matches} onSelect={setSelectedId} />
              </div>
            ) : (
              <div className="max-h-[60vh] overflow-auto" data-tour={TOUR_TARGET.topologyGraph}>
                <Table>
                  <THead>
                    <tr>
                      <TH>Resource</TH>
                      <TH>Namespace</TH>
                      <TH>Health</TH>
                      <TH>Status</TH>
                    </tr>
                  </THead>
                  <TBody>
                    {listed.map((n) => (
                      <TR key={n.id} className={cn("cursor-pointer", n.id === selected?.id && "bg-surface-3")} onClick={() => setSelectedId(n.id)}>
                        <TD>
                          <button type="button" className="text-left font-mono text-xs hover:text-accent" onClick={() => setSelectedId(n.id)}>
                            {n.name}
                          </button>
                          <div className="text-2xs text-faint">{n.kind}</div>
                        </TD>
                        <TD className="font-mono text-xs text-muted">{n.namespace ?? "—"}</TD>
                        <TD>
                          <Badge tone={NODE_HEALTH_META[n.health].tone} dot>
                            {NODE_HEALTH_META[n.health].label}
                          </Badge>
                        </TD>
                        <TD className="text-xs text-muted">{n.health_reason}</TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              </div>
            )}
          </div>
          <aside
            className="min-w-0 border-t border-line lg:max-h-[60vh] lg:overflow-y-auto lg:border-t-0 lg:border-l"
            aria-label="Inspector"
            data-tour={TOUR_TARGET.topologyInspector}
          >
            {selected ? (
              <Inspector topology={topology} node={selected} onSelect={setSelectedId} onClear={() => setSelectedId(null)} />
            ) : (
              <div className="grid gap-3 px-4 py-6 text-xs leading-relaxed text-muted">
                <p className="text-sm text-fg">Nothing selected</p>
                <ul className="grid list-disc gap-1.5 pl-4">
                  <li>Click a resource in the graph, or Tab to it and press Enter, to see its status, verified relationships, events and labels.</li>
                  <li>Drag the canvas to pan; scroll, pinch or use the + and − buttons to zoom.</li>
                  <li>The List view shows the same resources as a table.</li>
                  <li>Open the Legend for what colours and line styles mean.</li>
                </ul>
              </div>
            )}
          </aside>
        </div>

        <p className="border-t border-line px-4 py-2 text-2xs leading-relaxed text-faint">
          {nodes.length} of {topology.nodes.length} resources · {edges.length} relationships · {topology.traffic.detail}
        </p>
        <p aria-live="polite" className="sr-only">
          {selected ? `Selected ${selected.kind} ${selected.name}, ${relationCount} relationship${relationCount === 1 ? "" : "s"}.` : ""}
        </p>
      </Card>

      {topology.imported ? <ImportedPanel imported={topology.imported} onSelect={setSelectedId} /> : null}
      <Unknowns topology={topology} onSelect={setSelectedId} />
    </div>
  );
}

/** Planned (reviewed) vs observed resources of an imported application, and what its file declared. */
function ImportedPanel({ imported, onSelect }: { imported: ImportOverlay; onSelect: (id: string) => void }) {
  const missing = imported.planned.filter((p) => !p.observed);
  return (
    <Card>
      <CardHeader
        title="Imported application"
        description={`From ${SOURCE_META[imported.source].label.toLowerCase()} · ${imported.planned.length} planned resources, ${imported.planned.length - missing.length} observed now.`}
        actions={
          <ButtonLink href={importHref(imported.import_id)} size="sm">
            Import {imported.name}
          </ButtonLink>
        }
      />
      <CardBody className="grid gap-3 text-xs">
        <div>
          <h3 className="text-2xs font-medium tracking-wide text-faint uppercase">Planned vs observed</h3>
          <ul className="mt-1.5 flex flex-wrap gap-1.5">
            {imported.planned.map((p) => (
              <li key={p.id}>
                {p.observed ? (
                  <button type="button" onClick={() => onSelect(p.id)} className="rounded border border-line px-1.5 py-0.5 font-mono text-2xs text-fg hover:border-accent">
                    {p.kind} {p.name}
                  </button>
                ) : (
                  <span className="rounded border border-dashed border-warning/50 px-1.5 py-0.5 font-mono text-2xs text-warning">
                    {p.kind} {p.name} · not observed
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
        {imported.declared.length ? (
          <div>
            <h3 className="text-2xs font-medium tracking-wide text-faint uppercase">Declared in the source file (not verified)</h3>
            <ul className="mt-1.5 grid gap-1 text-muted">
              {imported.declared.map((d) => (
                <li key={`${d.source}-${d.target}`}>
                  <span className="font-mono text-fg">{d.source.split("/").at(-1)}</span> depends on{" "}
                  <span className="font-mono text-fg">{d.target.split("/").at(-1)}</span>
                </li>
              ))}
            </ul>
            <p className="mt-1.5 text-2xs text-faint">
              Start order the file states. Kubernetes does not record it, so it is not drawn as a line, and it says nothing about
              traffic.
            </p>
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}

function Unknowns({ topology, onSelect }: { topology: Topology; onSelect: (id: string) => void }) {
  if (!topology.unknowns.length) return null;
  return (
    <Card data-tour={TOUR_TARGET.topologyUnknowns}>
      <details>
        <summary className="cursor-pointer px-4 py-3 text-sm text-fg">
          Not verified ({topology.unknowns.length}){" "}
          <span className="text-xs text-muted">
            what the engine could not read or link, shown instead of guessed
          </span>
        </summary>
        <ul className="divide-y divide-line border-t border-line">
          {topology.unknowns.map((u, i) => (
            <li key={i} className="grid gap-0.5 px-4 py-2 text-xs">
              <p className="font-mono text-2xs text-warning">{u.type}</p>
              <p className="text-muted">{u.detail}</p>
              <p className="text-2xs text-faint">{UNKNOWN_META[u.type]}</p>
              {u.subject ? (
                <button type="button" onClick={() => onSelect(u.subject!)} className="justify-self-start font-mono text-2xs text-faint hover:text-accent">
                  {u.subject}
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      </details>
    </Card>
  );
}
