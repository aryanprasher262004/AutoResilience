import type { ReactNode } from "react";

import type { EdgeType, NodeHealth, NodeKind } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { TOUR_TARGET } from "@/lib/help-content";
import { EDGE_META, EDGE_TYPES, KIND_META, KINDS, NODE_HEALTH_META, TONE_DOT } from "@/lib/topology";

function EdgeSwatch({ type, stroke }: { type?: EdgeType; stroke?: string }) {
  const meta = type ? EDGE_META[type] : null;
  return (
    <svg aria-hidden width="36" height="10" viewBox="0 0 36 10" className="shrink-0">
      <line x1="1" y1="5" x2="29" y2="5" stroke={stroke ?? meta?.stroke} strokeWidth="1.5" strokeDasharray={meta?.dash} />
      <path d="M29 1.5 L35 5 L29 8.5 Z" fill={stroke ?? meta?.stroke} />
    </svg>
  );
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <h3 className="mb-1.5 text-2xs font-medium tracking-wide text-faint uppercase">{title}</h3>
      <ul className="grid gap-1.5 text-xs">{children}</ul>
    </div>
  );
}

function Item({ mark, label, children }: { mark: ReactNode; label: ReactNode; children: ReactNode }) {
  return (
    <li className="grid grid-cols-[2.5rem_1fr] items-start gap-2">
      <span className="flex h-4 items-center">{mark}</span>
      <span className="min-w-0">
        <span className="text-fg">{label}</span> <span className="text-muted">{children}</span>
      </span>
    </li>
  );
}

/**
 * What the topology's shapes, lines, colours and toggles mean. Collapsed by default; the
 * line styles and colours come from the same metadata the graph draws with.
 */
export function TopologyLegend({ kinds }: { kinds: NodeKind[] }) {
  return (
    <details data-tour={TOUR_TARGET.topologyLegend} className="group border-b border-line">
      <summary className="flex cursor-pointer flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2 text-xs">
        <span className="font-medium text-fg">
          Legend <span aria-hidden className="inline-block text-faint group-open:rotate-180 motion-safe:transition-transform">▾</span>
        </span>
        <span className="text-muted">Lines are relationships Kubernetes records, not measured traffic.</span>
      </summary>
      <div className="grid gap-5 border-t border-line px-4 py-3 md:grid-cols-2 xl:grid-cols-4">
        <Group title="Resource kinds">
          {KINDS.filter((k) => kinds.includes(k)).map((kind) => (
            <Item key={kind} mark={<span className="h-3 w-6 rounded-sm border border-line-strong bg-surface-2" />} label={KIND_META[kind].label}>
              {KIND_META[kind].description}
            </Item>
          ))}
        </Group>
        <Group title="Health (dot colour)">
          {(Object.keys(NODE_HEALTH_META) as NodeHealth[]).map((h) => (
            <Item key={h} mark={<span className={cn("size-2 rounded-full", TONE_DOT[NODE_HEALTH_META[h].tone])} />} label={NODE_HEALTH_META[h].label}>
              {NODE_HEALTH_META[h].description}
            </Item>
          ))}
        </Group>
        <Group title="Relationships (lines)">
          {EDGE_TYPES.map((type) => (
            <Item key={type} mark={<EdgeSwatch type={type} />} label={EDGE_META[type].label}>
              {EDGE_META[type].description}. {EDGE_META[type].verified}
            </Item>
          ))}
          <Item mark={<EdgeSwatch stroke="var(--color-warning)" />} label="amber">
            An endpoint that is not ready.
          </Item>
        </Group>
        <Group title="Marks and toggles">
          <Item mark={<span className="text-2xs text-info">imported</span>} label="Imported">
            Created by an import from its reviewed plan. Relationships its file declared (depends_on) are listed, never drawn.
          </Item>
          <Item mark={<span className="text-2xs text-accent">target</span>} label="Experiment target">
            A Deployment or StatefulSet on the execution cluster. Safety validation still decides every run.
          </Item>
          <Item mark={<span className="h-3 w-6 rounded-sm border border-accent ring-2 ring-accent/40" />} label="Selected">
            It, its direct relationships and its owner chain stay bright; everything else is dimmed.
          </Item>
          <Item mark={<span className="h-3 w-6 rounded-sm border border-line-strong bg-surface-2 opacity-30" />} label="Dimmed">
            Not matching the search, or not related to the selection. Still part of the snapshot.
          </Item>
          <Item mark={<span className="h-3 w-6 rounded-sm border border-dashed border-line-strong" />} label="Group">
            A namespace, or the cluster Nodes the Pods run on.
          </Item>
          <Item mark={<span className="font-mono text-2xs text-warning">?</span>} label="Not verified">
            Anything the engine could not read or link is listed below the graph, never drawn as a guess.
          </Item>
          <Item mark={<span className="h-3 w-6 rounded-sm border border-accent/50 bg-accent/10" />} label="Toggles">
            Pressed toggles are shown. Hiding a kind or relationship only changes this view.
          </Item>
        </Group>
      </div>
    </details>
  );
}
