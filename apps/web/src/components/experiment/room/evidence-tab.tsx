import { Badge, type Tone } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { DescriptionList } from "@/components/ui/description-list";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import type { Experiment } from "@/lib/api/types";
import { type OrchestrationView, policyName, readLitmus } from "@/lib/evidence";
import { formatDateTime } from "@/lib/format";

import { ChecksTable } from "../checks-table";

const GROUP_TONE: Record<string, Tone> = { OK: "success", UNAVAILABLE: "neutral", ERROR: "danger" };
const GROUPS = [
  ["availability", "Availability"],
  ["restarts", "Restarts"],
  ["requests", "Server requests"],
  ["client", "Client (load generator)"],
] as const;

function SafetySection({ e }: { e: Experiment }) {
  const v = e.validation_result;
  if (!v) {
    return (
      <Card>
        <CardHeader title="Safety validation" description="Not validated yet" />
      </Card>
    );
  }
  const policy = v.policy as Record<string, unknown>;
  return (
    <div className="grid gap-4">
      <Card>
        <CardHeader
          title="Safety validation"
          description="Server-side decision recorded before any fault"
          actions={<Badge tone={v.passed ? "success" : "danger"} dot>{v.passed ? "Passed" : "Blocked"}</Badge>}
        />
        <CardBody>
          <DescriptionList
            items={[
              { label: "Policy", value: policyName(e) ?? "—" },
              { label: "Why this policy", value: v.policy_selection?.rule ?? "—" },
              { label: "Max duration", value: `${policy.max_duration_seconds ?? "—"} s` },
              { label: "Max affected replicas", value: String(policy.max_affected_replicas ?? "—") },
              { label: "Min healthy replicas", value: String(policy.min_healthy_replicas ?? "—") },
              {
                label: "Forbidden namespaces",
                value: Array.isArray(policy.forbidden_namespaces) ? policy.forbidden_namespaces.join(", ") : "—",
              },
            ]}
          />
        </CardBody>
      </Card>
      <ChecksTable title="Static checks" description="Configuration against the policy" checks={v.static_checks} />
      <ChecksTable title="Cluster checks" description="Live Kubernetes state at validation time" checks={v.cluster_checks} />
    </div>
  );
}

function BaselineSection({ e }: { e: Experiment }) {
  const b = e.baseline;
  if (!b) {
    return (
      <Card>
        <CardHeader title="Baseline" description="No baseline has been captured" />
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader
        title="Baseline"
        description={`Captured ${formatDateTime(b.captured_at)} over ${b.window_seconds}s`}
        actions={<Badge tone={b.status === "CAPTURED" ? "success" : "danger"} dot>{b.status}</Badge>}
      />
      <Table>
        <THead>
          <tr>
            <TH>Group</TH>
            <TH>Status</TH>
            <TH>Summary</TH>
            <TH>Values</TH>
          </tr>
        </THead>
        <TBody>
          {GROUPS.map(([key, label]) => {
            const g = b[key];
            return (
              <TR key={key}>
                <TD className="text-xs font-medium">{label}</TD>
                <TD>{g ? <Badge tone={GROUP_TONE[g.status] ?? "neutral"}>{g.status}</Badge> : <Badge>Not recorded</Badge>}</TD>
                <TD className="text-xs text-muted">{g?.message ?? "Not part of this baseline"}</TD>
                <TD className="font-mono text-2xs text-muted">
                  {g && Object.keys(g.values).length
                    ? Object.entries(g.values).map(([k, val]) => (
                        <div key={k}>
                          {k}: {val === null ? "null" : String(val)}
                        </div>
                      ))
                    : "—"}
                </TD>
              </TR>
            );
          })}
        </TBody>
      </Table>
      {b.failure_reasons.length ? (
        <CardBody className="text-xs text-warning">{b.failure_reasons.join("; ")}</CardBody>
      ) : null}
    </Card>
  );
}

function ChaosSection({ e, orch }: { e: Experiment; orch: OrchestrationView }) {
  const c = e.chaos;
  const litmus = readLitmus(e);
  if (!c) {
    return (
      <Card>
        <CardHeader title="Chaos run" description="No fault has been started" />
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader title="Chaos run" description="LitmusChaos pod-delete, as recorded" />
      <CardBody>
        <DescriptionList
          items={[
            { label: "ChaosEngine", value: <span className="font-mono text-xs">{c.engine_name ?? "—"}</span> },
            { label: "Namespace", value: c.namespace ?? "—" },
            { label: "Deletion mode", value: c.pod_delete_mode ?? e.pod_delete_mode },
            { label: "Target pods", value: <span className="font-mono text-xs">{c.target_pods.join(", ") || "—"}</span> },
            { label: "Engine created", value: formatDateTime(c.created_at) },
            { label: "Deletion confirmed", value: formatDateTime(c.injected_at) },
            { label: "Litmus engine / experiment", value: litmus ? `${litmus.engineStatus ?? "—"} / ${litmus.experimentStatus ?? "—"}` : "—" },
            { label: "Litmus verdict", value: litmus?.verdict ?? "—" },
            { label: "Probe success", value: litmus?.probeSuccess ? `${litmus.probeSuccess} %` : "—" },
            { label: "Failure reason", value: c.failure_reason ?? "—" },
            {
              label: "Cleanup",
              value: orch.cleanup
                ? orch.cleanup.done
                  ? `Done ${formatDateTime(orch.cleanup.at)}`
                  : (orch.cleanup.waiting ?? orch.cleanup.error ?? "Pending")
                : "—",
            },
          ]}
        />
      </CardBody>
    </Card>
  );
}

function ObservationSection({ e }: { e: Experiment }) {
  const o = e.observation;
  if (!o) return null;
  return (
    <Card>
      <CardHeader title="Recovery rule" description={`${o.evaluations} evaluations · last ${formatDateTime(o.updated_at)}`} />
      <CardBody className="grid gap-2 text-xs">
        <p className="text-muted">{o.rule}</p>
        <p>
          <span className="text-faint">Result: </span>
          {o.result.status}
          {o.result.reason_code ? ` · ${o.result.reason_code}` : ""}
          {o.result.cause ? ` · cause ${o.result.cause}` : ""}
          {o.result.reason ? ` — ${o.result.reason}` : ""}
        </p>
      </CardBody>
    </Card>
  );
}

export function EvidenceTab({ experiment: e, orch }: { experiment: Experiment; orch: OrchestrationView }) {
  return (
    <div className="grid gap-4">
      <SafetySection e={e} />
      <BaselineSection e={e} />
      <ChaosSection e={e} orch={orch} />
      <ObservationSection e={e} />
      <details className="rounded-lg border border-line bg-surface">
        <summary className="cursor-pointer px-4 py-3 text-xs font-medium text-muted hover:text-fg">
          Raw API response (debug)
        </summary>
        <pre className="max-h-[60vh] overflow-auto border-t border-line px-4 py-3 font-mono text-2xs leading-relaxed text-muted">
          {JSON.stringify(e, null, 2)}
        </pre>
      </details>
    </div>
  );
}
