import { Callout } from "@/components/ui/callout";
import type { Experiment } from "@/lib/api/types";
import type { OrchestrationView } from "@/lib/evidence";
import { STATE_META, presentState } from "@/lib/experiment-state";
import { formatDateTime } from "@/lib/format";

const CAUSE: Record<string, string> = {
  platform:
    "AutoResilience could not observe the result reliably (Litmus, Prometheus or the cluster). This says nothing about the target's resilience.",
  application: "The measurements were reliable, but the target did not satisfy the recovery rule in time.",
  conflicting_evidence: "Litmus and the recovery measurements disagree, so no outcome is claimed.",
};

/** One sentence of truth about where the experiment stands. Never implies success on uncertainty. */
export function OutcomeBanner({ experiment: e, orch }: { experiment: Experiment; orch: OrchestrationView }) {
  const result = e.observation?.result;
  switch (e.state) {
    case "COMPLETED":
      return (
        <Callout tone="success" title="Recovered">
          {result?.reason ?? "The recovery rule was satisfied."}
        </Callout>
      );
    case "VALIDATION_FAILED": {
      const failed = [...(e.validation_result?.static_checks ?? []), ...(e.validation_result?.cluster_checks ?? [])]
        .filter((c) => c.status === "FAILED" || c.status === "ERROR")
        .map((c) => c.message);
      return (
        <Callout tone="danger" title="Blocked by safety validation · no fault was injected">
          {failed.length ? failed.join("; ") : "See the safety checks."}
        </Callout>
      );
    }
    case "INJECTION_FAILED":
      return (
        <Callout tone="danger" title="The fault could not be started or confirmed">
          {e.chaos?.failure_reason ?? "No failure reason was recorded."}
          {e.chaos?.engine_name
            ? e.chaos.stopped === false
              ? ` Stopping the ChaosEngine failed: ${e.chaos.stop_error ?? "unknown error"}.`
              : " The ChaosEngine was stopped."
            : ""}
        </Callout>
      );
    case "ABORTED":
      return (
        <Callout tone="neutral" title="Aborted">
          {orch.abort?.reason ? `“${orch.abort.reason}”` : "Aborted."}
          {orch.abort?.at ? ` at ${formatDateTime(orch.abort.at)}.` : ""}
          {orch.abort?.engineStopped
            ? ` ChaosEngine ${orch.abort.engineStopped} was stopped.`
            : orch.abort?.stopError
              ? ` Stopping the ChaosEngine failed: ${orch.abort.stopError}.`
              : orch.abort?.note
                ? ` ${orch.abort.note}.`
                : ""}
          {orch.result?.reason ? ` ${orch.result.reason}` : ""}
        </Callout>
      );
    case "UNKNOWN": {
      // The deciding stage recorded the reason: observation (Litmus/recovery) or orchestrator.
      const r =
        result?.status === "UNKNOWN"
          ? { reasonCode: result.reason_code ?? null, reason: result.reason ?? null, cause: result.cause ?? null }
          : orch.result;
      return (
        <Callout
          tone="warning"
          title={`Outcome undetermined${r?.reasonCode ? ` · ${r.reasonCode}` : ""} · not a success`}
        >
          {r?.reason ? <p>{r.reason}</p> : null}
          {r?.cause && CAUSE[r.cause] ? <p className="mt-1">{CAUSE[r.cause]}</p> : null}
        </Callout>
      );
    }
    default: {
      const meta = presentState(e);
      return (
        <Callout tone={meta.label === "Validated · not started" ? "neutral" : "info"} title={meta.label}>
          {meta.description}.
          {orch.mode === "auto"
            ? " The orchestrator advances this run automatically; this page refreshes while it is active."
            : ""}
        </Callout>
      );
    }
  }
}

export const isActive = (e: Experiment) => !STATE_META[e.state].terminal;
