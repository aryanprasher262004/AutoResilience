import type { ExperimentSummary, Score } from "@/lib/api/types";

/** The persisted score, or exactly why there is none. Never a made-up number. */
export function ScoreCell({ score }: { score: Score | ExperimentSummary["score"] }) {
  if (!score) return <span className="text-faint">—</span>;
  if (score.score === null || score.score === undefined) {
    return (
      <span className="text-xs text-faint" title={"explanation" in score ? score.explanation : undefined}>
        Not scored
      </span>
    );
  }
  return (
    <span className="font-mono tabular-nums" title={"explanation" in score ? score.explanation : undefined}>
      {score.score.toFixed(1)}
      <span className="ml-1 text-xs text-faint">{score.version}</span>
    </span>
  );
}
