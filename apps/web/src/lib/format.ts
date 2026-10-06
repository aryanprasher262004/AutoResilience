const dateTime = new Intl.DateTimeFormat("en-GB", {
  year: "numeric",
  month: "short",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
  timeZone: "UTC",
});

/** Absolute UTC timestamp, e.g. "06 Oct 2026, 11:38:57 UTC". */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "—" : `${dateTime.format(date)} UTC`;
}

/** Compact relative time, e.g. "3m ago". `now` is injectable for determinism. */
export function formatRelative(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "—";
  const seconds = Math.round((now - new Date(iso).getTime()) / 1000);
  if (Number.isNaN(seconds)) return "—";
  if (seconds < 60) return `${Math.max(seconds, 0)}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

/** First block of a UUID, for dense tables (full id stays in title/links). */
export function shortId(id: string): string {
  return id.split("-")[0] ?? id;
}

const clock = new Intl.DateTimeFormat("en-GB", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
  timeZone: "UTC",
});

/** UTC time of day with milliseconds when the source has them, e.g. "11:19:47.198". */
export function formatClock(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  const ms = date.getUTCMilliseconds();
  return ms ? `${clock.format(date)}.${String(ms).padStart(3, "0")}` : clock.format(date);
}

/** "8.36 s", "2 m 5 s"; null-safe. */
export function formatSeconds(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 60) return `${Number(seconds.toFixed(seconds < 10 ? 2 : 1))} s`;
  const m = Math.floor(seconds / 60);
  return `${m} m ${Math.round(seconds - m * 60)} s`;
}

/** Seconds between two ISO timestamps, or null. */
export function secondsBetween(from: string | null | undefined, to: string | null | undefined): number | null {
  if (!from || !to) return null;
  const d = (new Date(to).getTime() - new Date(from).getTime()) / 1000;
  return Number.isFinite(d) ? d : null;
}

export function formatPercent(ratio: number | null | undefined, digits = 2): string {
  if (ratio === null || ratio === undefined) return "—";
  return `${(ratio * 100).toFixed(digits)} %`;
}
