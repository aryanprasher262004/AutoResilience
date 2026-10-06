import type { ReactNode } from "react";

import { Card, CardHeader } from "@/components/ui/card";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import type { Experiment } from "@/lib/api/types";
import { groupValue, readImpact } from "@/lib/evidence";
import { formatPercent, formatSeconds, secondsBetween } from "@/lib/format";

type Group = { status: string; message: string; values: Record<string, unknown> } | null | undefined;

const none = (why?: string) => (
  <span className="text-faint" title={why}>
    {why ? "Unavailable" : "No data"}
  </span>
);
const num = (v: number | null, digits = 2, suffix = "") =>
  v === null ? null : <span className="font-mono tabular-nums">{`${Number(v.toFixed(digits))}${suffix}`}</span>;

/** Baseline vs during-fault, for the measurements the backend actually recorded. */
export function MetricsTable({ experiment: e }: { experiment: Experiment }) {
  const b = e.baseline;
  const i = readImpact(e);
  const c = i?.client;
  const unavailable = (g: Group) => (g && g.status !== "OK" ? g.message : undefined);
  const clientSpan = c ? secondsBetween(c.countedFrom, c.countedTo) : null;
  const clientRate = c?.requests && clientSpan ? c.requests / clientSpan : null;
  const serverRatio =
    i?.serverRequests && i.serverErrors !== null ? i.serverErrors / i.serverRequests : null;

  const rows: Array<{ metric: string; source: string; baseline: ReactNode; fault: ReactNode }> = [
    {
      metric: "Available replicas",
      source: "Kubernetes · sampled every scrape interval",
      baseline:
        num(groupValue(b?.availability, "available_replicas_avg")) ?? none(unavailable(b?.availability)),
      fault:
        i?.minAvailable !== null && i?.minAvailable !== undefined ? (
          <>
            {num(i.minAvailable, 0)} <span className="text-faint">min of {i.availabilitySamples} samples</span>
          </>
        ) : (
          none()
        ),
    },
    {
      metric: "Container restarts",
      source: "kube-state-metrics",
      baseline: num(groupValue(b?.restarts, "restarts_in_window"), 0) ?? none(unavailable(b?.restarts)),
      fault: num(i?.restarts ?? null, 0) ?? none(),
    },
    {
      metric: "Client request rate",
      source: "Load generator (client view)",
      baseline: num(groupValue(b?.client, "client_rate_rps"), 2, " req/s") ?? none(unavailable(b?.client)),
      fault: clientRate !== null ? num(clientRate, 2, " req/s") : none(c?.reason ?? undefined),
    },
    {
      metric: "Client failure ratio",
      source: "connection errors + timeouts + HTTP 5xx",
      baseline: groupValue(b?.client, "client_failure_ratio") !== null ? formatPercent(groupValue(b?.client, "client_failure_ratio")) : none(unavailable(b?.client)),
      fault: c?.failureRatio !== null && c?.failureRatio !== undefined ? formatPercent(c.failureRatio) : none(),
    },
    {
      metric: "Client outage",
      source: "Load generator outage counter",
      baseline:
        groupValue(b?.client, "client_outage_seconds") !== null ? (
          <>
            {formatSeconds(groupValue(b?.client, "client_outage_seconds"))}{" "}
            <span className="text-faint">in {b?.window_seconds}s</span>
          </>
        ) : (
          none(unavailable(b?.client))
        ),
      fault:
        c?.outage && c.outage.status === "OK" ? (
          <>
            {formatSeconds(c.outage.seconds)} <span className="text-faint">{c.outage.pattern?.toLowerCase()}</span>
          </>
        ) : (
          none(c?.outage?.reason ?? undefined)
        ),
    },
    {
      metric: "Client p95 latency",
      source: "Answered requests only",
      baseline: num(groupValue(b?.client, "client_latency_p95_seconds") !== null ? groupValue(b?.client, "client_latency_p95_seconds")! * 1000 : null, 1, " ms") ?? none(unavailable(b?.client)),
      fault: num(c?.latencyP95Seconds !== null && c?.latencyP95Seconds !== undefined ? c.latencyP95Seconds * 1000 : null, 1, " ms") ?? none(),
    },
    {
      metric: "Server request rate",
      source: "http_requests_total (target pods)",
      baseline: num(groupValue(b?.requests, "request_rate_rps"), 2, " req/s") ?? none(unavailable(b?.requests)),
      fault:
        i?.serverRequests !== null && i?.serverRequests !== undefined ? (
          <>
            {num(i.serverRequests, 0)} <span className="text-faint">requests in {i.windowSeconds}s</span>
          </>
        ) : (
          none()
        ),
    },
    {
      metric: "Server 5xx ratio",
      source: "http_requests_total{status=~5..}",
      baseline: groupValue(b?.requests, "error_ratio") !== null ? formatPercent(groupValue(b?.requests, "error_ratio")) : none(unavailable(b?.requests)),
      fault: serverRatio !== null ? formatPercent(serverRatio) : none(),
    },
  ];

  return (
    <Card>
      <CardHeader
        title="Measurements"
        description={
          b
            ? `Baseline: ${b.window_seconds}s before the fault (${b.status}). During fault: from the fault start to the final evaluation${i?.windowSeconds ? ` (${i.windowSeconds}s)` : ""}.`
            : "No baseline has been captured for this experiment."
        }
      />
      <Table>
        <THead>
          <tr>
            <TH>Metric</TH>
            <TH>Baseline</TH>
            <TH>During fault</TH>
            <TH>Source</TH>
          </tr>
        </THead>
        <TBody>
          {rows.map((r) => (
            <TR key={r.metric}>
              <TD className="text-xs font-medium">{r.metric}</TD>
              <TD className="text-xs">{r.baseline}</TD>
              <TD className="text-xs">{r.fault}</TD>
              <TD className="text-2xs text-faint">{r.source}</TD>
            </TR>
          ))}
        </TBody>
      </Table>
    </Card>
  );
}
