"use client";

import { type FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Input, Select } from "@/components/ui/field";
import type { PodDeleteMode } from "@/lib/api/types";
import { MODE_HELP, POD_DELETE_MODES } from "@/lib/experiment-options";
import { BUILT_IN_DEFAULTS, type ExperimentDefaults, updatePreferences, usePreferences } from "@/lib/preferences";

type Draft = { durationSeconds: string; affectedReplicas: string; mode: PodDeleteMode };

const toDraft = (d: ExperimentDefaults): Draft => ({
  durationSeconds: String(d.durationSeconds),
  affectedReplicas: String(d.affectedReplicas),
  mode: d.mode,
});

const positiveInt = (value: string) => /^\d+$/.test(value.trim()) && Number(value) > 0;

/**
 * Starting values for new experiments. Only obvious input checks happen here: limits such
 * as maximum duration or affected replicas belong to the server's namespace policy and are
 * deliberately not duplicated, so a preference can never make an unsafe run possible.
 */
export function PreferencesForm() {
  const saved = usePreferences().experimentDefaults;
  const [draft, setDraft] = useState<Draft | null>(null);
  const [errors, setErrors] = useState<Partial<Record<keyof Draft, string>>>({});
  const [status, setStatus] = useState<string | null>(null);
  const values = draft ?? toDraft(saved);

  function change<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft({ ...values, [key]: value });
    setErrors((e) => ({ ...e, [key]: undefined }));
    setStatus(null);
  }

  function save(event: FormEvent) {
    event.preventDefault();
    const found: typeof errors = {};
    if (!positiveInt(values.durationSeconds)) found.durationSeconds = "Whole number of seconds, > 0";
    if (!positiveInt(values.affectedReplicas)) found.affectedReplicas = "Whole number, > 0";
    setErrors(found);
    if (Object.keys(found).length) return;
    updatePreferences((p) => ({
      ...p,
      experimentDefaults: {
        durationSeconds: Number(values.durationSeconds),
        affectedReplicas: Number(values.affectedReplicas),
        mode: values.mode,
      },
    }));
    setDraft(null);
    setStatus("Saved. New experiments start with these values.");
  }

  function reset() {
    updatePreferences((p) => ({ ...p, experimentDefaults: BUILT_IN_DEFAULTS }));
    setDraft(null);
    setErrors({});
    setStatus("Reset to the built-in defaults.");
  }

  const describedBy = (key: keyof Draft) => (errors[key] ? `pref-${key}-error` : `pref-${key}-hint`);

  return (
    <Card>
      <CardHeader
        level={3}
        title="Experiment defaults"
        description="Starting values in New Experiment, stored in this browser. Every run is still validated by the server."
      />
      <CardBody>
        <form onSubmit={save} noValidate className="grid gap-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <Field id="pref-mode" label="Deletion mode" hint={MODE_HELP[values.mode]}>
              <Select
                id="pref-mode"
                value={values.mode}
                aria-describedby="pref-mode-hint"
                onChange={(e) => change("mode", e.target.value as PodDeleteMode)}
              >
                {POD_DELETE_MODES.map((mode) => (
                  <option key={mode} value={mode}>
                    {mode}
                  </option>
                ))}
              </Select>
            </Field>
            <Field id="pref-durationSeconds" label="Duration (seconds)" error={errors.durationSeconds} hint="Per experiment">
              <Input
                id="pref-durationSeconds"
                type="number"
                inputMode="numeric"
                min={1}
                step={1}
                className="font-mono"
                value={values.durationSeconds}
                aria-invalid={errors.durationSeconds ? true : undefined}
                aria-describedby={describedBy("durationSeconds")}
                onChange={(e) => change("durationSeconds", e.target.value)}
              />
            </Field>
            <Field id="pref-affectedReplicas" label="Affected replicas" error={errors.affectedReplicas} hint="Pods deleted at once">
              <Input
                id="pref-affectedReplicas"
                type="number"
                inputMode="numeric"
                min={1}
                step={1}
                className="font-mono"
                value={values.affectedReplicas}
                aria-invalid={errors.affectedReplicas ? true : undefined}
                aria-describedby={describedBy("affectedReplicas")}
                onChange={(e) => change("affectedReplicas", e.target.value)}
              />
            </Field>
          </div>
          <Callout tone="info" title="These are starting values, not permissions">
            The target namespace&apos;s safety policy still decides the maximum duration, how many pods may be
            deleted and how many must stay ready. A default the policy does not allow is refused at the safety
            check, exactly as if it had been typed in.
          </Callout>
          <div className="flex flex-wrap items-center justify-end gap-3">
            <p role="status" className="mr-auto text-xs text-success">
              {status}
            </p>
            <Button variant="ghost" onClick={reset}>
              Reset to defaults
            </Button>
            <Button type="submit" variant="primary">
              Save defaults
            </Button>
          </div>
        </form>
      </CardBody>
    </Card>
  );
}
