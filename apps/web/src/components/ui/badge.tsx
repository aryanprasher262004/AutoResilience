import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export type Tone = "neutral" | "info" | "fault" | "success" | "warning" | "danger";

const tones: Record<Tone, string> = {
  neutral: "bg-surface-3 text-muted ring-line-strong",
  info: "bg-info/10 text-info ring-info/25",
  fault: "bg-fault/10 text-fault ring-fault/25",
  success: "bg-success/10 text-success ring-success/25",
  warning: "bg-warning/10 text-warning ring-warning/25",
  danger: "bg-danger/10 text-danger ring-danger/25",
};

const dots: Record<Tone, string> = {
  neutral: "bg-faint",
  info: "bg-info",
  fault: "bg-fault",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
};

export function Badge({
  tone = "neutral",
  dot = false,
  title,
  className,
  children,
}: {
  tone?: Tone;
  dot?: boolean;
  title?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex h-5 items-center gap-1.5 rounded px-1.5 text-2xs font-medium whitespace-nowrap ring-1 ring-inset",
        tones[tone],
        className,
      )}
    >
      {dot ? <span aria-hidden className={cn("size-1.5 rounded-full", dots[tone])} /> : null}
      {children}
    </span>
  );
}
