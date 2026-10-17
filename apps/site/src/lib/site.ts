export const GITHUB_URL = "https://github.com/aryanprasher262004/AutoResilience";

/** A file in the repository, opened on GitHub (the docs site is planned). */
export function repoFile(path: string): string {
  return `${GITHUB_URL}/blob/main/${path}`;
}

export function commitUrl(sha: string): string {
  return `${GITHUB_URL}/commit/${sha}`;
}

export const NAV = [
  { href: "/product", label: "Product" },
  { href: "/how-it-works", label: "How It Works" },
  { href: "/playground", label: "Playground" },
  { href: "/docs", label: "Docs" },
  { href: "/download", label: "Download" },
  { href: "/about", label: "About" },
] as const;

/** Lifecycle phases as the engine runs them (apps/api, docs/orchestration.md). */
export const PHASES = [
  {
    id: "validate",
    name: "Validate",
    summary: "Code-defined safety policy and the live workload are checked before anything runs.",
  },
  {
    id: "baseline",
    name: "Baseline",
    summary: "Five minutes of Prometheus history: availability, restarts, request and client errors.",
  },
  {
    id: "inject",
    name: "Inject",
    summary: "LitmusChaos deletes exactly the selected pods, through an engine AutoResilience owns.",
  },
  {
    id: "observe",
    name: "Observe",
    summary: "Pod timestamps, sampled availability, server 5xx and client-side failures and outage.",
  },
  {
    id: "recover",
    name: "Recover",
    summary: "An explicit recovery rule decides COMPLETED, or UNKNOWN with a reason and a cause.",
  },
  {
    id: "score",
    name: "Score",
    summary: "An explainable 0–100 Resilience Score with its methodology version and breakdown.",
  },
] as const;

/** Resilience Score v3 weights (WeightsV3 in apps/api; docs/scoring/resilience-score-v3.md). */
export const SCORE_V3 = [
  { name: "Recovery time", weight: 35 },
  { name: "Request failures", weight: 30 },
  { name: "Client outage", weight: 15 },
  { name: "Restarts", weight: 10 },
  { name: "Litmus verdict", weight: 10 },
] as const;
