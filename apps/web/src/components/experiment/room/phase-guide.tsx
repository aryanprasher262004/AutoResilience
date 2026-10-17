import type { Experiment } from "@/lib/api/types";
import { PHASE_GUIDE } from "@/lib/guidance";
import { STATE_META, presentState } from "@/lib/experiment-state";

/** Plain-language context for the current phase of an active run (explanation only). */
export function PhaseGuide({ experiment: e }: { experiment: Experiment }) {
  const guide = PHASE_GUIDE[e.state];
  if (!guide || STATE_META[e.state].terminal) return null;
  const waiting = presentState(e).label === "Validated · not started";
  return (
    <section aria-labelledby="phase-guide-title" className="rounded-lg border border-info/25 bg-info/5 px-4 py-3">
      <h2 id="phase-guide-title" className="text-xs font-medium tracking-wide text-info uppercase">
        What&apos;s happening now · {STATE_META[e.state].label}
      </h2>
      {waiting ? (
        <p className="mt-1.5 text-sm text-fg">
          Validated manually and not started: nothing runs until it is started with Run (automatic orchestration).
        </p>
      ) : (
        <dl className="mt-2 grid gap-x-6 gap-y-2 text-sm md:grid-cols-3">
          <div>
            <dt className="text-2xs text-faint">The engine</dt>
            <dd className="mt-0.5 text-fg">{guide.doing}</dd>
          </div>
          <div>
            <dt className="text-2xs text-faint">Evidence recorded</dt>
            <dd className="mt-0.5 text-muted">{guide.evidence}</dd>
          </div>
          <div>
            <dt className="text-2xs text-faint">What ends this phase</dt>
            <dd className="mt-0.5 text-muted">{guide.next}</dd>
          </div>
        </dl>
      )}
    </section>
  );
}
