"use client";

import type { ReactNode } from "react";

import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { useEnvironment } from "@/lib/api/queries";
import { TOUR_TARGET } from "@/lib/help-content";
import { docsUrl } from "@/lib/runtime";

const AR = "python3 tools/ar/ar.py";

function Row({ what, where, children }: { what: string; where: string; children: ReactNode }) {
  return (
    <div className="grid gap-0.5 py-2.5 sm:grid-cols-[11rem_1fr] sm:gap-4">
      <dt className="text-sm text-fg">
        {what}
        <span className="block text-2xs text-faint">{where}</span>
      </dt>
      <dd className="text-xs leading-relaxed text-muted [&_code]:font-mono [&_code]:text-fg">{children}</dd>
    </div>
  );
}

/** Where data lives and what each data operation does. Explanations only; no controls. */
export function DataAndBackups() {
  const mode = useEnvironment().data?.runtime_mode;
  return (
    <Card data-tour={TOUR_TARGET.settingsData}>
      <CardHeader level={3} title="Data and backups" description="What is stored where, and what backing up or restoring does." />
      <CardBody>
        <dl className="divide-y divide-line">
          {mode === "development" ? (
            <Row what="Experiment history" where="your PostgreSQL (DATABASE_URL)">
              Development uses the database <code>./scripts/dev-db.sh</code> started. Back it up with your own PostgreSQL
              tools; <code>ar backup</code> covers only the local stack.
            </Row>
          ) : (
            <Row what="Experiment history" where="Docker volume autoresilience-data">
              Experiments, evidence, scores and onboarded applications live in the stack&apos;s PostgreSQL. Stopping or
              upgrading the stack keeps them; <code>{AR} uninstall</code> keeps them unless you pass{" "}
              <code>--delete-data</code>.
            </Row>
          )}
          <Row what="Backups" where="~/.autoresilience/backups">
            A <code>pg_dump</code> readable only by you, from Stack controls below or <code>{AR} backup</code>. Existing
            backups are kept, also by <code>{AR} uninstall</code>. <code>{AR} upgrade</code> takes one first.
          </Row>
          <Row what="Restore" where="terminal only">
            <code>{AR} restore FILE</code> replaces all current experiment data with the backup, after asking; it backs
            up the current data first and stops the engine while restoring. It is not offered here because it replaces
            data.
          </Row>
          <Row what="Cluster state" where="not backed up">
            The cluster&apos;s workloads, Prometheus samples (kept in memory) and Litmus results are not part of a backup;
            the evidence each experiment needs is already stored with it.
          </Row>
          <Row what="This browser" where="localStorage and sessionStorage">
            Experiment defaults and tour progress stay in this browser (Console below). The service-manager pairing
            lasts for this tab only.
          </Row>
        </dl>
        <p className="mt-2 text-xs">
          <a href={docsUrl("docs/local-stack.md")} target="_blank" rel="noreferrer" className="text-accent hover:underline">
            Backup, restore and upgrade guide ↗<span className="sr-only"> (opens in a new tab)</span>
          </a>
        </p>
      </CardBody>
    </Card>
  );
}
