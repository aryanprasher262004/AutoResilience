import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { RichText } from "@/components/ui/rich-text";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import type { DeploymentPlan, ImportFinding, ImportSpec, PlannedObject } from "@/lib/api/types";
import { TOUR_TARGET } from "@/lib/help-content";
import { GROUP_META, SEVERITY_META, countBySeverity, groupFindings } from "@/lib/imports";

/** The security review: findings grouped by what they are about, blocking first. */
export function FindingsView({ findings, level = 2 }: { findings: ImportFinding[]; level?: 2 | 3 }) {
  const counts = countBySeverity(findings);
  return (
    <Card data-tour={TOUR_TARGET.importFindings}>
      <CardHeader
        level={level}
        title="Security review"
        description="What the engine found in the file, and how each part is handled. Decided by the server, not this page."
        actions={
          <span className="flex flex-wrap gap-1.5">
            {(["blocking", "warning", "info"] as const).map((s) => (
              <Badge key={s} tone={counts[s] ? SEVERITY_META[s].tone : "neutral"}>
                {counts[s]} {SEVERITY_META[s].label.toLowerCase()}
              </Badge>
            ))}
          </span>
        }
      />
      {findings.length ? (
        <ul className="divide-y divide-line">
          {groupFindings(findings).map((group) => (
            <li key={group.subject} className="px-4 py-3">
              <h4 className="font-mono text-xs text-fg">{group.subject}</h4>
              <ul className="mt-2 grid gap-2">
                {group.items.map((f, i) => (
                  <li key={`${f.code}-${f.path}-${i}`} className="grid grid-cols-[minmax(0,1fr)] gap-1 sm:grid-cols-[6.5rem_minmax(0,1fr)] sm:gap-3">
                    <span>
                      <Badge tone={SEVERITY_META[f.severity].tone}>{SEVERITY_META[f.severity].label}</Badge>
                    </span>
                    <div className="min-w-0 text-xs leading-relaxed">
                      <p className="text-fg">{f.message}</p>
                      {f.hint ? (
                        <p className="mt-0.5 text-muted">
                          <RichText text={f.hint} />
                        </p>
                      ) : null}
                      {f.path ? <p className="mt-0.5 font-mono text-2xs break-all text-faint">{f.path}</p> : null}
                    </div>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      ) : (
        <CardBody>
          <p className="text-xs text-muted">Nothing to report: every setting is supported as written.</p>
        </CardBody>
      )}
    </Card>
  );
}

function probeText(w: ImportSpec["workloads"][number]): string {
  const p = w.readiness;
  if (!p) return "None (ready once running)";
  const what =
    p.type === "exec" ? (p.command ?? []).join(" ") : p.type === "http" ? `HTTP GET ${p.path} on ${p.port}` : `${p.type.toUpperCase()} ${p.port}`;
  return `${what}${p.generated ? " (added)" : ""}`;
}

/** The normalized application: what the plan deploys, in the user's terms. */
export function SpecView({ spec, level = 2 }: { spec: ImportSpec; level?: 2 | 3 }) {
  return (
    <Card>
      <CardHeader
        level={level}
        title="Application"
        description="Read from the file through the supported subset. Environment values are never kept: only their names are listed."
      />
      <Table>
        <THead>
          <tr>
            <TH>Workload</TH>
            <TH>Image</TH>
            <TH>Replicas</TH>
            <TH>Ports</TH>
            <TH>Readiness check</TH>
            <TH>Not set</TH>
          </tr>
        </THead>
        <TBody>
          {spec.workloads.map((w) => (
            <TR key={w.name}>
              <TD className="font-medium">
                {w.name}
                <span className="ml-1.5 text-2xs text-faint">{w.kind}</span>
              </TD>
              <TD className="min-w-48 max-w-64 font-mono text-2xs break-all text-muted">{w.image}</TD>
              <TD className="font-mono text-xs">{w.replicas}</TD>
              <TD className="font-mono text-xs text-muted">{(w.ports ?? []).map((p) => p.container_port).join(", ") || "—"}</TD>
              <TD className="min-w-40 max-w-56 font-mono text-2xs break-all text-muted">{probeText(w)}</TD>
              <TD className="text-2xs text-muted">
                {w.env_names?.length ? `${w.env_names.length} variable${w.env_names.length > 1 ? "s" : ""}` : "—"}
              </TD>
            </TR>
          ))}
        </TBody>
      </Table>
      {spec.declared?.length ? (
        <CardBody className="border-t border-line">
          <h4 className="text-2xs font-medium tracking-wide text-faint uppercase">Declared in the file (not verified)</h4>
          <ul className="mt-1.5 grid gap-1 text-xs text-muted">
            {spec.declared.map((d) => (
              <li key={`${d.source}-${d.target}`}>
                <span className="font-mono text-fg">{d.source}</span> {d.type === "depends_on" ? "depends on" : "shares a network with"}{" "}
                <span className="font-mono text-fg">{d.target}</span>: start order only, not evidence that they talk to each other.
              </li>
            ))}
          </ul>
        </CardBody>
      ) : null}
    </Card>
  );
}

const GROUP_ORDER: PlannedObject["group"][] = ["application", "isolation", "chaos", "load-generator"];

/** Every object a deployment creates, what it will do, and what it will never do. */
export function PlanView({
  plan,
  level = 2,
  title = "Deployment plan",
  preview = false,
}: {
  plan: DeploymentPlan;
  level?: 2 | 3;
  title?: string;
  /** Not saved yet: its digest is fixed (with the import's id) on saving. */
  preview?: boolean;
}) {
  return (
    <Card data-tour={TOUR_TARGET.importPlan}>
      <CardHeader
        level={level}
        title={title}
        description={
          <>
            Everything is created in namespace <code className="font-mono text-fg">{plan.namespace}</code> on the execution
            cluster.{" "}
            {preview ? (
              "The digest you approve is fixed when you save."
            ) : (
              <>
                Plan digest <code className="font-mono">{plan.digest.slice(0, 12)}</code>.
              </>
            )}
          </>
        }
      />
      <CardBody className="grid gap-4 md:grid-cols-2">
        <div>
          <h4 className="text-2xs font-medium tracking-wide text-faint uppercase">Deploying will</h4>
          <ul className="mt-1.5 grid list-disc gap-1 pl-4 text-xs text-muted">
            {plan.actions.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </div>
        <div>
          <h4 className="text-2xs font-medium tracking-wide text-faint uppercase">and never</h4>
          <ul className="mt-1.5 grid gap-1 text-xs text-muted">
            {plan.guarantees.map((g) => (
              <li key={g} className="flex gap-1.5">
                <span aria-hidden className="text-success">
                  ✓
                </span>
                {g}
              </li>
            ))}
          </ul>
        </div>
      </CardBody>
      <div className="border-t border-line">
        {GROUP_ORDER.map((group) => {
          const objects = plan.objects.filter((o) => o.group === group);
          if (!objects.length) return null;
          return (
            <details key={group} className="group border-b border-line last:border-b-0" open={group === "application"}>
              <summary className="flex cursor-pointer flex-wrap items-baseline gap-x-2 px-4 py-2 text-xs">
                <span className="font-medium text-fg">
                  {GROUP_META[group].label} ({objects.length})
                </span>
                <span className="text-muted">{GROUP_META[group].description}</span>
              </summary>
              <ul className="grid min-w-0 gap-1.5 px-4 pb-3">
                {objects.map((o) => (
                  <li key={`${o.kind}/${o.name}`} className="grid grid-cols-[minmax(0,1fr)] gap-0.5 text-xs sm:grid-cols-[12rem_minmax(0,1fr)] sm:gap-3">
                    <span className="min-w-0 font-mono break-all text-fg">
                      {o.kind} <span className="text-muted">{o.name}</span>
                    </span>
                    <span className="min-w-0 text-muted [overflow-wrap:anywhere]">{o.purpose}</span>
                  </li>
                ))}
              </ul>
            </details>
          );
        })}
      </div>
    </Card>
  );
}
