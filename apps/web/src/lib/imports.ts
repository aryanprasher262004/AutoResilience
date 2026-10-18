/**
 * Presentation of imports (P7). Text and grouping only: what is supported, safe and
 * deployable is decided by the API (`/imports/preview`), never here.
 */
import type { Tone } from "@/components/ui/badge";

import type { ImportFinding, ImportSourceKind, ImportStatus, PlannedObject } from "./api/types";

export const importHref = (id: string) => `/applications/imports/${encodeURIComponent(id)}`;

export const STATUS_META: Record<ImportStatus, { label: string; tone: Tone; description: string }> = {
  PLANNED: {
    label: "Reviewed · not deployed",
    tone: "neutral",
    description: "The plan is saved. Nothing exists in the cluster until you approve the deployment.",
  },
  DEPLOYING: {
    label: "Deploying",
    tone: "info",
    description: "The approved plan was applied; waiting for every workload to report ready.",
  },
  READY: {
    label: "Ready",
    tone: "success",
    description: "Deployed and healthy. Its topology is onboarded; its workloads may become experiment targets.",
  },
  FAILED: {
    label: "Failed",
    tone: "danger",
    description: "The deployment did not become healthy. Retry it or remove it; nothing retries by itself.",
  },
  REMOVING: {
    label: "Removing",
    tone: "warning",
    description: "Its namespace is being deleted (only after ownership was verified).",
  },
  REMOVED: {
    label: "Removed",
    tone: "neutral",
    description: "Nothing of it is left in the cluster. The record stays until you forget it.",
  },
};

export function isSettling(status: ImportStatus): boolean {
  return status === "DEPLOYING" || status === "REMOVING";
}

export const SOURCE_META: Record<ImportSourceKind, { label: string; short: string; description: string }> = {
  compose: {
    label: "Docker Compose file",
    short: "Compose",
    description:
      "A compose.yaml whose services reference published images. It is parsed, never run: nothing is built and no file it mentions is read.",
  },
  manifests: {
    label: "Kubernetes manifests",
    short: "Manifests",
    description:
      "Deployments, StatefulSets and Services in YAML. Read through an allowlist and rendered again; never applied as written.",
  },
  image: {
    label: "Container image",
    short: "Image",
    description: "One published image, deployed as a Deployment, with a Service if you give a port.",
  },
};

export const SEVERITY_META: Record<ImportFinding["severity"], { label: string; tone: Tone; description: string }> = {
  blocking: { label: "Blocking", tone: "danger", description: "Must be fixed in the file before it can be deployed." },
  warning: { label: "Warning", tone: "warning", description: "Deployable, but the test deployment behaves differently." },
  info: { label: "Note", tone: "info", description: "How something is translated or ignored." },
};

export const GROUP_META: Record<PlannedObject["group"], { label: string; description: string }> = {
  application: { label: "Your application", description: "Built from the reviewed file, nothing else." },
  isolation: { label: "Isolation", description: "Keeps the test deployment in its own namespace and within limits." },
  chaos: { label: "Chaos preparation", description: "The vetted pod-delete setup; it never runs by itself." },
  "load-generator": {
    label: "Load generator",
    description: "AutoResilience's client, sending requests only to the endpoints you approved.",
  },
};

export const SUPPORTED_COMPOSE = [
  "image (published; build is never run)",
  "command, entrypoint, working_dir",
  "ports / expose (inside the cluster only)",
  "deploy.replicas (up to 5), deploy.resources",
  "healthcheck (CMD or CMD-SHELL)",
  "depends_on, networks (recorded, not enforced)",
  "named volumes (as empty per-Pod directories)",
  "environment / env_file (names only, never values)",
];

export const REFUSED = [
  "build, privileged, cap_add, devices, network_mode, pid, ipc, security_opt",
  "host paths and the Docker socket in volumes",
  "secrets, configs, extends, include (they read other files)",
  "unresolved ${VARIABLES} (.env files are never read)",
  "Secrets, ConfigMaps, CRDs, RBAC, Jobs, DaemonSets, Ingresses, hooks (manifests)",
  "hostNetwork, hostPath, hostPort, added capabilities, privilege escalation (manifests)",
];

/** Findings grouped by what they are about, blocking first (the API sorts them). */
export function groupFindings(findings: ImportFinding[]): Array<{ subject: string; items: ImportFinding[] }> {
  const groups = new Map<string, ImportFinding[]>();
  for (const f of findings) {
    const key = f.subject ?? "The file";
    groups.set(key, [...(groups.get(key) ?? []), f]);
  }
  return [...groups.entries()].map(([subject, items]) => ({ subject, items }));
}

export function countBySeverity(findings: ImportFinding[]): Record<ImportFinding["severity"], number> {
  const counts = { blocking: 0, warning: 0, info: 0 };
  for (const f of findings) counts[f.severity] += 1;
  return counts;
}

/** A name for the import from a file name: lowercase, digits and '-', starting with a letter. */
export function suggestName(filename: string | null | undefined): string {
  const base = (filename ?? "")
    .replace(/\.(ya?ml)$/i, "")
    .replace(/(^|[.-])(docker-)?compose$/i, "")
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, "-")
    .replace(/^[^a-z]+/, "")
    .replace(/-+$/, "")
    .slice(0, 30)
    .replace(/-+$/, "");
  return base || "my-app";
}
