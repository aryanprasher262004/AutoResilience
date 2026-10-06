import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/cn";

const control =
  "h-8 w-full rounded-md border border-line-strong bg-surface-2 px-2.5 text-sm text-fg " +
  "placeholder:text-faint focus-visible:border-accent focus-visible:outline-none " +
  "disabled:opacity-50 aria-invalid:border-danger";

export function Input({ className, ...props }: ComponentProps<"input">) {
  return <input className={cn(control, className)} {...props} />;
}

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return <textarea className={cn(control, "h-auto min-h-16 py-1.5", className)} {...props} />;
}

export function Select({ className, children, ...props }: ComponentProps<"select">) {
  return (
    <div className="relative">
      <select className={cn(control, "appearance-none pr-8", className)} {...props}>
        {children}
      </select>
      <svg
        aria-hidden
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        className="pointer-events-none absolute top-1/2 right-2.5 size-3.5 -translate-y-1/2 text-faint"
      >
        <path d="m6 9 6 6 6-6" />
      </svg>
    </div>
  );
}

/** Label + control + hint/error, wired for accessibility. */
export function Field({
  id,
  label,
  hint,
  error,
  children,
}: {
  id: string;
  label: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-xs font-medium text-muted">
        {label}
      </label>
      {children}
      {error ? (
        <p id={`${id}-error`} className="text-xs text-danger">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-xs text-faint">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
