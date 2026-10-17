"use client";

import Link from "next/link";
import { type KeyboardEvent, type ReactNode, useEffect, useId, useRef, useState } from "react";

import { CloseIcon } from "@/components/icons";
import { Badge, type Tone } from "@/components/ui/badge";
import { Button, buttonClasses } from "@/components/ui/button";
import { useDashboardSummary, useReadiness, useServices } from "@/lib/api/queries";
import { cn } from "@/lib/cn";
import { MODE_HELP, POD_DELETE_MODES } from "@/lib/experiment-options";
import { SUPPORTED_FAULT } from "@/lib/guidance";
import { updatePreferences, useHydrated, usePreferences } from "@/lib/preferences";

import { closeGuide, guideStartStep, useGuideOpen } from "./guide-state";

const STEPS = [
  { id: "welcome", title: "Welcome to AutoResilience" },
  { id: "safety", title: "Safety is enforced by the server" },
  { id: "faults", title: "What you can test today" },
  { id: "workflow", title: "How an experiment runs" },
  { id: "environment", title: "Your environment" },
] as const;

/**
 * First-use guide. Opens by itself until it is finished or skipped once (remembered in
 * this browser), and can be replayed from the top bar, Help or Settings.
 */
export function Guide() {
  const hydrated = useHydrated();
  const preferences = usePreferences();
  const requested = useGuideOpen();
  if (!hydrated || !(requested || preferences.guideDismissedAt === null)) return null;
  return <GuideDialog initialStep={requested ? guideStartStep() : 0} />;
}

function dismiss() {
  updatePreferences((p) => ({ ...p, guideDismissedAt: new Date().toISOString() }));
  closeGuide();
}

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

function GuideDialog({ initialStep }: { initialStep: number }) {
  const [step, setStep] = useState(Math.min(initialStep, STEPS.length - 1));
  const dialog = useRef<HTMLDivElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const titleId = useId();
  const last = step === STEPS.length - 1;

  // Move focus into the dialog, lock page scroll, and give focus back on close.
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = overflow;
      previous?.focus?.();
    };
  }, []);
  useEffect(() => {
    heading.current?.focus();
  }, [step]);

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      dismiss();
      return;
    }
    if (event.key !== "Tab" || !dialog.current) return;
    const items = [...dialog.current.querySelectorAll<HTMLElement>(FOCUSABLE)];
    if (!items.length) return;
    const first = items[0];
    const end = items[items.length - 1];
    if (event.shiftKey && (document.activeElement === first || document.activeElement === heading.current)) {
      event.preventDefault();
      end.focus();
    } else if (!event.shiftKey && document.activeElement === end) {
      event.preventDefault();
      first.focus();
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-6">
      <div aria-hidden className="absolute inset-0 bg-canvas/75 backdrop-blur-sm motion-safe:animate-[fade-in_150ms_ease-out]" onClick={dismiss} />
      <div
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={onKeyDown}
        className={cn(
          "relative flex max-h-[92dvh] w-full max-w-2xl flex-col overflow-hidden border border-line-strong bg-surface shadow-[0_24px_80px_rgb(0_0_0/0.55)]",
          "rounded-t-2xl sm:rounded-2xl motion-safe:animate-[rise-in_200ms_ease-out]",
        )}
      >
        <header className="flex items-center justify-between gap-3 border-b border-line px-5 py-3">
          <p className="text-xs text-muted">
            Getting started · step {step + 1} of {STEPS.length}
          </p>
          <button
            type="button"
            onClick={dismiss}
            className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted hover:bg-surface-2 hover:text-fg"
          >
            Skip guide
            <CloseIcon className="size-3.5" />
          </button>
        </header>

        <nav aria-label="Guide steps" className="px-5 pt-4">
          <ol className="flex gap-1.5">
            {STEPS.map((s, i) => (
              <li key={s.id} className="flex-1">
                <button
                  type="button"
                  onClick={() => setStep(i)}
                  aria-current={i === step ? "step" : undefined}
                  aria-label={`Step ${i + 1}: ${s.title}`}
                  className={cn(
                    "block h-1.5 w-full rounded-full motion-safe:transition-colors",
                    i === step ? "bg-accent" : i < step ? "bg-accent/40" : "bg-surface-3 hover:bg-line-strong",
                  )}
                />
              </li>
            ))}
          </ol>
        </nav>

        <div className="overflow-y-auto px-5 pt-5 pb-6 sm:px-7">
          <h2 ref={heading} id={titleId} tabIndex={-1} className="text-xl font-semibold tracking-tight outline-none">
            {STEPS[step].title}
          </h2>
          <div className="mt-4 text-sm leading-relaxed text-muted">
            <StepContent id={STEPS[step].id} />
          </div>
        </div>

        <footer className="flex items-center justify-between gap-3 border-t border-line px-5 py-3">
          <Button variant="ghost" onClick={() => setStep(step - 1)} disabled={step === 0}>
            Back
          </Button>
          {last ? (
            <Button variant="primary" onClick={dismiss}>
              Finish
            </Button>
          ) : (
            <Button variant="primary" onClick={() => setStep(step + 1)}>
              Next
            </Button>
          )}
        </footer>
      </div>
    </div>
  );
}

function Points({ items }: { items: [string, string][] }) {
  return (
    <ul className="mt-4 grid gap-2.5">
      {items.map(([title, body]) => (
        <li key={title} className="rounded-lg border border-line bg-surface-2/60 px-3.5 py-3">
          <p className="text-sm font-medium text-fg">{title}</p>
          <p className="mt-0.5 text-xs leading-relaxed">{body}</p>
        </li>
      ))}
    </ul>
  );
}

function StepContent({ id }: { id: (typeof STEPS)[number]["id"] }) {
  switch (id) {
    case "welcome":
      return (
        <>
          <p>
            AutoResilience runs one controlled failure against a Kubernetes workload and turns what happened
            into evidence: did it recover, how fast, and what did its clients see?
          </p>
          <Points
            items={[
              ["Controlled failure", "A bounded pod-delete through LitmusChaos, only after the server's safety checks pass."],
              ["Evidence from three sides", "Kubernetes pod timestamps, server-side request metrics and client-side failures."],
              ["An explainable score", "A versioned 0–100 Resilience Score with the reason for every lost point."],
            ]}
          />
        </>
      );
    case "safety":
      return (
        <>
          <p>
            Every experiment is checked by the API before anything touches the cluster. This console only shows
            the result; no setting here can relax a limit.
          </p>
          <Points
            items={[
              ["Policy per namespace", "Limits come from a code-defined policy chosen by the target namespace, never from the request."],
              ["Static and live checks", "Duration and blast radius are checked, then the live workload: enough ready pods must remain."],
              ["Uncertain means no", "A check that cannot be evaluated is an error, never a pass. Safety is re-checked before injection."],
              ["Only its own resources", "The engine reads the cluster and writes only the ChaosEngines it created for its own runs."],
            ]}
          />
        </>
      );
    case "faults":
      return (
        <>
          <p>
            <span className="font-mono text-fg">{SUPPORTED_FAULT.type}</span>: {SUPPORTED_FAULT.summary}
          </p>
          <ul className="mt-4 grid gap-2.5 sm:grid-cols-2">
            {POD_DELETE_MODES.map((mode) => (
              <li key={mode} className="rounded-lg border border-line bg-surface-2/60 px-3.5 py-3">
                <p className="font-mono text-xs text-fg">{mode}</p>
                <p className="mt-1 text-xs leading-relaxed">{MODE_HELP[mode]}</p>
              </li>
            ))}
          </ul>
          <p className="mt-4 text-xs text-faint">{SUPPORTED_FAULT.unsupported}</p>
        </>
      );
    case "workflow":
      return (
        <ol className="grid gap-2">
          {[
            ["Configure", "Pick a discovered workload, the deletion mode, duration and how many pods."],
            ["Safety check", "The server creates the experiment and validates it. A refusal is recorded; nothing is injected."],
            ["Run", "The orchestrator captures a baseline, injects the fault and observes. Abort is always available."],
            ["Recover", "An explicit rule decides Completed, or Undetermined with a reason and a cause."],
            ["Score and report", "Read the score breakdown, the evidence and a printable report."],
          ].map(([title, body], i) => (
            <li key={title} className="flex gap-3">
              <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-accent/15 font-mono text-2xs text-accent">
                {i + 1}
              </span>
              <span>
                <span className="font-medium text-fg">{title}.</span> {body}
              </span>
            </li>
          ))}
        </ol>
      );
    case "environment":
      return <EnvironmentStep />;
  }
}

function Check({ label, tone, status, children }: { label: string; tone: Tone; status: string; children: ReactNode }) {
  return (
    <li className="flex items-start justify-between gap-3 rounded-lg border border-line px-3.5 py-3">
      <div>
        <p className="text-sm text-fg">{label}</p>
        <p className="mt-0.5 text-xs">{children}</p>
      </div>
      <Badge tone={tone} dot>
        {status}
      </Badge>
    </li>
  );
}

/** Live checks from the API; each one says what to do when it is not OK. */
function EnvironmentStep() {
  const readiness = useReadiness();
  const services = useServices();
  const summary = useDashboardSummary();
  const ready = readiness.data?.status === "ready";
  const workloads = services.data?.items ?? [];
  const namespaces = new Set(workloads.map((w) => w.namespace)).size;

  return (
    <>
      <p>Checked live against this console&apos;s API.</p>
      <ul className="mt-4 grid gap-2">
        <Check
          label="API and database"
          tone={readiness.isPending ? "neutral" : ready ? "success" : "danger"}
          status={readiness.isPending ? "Checking" : ready ? "Ready" : readiness.data ? "Not ready" : "Unreachable"}
        >
          {ready ? "The engine answers and its database is migrated." : "See Help → Troubleshooting for the exact fix."}
        </Check>
        <Check
          label="Workloads discovered"
          tone={services.isPending ? "neutral" : services.isError ? "danger" : workloads.length ? "success" : "warning"}
          status={services.isPending ? "Checking" : services.isError ? "Unavailable" : String(workloads.length)}
        >
          {services.isError
            ? "The API could not list the cluster. Check KUBE_CONTEXT and that the cluster is running."
            : workloads.length
              ? `Deployments and StatefulSets in ${namespaces} namespace${namespaces === 1 ? "" : "s"} (system namespaces are never listed).`
              : "No workloads yet. The local setup script deploys two sample applications."}
        </Check>
        <Check
          label="Experiments recorded"
          tone={summary.isPending ? "neutral" : summary.isError ? "danger" : "info"}
          status={summary.isPending ? "Checking" : summary.isError ? "Unavailable" : String(summary.data?.total ?? 0)}
        >
          {summary.data?.total ? "Your history, scores and reports are under Experiments and Reports." : "Your first run will appear here."}
        </Check>
      </ul>
      <div className="mt-5 flex flex-wrap gap-2">
        <Link href="/experiments/new" onClick={dismiss} className={buttonClasses("primary")}>
          Create an experiment
        </Link>
        <Link href="/services" onClick={dismiss} className={buttonClasses("secondary")}>
          Browse services
        </Link>
      </div>
    </>
  );
}
