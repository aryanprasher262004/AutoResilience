"use client";

import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import type { ScorePoint } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";

const MIN_POINTS = 3;
const W = 720;
const H = 220;
const PAD = { top: 14, right: 44, bottom: 26, left: 34 };
const BANDS = [
  { at: 90, label: "Excellent" },
  { at: 75, label: "Good" },
  { at: 50, label: "Fair" },
];

/**
 * Resilience Score of each scored run, oldest → newest (one series, current methodology).
 * x is run order, not time: runs are irregular, and the tooltip/table give exact times.
 */
export function ScoreTrend({ points, version }: { points: ScorePoint[]; version: string }) {
  const [active, setActive] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const enough = points.length >= MIN_POINTS;

  const x = (i: number) =>
    PAD.left + (points.length === 1 ? 0 : (i / (points.length - 1)) * (W - PAD.left - PAD.right));
  const y = (score: number) => PAD.top + (1 - score / 100) * (H - PAD.top - PAD.bottom);
  const path = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.score).toFixed(1)}`).join(" ");

  function nearest(clientX: number, rect: DOMRect) {
    const px = ((clientX - rect.left) / rect.width) * W;
    let best = 0;
    points.forEach((_, i) => {
      if (Math.abs(x(i) - px) < Math.abs(x(best) - px)) best = i;
    });
    setActive(best);
  }

  const point = active !== null ? points[active] : null;
  return (
    <Card>
      <CardHeader
        title="Resilience Score by run"
        description={`Scored runs, oldest to newest · methodology ${version} only`}
        actions={
          enough ? (
            <Button size="sm" variant="ghost" onClick={() => setTable((t) => !t)} aria-pressed={table}>
              {table ? "Chart" : "Table"}
            </Button>
          ) : null
        }
      />
      {!enough ? (
        <CardBody>
          <p className="text-xs text-muted">
            {points.length
              ? `${points.length} scored run${points.length === 1 ? "" : "s"} so far. The trend appears from ${MIN_POINTS} scored runs, so a single result is not read as a trend.`
              : `No ${version}-scored runs yet. Scores appear after experiments complete.`}
          </p>
        </CardBody>
      ) : table ? (
        <Table>
          <THead>
            <tr>
              <TH>#</TH>
              <TH>Experiment</TH>
              <TH>Target</TH>
              <TH className="text-right">Score</TH>
              <TH>Rating</TH>
              <TH>Scored</TH>
            </tr>
          </THead>
          <TBody>
            {points.map((p, i) => (
              <TR key={p.experiment_id}>
                <TD className="font-mono text-xs text-faint">{i + 1}</TD>
                <TD className="text-xs">
                  <Link href={`/experiments/${p.experiment_id}`} className="hover:text-accent">{p.name}</Link>
                </TD>
                <TD className="font-mono text-xs">{p.namespace}/{p.workload}</TD>
                <TD className="text-right font-mono text-xs tabular-nums">{p.score.toFixed(1)}</TD>
                <TD className="text-xs">{p.rating ?? "—"}</TD>
                <TD className="text-xs text-muted">{formatDateTime(p.at)}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      ) : (
        <CardBody className="relative">
          <svg
            viewBox={`0 0 ${W} ${H}`}
            className="w-full"
            role="img"
            aria-label={`Resilience Score of ${points.length} scored runs, from ${points[0].score.toFixed(1)} to ${points.at(-1)!.score.toFixed(1)}`}
            onPointerMove={(ev) => nearest(ev.clientX, ev.currentTarget.getBoundingClientRect())}
            onPointerLeave={() => setActive(null)}
          >
            {/* Recessive 1px solid grid at the rating thresholds + axis bounds. */}
            {[0, 100].map((v) => (
              <g key={v}>
                <line x1={PAD.left} x2={W - PAD.right} y1={y(v)} y2={y(v)} className="stroke-line" strokeWidth={1} />
                <text x={PAD.left - 6} y={y(v) + 3} textAnchor="end" className="fill-faint text-[10px]">{v}</text>
              </g>
            ))}
            {BANDS.map((b) => (
              <g key={b.at}>
                <line x1={PAD.left} x2={W - PAD.right} y1={y(b.at)} y2={y(b.at)} className="stroke-line" strokeWidth={1} />
                <text x={PAD.left - 6} y={y(b.at) + 3} textAnchor="end" className="fill-faint text-[10px]">{b.at}</text>
                <text x={W - PAD.right + 4} y={y(b.at) + 3} className="fill-faint text-[9px]">{b.label}</text>
              </g>
            ))}
            <text x={PAD.left} y={H - 6} className="fill-faint text-[10px]">oldest</text>
            <text x={W - PAD.right} y={H - 6} textAnchor="end" className="fill-faint text-[10px]">newest</text>

            {point && active !== null ? (
              <line x1={x(active)} x2={x(active)} y1={PAD.top} y2={H - PAD.bottom} className="stroke-line-strong" strokeWidth={1} />
            ) : null}
            <path d={path} fill="none" className="stroke-accent" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
            {points.map((p, i) => (
              <g
                key={p.experiment_id}
                tabIndex={0}
                role="img"
                aria-label={`${p.name}: ${p.score.toFixed(1)} (${p.rating ?? "no rating"}), ${formatDateTime(p.at)}`}
                onFocus={() => setActive(i)}
                onBlur={() => setActive(null)}
                className="outline-none"
              >
                {/* 24px transparent hit target around an 8px dot with a 2px surface ring. */}
                <circle cx={x(i)} cy={y(p.score)} r={12} fill="transparent" />
                <circle cx={x(i)} cy={y(p.score)} r={active === i ? 5 : 4} className="fill-accent stroke-surface" strokeWidth={2} />
              </g>
            ))}
            {/* Direct label on the latest run only. */}
            <text x={x(points.length - 1)} y={y(points.at(-1)!.score) - 10} textAnchor="end" className="fill-fg text-[11px] font-medium">
              {points.at(-1)!.score.toFixed(1)}
            </text>
          </svg>
          {point && active !== null ? (
            <div
              role="status"
              className="pointer-events-none absolute top-2 rounded-md border border-line-strong bg-surface-2 px-2.5 py-1.5 text-xs shadow-lg"
              style={{ left: `clamp(0.5rem, calc(${(x(active) / W) * 100}% - 4rem), calc(100% - 12rem))` }}
            >
              <p className="font-mono text-sm font-semibold text-fg">
                {point.score.toFixed(1)} <span className="text-xs font-normal text-muted">{point.rating}</span>
              </p>
              <p className="text-muted">{point.name}</p>
              <p className="font-mono text-2xs text-faint">{point.namespace}/{point.workload} · {formatDateTime(point.at)}</p>
            </div>
          ) : null}
        </CardBody>
      )}
    </Card>
  );
}
