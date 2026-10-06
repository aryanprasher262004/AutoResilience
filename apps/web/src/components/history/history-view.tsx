"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";

import { ScoreCell } from "@/components/experiment/score-cell";
import { ExperimentStateBadge } from "@/components/experiment/state-badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/field";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { useDashboardSummary, useExperimentHistory } from "@/lib/api/queries";
import type { ExperimentState, FaultType, HistoryQuery } from "@/lib/api/types";
import { FAULT_TYPES } from "@/lib/experiment-options";
import { isTerminal } from "@/lib/experiment-state";
import { formatDateTime, formatRelative, formatSeconds, shortId } from "@/lib/format";

const PAGE_SIZE = 25;

const ACTIVE: ExperimentState[] = ["CREATED", "VALIDATING", "BASELINING", "INJECTING", "OBSERVING", "RECOVERING"];
const FINISHED: ExperimentState[] = ["COMPLETED", "VALIDATION_FAILED", "INJECTION_FAILED", "ABORTED", "UNKNOWN"];

/** Outcome groups map onto the backend's state filter (no client-side filtering). */
const GROUPS: Record<string, { label: string; states: ExperimentState[] }> = {
  active: { label: "Not finished (running or not started)", states: ACTIVE },
  completed: { label: "Completed", states: ["COMPLETED"] },
  failed: { label: "Failed (validation / injection)", states: ["VALIDATION_FAILED", "INJECTION_FAILED"] },
  aborted: { label: "Aborted", states: ["ABORTED"] },
  undetermined: { label: "Undetermined", states: ["UNKNOWN"] },
};

const SORTS: Record<string, { label: string; sort: NonNullable<HistoryQuery["sort"]>; order: "asc" | "desc" }> = {
  newest: { label: "Newest first", sort: "created_at", order: "desc" },
  oldest: { label: "Oldest first", sort: "created_at", order: "asc" },
  updated: { label: "Recently updated", sort: "updated_at", order: "desc" },
  name: { label: "Name A–Z", sort: "name", order: "asc" },
  score_desc: { label: "Score: high to low", sort: "score", order: "desc" },
  score_asc: { label: "Score: low to high", sort: "score", order: "asc" },
};

type Mode = "history" | "reports";

function useUrlState() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const get = (key: string) => params.get(key) ?? "";
  const set = (changes: Record<string, string>, resetPage = true) => {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    if (resetPage) next.delete("page");
    const s = next.toString();
    router.replace(s ? `${pathname}?${s}` : pathname, { scroll: false });
  };
  return { get, set, any: params.toString() !== "", clear: () => router.replace(pathname, { scroll: false }) };
}

function Filters({ mode, url }: { mode: Mode; url: ReturnType<typeof useUrlState> }) {
  const [search, setSearch] = useState(url.get("q"));
  const namespaces = useDashboardSummary().data?.namespaces ?? [];
  const q = url.get("q");

  // Debounced search; keeps the input responsive and the URL authoritative.
  useEffect(() => {
    if (search === q) return;
    const timer = setTimeout(() => url.set({ q: search.trim() }), 300);
    return () => clearTimeout(timer);
  }, [search, q, url]);

  const groups = Object.entries(GROUPS).filter(([key]) => mode === "history" || key !== "active");
  return (
    <div className="flex flex-wrap items-end gap-2 border-b border-line px-4 py-3">
      <div className="w-full sm:w-64">
        <label htmlFor="history-q" className="sr-only">
          Search
        </label>
        <Input
          id="history-q"
          type="search"
          placeholder="Search name, workload or namespace"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>
      <FilterSelect label={mode === "reports" ? "Outcome" : "State"} id="history-state" value={url.get("state")} onChange={(v) => url.set({ state: v })}>
        <option value="">{mode === "reports" ? "All outcomes" : "All states"}</option>
        {groups.map(([key, g]) => (
          <option key={key} value={key}>
            {g.label}
          </option>
        ))}
      </FilterSelect>
      <FilterSelect label="Fault" id="history-fault" value={url.get("fault")} onChange={(v) => url.set({ fault: v })}>
        <option value="">All faults</option>
        {FAULT_TYPES.map((f) => (
          <option key={f} value={f}>
            {f}
          </option>
        ))}
      </FilterSelect>
      <FilterSelect label="Namespace" id="history-ns" value={url.get("ns")} onChange={(v) => url.set({ ns: v })}>
        <option value="">All namespaces</option>
        {namespaces.map((n) => (
          <option key={n.namespace} value={n.namespace}>
            {n.namespace} ({n.total})
          </option>
        ))}
      </FilterSelect>
      <FilterSelect label="Sort" id="history-sort" value={url.get("sort") || "newest"} onChange={(v) => url.set({ sort: v === "newest" ? "" : v })}>
        {Object.entries(SORTS).map(([key, s]) => (
          <option key={key} value={key}>
            {s.label}
          </option>
        ))}
      </FilterSelect>
      {url.any ? (
        <Button
          variant="ghost"
          size="sm"
          className="mb-0.5"
          onClick={() => {
            setSearch("");
            url.clear();
          }}
        >
          Reset
        </Button>
      ) : null}
    </div>
  );
}

function FilterSelect({
  id,
  label,
  value,
  onChange,
  children,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: ReactNode;
}) {
  return (
    <div className="w-44">
      <label htmlFor={id} className="mb-1 block text-2xs font-medium tracking-wide text-faint uppercase">
        {label}
      </label>
      <Select id={id} value={value} onChange={(e) => onChange(e.target.value)} className="h-7 text-xs">
        {children}
      </Select>
    </div>
  );
}

/** Experiment history (or finished-run reports): server-side filtering, sorting and paging. */
export function HistoryView({ mode }: { mode: Mode }) {
  const url = useUrlState();
  const router = useRouter();
  const page = Math.max(1, Number(url.get("page")) || 1);
  const group = GROUPS[url.get("state")];
  const sort = SORTS[url.get("sort")] ?? SORTS.newest;
  const fault = url.get("fault");
  const query: HistoryQuery = {
    q: url.get("q") || undefined,
    state: group ? group.states : mode === "reports" ? FINISHED : undefined,
    fault_type: fault && (FAULT_TYPES as readonly string[]).includes(fault) ? [fault as FaultType] : undefined,
    namespace: url.get("ns") ? [url.get("ns")] : undefined,
    sort: sort.sort,
    order: sort.order,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  };
  const { data, isPending, isError, error, refetch, isPlaceholderData } = useExperimentHistory(query);
  const hrefFor = (id: string) => (mode === "reports" ? `/reports/${id}` : `/experiments/${id}`);

  let body: ReactNode;
  if (isPending) body = <LoadingState rows={6} label="Loading experiments" />;
  else if (isError) body = <ErrorState message={error.message} onRetry={() => refetch()} />;
  else if (data.total === 0 && !url.any)
    body =
      mode === "reports" ? (
        <EmptyState
          title="No finished experiments yet"
          description="A report becomes available for every experiment that finishes: completed, blocked, failed, aborted or undetermined."
          action={<ButtonLink href="/experiments/new" variant="primary" size="sm">New Experiment</ButtonLink>}
        />
      ) : (
        <EmptyState
          title="No experiments yet"
          description="Every experiment you create appears here with its live state, score and outcome."
          action={<ButtonLink href="/experiments/new" variant="primary" size="sm">New Experiment</ButtonLink>}
        />
      );
  else if (data.total === 0)
    body = (
      <EmptyState
        title="No experiments match these filters"
        action={<Button size="sm" onClick={url.clear}>Reset filters</Button>}
      />
    );
  else if (!data.items.length)
    // e.g. a bookmarked ?page= beyond the end after records changed
    body = (
      <EmptyState
        title={`Page ${page} is past the end`}
        description={`${data.total} experiment${data.total === 1 ? "" : "s"} match these filters.`}
        action={<Button size="sm" onClick={() => url.set({ page: "" }, false)}>First page</Button>}
      />
    );
  else {
    const first = data.offset + 1;
    const last = data.offset + data.items.length;
    const pages = Math.ceil(data.total / data.limit);
    body = (
      <div className={isPlaceholderData ? "opacity-60 transition-opacity" : undefined}>
        <Table>
          <THead>
            <tr>
              <TH>Experiment</TH>
              <TH>Target</TH>
              <TH>Fault</TH>
              <TH>{mode === "reports" ? "Outcome" : "State"}</TH>
              <TH className="text-right">Score</TH>
              <TH className="text-right">Recovery</TH>
              <TH>{mode === "reports" ? "Finished" : "Created"}</TH>
              <TH><span className="sr-only">Actions</span></TH>
            </tr>
          </THead>
          <TBody>
            {data.items.map((e) => (
              <TR key={e.id} className="cursor-pointer" onClick={() => router.push(hrefFor(e.id))}>
                <TD>
                  <Link href={hrefFor(e.id)} className="font-medium hover:text-accent" onClick={(ev) => ev.stopPropagation()}>
                    {e.name}
                  </Link>
                  <div className="font-mono text-2xs text-faint" title={e.id}>
                    {shortId(e.id)}
                  </div>
                </TD>
                <TD className="font-mono text-xs">
                  {e.target.namespace}/{e.target.name}
                  <div className="font-sans text-2xs text-faint">{e.target.kind}</div>
                </TD>
                <TD className="text-xs">
                  {e.fault_type}
                  <div className="text-2xs text-faint">
                    {e.pod_delete_mode} · {e.affected_replicas}× · {e.duration_seconds}s
                  </div>
                </TD>
                <TD>
                  <ExperimentStateBadge experiment={e} />
                  {mode === "reports" && e.outcome_reason ? (
                    <div className="mt-0.5 max-w-64 truncate text-2xs text-faint" title={e.outcome_reason}>
                      {e.outcome_reason}
                    </div>
                  ) : null}
                </TD>
                <TD className="text-right">
                  <ScoreCell score={e.score} />
                </TD>
                <TD className="text-right font-mono text-xs tabular-nums">
                  {e.time_to_recovery_seconds !== null ? formatSeconds(e.time_to_recovery_seconds) : <span className="text-faint">—</span>}
                </TD>
                <TD className="text-xs text-muted" title={formatDateTime(mode === "reports" ? e.updated_at : e.created_at)}>
                  {formatRelative(mode === "reports" ? e.updated_at : e.created_at)}
                  {mode === "history" ? <div className="text-2xs text-faint">updated {formatRelative(e.updated_at)}</div> : null}
                </TD>
                <TD className="text-right whitespace-nowrap" onClick={(ev) => ev.stopPropagation()}>
                  {mode === "history" ? (
                    isTerminal(e.state) ? (
                      <Link href={`/reports/${e.id}`} className="text-xs text-muted hover:text-accent">
                        Report
                      </Link>
                    ) : (
                      <Link href={`/experiments/${e.id}`} className="text-xs text-info hover:text-accent">
                        Watch live
                      </Link>
                    )
                  ) : (
                    <Link href={`/experiments/${e.id}`} className="text-xs text-muted hover:text-accent">
                      Experiment room
                    </Link>
                  )}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
        <div className="flex items-center justify-between border-t border-line px-4 py-2 text-xs text-muted">
          <span>
            {first}–{last} of {data.total}
          </span>
          {pages > 1 ? (
            <div className="flex items-center gap-2">
              <Button size="sm" disabled={page <= 1} onClick={() => url.set({ page: page - 1 > 1 ? String(page - 1) : "" }, false)}>
                Previous
              </Button>
              <span className="font-mono">
                {page} / {pages}
              </span>
              <Button size="sm" disabled={page >= pages} onClick={() => url.set({ page: String(page + 1) }, false)}>
                Next
              </Button>
            </div>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <Card>
      <Filters mode={mode} url={url} />
      {body}
    </Card>
  );
}
