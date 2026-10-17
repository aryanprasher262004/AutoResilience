/** Mark: a replica set with one pod replaced (the thing AutoResilience measures). */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className={className} fill="none">
      <rect x="2.5" y="2.5" width="19" height="19" rx="5" className="stroke-line-strong" />
      <circle cx="8" cy="9" r="2.2" className="fill-fg" />
      <circle cx="16" cy="9" r="2.2" className="fill-fg" />
      <circle cx="8" cy="15.5" r="2.2" className="fill-fg" />
      <circle cx="16" cy="15.5" r="2.2" className="fill-accent" />
    </svg>
  );
}
