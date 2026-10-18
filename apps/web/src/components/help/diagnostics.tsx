"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { API_BASE_PATH } from "@/lib/api/client";
import { useEnvironment, useReadiness } from "@/lib/api/queries";
import { useHydrated } from "@/lib/preferences";
import { CONSOLE_VERSION, RUNTIME_MODE } from "@/lib/runtime";

/**
 * A plain-text summary to paste into an issue. Secret-free by construction: only build
 * facts, the readiness answer and the browser; no experiment data, kubeconfig or tokens.
 */
export function Diagnostics({ upstream }: { upstream: string }) {
  const readiness = useReadiness();
  const environment = useEnvironment();
  // Browser-only facts (user agent, time): rendered after hydration, never on the server.
  const hydrated = useHydrated();
  const [copied, setCopied] = useState<"idle" | "copied" | "failed">("idle");
  const [generated] = useState(() => new Date().toISOString());
  const ready = readiness.data
    ? JSON.stringify(readiness.data)
    : readiness.isPending
      ? "checking"
      : `error: ${readiness.error?.message ?? "unknown"}`;
  // Mode, context name and per-check status only: the details name hosts, never credentials.
  const env = environment.data
    ? `${environment.data.runtime_mode}, context ${environment.data.kube_context ?? "current"}, ` +
      environment.data.checks.map((c) => `${c.name}=${c.status}`).join(" ")
    : environment.isPending
      ? "checking"
      : `error: ${environment.error?.message ?? "unknown"}`;
  const text = [
    `console version: ${CONSOLE_VERSION}`,
    `runtime mode: ${RUNTIME_MODE}`,
    `browser endpoint: ${API_BASE_PATH} -> ${upstream}`,
    `GET /ready: ${ready}`,
    `GET /environment: ${env}`,
    `user agent: ${typeof navigator === "undefined" ? "unknown" : navigator.userAgent}`,
    `generated: ${generated}`,
  ].join("\n");

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied("copied");
    } catch {
      setCopied("failed");
    }
  }

  return (
    <div className="grid gap-3">
      <pre
        tabIndex={0}
        aria-label="Diagnostics"
        className="overflow-x-auto rounded-md border border-line bg-canvas p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap text-muted"
      >
        {hydrated ? text : "Collecting…"}
      </pre>
      <div className="flex items-center gap-3">
        <Button onClick={() => void copy()} disabled={!hydrated}>
          Copy diagnostics
        </Button>
        <p role="status" className="text-xs text-muted">
          {copied === "copied" ? "Copied to the clipboard." : copied === "failed" ? "Copy failed: select the text instead." : ""}
        </p>
      </div>
    </div>
  );
}
