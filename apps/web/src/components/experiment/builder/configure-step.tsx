"use client";

import type { FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { FAULT_TYPES, MODE_HELP, POD_DELETE_MODES, WORKLOAD_KINDS } from "@/lib/experiment-options";

import type { FieldErrors, FormValues } from "./form";

export function ConfigureStep({
  values,
  errors,
  formError,
  busy,
  supersedes,
  onChange,
  onSubmit,
}: {
  values: FormValues;
  errors: FieldErrors;
  formError: string | null;
  busy: boolean;
  /** An earlier attempt that a changed configuration will not reuse. */
  supersedes: { id: string; state: string } | null;
  onChange: <K extends keyof FormValues>(key: K, value: FormValues[K]) => void;
  onSubmit: () => void;
}) {
  function submit(event: FormEvent) {
    event.preventDefault();
    onSubmit();
  }

  const invalid = (key: keyof FormValues) => (errors[key] ? true : undefined);
  const describedBy = (key: string) => (errors[key as keyof FormValues] ? `${key}-error` : `${key}-hint`);

  return (
    <form onSubmit={submit} noValidate aria-busy={busy}>
      <fieldset disabled={busy} className="grid gap-4">
        <Card>
          <CardHeader title="Experiment" description="How this run is identified in history." />
          <CardBody className="grid gap-4 sm:grid-cols-2">
            <Field id="name" label="Name" error={errors.name} hint="Up to 200 characters.">
              <Input
                id="name"
                value={values.name}
                maxLength={200}
                autoComplete="off"
                aria-invalid={invalid("name")}
                aria-describedby={describedBy("name")}
                onChange={(e) => onChange("name", e.target.value)}
              />
            </Field>
            <Field id="description" label="Description (optional)" error={errors.description}>
              <Textarea
                id="description"
                rows={2}
                maxLength={2000}
                value={values.description}
                aria-invalid={invalid("description")}
                onChange={(e) => onChange("description", e.target.value)}
              />
            </Field>
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Target"
            description="The workload whose pods will be deleted. The server checks that it exists and is safe to target."
          />
          <CardBody className="grid gap-4 sm:grid-cols-3">
            <Field id="namespace" label="Namespace" error={errors.namespace} hint="Kubernetes namespace">
              <Input
                id="namespace"
                value={values.namespace}
                autoComplete="off"
                spellCheck={false}
                className="font-mono"
                aria-invalid={invalid("namespace")}
                aria-describedby={describedBy("namespace")}
                onChange={(e) => onChange("namespace", e.target.value)}
              />
            </Field>
            <Field id="workload" label="Workload name" error={errors.workload} hint="Deployment or StatefulSet name">
              <Input
                id="workload"
                value={values.workload}
                autoComplete="off"
                spellCheck={false}
                className="font-mono"
                aria-invalid={invalid("workload")}
                aria-describedby={describedBy("workload")}
                onChange={(e) => onChange("workload", e.target.value)}
              />
            </Field>
            <Field id="kind" label="Workload kind" error={errors.kind}>
              <Select
                id="kind"
                value={values.kind}
                onChange={(e) => onChange("kind", e.target.value as FormValues["kind"])}
              >
                {WORKLOAD_KINDS.map((kind) => (
                  <option key={kind} value={kind}>
                    {kind}
                  </option>
                ))}
              </Select>
            </Field>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Fault" description="What happens to the target, and how much of it." />
          <CardBody className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field id="faultType" label="Fault type" error={errors.faultType}>
              <Select
                id="faultType"
                value={values.faultType}
                onChange={(e) => onChange("faultType", e.target.value as FormValues["faultType"])}
              >
                {FAULT_TYPES.map((fault) => (
                  <option key={fault} value={fault}>
                    {fault}
                  </option>
                ))}
              </Select>
            </Field>
            {values.faultType === "pod-delete" ? (
              <Field id="mode" label="Deletion mode" error={errors.mode} hint={MODE_HELP[values.mode]}>
                <Select
                  id="mode"
                  value={values.mode}
                  aria-describedby={describedBy("mode")}
                  onChange={(e) => onChange("mode", e.target.value as FormValues["mode"])}
                >
                  {POD_DELETE_MODES.map((mode) => (
                    <option key={mode} value={mode}>
                      {mode}
                    </option>
                  ))}
                </Select>
              </Field>
            ) : null}
            <Field
              id="durationSeconds"
              label="Duration (seconds)"
              error={errors.durationSeconds}
              hint="Observation window for the fault"
            >
              <Input
                id="durationSeconds"
                type="number"
                inputMode="numeric"
                min={1}
                step={1}
                className="font-mono"
                value={values.durationSeconds}
                aria-invalid={invalid("durationSeconds")}
                aria-describedby={describedBy("durationSeconds")}
                onChange={(e) => onChange("durationSeconds", e.target.value)}
              />
            </Field>
            <Field
              id="affectedReplicas"
              label="Affected replicas"
              error={errors.affectedReplicas}
              hint="Pods deleted at once (blast radius)"
            >
              <Input
                id="affectedReplicas"
                type="number"
                inputMode="numeric"
                min={1}
                step={1}
                className="font-mono"
                value={values.affectedReplicas}
                aria-invalid={invalid("affectedReplicas")}
                aria-describedby={describedBy("affectedReplicas")}
                onChange={(e) => onChange("affectedReplicas", e.target.value)}
              />
            </Field>
          </CardBody>
        </Card>

        {formError ? (
          <Callout tone="danger" title="Could not create the experiment" role="alert">
            <span className="font-mono">{formError}</span>
          </Callout>
        ) : null}
        {supersedes ? (
          <Callout tone="info" title="The configuration changed since the last safety check">
            Checking again creates a new experiment. The earlier attempt{" "}
            <span className="font-mono">{supersedes.id.split("-")[0]}</span> stays in history as{" "}
            {supersedes.state}.
          </Callout>
        ) : null}

        <div className="flex items-center justify-end gap-3">
          <p className="text-xs text-faint">
            Creates the experiment and runs the server-side safety checks. Nothing is injected yet.
          </p>
          <Button type="submit" variant="primary" disabled={busy}>
            {busy ? "Checking…" : "Check safety"}
          </Button>
        </div>
      </fieldset>
    </form>
  );
}
