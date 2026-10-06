import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

type Tone = "info" | "warning" | "danger" | "success" | "neutral";

const tones: Record<Tone, string> = {
  info: "border-info/30 bg-info/5",
  warning: "border-warning/35 bg-warning/5",
  danger: "border-danger/35 bg-danger/5",
  success: "border-success/30 bg-success/5",
  neutral: "border-line-strong bg-surface-2",
};

const titles: Record<Tone, string> = {
  info: "text-info",
  warning: "text-warning",
  danger: "text-danger",
  success: "text-success",
  neutral: "text-fg",
};

export function Callout({
  tone = "info",
  title,
  children,
  role,
}: {
  tone?: Tone;
  title: ReactNode;
  children?: ReactNode;
  role?: "alert" | "status";
}) {
  return (
    <div role={role} className={cn("rounded-md border px-3 py-2.5", tones[tone])}>
      <p className={cn("text-xs font-semibold", titles[tone])}>{title}</p>
      {children ? <div className="mt-1 text-xs leading-relaxed text-muted">{children}</div> : null}
    </div>
  );
}
