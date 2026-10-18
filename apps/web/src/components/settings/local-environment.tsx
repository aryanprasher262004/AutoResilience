"use client";

import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { DescriptionList } from "@/components/ui/description-list";
import { LoadingState } from "@/components/ui/states";
import { useEnvironment } from "@/lib/api/queries";
import type { Environment, EnvironmentCheck } from "@/lib/api/types";
import { docsUrl } from "@/lib/runtime";

type Mode = Environment["runtime_mode"];

const MODE_LABEL: Record<Mode, string> = {
  "local-stack": "Local stack (containers managed by ar)",
  development: "Development (host processes)",
};

const CHECK_LABEL: Record<EnvironmentCheck["name"], string> = {
  database: "Database",
  kubernetes: "Cluster (Kubernetes API)",
  prometheus: "Prometheus",
};

const AR = "python3 tools/ar/ar.py";

/** What to do when a check fails; the commands that exist for that runtime mode only. */
const FIX: Record<Mode, Record<EnvironmentCheck["name"], ReactNode>> = {
  "local-stack": {
    database: (
      <>
        Run <code>{AR} status</code>, then <code>{AR} start</code>. The migrate container applies schema changes before
        the engine starts.
      </>
    ),
    kubernetes: (
      <>
        <code>{AR} start</code> restarts a stopped kind node. A 401/403 means the engine&apos;s access was revoked or
        changed: <code>{AR} install</code> re-grants it.
      </>
    ),
    prometheus: (
      <>
        Prometheus runs inside the cluster: <code>{AR} start</code>. After a restart it needs about a minute of samples
        before baselines succeed.
      </>
    ),
  },
  development: {
    database: (
      <>
        <code>./scripts/dev-db.sh</code> starts PostgreSQL and applies the migrations.
      </>
    ),
    kubernetes: (
      <>
        Start the API with <code>KUBE_CONTEXT=kind-autoresilience</code>; <code>./scripts/dev-cluster.sh</code> creates
        the cluster.
      </>
    ),
    prometheus: (
      <>
        <code>./scripts/dev-cluster.sh</code> installs Prometheus on <code>localhost:9090</code> (set{" "}
        <code>PROMETHEUS_URL</code> otherwise).
      </>
    ),
  },
};

/** The engine's own view of its dependencies (GET /environment). Read-only: nothing here changes the stack. */
export function LocalEnvironment() {
  const { data, error, isPending, isFetching, refetch } = useEnvironment();
  const recheck = (
    <Button size="sm" onClick={() => void refetch()} disabled={isFetching}>
      {isFetching ? "Checking…" : "Re-check"}
    </Button>
  );

  return (
    <Card>
      <CardHeader
        title="Local environment"
        description="Database, cluster and Prometheus as the engine reaches them (GET /environment)."
        actions={recheck}
      />
      {isPending ? (
        <LoadingState rows={3} label="Checking the environment" />
      ) : !data ? (
        <CardBody className="grid gap-2 text-xs leading-relaxed text-muted [&_code]:font-mono [&_code]:text-fg">
          <p className="text-sm font-medium text-danger">Engine unreachable</p>
          <p className="font-mono break-all">{error?.message}</p>
          <p>
            Local stack: <code>{AR} status</code> shows which container is down; <code>{AR} start</code> starts it.
            Development: start the API from <code>apps/api</code>.
          </p>
        </CardBody>
      ) : (
        <>
          <CardBody>
            <DescriptionList
              items={[
                { label: "Runtime mode", value: MODE_LABEL[data.runtime_mode] },
                {
                  label: "Kubernetes context",
                  value: data.kube_context ? (
                    <code className="font-mono">{data.kube_context}</code>
                  ) : (
                    "Not set: the kubeconfig's current context (development only)"
                  ),
                },
                { label: "Prometheus", value: <code className="font-mono">{data.prometheus_url}</code> },
              ]}
            />
          </CardBody>
          <ul className="divide-y divide-line border-t border-line" aria-label="Environment checks">
            {data.checks.map((check) => (
              <li key={check.name} className="grid gap-1 px-4 py-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="text-sm text-fg">{CHECK_LABEL[check.name]}</p>
                  <Badge tone={check.status === "pass" ? "success" : "danger"} dot>
                    {check.status === "pass" ? "Connected" : "Failing"}
                  </Badge>
                </div>
                <p className="font-mono text-2xs break-all text-faint">{check.detail}</p>
                {check.status === "fail" ? (
                  <p className="text-xs leading-relaxed text-muted [&_code]:font-mono [&_code]:text-fg">
                    {FIX[data.runtime_mode][check.name]}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}

const COMMANDS: [string, string][] = [
  ["status", "health of the cluster, containers, engine and console"],
  ["start / stop", "start or stop the stack; containers and data are kept"],
  ["backup / restore FILE", "pg_dump of the experiment database to ~/.autoresilience/backups"],
  ["upgrade", "back up, rebuild from this checkout, migrate, restart"],
  ["diagnostics --logs", "secret-free report for a bug report"],
  ["uninstall", "remove the stack; data and the cluster are kept unless you opt in"],
];

/** Static reference: the console cannot run these (no service-manager endpoint exists yet). */
export function StackCommands() {
  return (
    <Card>
      <CardHeader title="Managing the local stack" description="Run in a terminal at the repository root." />
      <CardBody className="grid gap-3 text-xs text-muted">
        <dl className="grid gap-1.5 sm:grid-cols-[12rem_1fr]">
          {COMMANDS.map(([command, summary]) => (
            <div key={command} className="contents">
              <dt className="font-mono text-fg">ar {command}</dt>
              <dd>{summary}</dd>
            </div>
          ))}
        </dl>
        <p>
          <code className="font-mono text-fg">ar</code> is <code className="font-mono text-fg">{AR}</code>. Every step
          that creates or deletes resources prints its plan and asks first.{" "}
          <a href={docsUrl("docs/local-stack.md")} target="_blank" rel="noreferrer" className="text-accent hover:underline">
            Install, upgrade, backup and uninstall guide ↗<span className="sr-only"> (opens in a new tab)</span>
          </a>
        </p>
      </CardBody>
    </Card>
  );
}
