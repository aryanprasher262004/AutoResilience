"use client";

import { useEffect, useId, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/field";
import {
  DEFAULT_MANAGER_PORT,
  type ManagerJob,
  type ManagerOperation,
  type ManagerPlan,
  type Pairing,
  loadPairing,
  manager,
  savePairing,
  summarizeStatus,
} from "@/lib/manager";

const AR = "python3 tools/ar/ar.py";
const POLL_MS = 1000;

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * Start, stop and back up the local stack through `ar manager` (loopback only). Every
 * operation shows the manager's own plan and needs an explicit confirmation.
 */
export function StackControls() {
  const [pairing, setPairing] = useState<Pairing | null>(null);
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);
  const [operations, setOperations] = useState<ManagerOperation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [port, setPort] = useState(String(DEFAULT_MANAGER_PORT));
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const portId = useId();
  const tokenId = useId();

  async function connect(p: Pairing) {
    setBusy(true);
    setError(null);
    try {
      const [s, ops] = await Promise.all([manager.status(p), manager.operations(p)]);
      setStatus(s);
      setOperations(ops.items);
      setPairing(p);
      savePairing(p);
    } catch (e) {
      setError(message(e));
      setPairing(null);
      savePairing(null);
    } finally {
      setBusy(false);
    }
  }

  // Reconnect with this tab's earlier pairing, if the manager still accepts it.
  useEffect(() => {
    const saved = loadPairing();
    if (!saved) return;
    let cancelled = false;
    Promise.all([manager.status(saved), manager.operations(saved)])
      .then(([s, ops]) => {
        if (cancelled) return;
        setStatus(s);
        setOperations(ops.items);
        setPairing(saved);
      })
      .catch(() => savePairing(null)); // manager restarted (new token) or stopped
    return () => {
      cancelled = true;
    };
  }, []);

  const refresh = async () => {
    if (!pairing) return;
    try {
      setStatus(await manager.status(pairing));
    } catch (e) {
      setError(message(e));
    }
  };

  return (
    <Card>
      <CardHeader
        title="Stack controls"
        description="Start, stop or back up the local stack through the loopback service manager (ar manager)."
        actions={
          pairing ? (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                savePairing(null);
                setPairing(null);
                setStatus(null);
              }}
            >
              Disconnect
            </Button>
          ) : null
        }
      />
      <CardBody className="grid gap-3 text-xs text-muted [&_code]:font-mono [&_code]:text-fg">
        {!pairing ? (
          <>
            <p>
              Run <code>{AR} manager</code> in a terminal. It listens on 127.0.0.1 only, accepts requests from this
              console only and prints a pairing token valid while it runs. Installing, uninstalling, restoring and
              cluster imports stay terminal-only.
            </p>
            <form
              className="grid gap-3 sm:grid-cols-[8rem_1fr_auto] sm:items-end"
              onSubmit={(e) => {
                e.preventDefault();
                const n = Number(port);
                if (Number.isInteger(n) && n >= 1024 && n <= 65535 && token.trim()) void connect({ port: n, token: token.trim() });
              }}
            >
              <Field id={portId} label="Manager port">
                <Input id={portId} inputMode="numeric" value={port} onChange={(e) => setPort(e.target.value)} />
              </Field>
              <Field id={tokenId} label="Pairing token">
                <Input
                  id={tokenId}
                  type="password"
                  autoComplete="off"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder="from the ar manager terminal"
                />
              </Field>
              <Button type="submit" variant="primary" disabled={busy || !token.trim()}>
                {busy ? "Connecting…" : "Connect"}
              </Button>
            </form>
          </>
        ) : (
          <>
            {status ? (
              <dl className="grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
                {summarizeStatus(status).map((row) => (
                  <div key={row.label} className="flex items-center justify-between gap-2">
                    <dt>{row.label}</dt>
                    <dd>
                      <Badge tone={row.ok === null ? "neutral" : row.ok ? "success" : "danger"} dot>
                        {row.value}
                      </Badge>
                    </dd>
                  </div>
                ))}
              </dl>
            ) : null}
            <div className="flex flex-wrap gap-2">
              {operations.map((op) => (
                <OperationButton key={op.name} pairing={pairing} operation={op} onDone={() => void refresh()} />
              ))}
              <Button size="sm" variant="ghost" onClick={() => void refresh()}>
                Re-check
              </Button>
            </div>
          </>
        )}
        {error ? (
          <Callout tone="danger" title="Service manager" role="alert">
            <span className="font-mono">{error}</span>
          </Callout>
        ) : null}
      </CardBody>
    </Card>
  );
}

function OperationButton({ pairing, operation, onDone }: { pairing: Pairing; operation: ManagerOperation; onDone: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [plan, setPlan] = useState<ManagerPlan | null>(null);
  const [job, setJob] = useState<ManagerJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const titleId = useId();

  async function open() {
    setPlan(null);
    setJob(null);
    setError(null);
    dialogRef.current?.showModal();
    try {
      setPlan(await manager.plan(pairing, operation.name));
    } catch (e) {
      setError(message(e));
    }
  }

  async function run() {
    if (!plan || busy) return;
    setBusy(true);
    setError(null);
    try {
      let current = await manager.run(pairing, operation.name, plan.confirmation);
      setJob(current);
      while (current.state === "running") {
        await new Promise((r) => setTimeout(r, POLL_MS));
        current = await manager.job(pairing, current.id);
        setJob(current);
      }
      onDone();
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button size="sm" variant={operation.name === "stop" ? "danger" : "secondary"} onClick={() => void open()}>
        {operation.title}
      </Button>
      <dialog
        ref={dialogRef}
        aria-labelledby={titleId}
        className="m-auto w-full max-w-lg rounded-lg border border-line-strong bg-surface p-0 text-fg backdrop:bg-black/60"
        onCancel={(e) => {
          if (busy) e.preventDefault();
        }}
      >
        <div className="grid gap-4 p-5 text-xs">
          <h2 id={titleId} className="text-base font-semibold">
            {operation.title}?
          </h2>
          {plan ? (
            <div>
              <p className="text-muted">The service manager will:</p>
              <ul className="mt-1 list-disc space-y-1 pl-5 text-fg">
                {plan.plan.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
              <p className="mt-2 text-faint">This confirmation expires in {plan.expires_in_seconds}s and works once.</p>
            </div>
          ) : !error ? (
            <p className="text-muted">Asking the manager for its plan…</p>
          ) : null}
          {job ? (
            <div>
              <Badge tone={job.state === "succeeded" ? "success" : job.state === "failed" ? "danger" : "info"} dot>
                {job.state}
              </Badge>
              <pre className="mt-2 max-h-48 overflow-auto rounded bg-canvas p-2 font-mono text-2xs whitespace-pre-wrap text-muted">
                {job.output.join("\n") || "…"}
              </pre>
            </div>
          ) : null}
          {error ? (
            <Callout tone="danger" title="Not done" role="alert">
              <span className="font-mono">{error}</span>
            </Callout>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => dialogRef.current?.close()} disabled={busy}>
              {job && job.state !== "running" ? "Close" : "Cancel"}
            </Button>
            {!job ? (
              <Button variant={operation.name === "stop" ? "danger" : "primary"} onClick={() => void run()} disabled={!plan || busy}>
                Confirm and run
              </Button>
            ) : null}
          </div>
        </div>
      </dialog>
    </>
  );
}
