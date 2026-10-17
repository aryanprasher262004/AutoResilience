import { Badge } from "@autoresilience/ui/badge";
import { buttonClasses, type ButtonVariant } from "@autoresilience/ui/button";
import { cn } from "@autoresilience/ui/cn";
import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

export function Container({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("mx-auto w-full max-w-6xl px-5 sm:px-8", className)} {...props} />;
}

export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <p className={cn("font-mono text-xs font-medium tracking-[0.14em] text-accent uppercase", className)}>
      {children}
    </p>
  );
}

export function SectionHeading({
  eyebrow,
  title,
  children,
  id,
}: {
  eyebrow: string;
  title: ReactNode;
  children?: ReactNode;
  id?: string;
}) {
  return (
    <div className="reveal max-w-2xl">
      <Eyebrow>{eyebrow}</Eyebrow>
      <h2 id={id} className="mt-3 text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
        {title}
      </h2>
      {children ? <p className="mt-4 text-base leading-relaxed text-muted text-pretty">{children}</p> : null}
    </div>
  );
}

export function ButtonLink({
  variant = "secondary",
  className,
  ...props
}: ComponentProps<typeof Link> & { variant?: ButtonVariant }) {
  return <Link className={cn(buttonClasses(variant, "lg"), className)} {...props} />;
}

export function ExternalLink({ className, children, ...props }: ComponentProps<"a">) {
  return (
    <a target="_blank" rel="noreferrer" className={className} {...props}>
      {children}
      <span className="sr-only"> (opens in a new tab)</span>
    </a>
  );
}

export type Availability = "available" | "planned" | "placeholder";

const availability: Record<Availability, { label: string; tone: "success" | "warning" | "neutral" }> = {
  available: { label: "Available from source", tone: "success" },
  planned: { label: "Planned", tone: "warning" },
  placeholder: { label: "Placeholder", tone: "neutral" },
};

export function StatusBadge({ status, children }: { status: Availability; children?: ReactNode }) {
  const meta = availability[status];
  return (
    <Badge tone={meta.tone} dot>
      {children ?? meta.label}
    </Badge>
  );
}

export function Panel({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "rounded-xl border border-line bg-surface/80 shadow-[inset_0_1px_0_rgb(255_255_255/0.035)]",
        className,
      )}
      {...props}
    />
  );
}

/** Page intro for inner pages; every page has exactly one h1. */
export function PageHeader({
  eyebrow,
  title,
  status,
  children,
}: {
  eyebrow: string;
  title: string;
  status?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header className="relative overflow-hidden border-b border-line pt-36 pb-14 sm:pt-44">
      <div aria-hidden className="hero-grid absolute inset-0 -z-10" />
      <Container>
        <div className="flex flex-wrap items-center gap-3">
          <Eyebrow>{eyebrow}</Eyebrow>
          {status}
        </div>
        <h1 className="mt-4 max-w-3xl text-4xl font-semibold tracking-tight text-balance sm:text-5xl">{title}</h1>
        {children ? <div className="mt-5 max-w-2xl text-lg leading-relaxed text-muted text-pretty">{children}</div> : null}
      </Container>
    </header>
  );
}
