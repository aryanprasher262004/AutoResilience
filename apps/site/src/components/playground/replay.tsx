"use client";

import { Badge, type Tone } from "@autoresilience/ui/badge";
import { buttonClasses } from "@autoresilience/ui/button";
import { cn } from "@autoresilience/ui/cn";
import { type ReactNode, useEffect, useId, useMemo, useRef, useState } from "react";

import { buildReplay, relative, utc, type PodAt, type ReplayEvent, type ReplayModel, type Span } from "@/lib/recordings/replay";
import type { RecordedExperiment } from "@/lib/recordings/types";

const SPEEDS = [1, 4, 10] as const;

const SOURCE_TONE: Record<ReplayEvent["source"], Tone> = {
  Engine: "info",
  Prometheus: "neutral",
  Litmus: "fault",
  Kubernetes: "success",
  Client: "warning",
};

/** Interactive replay of one recorded experiment. Plays back recorded time only. */
export function Replay({ recording }: { recording: RecordedExperiment }) {
  const model = useMemo(() => buildReplay(recording), [recording]);
  const [t, setT] = useState(model.start);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<(typeof SPEEDS)[number]>(4);
  const position = useRef(model.start);
  const sliderId = useId();

  const seek = (value: number) => {
    const next = Math.min(Math.max(value, model.start), model.end);
    position.current = next;
    setT(next);
  };

  useEffect(() => {
    if (!playing) return;
    let last = performance.now();
    let frame = requestAnimationFrame(function tick(now) {
      const next = Math.min(position.current + (now - last) * speed, model.end);
      last = now;
      position.current = next;
      setT(next);
      if (next >= model.end) setPlaying(false);
      else frame = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(frame);
  }, [playing, speed, model.end]);

  const togglePlay = () => {
    if (!playing && position.current >= model.end) seek(model.start);
    setPlaying(!playing);
  };
  const restart = () => {
    seek(model.start);
    setPlaying(false);
  };
  const currentIndex = lastIndexAtOrBefore(model.events, t);
  const current = model.events[Math.max(currentIndex, 0)];
  const step = (direction: 1 | -1) => {
    setPlaying(false);
    // Read the live position: several quick presses must each move one event.
    const now = position.current;
    const index = lastIndexAtOrBefore(model.events, now);
    const at = model.events[Math.max(index, 0)];
    // Previous: back to the start of the current event, or to the one before it.
    const target =
      direction === 1 ? model.events.find((e) => e.at > now) : now > at.at ? at : model.events[index - 1];
    seek(target ? target.at : direction === 1 ? model.end : model.start);
  };
  const phase = model.phaseAt(t);
  const pods = model.podsAt(t);

  return (
    <section aria-labelledby="replay-title" className="space-y-4">
      <h2 id="replay-title" className="sr-only">
        Interactive replay
      </h2>

      <nav aria-label="Lifecycle phases" className="overflow-x-auto">
        <ol className="flex min-w-max gap-1 rounded-xl border border-line bg-surface p-1">
          {model.phases.map((p, i) => {
            const active = p.id === phase.id;
            const done = t > p.end || (t >= model.end && i === model.phases.length - 1);
            return (
              <li key={p.id}>
                <button
                  type="button"
                  aria-current={active ? "step" : undefined}
                  onClick={() => {
                    setPlaying(false);
                    seek(p.start);
                  }}
                  className={cn(
                    "flex items-center gap-2 rounded-lg px-3 py-2 text-sm motion-safe:transition-colors",
                    active ? "bg-surface-3 text-fg" : done ? "text-muted hover:text-fg" : "text-faint hover:text-fg",
                  )}
                >
                  <span className="font-mono text-xs text-accent">{String(i + 1).padStart(2, "0")}</span>
                  {p.label}
                  <span className="font-mono text-2xs text-faint">{relative(p.start, model.start)}</span>
                </button>
              </li>
            );
          })}
        </ol>
      </nav>

      <div className="grid gap-4 lg:grid-cols-[1.15fr_1fr]">
        <PodsView pods={pods} model={model} />
        <NowPanel model={model} t={t} current={current} recording={recording} />
      </div>

      <div className="rounded-xl border border-line bg-surface p-4 sm:p-5">
        <Lanes model={model} t={t} onSeek={(v) => { setPlaying(false); seek(v); }} />

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button type="button" className={buttonClasses("primary", "md")} onClick={togglePlay} aria-pressed={playing}>
            {playing ? "Pause" : t >= model.end ? "Replay again" : "Play"}
          </button>
          <button type="button" className={buttonClasses("secondary", "md")} onClick={restart}>
            Restart
          </button>
          <button type="button" className={buttonClasses("ghost", "md")} onClick={() => step(-1)} aria-label="Previous event">
            ← Prev
          </button>
          <button type="button" className={buttonClasses("ghost", "md")} onClick={() => step(1)} aria-label="Next event">
            Next →
          </button>
          <label className="ml-auto flex items-center gap-2 text-xs text-muted">
            Speed
            <select
              value={speed}
              onChange={(e) => setSpeed(Number(e.target.value) as (typeof SPEEDS)[number])}
              className="h-8 rounded-md border border-line-strong bg-surface-2 px-2 text-sm text-fg"
            >
              {SPEEDS.map((s) => (
                <option key={s} value={s}>
                  {s}× recorded time
                </option>
              ))}
            </select>
          </label>
        </div>

        <label htmlFor={sliderId} className="sr-only">
          Replay position
        </label>
        <input
          id={sliderId}
          type="range"
          min={0}
          max={Math.round((model.end - model.start) / 100)}
          step={1}
          value={Math.round((t - model.start) / 100)}
          aria-valuetext={`${relative(t, model.start)}, ${phase.label} phase: ${current.title}`}
          onChange={(e) => {
            setPlaying(false);
            // 0.1 s steps; the last step is the recorded end exactly, not a rounded time.
            const value = Number(e.target.value);
            seek(value >= Math.round((model.end - model.start) / 100) ? model.end : model.start + value * 100);
          }}
          className="mt-4 w-full accent-[var(--color-accent)]"
        />
        <div className="mt-1 flex justify-between font-mono text-2xs text-faint">
          <span>{utc(model.start)}</span>
          <span aria-hidden>{relative(t, model.start)}</span>
          <span>{relative(model.end, model.start)}</span>
        </div>
        <p aria-live="polite" className="sr-only">
          {playing ? "" : `${relative(current.at, model.start)}: ${current.title}`}
        </p>
      </div>

      <EventLog
        events={model.events}
        origin={model.start}
        currentIndex={currentIndex}
        onSelect={(e) => {
          setPlaying(false);
          seek(e.at);
        }}
      />
    </section>
  );
}

function lastIndexAtOrBefore(events: ReplayEvent[], t: number): number {
  let index = -1;
  events.forEach((e, i) => {
    if (e.at <= t) index = i;
  });
  return index;
}

const POD_STATE: Record<PodAt["state"], { label: string; tone: Tone }> = {
  running: { label: "Running", tone: "success" },
  targeted: { label: "Targeted", tone: "fault" },
  deleted: { label: "Deleted", tone: "danger" },
  starting: { label: "Starting", tone: "info" },
  ready: { label: "Ready", tone: "success" },
  absent: { label: "Not created yet", tone: "neutral" },
};

const ROLE: Record<PodAt["role"], string> = {
  target: "Fault target",
  replacement: "Replacement",
  other: "Other replica",
};

function PodsView({ pods, model }: { pods: PodAt[]; model: ReplayModel }) {
  const ready = pods.filter((p) => p.state === "running" || p.state === "targeted" || p.state === "ready").length;
  return (
    <div className="rounded-xl border border-line bg-surface p-4 sm:p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-medium">Pods</h3>
        <p className="font-mono text-xs text-muted">
          {ready}/{model.desiredReplicas ?? "?"} desired running <span className="text-faint">(from pod timestamps)</span>
        </p>
      </div>
      <ul className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
        {pods.map((pod) => {
          const meta = POD_STATE[pod.state];
          return (
            <li
              key={pod.name}
              data-state={pod.state}
              className={cn(
                "rounded-lg border p-3 motion-safe:transition-all motion-safe:duration-300",
                pod.state === "deleted" && "border-dashed border-danger/50 opacity-60",
                pod.state === "absent" && "border-dashed border-line opacity-50",
                pod.state === "targeted" && "border-fault/60 bg-fault/5",
                pod.state === "starting" && "border-info/50 bg-info/5",
                (pod.state === "running" || pod.state === "ready") && "border-line-strong bg-surface-2",
              )}
            >
              <p className="font-mono text-sm">{pod.name}</p>
              <p className="mt-0.5 text-2xs text-faint">{ROLE[pod.role]}</p>
              <div className="mt-2">
                <Badge tone={meta.tone} dot>
                  {meta.label}
                </Badge>
              </div>
            </li>
          );
        })}
      </ul>
      <p className="mt-4 text-xs leading-relaxed text-faint">
        Pod names are per-recording aliases. The exact moment Litmus deleted the target is not
        recorded; it is shown deleted from when Kubernetes created its replacement.
        {model.otherPods === null ? " Other replicas were not individually recorded." : null}
      </p>
    </div>
  );
}

function NowPanel({
  model,
  t,
  current,
  recording,
}: {
  model: ReplayModel;
  t: number;
  current: ReplayEvent;
  recording: RecordedExperiment;
}) {
  const run = recording.experiment;
  const client = run.impact.client;
  const outage = client?.outage;
  const window = outage?.outage_windows[0];
  const recoveredAt = Date.parse(run.recovery.recovered_at);
  const failed = model.failedRequestsAt(t);

  let outageText = "No client outage recorded";
  if (window) {
    const start = Date.parse(window.start);
    const end = window.end ? Date.parse(window.end) : null;
    if (t < start) outageText = "No outage yet";
    else if (end === null || t < end) outageText = `Outage in progress (${((t - start) / 1000).toFixed(1)} s)`;
    else outageText = `Outage ended after ${window.seconds} s`;
  } else if (!outage || outage.pattern === "INSUFFICIENT_DATA") {
    outageText = "Not measured for this run";
  }

  return (
    <div className="rounded-xl border border-line bg-surface p-4 sm:p-5">
      <h3 className="text-sm font-medium">At {relative(t, model.start)}</h3>
      <div className="mt-3 rounded-lg border border-line bg-surface-2 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={SOURCE_TONE[current.source]}>{current.source}</Badge>
          <span className="font-mono text-2xs text-faint">{relative(current.at, model.start)}</span>
        </div>
        <p className="mt-2 text-sm font-medium">{current.title}</p>
        {current.detail ? <p className="mt-1 text-xs leading-relaxed text-muted">{current.detail}</p> : null}
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <Stat label="Client failures so far">
          {client && client.status === "OK" ? (
            <>
              <span className="font-mono tabular-nums">{failed}</span>
              <span className="text-faint"> / {client.failed ?? "?"} in window</span>
            </>
          ) : (
            <span className="text-faint">Not measured</span>
          )}
        </Stat>
        <Stat label="Client outage">{outageText}</Stat>
        <Stat label="Time to recovery">
          {t >= recoveredAt ? (
            <span className="font-mono tabular-nums">{run.recovery.time_to_recovery_seconds} s</span>
          ) : (
            <span className="text-faint">Not yet recovered</span>
          )}
        </Stat>
        <Stat label="Resilience Score">
          {t >= model.end ? (
            <span className="font-mono tabular-nums">
              {run.score.score} <span className="text-faint">({run.score.rating})</span>
            </span>
          ) : (
            <span className="text-faint">Computed at completion</span>
          )}
        </Stat>
      </dl>
    </div>
  );
}

function Stat({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border border-line p-3">
      <dt className="text-2xs text-faint">{label}</dt>
      <dd className="mt-1 text-sm">{children}</dd>
    </div>
  );
}

const LANES: { key: keyof ReplayModel["lanes"]; label: string; className: string }[] = [
  { key: "litmus", label: "Litmus run", className: "bg-fault/25 border-fault/50" },
  { key: "pods", label: "Target pod", className: "bg-fault/40 border-fault" },
  { key: "replacements", label: "Replacement", className: "bg-info/30 border-info" },
  { key: "failures", label: "Client failures", className: "bg-warning/30 border-warning" },
  { key: "outages", label: "Client outage", className: "bg-danger/40 border-danger" },
];

/** Visual timeline of recorded spans. Decorative for screen readers: the slider and the
 * event log carry the same information. Clicking seeks. */
function Lanes({ model, t, onSeek }: { model: ReplayModel; t: number; onSeek: (t: number) => void }) {
  const span = model.end - model.start;
  const pct = (v: number) => `${((v - model.start) / span) * 100}%`;
  const width = (s: Span) => `max(2px, ${((s.end - s.start) / span) * 100}%)`;
  return (
    <div aria-hidden className="relative">
      <div className="grid grid-cols-[6.5rem_1fr] gap-y-1.5 text-2xs sm:grid-cols-[8rem_1fr]">
        <span className="self-center text-faint">Phase</span>
        <div className="relative h-6 overflow-hidden rounded bg-surface-2">
          {model.phases.map((p, i) => (
            <div
              key={p.id}
              title={p.label}
              className={cn(
                "absolute inset-y-0 flex items-center overflow-hidden border-r border-canvas px-1 text-faint",
                i % 2 ? "bg-surface-3" : "bg-surface-2",
              )}
              style={{ left: pct(p.start), width: width(p) }}
            >
              <span className="truncate">{p.label}</span>
            </div>
          ))}
        </div>
        {LANES.map((lane) => (
          <LaneRow key={lane.key} label={lane.label}>
            {model.lanes[lane.key].length === 0 ? (
              <span className="absolute inset-0 flex items-center px-2 text-faint">none recorded</span>
            ) : (
              model.lanes[lane.key].map((s) => (
                <div
                  key={`${s.start}-${s.label}`}
                  title={s.label}
                  className={cn("absolute inset-y-1 rounded-sm border", lane.className)}
                  style={{ left: pct(s.start), width: width(s) }}
                />
              ))
            )}
          </LaneRow>
        ))}
      </div>
      <div
        className="pointer-events-none absolute inset-y-0 left-[6.5rem] right-0 sm:left-[8rem]"
      >
        <div className="absolute inset-y-0 w-px bg-accent" style={{ left: pct(t) }} />
      </div>
      <button
        type="button"
        tabIndex={-1}
        className="absolute inset-y-0 left-[6.5rem] right-0 cursor-col-resize sm:left-[8rem]"
        onClick={(e) => {
          const box = e.currentTarget.getBoundingClientRect();
          onSeek(model.start + ((e.clientX - box.left) / box.width) * span);
        }}
      >
        <span className="sr-only">Seek</span>
      </button>
    </div>
  );
}

function LaneRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <span className="self-center text-faint">{label}</span>
      <div className="relative h-6 rounded bg-surface-2/60">{children}</div>
    </>
  );
}

function EventLog({
  events,
  origin,
  currentIndex,
  onSelect,
}: {
  events: ReplayEvent[];
  origin: number;
  currentIndex: number;
  onSelect: (event: ReplayEvent) => void;
}) {
  return (
    <div className="rounded-xl border border-line bg-surface">
      <h3 className="border-b border-line px-4 py-3 text-sm font-medium sm:px-5">Recorded events</h3>
      <ol className="max-h-[26rem] divide-y divide-line overflow-y-auto">
        {events.map((event, i) => (
          <li key={`${event.at}-${event.title}`}>
            <button
              type="button"
              aria-current={i === currentIndex ? "true" : undefined}
              onClick={() => onSelect(event)}
              className={cn(
                "grid w-full grid-cols-[4.75rem_1fr] items-start gap-3 px-4 py-2.5 text-left sm:grid-cols-[5.5rem_6.5rem_1fr] sm:px-5",
                i === currentIndex ? "bg-surface-3" : "hover:bg-surface-2",
                i > currentIndex && "opacity-55",
              )}
            >
              <span className="font-mono text-xs text-muted tabular-nums">{relative(event.at, origin)}</span>
              <span className="hidden sm:block">
                <Badge tone={SOURCE_TONE[event.source]}>{event.source}</Badge>
              </span>
              <span className="min-w-0">
                <span className="block text-sm">{event.title}</span>
                {event.detail ? <span className="mt-0.5 block text-xs text-faint">{event.detail}</span> : null}
              </span>
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}
