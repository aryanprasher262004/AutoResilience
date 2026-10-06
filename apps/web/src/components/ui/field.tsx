import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/cn";

const control =
  "h-8 w-full rounded-md border border-line-strong bg-surface-2 px-2.5 text-sm text-fg " +
  "placeholder:text-faint focus-visible:border-accent focus-visible:outline-none " +
  "disabled:opacity-50 aria-invalid:border-danger";

export function Input({ className, ...props }: ComponentProps<"input">) {
  return <input className={cn(control, className)} {...props} />;
}

export function Select({ className, children, ...props }: ComponentProps<"select">) {
  return (
    <select className={cn(control, "appearance-none pr-8", className)} {...props}>
      {children}
    </select>
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
