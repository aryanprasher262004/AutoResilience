import type { Score } from "@/lib/api/types";

/** The persisted score, or exactly why there is none. Never a made-up number. */
export function ScoreCell({ score }: { score: Score | null }) {
  if (!score) return <span className="text-faint">—</span>;
  if (score.score === null || score.score === undefined) {
    return (
      <span className="text-xs text-faint" title={score.explanation}>
        Not scored
      </span>
    );
  }
  return (
    <span className="font-mono tabular-nums" title={score.explanation}>
      {score.score.toFixed(1)}
      <span className="ml-1 text-xs text-faint">{score.version}</span>
    </span>
  );
}
