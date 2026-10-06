import type { ReactNode } from "react";

/** Compact label/value grid for detail views. */
export function DescriptionList({ items }: { items: Array<{ label: string; value: ReactNode }> }) {
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2 xl:grid-cols-3">
      {items.map((item) => (
        <div key={item.label} className="min-w-0">
          <dt className="text-2xs font-medium tracking-wide text-faint uppercase">{item.label}</dt>
          <dd className="mt-0.5 truncate text-sm text-fg">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}
