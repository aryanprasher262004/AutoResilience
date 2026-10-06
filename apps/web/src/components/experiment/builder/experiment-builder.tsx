"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Stepper } from "@/components/ui/stepper";
import { ApiError, api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queries";
import type { Experiment } from "@/lib/api/types";
import { presentState } from "@/lib/experiment-state";

import { ConfigureStep } from "./configure-step";
import {
  type FieldErrors,
  type FormValues,
  INITIAL_VALUES,
  checkObvious,
  serverFieldErrors,
  toPayload,
} from "./form";
import { ReviewStep } from "./review-step";
import { SafetyStep } from "./safety-step";

type StepId = "configure" | "safety" | "review";

const STEPS: Array<{ id: StepId; label: string; heading: string }> = [
  { id: "configure", label: "Configure", heading: "Configure the experiment" },
  { id: "safety", label: "Safety check", heading: "Server-side safety check" },
  { id: "review", label: "Review & start", heading: "Review and start" },
];

/** The backend's own words, with context for the cases the user can act on. */
function describe(error: unknown): string {
  if (!(error instanceof ApiError)) return String(error);
  if (error.unavailable) return error.message;
  if (error.status === 404) return `Not found (404): ${error.detail}`;
  if (error.status === 409) return `Conflict (409): ${error.detail}`;
  return `${error.status}: ${error.detail}`;
}

export function ExperimentBuilder() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [step, setStep] = useState<StepId>("configure");
  const [values, setValues] = useState<FormValues>(INITIAL_VALUES);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [experiment, setExperiment] = useState<Experiment | null>(null);
  // Payload the current experiment was created from; any change means a new one.
  const [createdFrom, setCreatedFrom] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [started, setStarted] = useState(false);
  const inFlight = useRef(false);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const firstRender = useRef(true);

  // Move focus to the new step's heading so keyboard/screen-reader users follow along.
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    headingRef.current?.focus();
  }, [step]);

  /** One request at a time: ignores clicks/Enter while a request is running. */
  async function guarded(action: () => Promise<void>) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    try {
      await action();
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  function refreshLists() {
    void queryClient.invalidateQueries({ queryKey: queryKeys.experiments });
  }

  function onChange<K extends keyof FormValues>(key: K, value: FormValues[K]) {
    setValues((v) => ({ ...v, [key]: value }));
    setErrors((e) => ({ ...e, [key]: undefined }));
    setFormError(null);
  }

  async function validate(target: Experiment) {
    setStep("safety");
    setValidationError(null);
    try {
      setExperiment(await api.validateExperiment(target.id));
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        // Already validated (e.g. an earlier response was lost): show the stored result.
        const current = await api.getExperiment(target.id).catch(() => null);
        if (current?.validation_result) {
          setExperiment(current);
          return;
        }
      }
      setValidationError(describe(error));
    } finally {
      refreshLists();
    }
  }

  function checkSafety() {
    const obvious = checkObvious(values);
    if (Object.keys(obvious).length) {
      setErrors(obvious);
      document.getElementById(Object.keys(obvious)[0])?.focus();
      return;
    }
    const payload = toPayload(values);
    const key = JSON.stringify(payload);
    void guarded(async () => {
      let current = experiment;
      if (!current || key !== createdFrom) {
        try {
          current = await api.createExperiment(payload);
        } catch (error) {
          if (error instanceof ApiError && error.status === 422) {
            const { fields, other } = serverFieldErrors(error.fieldErrors());
            setErrors(fields);
            setFormError(other.length ? other.join("; ") : null);
            const first = Object.keys(fields)[0];
            if (first) document.getElementById(first)?.focus();
          } else {
            setFormError(describe(error));
          }
          return;
        }
        setExperiment(current);
        setCreatedFrom(key);
        setValidationError(null);
        refreshLists();
      }
      if (current.validation_result) {
        setStep("safety"); // unchanged configuration: reuse the existing result
        return;
      }
      await validate(current);
    });
  }

  function run() {
    if (!experiment || started) return;
    const id = experiment.id;
    void guarded(async () => {
      setRunError(null);
      try {
        await api.runExperiment(id);
      } catch (error) {
        setRunError(describe(error));
        return;
      }
      setStarted(true); // keep actions disabled while navigating
      refreshLists();
      void queryClient.invalidateQueries({ queryKey: queryKeys.experiment(id) });
      router.push(`/experiments/${id}`);
    });
  }

  const supersedes =
    step === "configure" && experiment && createdFrom && JSON.stringify(toPayload(values)) !== createdFrom
      ? { id: experiment.id, state: presentState(experiment).label }
      : null;
  const current = STEPS.find((s) => s.id === step) ?? STEPS[0];

  return (
    <div className="grid gap-5">
      <Stepper steps={STEPS} current={step} />
      <h2 ref={headingRef} tabIndex={-1} className="text-base font-semibold text-fg outline-none">
        {current.heading}
      </h2>
      {step === "configure" ? (
        <ConfigureStep
          values={values}
          errors={errors}
          formError={formError}
          busy={busy}
          supersedes={supersedes}
          onChange={onChange}
          onSubmit={checkSafety}
        />
      ) : null}
      {step === "safety" && experiment ? (
        <SafetyStep
          experiment={experiment}
          validationError={validationError}
          busy={busy}
          onRetryValidation={() => void guarded(() => validate(experiment))}
          onEdit={() => setStep("configure")}
          onContinue={() => {
            setRunError(null);
            setStep("review");
          }}
        />
      ) : null}
      {step === "review" && experiment ? (
        <ReviewStep
          experiment={experiment}
          runError={runError}
          busy={busy || started}
          onBack={() => setStep("safety")}
          onRun={run}
        />
      ) : null}
    </div>
  );
}
