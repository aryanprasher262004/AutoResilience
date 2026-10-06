import { Badge, type Tone } from "@/components/ui/badge";
import { Callout } from "@/components/ui/callout";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import type { Experiment, Score } from "@/lib/api/types";

/** Why a finished experiment has no score record (scoring only runs for COMPLETED/UNKNOWN). */
const NO_SCORE: Partial<Record<Experiment["state"], string>> = {
  ABORTED: "Aborted runs are not scored: the experiment was stopped before an outcome was measured.",
  VALIDATION_FAILED: "Not scored: the experiment was blocked by safety validation and no fault was injected.",
  INJECTION_FAILED: "Not scored: the fault could not be started or confirmed.",
  UNKNOWN: "No score was recorded for this experiment.",
};

const RATING_TONE: Record<string, Tone> = { Excellent: "success", Good: "success", Fair: "warning", Poor: "danger" };
const LABELS: Record<string, string> = {
  recovery_time: "Recovery time",
  client_outage: "Client outage",
  request_failures: "Request failures",
  availability: "Availability",
  error_ratio: "Error ratio",
  restarts: "Restarts",
  litmus_verdict: "Litmus verdict",
};

function sourceOf(raw: Record<string, unknown>): string | null {
  const source = raw.source;
  return typeof source === "string" ? source.replace("_", " ") : null;
}

function Breakdown({ score }: { score: Score }) {
  return (
    <Table>
      <THead>
        <tr>
          <TH>Component</TH>
          <TH className="w-40">Normalized</TH>
          <TH className="text-right">Weight</TH>
          <TH className="text-right">Points</TH>
          <TH>Why</TH>
        </tr>
      </THead>
      <TBody>
        {score.components.map((c) => {
          const applicable = c.status === "SCORED" && c.normalized !== null;
          const lost = applicable ? c.effective_weight - c.contribution : 0;
          const source = sourceOf(c.raw);
          return (
            <TR key={c.name} className={applicable ? undefined : "opacity-70"}>
              <TD className="text-xs">
                <span className="font-medium">{LABELS[c.name] ?? c.name}</span>
                {source ? <div className="text-2xs text-faint">source: {source}</div> : null}
              </TD>
              <TD>
                {applicable ? (
                  <div className="flex items-center gap-2">
                    <span
                      aria-hidden
                      className="h-1.5 w-20 overflow-hidden rounded-full bg-surface-3"
                    >
                      <span
                        className={`block h-full ${c.normalized! >= 0.9 ? "bg-success" : c.normalized! >= 0.5 ? "bg-warning" : "bg-danger"}`}
                        style={{ width: `${Math.round(c.normalized! * 100)}%` }}
                      />
                    </span>
                    <span className="font-mono text-xs tabular-nums">{c.normalized!.toFixed(2)}</span>
                  </div>
                ) : (
                  <Badge>Not applicable</Badge>
                )}
              </TD>
              <TD className="text-right font-mono text-xs tabular-nums" title={`declared weight ${c.weight}`}>
                {applicable ? c.effective_weight.toFixed(1) : "—"}
              </TD>
              <TD className="text-right font-mono text-xs tabular-nums">
                {applicable ? (
                  <>
                    {c.contribution.toFixed(1)}
                    {lost >= 0.05 ? <div className="text-2xs text-danger">−{lost.toFixed(1)}</div> : null}
                  </>
                ) : (
                  "—"
                )}
              </TD>
              <TD className="text-xs text-muted">{c.reason}</TD>
            </TR>
          );
        })}
      </TBody>
    </Table>
  );
}

/** Headline + where the points went (details per component are in the table below). */
function WhyThisScore({ score }: { score: Score }) {
  const lost = score.components
    .filter((c) => c.status === "SCORED" && c.normalized !== null)
    .map((c) => ({ name: LABELS[c.name] ?? c.name, points: c.effective_weight - c.contribution }))
    .filter((c) => c.points >= 0.05)
    .sort((a, b) => b.points - a.points);
  const excluded = score.components.filter((c) => c.status !== "SCORED").map((c) => LABELS[c.name] ?? c.name);
  return (
    <div className="text-xs leading-relaxed">
      <h3 className="font-semibold text-fg">Why this score?</h3>
      {lost.length ? (
        <p className="mt-1 text-muted">
          Lost {lost.reduce((sum, c) => sum + c.points, 0).toFixed(1)} points:{" "}
          {lost.map((c, i) => (
            <span key={c.name}>
              {i ? " · " : ""}
              <span className="text-fg">{c.name}</span> <span className="font-mono text-danger">−{c.points.toFixed(1)}</span>
            </span>
          ))}
          . Each reason is listed below.
        </p>
      ) : (
        <p className="mt-1 text-muted">Full marks on every applicable component.</p>
      )}
      {excluded.length ? (
        <p className="mt-1 text-faint">
          Not applicable for this target (weights re-normalized): {excluded.join(", ")}.
        </p>
      ) : null}
    </div>
  );
}

/** The stored Resilience Score, or exactly why there is none. */
export function ScorePanel({ experiment: e }: { experiment: Experiment }) {
  const score = e.score;
  if (!score) {
    return (
      <Card>
        <CardHeader title="Resilience Score" />
        <CardBody>
          <p className="text-xs text-muted">{NO_SCORE[e.state] ?? "Scored automatically when the experiment finishes."}</p>
        </CardBody>
      </Card>
    );
  }
  if (score.score === null || score.score === undefined) {
    return (
      <Card>
        <CardHeader title="Resilience Score" description={`Methodology ${score.version}`} />
        <CardBody>
          <Callout tone="neutral" title="Not scored">
            {score.explanation}
          </Callout>
        </CardBody>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader
        title="Resilience Score"
        description={`Methodology ${score.version} · computed from this run's recorded evidence`}
      />
      <CardBody className="grid gap-4">
        <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
          <p className="font-mono text-4xl font-semibold tabular-nums">
            {score.score.toFixed(1)}
            <span className="ml-1 text-base text-faint">/ 100</span>
          </p>
          <div className="flex items-center gap-2 pb-1.5">
            {score.rating ? <Badge tone={RATING_TONE[score.rating] ?? "neutral"}>{score.rating}</Badge> : null}
            {score.status === "SCORED_NOT_RECOVERED" ? <Badge tone="danger">Did not recover</Badge> : null}
          </div>
        </div>
        {score.cap_applied ? (
          <Callout tone="warning" title="Capped">
            The target did not recover, so the score is capped at {score.cap_applied.cap} (uncapped:{" "}
            {score.cap_applied.uncapped_score}).
          </Callout>
        ) : null}
        <WhyThisScore score={score} />
      </CardBody>
      <Breakdown score={score} />
    </Card>
  );
}
