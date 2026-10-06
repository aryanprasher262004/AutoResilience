import type { ReactNode } from "react";

import { Badge, type Tone } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import type { Experiment } from "@/lib/api/types";
import {
  type ImpactView,
  type LitmusView,
  type OrchestrationView,
  type RecoveryView,
  groupValue,
  readImpact,
  readLitmus,
  readRecovery,
  readTargetEvidence,
} from "@/lib/evidence";
import { isTerminal } from "@/lib/experiment-state";
import { formatClock, formatPercent, formatSeconds } from "@/lib/format";

const PATTERN_TONE: Record<string, Tone> = {
  NONE: "success",
  CONTINUOUS: "danger",
  INTERMITTENT: "warning",
  INSUFFICIENT_DATA: "neutral",
};

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[9.5rem_1fr] gap-3 py-1.5 text-xs">
      <dt className="text-faint">{label}</dt>
      <dd className="min-w-0 text-fg">{children}</dd>
    </div>
  );
}

const nodata = <span className="text-faint">No data</span>;
const mono = (v: ReactNode) => <span className="font-mono">{v}</span>;

function Column({ step, title, children }: { step: string; title: string; children: ReactNode }) {
  return (
    <div className="min-w-0 px-4 py-3">
      <p className="text-2xs font-medium tracking-wide text-faint uppercase">{step}</p>
      <h3 className="mt-0.5 text-sm font-semibold">{title}</h3>
      <dl className="mt-2 divide-y divide-line/60">{children}</dl>
    </div>
  );
}

function FaultColumn({ e, litmus }: { e: Experiment; litmus: LitmusView | null }) {
  const c = e.chaos;
  return (
    <Column step="1 · Fault" title={`pod-delete · ${e.pod_delete_mode}`}>
      <Row label="Pods deleted">{c?.target_pods?.length ? mono(c.target_pods.join(", ")) : nodata}</Row>
      <Row label="ChaosEngine created">{c?.created_at ? mono(formatClock(c.created_at)) : nodata}</Row>
      <Row label="Deletion confirmed">{c?.injected_at ? mono(formatClock(c.injected_at)) : nodata}</Row>
      <Row label="Litmus verdict">
        {litmus?.verdict ? (
          <>
            <Badge tone={litmus.verdict === "Pass" ? "success" : litmus.verdict === "Awaited" ? "info" : "danger"}>
              {litmus.verdict}
            </Badge>
            {litmus.failStep ? <span className="ml-2 text-muted">{litmus.failStep}</span> : null}
          </>
        ) : (
          nodata
        )}
      </Row>
      <Row label="Litmus finished">
        {litmus?.finishedAt ? (
          <span title="When AutoResilience observed the run as finished">{mono(formatClock(litmus.finishedAt))}</span>
        ) : litmus?.experimentStatus ? (
          <span className="text-muted">{litmus.experimentStatus}</span>
        ) : (
          nodata
        )}
      </Row>
    </Column>
  );
}

function ImpactColumn({ e, impact }: { e: Experiment; impact: ImpactView | null }) {
  const client = impact?.client;
  const outage = client?.outage;
  const desired = groupValue(e.baseline?.availability, "desired_replicas");
  return (
    <Column step="2 · Impact" title="What clients and Kubernetes saw">
      <Row label="Client outage">
        {outage && outage.status === "OK" ? (
          <>
            <Badge tone={PATTERN_TONE[outage.pattern ?? ""] ?? "neutral"}>{outage.pattern}</Badge>{" "}
            <span className="ml-1 font-mono">{formatSeconds(outage.seconds)}</span>
            {outage.windows.map((w) => (
              <div key={w.start} className="mt-1 font-mono text-2xs text-muted">
                {formatClock(w.start)} → {w.end ? formatClock(w.end) : "ongoing"}
              </div>
            ))}
          </>
        ) : outage ? (
          <span className="text-muted">{outage.reason ?? "Insufficient data"}</span>
        ) : client?.status === "UNAVAILABLE" ? (
          <span className="text-muted">{client.reason ?? "No client measurement for this target"}</span>
        ) : (
          nodata
        )}
      </Row>
      <Row label="Client requests">
        {client?.requests !== null && client?.requests !== undefined ? (
          <>
            {mono(`${client.failed ?? 0} failed / ${client.requests}`)}
            <span className="ml-2 text-muted">{formatPercent(client.failureRatio)}</span>
          </>
        ) : (
          nodata
        )}
      </Row>
      <Row label="Failure types">
        {client?.requests !== null && client?.requests !== undefined
          ? mono(
              `${client.connectionErrors ?? 0} connection · ${client.timeouts ?? 0} timeout · ${client.httpErrors ?? 0} HTTP 5xx`,
            )
          : nodata}
      </Row>
      <Row label="Lowest availability">
        {impact?.minAvailable !== null && impact?.minAvailable !== undefined ? (
          <span title="Minimum of Kubernetes availability samples (scrape interval)">
            {mono(`${impact.minAvailable}${desired !== null ? ` / ${desired}` : ""}`)}
            <span className="ml-2 text-muted">{impact.dipObserved ? "dip sampled" : "no dip sampled"}</span>
          </span>
        ) : (
          nodata
        )}
      </Row>
      <Row label="Container restarts">{impact?.restarts !== null && impact?.restarts !== undefined ? mono(impact.restarts) : nodata}</Row>
    </Column>
  );
}

function RecoveryColumn({ e, recovery }: { e: Experiment; recovery: RecoveryView | null }) {
  const impact = readImpact(e);
  const target = readTargetEvidence(e);
  return (
    <Column
      step="3 · Recovery"
      title={
        recovery?.status === "RECOVERED"
          ? "Recovered"
          : isTerminal(e.state)
            ? recovery
              ? "Did not meet the recovery rule"
              : "Not measured"
            : recovery
              ? "Not recovered yet"
              : "Not measured yet"
      }
    >
      <Row label="Time to recovery">
        {recovery?.timeToRecoverySeconds !== null && recovery?.timeToRecoverySeconds !== undefined ? (
          <span title="Replacement pod created → Ready (Kubernetes timestamps, 1 s resolution)">
            {mono(formatSeconds(recovery.timeToRecoverySeconds))}
          </span>
        ) : (
          nodata
        )}
      </Row>
      <Row label="Replacement pods">
        {impact?.replacementPods.length ? (
          impact.replacementPods.map((p) => (
            <div key={p.pod} className="font-mono text-2xs">
              {p.pod} <span className="text-muted">created {formatClock(p.createdAt)} · Ready {formatClock(p.readyAt)}</span>
            </div>
          ))
        ) : (
          nodata
        )}
      </Row>
      <Row label="Recovery confirmed">
        {recovery?.confirmedAt ? (
          <>
            {mono(formatClock(recovery.confirmedAt))}
            <span className="ml-2 text-muted">after {recovery.stableSamples} stable samples</span>
          </>
        ) : recovery?.message ? (
          <span className="text-muted">{recovery.message}</span>
        ) : (
          nodata
        )}
      </Row>
      <Row label="Error check">
        {recovery?.errorCheck ? (
          recovery.errorCheck.applicable ? (
            <span className={recovery.errorCheck.ok ? "text-fg" : "text-warning"}>{recovery.errorCheck.message}</span>
          ) : (
            <span className="text-muted">Not applicable (no baseline traffic metrics)</span>
          )
        ) : (
          nodata
        )}
      </Row>
      <Row label="Deleted pods gone">
        {target?.stillPresent ? (target.stillPresent.length ? mono(`still present: ${target.stillPresent.join(", ")}`) : "Yes") : target?.error ? <span className="text-warning">{target.error}</span> : nodata}
      </Row>
    </Column>
  );
}

/** fault → impact → recovery, from recorded evidence only. */
export function ImpactRecovery({ experiment: e }: { experiment: Experiment }) {
  const impact = readImpact(e);
  const recovery = readRecovery(e);
  const litmus = readLitmus(e);
  const started = Boolean(e.chaos?.engine_name);
  return (
    <Card>
      <CardHeader
        title="Fault → impact → recovery"
        description={
          !started
            ? "No fault has been started for this experiment, so there is no impact or recovery to show"
            : e.observation
              ? "Recorded by the observation step; times are UTC"
              : isTerminal(e.state)
                ? "The fault started, but the run ended before any observation was recorded; impact and recovery were not measured"
                : "The fault is running; impact and recovery appear once the first observation is recorded"
        }
      />
      {started ? (
        <div className="grid divide-y divide-line lg:grid-cols-3 lg:divide-x lg:divide-y-0">
          <FaultColumn e={e} litmus={litmus} />
          <ImpactColumn e={e} impact={impact} />
          <RecoveryColumn e={e} recovery={recovery} />
        </div>
      ) : null}
    </Card>
  );
}

// --- evidence milestones ---------------------------------------------------------

export type Milestone = { at: string; label: string; detail?: string; tone: Tone };

/** Every recorded timestamp, in order. Nothing is estimated. */
export function milestones(e: Experiment, orch: OrchestrationView): Milestone[] {
  const out: Milestone[] = [];
  const add = (at: string | null | undefined, label: string, tone: Tone, detail?: string) => {
    if (at) out.push({ at, label, tone, detail });
  };
  add(e.created_at, "Experiment created", "neutral");
  add(e.baseline?.captured_at, `Baseline ${e.baseline?.status === "CAPTURED" ? "captured" : "capture failed"}`, e.baseline?.status === "CAPTURED" ? "info" : "warning");
  add(e.chaos?.created_at, "ChaosEngine created", "fault", e.chaos?.engine_name ?? undefined);
  add(e.chaos?.injected_at, "Target pod deletion confirmed", "fault", e.chaos?.target_pods?.join(", "));
  const impact = readImpact(e);
  for (const w of impact?.client?.outage?.windows ?? []) {
    add(w.start, "Client outage began", "danger");
    add(w.end, "Client outage ended", "success", w.seconds !== null ? formatSeconds(w.seconds) : undefined);
  }
  for (const p of impact?.replacementPods ?? []) {
    add(p.createdAt, "Replacement pod created", "info", p.pod);
    add(p.readyAt, "Replacement pod Ready", "success", p.pod);
  }
  const litmus = readLitmus(e);
  add(litmus?.finishedAt, "Litmus run finished (observed)", litmus?.verdict === "Pass" ? "success" : "warning", litmus?.verdict ?? undefined);
  const recovery = readRecovery(e);
  add(recovery?.confirmedAt, "Recovery confirmed", "success", `${recovery?.stableSamples} stable samples`);
  add(orch.abort?.at, "Abort requested", "neutral", orch.abort?.reason ?? undefined);
  add(orch.cleanup?.at, "Chaos resources cleaned up", "neutral", orch.cleanup ? `engine ${orch.cleanup.engine}, result ${orch.cleanup.result}` : undefined);
  return out.sort((a, b) => new Date(a.at).getTime() - new Date(b.at).getTime());
}
