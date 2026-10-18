/**
 * Page help and guided tours: one content source for the tour host, the Help panel, the
 * Help page and the inline explanations. Explanatory text only; it never decides
 * anything (limits, verdicts and permissions come from the API and the engine).
 */
import { isKnownRoute } from "./routes";

/**
 * Controls a tour may highlight, as `data-tour` attribute values. Components mark the
 * real element with `data-tour={TOUR_TARGET.x}`, so a renamed target fails the typecheck.
 */
export const TOUR_TARGET = {
  navNewExperiment: "nav-new-experiment",
  navApplications: "nav-applications",
  topBarHelp: "top-bar-help",
  overviewOutcomes: "overview-outcomes",
  overviewScore: "overview-score",
  experimentsNew: "experiments-new",
  experimentsFilters: "experiments-filters",
  experimentsList: "experiments-list",
  applicationsOnboard: "applications-onboard",
  applicationsAbout: "applications-about",
  applicationsList: "applications-list",
  topologyCluster: "topology-cluster",
  topologyGraph: "topology-graph",
  topologyKinds: "topology-kinds",
  topologyEdges: "topology-edges",
  topologyLegend: "topology-legend",
  topologyView: "topology-view",
  topologyInspector: "topology-inspector",
  topologyUnknowns: "topology-unknowns",
  settingsSections: "settings-sections",
  settingsEnvironment: "settings-environment",
  settingsAccess: "settings-access",
  settingsData: "settings-data",
  settingsManager: "settings-manager",
  settingsTours: "settings-tours",
} as const;
export type TourTarget = (typeof TOUR_TARGET)[keyof typeof TOUR_TARGET];

/**
 * How a step may move on by itself. Only view-state controls (filters, legend, view
 * switch, graph selection) are ever `advance` targets: never a control that creates,
 * runs, stops or approves anything.
 */
export type Advance = "click" | "toggle";

export type TourStep = {
  /** Highlighted control; omitted for an introductory step shown in the middle. */
  target?: TourTarget;
  title: string;
  body: string;
  /** Shown when the control is not on screen (loading, no data, collapsed on phones). */
  missing?: string;
  /** The highlighted control stays usable and using it moves the tour on. */
  advance?: Advance;
  /** What to try, shown with `advance`. */
  tryIt?: string;
};

export type Topic = { title: string; body: string };
export type DocLink = { label: string; path: string };

export type PageHelp = {
  title: string;
  summary: string;
  /** Where the page is, for links; null for pages that need an id (an application). */
  href: string | null;
  topics: Topic[];
  docs: DocLink[];
  tour?: TourStep[];
};

export type PageId =
  | "overview"
  | "experiments"
  | "new-experiment"
  | "experiment"
  | "applications"
  | "onboard"
  | "topology"
  | "services"
  | "service"
  | "reports"
  | "report"
  | "settings"
  | "learn";

const ON_PHONES = "On a phone it is in the menu (top left).";

/** What onboarding means, shared by the Applications page, the onboarding flow and Help. */
export const ONBOARDING_FACTS: Topic[] = [
  {
    title: "What onboarding is",
    body: "A named, read-only view of namespaces in a cluster the engine may already read. Saving it stores a database record; nothing is installed or changed in the cluster.",
  },
  {
    title: "Supported clusters",
    body: "The execution cluster (the engine's KUBE_CONTEXT) and read-only discovery clusters granted from a terminal with `ar cluster import`. The browser cannot add a cluster.",
  },
  {
    title: "Namespaces",
    body: "Pick the namespaces your application runs in. System namespaces are never offered; on a discovery cluster only the namespaces granted at import are.",
  },
  {
    title: "Permissions",
    body: "The engine only lists and reads: Deployments, ReplicaSets, StatefulSets, Pods, Services, EndpointSlices, Events, and Nodes when granted. It cannot read Secrets or ConfigMaps. What it may not read is reported as not verified.",
  },
  {
    title: "Experiment eligibility",
    body: "Deployments and StatefulSets on the execution cluster can be chosen as experiment targets. The server's safety validation still decides every run; discovery clusters never get chaos.",
  },
];

export const PAGE_HELP: Record<PageId, PageHelp> = {
  overview: {
    title: "Overview",
    summary: "Outcomes, scores and recovery across every recorded experiment. Every number is computed by the engine.",
    href: "/",
    topics: [
      { title: "Outcome counts", body: "Each count links to the matching filtered history. Undetermined means the evidence did not support a verdict; it is never counted as a pass." },
      { title: "Resilience Score", body: "A versioned 0–100 score with the reason for every lost point. Runs scored with an older methodology are listed but excluded from the average." },
      { title: "Recovery and outage", body: "Time to recovery is replacement created → Ready. Client-observed outage comes from the load generator, where one runs." },
    ],
    docs: [
      { label: "Resilience Score v3", path: "docs/scoring/resilience-score-v3.md" },
      { label: "History and reports", path: "docs/history-and-reports.md" },
    ],
    tour: [
      {
        title: "Welcome to AutoResilience",
        body: "AutoResilience runs one controlled failure against a Kubernetes workload and turns what happened into evidence: did it recover, how fast, and what did its clients see? This short tour shows where things are. It never starts anything.",
      },
      {
        title: "Safety is enforced by the server",
        body: "Every experiment is checked by the engine against a namespace-bound policy and the live workload before anything touches the cluster. Nothing in this console can relax a limit, and a check that cannot be evaluated is a failure, never a pass.",
      },
      {
        target: TOUR_TARGET.overviewOutcomes,
        title: "Outcomes at a glance",
        body: "How many experiments completed, failed, were aborted or stayed undetermined. Each number opens the matching history.",
        missing: "These counts appear after your first experiment.",
      },
      {
        target: TOUR_TARGET.overviewScore,
        title: "The Resilience Score",
        body: "The average of scored runs with its methodology version. Open any run to see why each point was lost.",
        missing: "The score summary appears after your first scored run.",
      },
      {
        target: TOUR_TARGET.navApplications,
        title: "Start from your application",
        body: "Applications shows the live Kubernetes topology of the namespaces you onboard, read-only, and which workloads can be experiment targets.",
        missing: ON_PHONES,
      },
      {
        target: TOUR_TARGET.navNewExperiment,
        title: "Create an experiment",
        body: "The builder walks you through target, fault and blast radius, runs the server's safety check and asks you to confirm before anything starts.",
        missing: ON_PHONES,
      },
      {
        target: TOUR_TARGET.topBarHelp,
        title: "Help for every page",
        body: "Help explains the page you are on and links to the detailed documentation. Press ? anywhere to open it. Tour replays this page's tour.",
      },
    ],
  },
  experiments: {
    title: "Experiments",
    summary: "Every experiment the engine recorded, with its state, score and recovery. Filtering, sorting and paging run on the server.",
    href: "/experiments",
    topics: [
      { title: "States", body: "Active runs show where they are in the lifecycle; Watch live opens the experiment room. Finished runs link to their report." },
      { title: "Filters live in the URL", body: "Search, state, fault, namespace and sort are kept in the address, so refreshing or sharing the link keeps them." },
      { title: "Blocked is a result", body: "An experiment refused by safety validation is recorded as Validation failed with every check's message; nothing was injected." },
    ],
    docs: [
      { label: "Orchestration", path: "docs/orchestration.md" },
      { label: "History and reports", path: "docs/history-and-reports.md" },
    ],
    tour: [
      {
        target: TOUR_TARGET.experimentsList,
        title: "Your experiment history",
        body: "Each row is one experiment: its target workload, fault settings, state, score and time to recovery. Click a row to open it.",
        missing: "The list appears once the engine answers.",
      },
      {
        target: TOUR_TARGET.experimentsFilters,
        title: "Find runs",
        body: "Search by name, workload or namespace and filter by state, fault or namespace. The server does the filtering, and the URL keeps it.",
        advance: "click",
        tryIt: "Try a filter, or press Next.",
      },
      {
        target: TOUR_TARGET.experimentsNew,
        title: "Start a new experiment",
        body: "Opens the builder. Creating an experiment only runs the safety check; it starts only after you review it and confirm.",
      },
    ],
  },
  "new-experiment": {
    title: "New experiment",
    summary: "Configure a target and a fault, let the server check safety, then review and start.",
    href: "/experiments/new",
    topics: [
      { title: "Configure", body: "Pick a discovered workload or type its namespace, kind and name. Duration and affected replicas are validated by the server's policy, not here." },
      { title: "Safety check", body: "The server creates the experiment and validates it: namespace policy, duration and blast radius, then the live workload. A refusal is recorded; nothing is injected." },
      { title: "Review and start", body: "Nothing touches the cluster until you confirm. Abort is always available in the experiment room." },
      { title: "GRACEFUL or FORCE", body: "GRACEFUL lets the pods shut down normally; FORCE deletes them immediately, like a crash." },
    ],
    docs: [
      { label: "Safety policy", path: "chaos/policies/safety-policy.md" },
      { label: "Orchestration", path: "docs/orchestration.md" },
    ],
  },
  experiment: {
    title: "Experiment room",
    summary: "One experiment, live: lifecycle, fault → impact → recovery, score and evidence. It refreshes only while the run is active.",
    href: null,
    topics: [
      { title: "Lifecycle", body: "Each phase stores its evidence before the next begins. The phase guide says what the engine is doing now and what ends the phase." },
      { title: "Abort", body: "Stops the run and the engine's own ChaosEngine. It never deletes anything else." },
      { title: "Undetermined", body: "The evidence did not support a verdict. The reason and cause (platform, application or conflicting evidence) are shown; the run is not scored as a pass." },
    ],
    docs: [
      { label: "Orchestration", path: "docs/orchestration.md" },
      { label: "Resilience Score v3", path: "docs/scoring/resilience-score-v3.md" },
    ],
  },
  applications: {
    title: "Applications",
    summary: "Read-only views of namespaces in authorized clusters, with their live topology and experiment targets.",
    href: "/applications",
    topics: ONBOARDING_FACTS,
    docs: [
      { label: "Onboarding runbook", path: "docs/onboarding.md" },
      { label: "Topology contract", path: "docs/topology.md" },
    ],
    tour: [
      {
        target: TOUR_TARGET.applicationsAbout,
        title: "What onboarding means",
        body: "An application here is a named, read-only view of namespaces. Onboarding installs nothing and changes nothing in the cluster.",
      },
      {
        target: TOUR_TARGET.applicationsList,
        title: "Your applications",
        body: "Each application shows its cluster and whether that cluster is the execution cluster (experiments may run there) or read-only discovery.",
        missing: "The list appears once the engine answers.",
      },
      {
        target: TOUR_TARGET.applicationsOnboard,
        title: "Onboard an application",
        body: "Three steps: choose an authorized cluster, the namespaces, then review the discovered workloads and save. Every choice is checked by the server.",
      },
    ],
  },
  onboard: {
    title: "Onboard an application",
    summary: "Choose a cluster the engine may read, the application's namespaces, review the workloads and save a read-only view.",
    href: "/applications/new",
    topics: [
      ...ONBOARDING_FACTS,
      { title: "Namespace access", body: "A namespace marked forbidden or error cannot be read with the engine's identity. On a discovery cluster, `ar cluster import --namespace` grants more." },
    ],
    docs: [{ label: "Onboarding runbook", path: "docs/onboarding.md" }],
  },
  topology: {
    title: "Application topology",
    summary: "The application's Kubernetes objects and the relationships the API states between them, read live from the cluster.",
    href: null,
    topics: [
      { title: "Lines are relationships, not traffic", body: "Every line is a reference Kubernetes records (owner references, selectors, endpoints, scheduling). No line shows measured traffic; the engine never infers it." },
      { title: "Verified or not verified", body: "A relationship is drawn only when it can be verified (for example the owner's UID matches). Whatever could not be read or linked is listed under Not verified instead of guessed." },
      { title: "Filters hide, never change", body: "Resource-kind and relationship toggles hide parts of the snapshot. Search dims non-matching resources but keeps them for context." },
      { title: "Snapshots", body: "The view re-reads the cluster every 15 seconds. If a refresh fails, the last snapshot stays visible with its age." },
      { title: "Experiment targets", body: "Resources marked target are Deployments and StatefulSets on the execution cluster. The inspector opens the builder pre-filled; safety validation still decides." },
    ],
    docs: [
      { label: "Topology contract", path: "docs/topology.md" },
      { label: "Onboarding runbook", path: "docs/onboarding.md" },
    ],
    tour: [
      {
        target: TOUR_TARGET.topologyCluster,
        title: "Which cluster this is",
        body: "Execution cluster: experiments may run here after safety validation. Read-only discovery: topology only, never chaos.",
      },
      {
        target: TOUR_TARGET.topologyGraph,
        title: "The topology graph",
        body: "Kubernetes objects grouped by namespace, from Services on the left to Pods and cluster Nodes on the right. Drag to pan, scroll or pinch to zoom.",
        advance: "click",
        tryIt: "Select a resource to inspect it.",
        missing: "The graph appears once the snapshot is read, or switch back from List view.",
      },
      {
        target: TOUR_TARGET.topologyInspector,
        title: "The inspector",
        body: "Status as the API reports it, verified relationships with their source, unknowns, events and labels. Relationship names select the other resource.",
      },
      {
        target: TOUR_TARGET.topologyKinds,
        title: "Show or hide resource kinds",
        body: "Each toggle hides or shows one kind. Hover or focus a toggle for what it is.",
        advance: "click",
        tryIt: "Toggle a kind.",
      },
      {
        target: TOUR_TARGET.topologyEdges,
        title: "Relationship types",
        body: "Hide or show each kind of relationship. They are read from Kubernetes, not measured traffic.",
      },
      {
        target: TOUR_TARGET.topologyLegend,
        title: "The legend",
        body: "What each colour, line style and mark means, and how verified relationships differ from unknowns.",
        advance: "toggle",
        tryIt: "Open the legend.",
      },
      {
        target: TOUR_TARGET.topologyView,
        title: "Graph or list",
        body: "The list shows the same resources as a table, for keyboard and screen-reader use or small screens.",
      },
      {
        target: TOUR_TARGET.topologyUnknowns,
        title: "Not verified",
        body: "What the engine could not read or link, for example a listing it may not perform. Shown instead of guessed.",
        missing: "Nothing is unverified in this snapshot, so the list is not shown.",
      },
    ],
  },
  services: {
    title: "Services",
    summary: "Deployments and StatefulSets the engine discovers in the execution cluster, with their health and experiment history.",
    href: "/services",
    topics: [
      { title: "Health", body: "Read from the controller's replica status. System namespaces are never listed." },
      { title: "From a service to an experiment", body: "New experiment pre-fills the builder with the workload; every field stays editable and the server validates it." },
    ],
    docs: [{ label: "Services", path: "docs/services.md" }],
  },
  service: {
    title: "Service",
    summary: "One workload's current health and every experiment that targeted it.",
    href: null,
    topics: [{ title: "History", body: "Experiments are matched by namespace, kind and name, so history survives the workload being recreated." }],
    docs: [{ label: "Services", path: "docs/services.md" }],
  },
  reports: {
    title: "Reports",
    summary: "A printable report for every finished experiment: outcome, evidence and score.",
    href: "/reports",
    topics: [{ title: "Printing", body: "Print / save as PDF uses the browser's print dialog; the report prints on white without the console around it." }],
    docs: [{ label: "History and reports", path: "docs/history-and-reports.md" }],
  },
  report: {
    title: "Report",
    summary: "The full record of one finished experiment.",
    href: null,
    topics: [{ title: "Evidence", body: "Every value is shown as stored by the engine. Missing evidence reads No data; nothing is filled in." }],
    docs: [{ label: "Recorded experiments", path: "docs/recordings.md" }],
  },
  settings: {
    title: "Settings",
    summary: "How this console reaches the engine, what the engine can reach, where data lives, and the operations allowed from the browser.",
    href: "/settings",
    topics: [
      { title: "Environment health", body: "The engine's own checks of its database, cluster and Prometheus. Each failing check says what to run." },
      { title: "Kubernetes access", body: "The clusters the engine was configured with. Access is granted or revoked only from a terminal." },
      { title: "Data and backups", body: "Experiments live in the engine's PostgreSQL database. Backups can be taken here; restoring replaces data and stays terminal-only." },
      { title: "Stack controls", body: "Start, stop and back up the local stack through the loopback service manager. Each operation shows the manager's plan and needs your confirmation." },
      { title: "Console preferences", body: "Experiment defaults only pre-fill the builder; the server's policy decides every run. Preferences and tour progress stay in this browser." },
    ],
    docs: [
      { label: "Local stack: install, upgrade, backup", path: "docs/local-stack.md" },
      { label: "Readiness", path: "docs/readiness.md" },
    ],
    tour: [
      {
        target: TOUR_TARGET.settingsSections,
        title: "Settings at a glance",
        body: "Settings are grouped by what they affect. Jump to a group here.",
      },
      {
        target: TOUR_TARGET.settingsEnvironment,
        title: "Environment health",
        body: "The engine checks its database, the Kubernetes API and Prometheus. A failing check shows the exact command that fixes it.",
      },
      {
        target: TOUR_TARGET.settingsAccess,
        title: "Kubernetes access",
        body: "Which clusters the engine may read and where experiments may run. Granting access is terminal-only, so a browser can never widen it.",
      },
      {
        target: TOUR_TARGET.settingsData,
        title: "Data and backups",
        body: "Where experiment history is stored and how to back it up and restore it.",
      },
      {
        target: TOUR_TARGET.settingsManager,
        title: "Stack controls",
        body: "Pair with `ar manager` (it prints a token in your terminal) to start, stop or back up the stack from here. Every operation shows its plan first; the tour never runs one.",
      },
      {
        target: TOUR_TARGET.settingsTours,
        title: "Replay or reset tours",
        body: "Each page's tour is remembered in this browser once finished or skipped. Replay or reset them here.",
      },
    ],
  },
  learn: {
    title: "Help and reference",
    summary: "How AutoResilience works, how to get help, and what it is.",
    href: "/help",
    topics: [
      { title: "Keyboard", body: "Every control is reachable with Tab; Skip to content is the first stop. Press ? to open help for the current page; Escape closes dialogs and tours." },
    ],
    docs: [
      { label: "Setup and usage guide", path: "README.md" },
      { label: "Local stack", path: "docs/local-stack.md" },
    ],
  },
};

/** Pages with a tour, in the order Settings lists them. */
export const TOUR_PAGES = (Object.keys(PAGE_HELP) as PageId[]).filter((id) => PAGE_HELP[id].tour);

/** The help entry for a URL path; unknown paths get the general entry. */
export function pageFor(pathname: string): PageId {
  if (!isKnownRoute(pathname)) return "learn";
  const [first, second] = pathname.split("/").filter(Boolean);
  switch (first) {
    case undefined:
      return "overview";
    case "experiments":
      return second === "new" ? "new-experiment" : second ? "experiment" : "experiments";
    case "applications":
      return second === "new" ? "onboard" : second ? "topology" : "applications";
    case "services":
      return second ? "service" : "services";
    case "reports":
      return second ? "report" : "reports";
    case "settings":
      return "settings";
    default:
      return "learn";
  }
}
