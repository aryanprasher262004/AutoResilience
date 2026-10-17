import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

import {
  buttonClasses,
  type ButtonSize as Size,
  type ButtonVariant as Variant,
} from "@autoresilience/ui/button";

import { cn } from "@/lib/cn";

export { buttonClasses };

type ButtonProps = ComponentProps<"button"> & { variant?: Variant; size?: Size };

export function Button({ variant, size, className, type = "button", ...props }: ButtonProps) {
  return <button type={type} className={cn(buttonClasses(variant, size), className)} {...props} />;
}

type ButtonLinkProps = ComponentProps<typeof Link> & {
  variant?: Variant;
  size?: Size;
  children: ReactNode;
};

export function ButtonLink({ variant, size, className, ...props }: ButtonLinkProps) {
  return <Link className={cn(buttonClasses(variant, size), className)} {...props} />;
}
