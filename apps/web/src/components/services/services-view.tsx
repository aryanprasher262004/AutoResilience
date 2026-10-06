"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { type ReactNode, useEffect, useMemo, useState } from "react";

import { ScoreCell } from "@/components/experiment/score-cell";
import { ExperimentStateBadge } from "@/components/experiment/state-badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/field";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { useServices } from "@/lib/api/queries";
import type { ServiceSummary } from "@/lib/api/types";
import { formatRelative } from "@/lib/format";
import { HEALTH_META } from "@/lib/workload-health";

import { HealthBadge, Replicas, newExperimentHref, serviceHref } from "./health-badge";

type Sorter = (a: ServiceSummary, b: ServiceSummary) => number;
const byName: Sorter = (a, b) => a.namespace.localeCompare(b.namespace) || a.name.localeCompare(b.name);
const nullsLast = (a: number | null | undefined, b: number | null | undefined, dir: 1 | -1) =>
  a == null ? (b == null ? 0 : 1) : b == null ? -1 : (a - b) * dir;
const time = (s: ServiceSummary) => (s.latest_experiment ? Date.parse(s.latest_experiment.created_at) : null);

const SORTS: Record<string, { label: string; compare: Sorter }> = {
  name: { label: "Namespace, name", compare: byName },
  health: { label: "Health: worst first", compare: (a, b) => HEALTH_META[a.health].rank - HEALTH_META[b.health].rank || byName(a, b) },
  score_asc: { label: "Latest score: low to high", compare: (a, b) => nullsLast(a.latest_score?.score, b.latest_score?.score, 1) || byName(a, b) },
  score_desc: { label: "Latest score: high to low", compare: (a, b) => nullsLast(a.latest_score?.score, b.latest_score?.score, -1) || byName(a, b) },
  tested: { label: "Recently tested", compare: (a, b) => nullsLast(time(a), time(b), -1) || byName(a, b) },
  most: { label: "Most experiments", compare: (a, b) => b.experiment_count - a.experiment_count || byName(a, b) },
  untested: { label: "Untested first", compare: (a, b) => a.experiment_count - b.experiment_count || byName(a, b) },
};

function useUrlParam() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(key, value);
    else next.delete(key);
    const s = next.toString();
    router.replace(s ? `${pathname}?${s}` : pathname, { scroll: false });
  };
  return { get: (key: string) => params.get(key) ?? "", set, any: params.size > 0, clear: () => router.replace(pathname, { scroll: false }) };
}

function Control({ id, label, children }: { id: string; label: string; children: ReactNode }) {
  return (
    <div className="w-48">
      <label htmlFor={id} className="mb-1 block text-2xs font-medium tracking-wide text-faint uppercase">
        {label}
      </label>
      {children}
    </div>
  );
}

/**
 * Discovered workloads. The API returns the complete inventory (one cluster, not paged),
 * so search/filter/sort only reorder what the server sent; no values are derived here.
 */
export function ServicesView() {
  const url = useUrlParam();
  const router = useRouter();
  const { data, isPending, isError, error, refetch } = useServices();
  // Filtering uses the input immediately; the URL follows (debounced) for refresh/links.
  const [search, setSearch] = useState(url.get("q"));
  const urlQ = url.get("q");
  useEffect(() => {
    if (search === urlQ) return;
    const timer = setTimeout(() => url.set("q", search.trim()), 300);
    return () => clearTimeout(timer);
  }, [search, urlQ, url]);
  const q = search.trim().toLowerCase();
  const reset = () => {
    setSearch("");
    url.clear();
  };
  const ns = url.get("ns");
  const sort = SORTS[url.get("sort")] ?? SORTS.name;

  const namespaces = useMemo(() => [...new Set(data?.items.map((s) => s.namespace))].sort(), [data]);
  const rows = useMemo(
    () =>
      (data?.items ?? [])
        .filter((s) => (!ns || s.namespace === ns) && (!q || `${s.namespace}/${s.name}`.toLowerCase().includes(q)))
        .sort(sort.compare),
    [data, ns, q, sort],
  );

  let body: ReactNode;
  if (isPending) body = <LoadingState rows={6} label="Discovering workloads" />;
  else if (isError) body = <ErrorState title="Could not discover workloads" message={error.message} onRetry={() => refetch()} />;
  else if (!data.items.length)
    body = (
      <EmptyState
        title="No workloads found"
        description="The cluster has no Deployments or StatefulSets outside system namespaces."
      />
    );
  else if (!rows.length)
    body = <EmptyState title="No workloads match these filters" action={<Button size="sm" onClick={reset}>Reset filters</Button>} />;
  else
    body = (
      <Table>
        <THead>
          <tr>
            <TH>Workload</TH>
            <TH>Namespace</TH>
            <TH>Health</TH>
            <TH className="text-right">Ready</TH>
            <TH className="text-right">Latest score</TH>
            <TH className="text-right">Experiments</TH>
            <TH>Latest experiment</TH>
            <TH><span className="sr-only">Actions</span></TH>
          </tr>
        </THead>
        <TBody>
          {rows.map((s) => (
            <TR key={`${s.namespace}/${s.kind}/${s.name}`} className="cursor-pointer" onClick={() => router.push(serviceHref(s))}>
              <TD>
                <Link href={serviceHref(s)} className="font-mono text-xs font-medium hover:text-accent" onClick={(e) => e.stopPropagation()}>
                  {s.name}
                </Link>
                <div className="text-2xs text-faint">{s.kind}</div>
              </TD>
              <TD className="font-mono text-xs text-muted">{s.namespace}</TD>
              <TD><HealthBadge health={s.health} /></TD>
              <TD className="text-right" title={`${s.current_replicas} pod(s) exist, ${s.available_replicas} available`}>
                <Replicas ready={s.ready_replicas} desired={s.desired_replicas} />
              </TD>
              <TD className="text-right">
                {s.latest_score ? <ScoreCell score={s.latest_score} /> : <span className="text-faint">—</span>}
              </TD>
              <TD className="text-right font-mono text-xs tabular-nums">
                {s.experiment_count || <span className="text-faint">0</span>}
              </TD>
              <TD className="text-xs">
                {s.latest_experiment ? (
                  <div className="flex items-center gap-2">
                    <ExperimentStateBadge experiment={s.latest_experiment} />
                    <span className="text-muted">{formatRelative(s.latest_experiment.created_at)}</span>
                  </div>
                ) : (
                  <span className="text-faint">Never tested</span>
                )}
              </TD>
              <TD className="text-right" onClick={(e) => e.stopPropagation()}>
                <Link href={newExperimentHref(s)} className="text-xs whitespace-nowrap text-muted hover:text-accent">
                  New experiment
                </Link>
              </TD>
            </TR>
          ))}
        </TBody>
      </Table>
    );

  return (
    <Card>
      <div className="flex flex-wrap items-end gap-2 border-b border-line px-4 py-3">
        <div className="w-full sm:w-64">
          <label htmlFor="services-q" className="sr-only">Search</label>
          <Input
            id="services-q"
            type="search"
            placeholder="Search workload or namespace"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Control id="services-ns" label="Namespace">
          <Select id="services-ns" value={ns} onChange={(e) => url.set("ns", e.target.value)} className="h-7 text-xs">
            <option value="">All namespaces</option>
            {namespaces.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </Select>
        </Control>
        <Control id="services-sort" label="Sort">
          <Select
            id="services-sort"
            value={url.get("sort") || "name"}
            onChange={(e) => url.set("sort", e.target.value === "name" ? "" : e.target.value)}
            className="h-7 text-xs"
          >
            {Object.entries(SORTS).map(([key, s]) => (
              <option key={key} value={key}>{s.label}</option>
            ))}
          </Select>
        </Control>
        {url.any || search ? (
          <Button variant="ghost" size="sm" className="mb-0.5" onClick={reset}>Reset</Button>
        ) : null}
      </div>
      {body}
      {data ? (
        <p className="border-t border-line px-4 py-2 text-2xs text-faint">
          {rows.length} of {data.items.length} workloads · Deployments and StatefulSets, replica counts from their
          controllers · system namespaces hidden: {data.excluded_namespaces.join(", ")}
        </p>
      ) : null}
    </Card>
  );
}
