import { cn } from "@autoresilience/ui/cn";

import { PHASES } from "@/lib/site";

/**
 * The sample `shop` app under one pod-delete: loadgen → frontend ×3 → checkout ×2 →
 * cart-redis. Static SVG; CSS (globals.css, .topo-*) plays one deletion and recovery on a
 * loop, and reduced motion shows the steady state. An illustration, never recorded data;
 * the interactive version is P3.
 */
export function Topology({ className }: { className?: string }) {
  return (
    <figure className={cn("relative", className)}>
      {/* Readable at phone width: keeps a minimum size and scrolls horizontally instead. */}
      <div
        className="overflow-x-auto rounded-md"
        tabIndex={0}
        role="region"
        aria-label="Topology illustration, scrolls horizontally on small screens"
      >
        <svg
          viewBox="0 0 800 390"
          role="img"
          aria-labelledby="topology-title topology-desc"
          className="h-auto w-full min-w-[620px]"
        >
          <title id="topology-title">Illustration of the sample shop application under a pod-delete</title>
          <desc id="topology-desc">
            A load generator sends requests to three frontend pods, which call two checkout pods, which use
            a cart-redis StatefulSet. LitmusChaos deletes one checkout pod; requests to it fail until a
            replacement pod becomes ready, after which traffic returns to steady state and the run is scored.
          </desc>

          {/* Request paths */}
          <g fill="none" strokeWidth="1.5" className="stroke-signal">
            {[122, 192, 262].map((y) => (
              <path key={y} d={`M134 190 C 170 190, 180 ${y}, 215 ${y}`} opacity="0.7" />
            ))}
            <path d="M340 190 C 380 190, 390 157, 425 157" opacity="0.7" />
            <path d="M340 190 C 380 190, 390 227, 425 227" className="topo-edge-degraded" opacity="0.85" />
            <path d="M525 157 C 570 157, 575 190, 610 190" opacity="0.7" />
            <path d="M525 227 C 570 227, 575 190, 610 190" opacity="0.7" />
          </g>

          <Boundary x={24} y={160} w={110} h={60} label="client" />
          <Pod x={36} y={172} w={86} label="loadgen" />

          <Boundary x={190} y={62} w={150} h={256} label="frontend · Deployment ×3" />
          {["a", "b", "c"].map((id, i) => (
            <Pod key={id} x={215} y={100 + i * 70} label={`frontend-${id}`} />
          ))}

          <Boundary x={400} y={97} w={150} h={186} label="checkout · Deployment ×2" />
          <Pod x={425} y={135} label="checkout-a" />
          <g className="topo-deleted">
            <Pod x={425} y={205} label="checkout-b" />
          </g>
          <g className="topo-replacement" opacity="0">
            <Pod x={425} y={205} label="checkout-c" accent />
          </g>
          <g className="topo-fault" opacity="0">
            <rect x="419" y="199" width="112" height="56" rx="10" fill="none" strokeWidth="1.5" strokeDasharray="4 4" className="stroke-fault" />
            <text x="475" y="276" textAnchor="middle" className="fill-fault font-mono text-[11px]">
              pod-delete · LitmusChaos
            </text>
          </g>

          <Boundary x={610} y={150} w={126} h={80} label="cart-redis · StatefulSet" />
          <Pod x={619} y={168} w={108} label="cart-redis-0" />

          <g className="topo-score" opacity="0">
            <rect x="586" y="292" width="150" height="30" rx="15" className="fill-success/10 stroke-success/40" />
            <text x="661" y="311" textAnchor="middle" className="fill-success font-mono text-[11px]">
              recovered · scored
            </text>
          </g>

          {/* Lifecycle phases, highlighted in turn */}
          <line x1="24" x2="776" y1="350" y2="350" className="stroke-line" />
          {PHASES.map((phase, i) => (
            <text
              key={phase.id}
              x={24 + i * 128}
              y="374"
              className="topo-phase fill-faint font-mono text-[11px] tracking-wider uppercase"
              style={{ ["--phase" as string]: i }}
            >
              {String(i + 1).padStart(2, "0")} {phase.name}
            </text>
          ))}
        </svg>
      </div>
      <figcaption className="mt-3 font-mono text-xs text-faint">
        Illustration of the sample shop app under one pod-delete. Not recorded data.
      </figcaption>
    </figure>
  );
}

function Boundary({ x, y, w, h, label }: { x: number; y: number; w: number; h: number; label: string }) {
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx="12" className="fill-surface/60 stroke-line-strong" strokeDasharray="3 4" />
      <text x={x + 10} y={y - 8} className="fill-muted font-mono text-[11px]">
        {label}
      </text>
    </g>
  );
}

function Pod({ x, y, w = 100, label, accent = false }: { x: number; y: number; w?: number; label: string; accent?: boolean }) {
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={w}
        height={44}
        rx="8"
        className={accent ? "fill-accent/10 stroke-accent" : "fill-surface-3 stroke-line-strong"}
      />
      <circle cx={x + 14} cy={y + 22} r="3.5" className={accent ? "fill-accent" : "fill-success"} />
      <text x={x + 26} y={y + 26} className="fill-fg font-mono text-[11px]">
        {label}
      </text>
    </g>
  );
}
