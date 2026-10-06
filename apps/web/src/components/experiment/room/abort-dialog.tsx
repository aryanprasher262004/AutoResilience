"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Field, Textarea } from "@/components/ui/field";
import { ApiError, api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queries";
import type { Experiment, ExperimentState } from "@/lib/api/types";

/** States the backend accepts an abort for (orchestrator.ABORTABLE); it still decides. */
export const ABORTABLE: ExperimentState[] = [
  "CREATED",
  "VALIDATING",
  "BASELINING",
  "INJECTING",
  "OBSERVING",
  "RECOVERING",
];

const DEFAULT_REASON = "Aborted from the web console";

export function AbortControl({ experiment }: { experiment: Experiment }) {
  const queryClient = useQueryClient();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const inFlight = useRef(false);
  const [reason, setReason] = useState(DEFAULT_REASON);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reasonId = useId();
  const engine = experiment.chaos?.engine_name;

  // A run that becomes terminal while the dialog is open: nothing to abort any more.
  useEffect(() => {
    if (!ABORTABLE.includes(experiment.state)) dialogRef.current?.close();
  }, [experiment.state]);

  if (!ABORTABLE.includes(experiment.state)) return null;

  function open() {
    setReason(DEFAULT_REASON);
    setError(null);
    dialogRef.current?.showModal();
  }

  async function confirm() {
    const trimmed = reason.trim();
    if (!trimmed || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      const updated = await api.abortExperiment(experiment.id, { reason: trimmed });
      queryClient.setQueryData(queryKeys.experiment(experiment.id), updated);
      void queryClient.invalidateQueries({ queryKey: queryKeys.experiments });
      dialogRef.current?.close();
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.unavailable
            ? e.message
            : `${e.status}: ${e.detail}`
          : String(e),
      );
      void queryClient.invalidateQueries({ queryKey: queryKeys.experiment(experiment.id) });
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <>
      <Button variant="danger" onClick={open}>
        Abort experiment
      </Button>
      <dialog
        ref={dialogRef}
        aria-labelledby={`${reasonId}-title`}
        className="m-auto w-full max-w-lg rounded-lg border border-line-strong bg-surface p-0 text-fg backdrop:bg-black/60"
        onCancel={(event) => {
          if (busy) event.preventDefault();
        }}
      >
        <form
          method="dialog"
          className="grid gap-4 p-5"
          onSubmit={(event) => {
            event.preventDefault();
            void confirm();
          }}
        >
          <div>
            <h2 id={`${reasonId}-title`} className="text-base font-semibold">
              Abort “{experiment.name}”?
            </h2>
            <p className="mt-1 text-xs text-muted">
              The run stops and is recorded as Aborted.{" "}
              {engine
                ? `Only this experiment's ChaosEngine (${engine}) is stopped. Pods already deleted are not restored; Kubernetes replaces them as usual.`
                : "No ChaosEngine has been created yet, so nothing in the cluster is touched."}
            </p>
          </div>
          <Field id={reasonId} label="Reason (recorded with the experiment)" hint="1–500 characters">
            <Textarea
              id={reasonId}
              rows={2}
              maxLength={500}
              required
              value={reason}
              disabled={busy}
              onChange={(e) => setReason(e.target.value)}
            />
          </Field>
          {error ? (
            <Callout tone="danger" title="The experiment was not aborted" role="alert">
              <span className="font-mono">{error}</span>
            </Callout>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => dialogRef.current?.close()} disabled={busy}>
              Cancel
            </Button>
            <Button type="submit" variant="danger" disabled={busy || !reason.trim()}>
              {busy ? "Aborting…" : "Abort experiment"}
            </Button>
          </div>
        </form>
      </dialog>
    </>
  );
}
