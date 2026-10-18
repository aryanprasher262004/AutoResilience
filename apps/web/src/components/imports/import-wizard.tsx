"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type ChangeEvent, type ReactNode, useId, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Input, Textarea } from "@/components/ui/field";
import { InfoHint } from "@/components/ui/info-hint";
import { Stepper } from "@/components/ui/stepper";
import { ApiError, api } from "@/lib/api/client";
import { queryKeys, useImportCapabilities } from "@/lib/api/queries";
import type { ImportPreview, ImportRequest, ImportSourceKind, TrafficTarget } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { TOUR_TARGET } from "@/lib/help-content";
import { REFUSED, SOURCE_META, SUPPORTED_COMPOSE, importHref, suggestName } from "@/lib/imports";

import { FindingsView, PlanView, SpecView } from "./plan-view";

const STEPS = [
  { id: "source", label: "Source" },
  { id: "review", label: "Security review" },
  { id: "plan", label: "Plan & save" },
];
type StepId = "source" | "review" | "plan";
const MAX_BYTES_FALLBACK = 256 * 1024;

/** "ghcr.io/org/podinfo:6.7.1" -> "podinfo". */
function imageName(image: string): string {
  return image.trim().split("@")[0].split("/").at(-1)?.split(":")[0] ?? "";
}

function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.unavailable ? error.message : `${error.status}: ${error.detail}`;
  return String(error);
}

type Source = {
  kind: ImportSourceKind;
  filename: string | null;
  content: string;
  image: string;
  port: string;
  replicas: string;
};

function toRequest(name: string, source: Source, traffic: TrafficTarget[]): ImportRequest {
  return {
    name,
    traffic,
    source:
      source.kind === "image"
        ? {
            kind: "image",
            image: {
              image: source.image.trim(),
              port: source.port ? Number(source.port) : null,
              replicas: Number(source.replicas) || 2,
            },
          }
        : { kind: source.kind, filename: source.filename, content: source.content },
  };
}

/**
 * Import: choose a Compose file, manifests or an image; the engine parses and reviews
 * it and renders the deployment plan; saving stores that plan. Nothing is deployed here
 * (that is a separate, explicit step on the import's page).
 */
export function ImportWizard() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const caps = useImportCapabilities();
  const [step, setStep] = useState<StepId>("source");
  const [source, setSource] = useState<Source>({ kind: "compose", filename: null, content: "", image: "", port: "", replicas: "2" });
  const [name, setName] = useState("");
  const [nameTouched, setNameTouched] = useState(false);
  const [traffic, setTraffic] = useState<TrafficTarget[]>([]);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [stale, setStale] = useState(false);
  const [busy, setBusy] = useState<"check" | "save" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  async function check(nextTraffic: TrafficTarget[] = traffic, goTo: StepId = "review") {
    setBusy("check");
    setError(null);
    setFieldErrors({});
    try {
      const result = await api.previewImport(toRequest(name || "my-app", source, nextTraffic));
      setPreview(result);
      setStale(false);
      setStep(goTo);
    } catch (e) {
      setError(errorText(e));
      if (e instanceof ApiError) setFieldErrors(e.fieldErrors());
    } finally {
      setBusy(null);
    }
  }

  async function save() {
    setBusy("save");
    setError(null);
    try {
      const created = await api.createImport(toRequest(name, source, traffic));
      void queryClient.invalidateQueries({ queryKey: queryKeys.imports });
      router.push(importHref(created.id));
    } catch (e) {
      setError(errorText(e));
      if (e instanceof ApiError) setFieldErrors(e.fieldErrors());
      setBusy(null);
    }
  }

  const deployAvailable = caps.data?.provisioner.configured;

  return (
    <div className="grid gap-4">
      <Stepper steps={STEPS} current={step} />
      {error ? (
        <Callout tone="danger" title="The engine did not accept this" role="alert">
          <span className="font-mono break-words">{error}</span>
        </Callout>
      ) : null}
      {step === "source" ? (
        <SourceStep
          source={source}
          name={name}
          maxBytes={caps.data?.max_bytes ?? MAX_BYTES_FALLBACK}
          errors={fieldErrors}
          busy={busy === "check"}
          onSource={(s) => {
            setSource(s);
            setPreview(null);
            if (!nameTouched) setName(suggestName(s.kind === "image" ? imageName(s.image) : s.filename));
          }}
          onName={(n) => {
            setNameTouched(true);
            setName(n);
          }}
          onCheck={() => void check([], "review")}
        />
      ) : step === "review" && preview ? (
        <div className="grid gap-4">
          <FindingsView findings={preview.findings} />
          {!preview.deployable ? (
            <Callout tone="danger" title="Not deployable as it is" role="status">
              Fix the blocking findings in the file, then check it again. Nothing was stored.
            </Callout>
          ) : null}
          <div className="flex flex-wrap justify-between gap-2">
            <Button variant="ghost" onClick={() => setStep("source")}>
              Back
            </Button>
            <Button variant="primary" disabled={!preview.deployable} onClick={() => setStep("plan")}>
              Review the plan
            </Button>
          </div>
        </div>
      ) : step === "plan" && preview?.spec && preview.plan ? (
        <div className="grid gap-4">
          {deployAvailable === false ? (
            <Callout tone="warning" title="Deployment is not available on this engine" role="status">
              {caps.data?.provisioner.detail} You can still save the reviewed plan.
            </Callout>
          ) : null}
          <SpecView spec={preview.spec} />
          <TrafficPicker
            preview={preview}
            selected={traffic}
            onChange={(t) => {
              setTraffic(t);
              setStale(true);
            }}
            stale={stale}
            busy={busy === "check"}
            onUpdate={() => void check(traffic, "plan")}
          />
          <PlanView plan={preview.plan} preview />
          <Card data-tour={TOUR_TARGET.importSave}>
            <CardBody className="flex flex-wrap items-end justify-between gap-3">
              <Field
                id="import-name"
                label="Import name (also the namespace: ar-imp-<name>)"
                error={fieldErrors.name}
                hint="Lowercase letters, digits and '-', starting with a letter."
                className="min-w-56 flex-1"
              >
                <Input
                  id="import-name"
                  value={name}
                  maxLength={30}
                  aria-invalid={!!fieldErrors.name || undefined}
                  onChange={(e) => {
                    setName(e.target.value);
                    setStale(true);
                  }}
                />
              </Field>
              <div className="flex flex-wrap gap-2">
                <Button variant="ghost" onClick={() => setStep("review")}>
                  Back
                </Button>
                {stale ? (
                  <Button onClick={() => void check(traffic, "plan")} disabled={busy !== null}>
                    {busy === "check" ? "Updating…" : "Update the plan"}
                  </Button>
                ) : null}
                <Button variant="primary" onClick={() => void save()} disabled={busy !== null || stale || !name}>
                  {busy === "save" ? "Saving…" : "Save reviewed import"}
                </Button>
              </div>
            </CardBody>
            <p className="border-t border-line px-4 py-2 text-xs text-muted">
              Saving deploys nothing. On the next page you can approve this exact plan, or leave it saved.
            </p>
          </Card>
        </div>
      ) : null}
    </div>
  );
}

function SourceChoice({
  kind,
  selected,
  onSelect,
  children,
}: {
  kind: ImportSourceKind;
  selected: boolean;
  onSelect: () => void;
  children?: ReactNode;
}) {
  const id = useId();
  return (
    <label
      htmlFor={id}
      className={cn(
        "flex cursor-pointer items-start gap-2.5 rounded-lg border px-3 py-2.5",
        selected ? "border-accent bg-accent/5" : "border-line hover:border-line-strong",
      )}
    >
      <input id={id} type="radio" name="import-source" checked={selected} onChange={onSelect} className="mt-0.5 accent-[var(--color-accent)]" />
      <span className="min-w-0">
        <span className="text-sm font-medium text-fg">{SOURCE_META[kind].label}</span>
        <span className="mt-0.5 block text-xs text-muted">{SOURCE_META[kind].description}</span>
        {children}
      </span>
    </label>
  );
}

function SourceStep({
  source,
  name,
  maxBytes,
  errors,
  busy,
  onSource,
  onName,
  onCheck,
}: {
  source: Source;
  name: string;
  maxBytes: number;
  errors: Record<string, string>;
  busy: boolean;
  onSource: (s: Source) => void;
  onName: (n: string) => void;
  onCheck: () => void;
}) {
  const [fileError, setFileError] = useState<string | null>(null);
  const isFile = source.kind !== "image";
  const ready = isFile ? source.content.trim().length > 0 : source.image.trim().length > 0;

  function onFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    setFileError(null);
    if (!file) return;
    if (file.size > maxBytes) {
      setFileError(`${file.name} is ${Math.ceil(file.size / 1024)} KiB; imports are limited to ${maxBytes / 1024} KiB.`);
      return;
    }
    // Read as text in the browser; only this text is sent. Nothing else from the disk is read.
    void file.text().then((content) => onSource({ ...source, filename: file.name, content }));
  }

  return (
    <div className="grid gap-4">
      <Card data-tour={TOUR_TARGET.importSource}>
        <CardHeader title="What do you want to import?" description="Nothing is deployed in this wizard: you review a security report and a plan, then save." />
        <CardBody className="grid gap-2 md:grid-cols-2">
          {(["compose", "manifests", "image"] as const).map((kind) => (
            <SourceChoice key={kind} kind={kind} selected={source.kind === kind} onSelect={() => onSource({ ...source, kind })} />
          ))}
          <Link
            href="/applications/new"
            className="flex items-start gap-2.5 rounded-lg border border-dashed border-line px-3 py-2.5 hover:border-line-strong"
          >
            <span aria-hidden className="mt-0.5 text-faint">
              →
            </span>
            <span>
              <span className="text-sm font-medium text-fg">Kubernetes connection</span>
              <span className="mt-0.5 block text-xs text-muted">
                Already running in a cluster the engine may read? Onboard its namespaces instead: read-only, nothing is deployed.
              </span>
            </span>
          </Link>
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title={SOURCE_META[source.kind].label}
          actions={
            <InfoHint label="supported inputs">
              <strong className="text-fg">Supported:</strong> {SUPPORTED_COMPOSE.join("; ")}.{" "}
              <strong className="text-fg">Always refused:</strong> {REFUSED.join("; ")}.
            </InfoHint>
          }
        />
        <CardBody className="grid gap-3">
          {isFile ? (
            <>
              <Field
                id="import-file"
                label={source.kind === "compose" ? "Compose file (compose.yaml)" : "Manifest file (.yaml, several documents allowed)"}
                error={fileError}
                hint={source.filename ? `Loaded ${source.filename}. Only its text is sent; files it mentions are never read.` : `Up to ${maxBytes / 1024} KiB.`}
              >
                <input
                  id="import-file"
                  type="file"
                  accept=".yaml,.yml,application/yaml,text/yaml"
                  onChange={onFile}
                  className="text-xs text-muted file:mr-3 file:rounded-md file:border file:border-line-strong file:bg-surface-2 file:px-2.5 file:py-1 file:text-xs file:text-fg"
                />
              </Field>
              <Field id="import-content" label="Or paste it" error={errors["source.content"]}>
                <Textarea
                  id="import-content"
                  value={source.content}
                  rows={10}
                  spellCheck={false}
                  className="font-mono text-xs"
                  placeholder={source.kind === "compose" ? "services:\n  web:\n    image: nginx:1.27-alpine\n    ports: [\"8080:80\"]" : "apiVersion: apps/v1\nkind: Deployment\n…"}
                  onChange={(e) => onSource({ ...source, content: e.target.value, filename: source.filename })}
                />
              </Field>
            </>
          ) : (
            <div className="grid gap-3 sm:grid-cols-[1fr_8rem_8rem]">
              <Field id="import-image" label="Image" error={errors["source.image.image"]} hint="A published image with a version tag or digest.">
                <Input
                  id="import-image"
                  value={source.image}
                  placeholder="ghcr.io/stefanprodan/podinfo:6.7.1"
                  onChange={(e) => onSource({ ...source, image: e.target.value })}
                />
              </Field>
              <Field id="import-port" label="Port (optional)" error={errors["source.image.port"]}>
                <Input id="import-port" inputMode="numeric" value={source.port} onChange={(e) => onSource({ ...source, port: e.target.value.replace(/\D/g, "") })} />
              </Field>
              <Field id="import-replicas" label="Replicas" error={errors["source.image.replicas"]}>
                <Input id="import-replicas" inputMode="numeric" value={source.replicas} onChange={(e) => onSource({ ...source, replicas: e.target.value.replace(/\D/g, "") })} />
              </Field>
            </div>
          )}
          <Field id="import-source-name" label="Import name" error={errors.name} hint="Becomes the namespace ar-imp-<name>. Lowercase letters, digits and '-'.">
            <Input id="import-source-name" value={name} maxLength={30} onChange={(e) => onName(e.target.value)} />
          </Field>
        </CardBody>
      </Card>
      <div className="flex justify-end">
        <Button variant="primary" onClick={onCheck} disabled={!ready || busy}>
          {busy ? "Checking…" : "Check it"}
        </Button>
      </div>
    </div>
  );
}

function TrafficPicker({
  preview,
  selected,
  onChange,
  stale,
  busy,
  onUpdate,
}: {
  preview: ImportPreview;
  selected: TrafficTarget[];
  onChange: (t: TrafficTarget[]) => void;
  stale: boolean;
  busy: boolean;
  onUpdate: () => void;
}) {
  const services = (preview.spec?.services ?? []).filter((s) => !s.headless && s.ports.some((p) => p.protocol === "TCP"));
  return (
    <Card data-tour={TOUR_TARGET.importTraffic}>
      <CardHeader
        title="Load generator (optional)"
        description="For client-side evidence: AutoResilience's client sends 5 requests per second to the endpoints you pick, and nowhere else. Without it, client evidence is reported as unavailable."
        actions={stale ? <Badge tone="warning">Plan out of date</Badge> : null}
      />
      {services.length ? (
        <ul className="divide-y divide-line">
          {services.map((s) => {
            const current = selected.find((t) => t.service === s.name);
            const ports = s.ports.filter((p) => p.protocol === "TCP");
            const set = (patch: Partial<TrafficTarget> | null) =>
              onChange(
                patch === null
                  ? selected.filter((t) => t.service !== s.name)
                  : [...selected.filter((t) => t.service !== s.name), { service: s.name, port: ports[0].port, path: "/", ...current, ...patch }],
              );
            return (
              <li key={s.name} className="flex flex-wrap items-center gap-3 px-4 py-2.5">
                <label className="flex min-w-36 items-center gap-2 text-sm">
                  <input type="checkbox" checked={!!current} onChange={(e) => set(e.target.checked ? {} : null)} className="accent-[var(--color-accent)]" />
                  <span className="font-mono">{s.name}</span>
                </label>
                {current ? (
                  <>
                    <label className="flex items-center gap-1.5 text-xs text-muted">
                      Port
                      <select
                        value={current.port}
                        onChange={(e) => set({ port: Number(e.target.value) })}
                        className="h-7 rounded-md border border-line-strong bg-surface-2 px-1.5 font-mono text-xs text-fg"
                      >
                        {ports.map((p) => (
                          <option key={p.port} value={p.port}>
                            {p.port}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="flex flex-1 items-center gap-1.5 text-xs text-muted">
                      Path
                      <Input value={current.path ?? "/"} onChange={(e) => set({ path: e.target.value })} className="h-7 max-w-56 font-mono text-xs" aria-label={`HTTP path for ${s.name}`} />
                    </label>
                  </>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : (
        <CardBody>
          <p className="text-xs text-muted">No Service with a TCP port, so there is nothing to send load to.</p>
        </CardBody>
      )}
      {stale ? (
        <CardBody className="flex items-center justify-between gap-3 border-t border-line">
          <p className="text-xs text-muted">The plan changes with the load targets; update it before saving.</p>
          <Button size="sm" onClick={onUpdate} disabled={busy}>
            {busy ? "Updating…" : "Update the plan"}
          </Button>
        </CardBody>
      ) : null}
    </Card>
  );
}

export function ImportEntry() {
  return (
    <ButtonLink href="/applications/import" data-tour={TOUR_TARGET.applicationsImport}>
      Import application
    </ButtonLink>
  );
}
