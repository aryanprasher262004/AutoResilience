/**
 * In-memory stand-in for next/navigation and next/link (the App Router is not mounted
 * in unit tests). The URL lives here, so URL-state behaviour is exercised for real.
 */
import { type AnchorHTMLAttributes, type MouseEvent, useMemo, useSyncExternalStore } from "react";
import { vi } from "vitest";

let current = new URL("http://localhost/");
const listeners = new Set<() => void>();

function navigate(href: string) {
  current = new URL(href, current);
  listeners.forEach((listener) => listener());
}

/** Set the URL a test starts at, e.g. setUrl("/experiments?q=x"). */
export function setUrl(href: string) {
  navigate(href);
}

export function currentUrl(): URL {
  return new URL(current);
}

export const router = {
  push: vi.fn((href: string) => navigate(href)),
  replace: vi.fn((href: string) => navigate(href)),
  back: vi.fn(),
  forward: vi.fn(),
  refresh: vi.fn(),
  prefetch: vi.fn(),
};

export function resetNavigation() {
  current = new URL("http://localhost/");
  Object.values(router).forEach((fn) => fn.mockClear());
}

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

export function useRouter() {
  return router;
}

export function usePathname() {
  return useSyncExternalStore(subscribe, () => current.pathname);
}

export function useSearchParams() {
  const search = useSyncExternalStore(subscribe, () => current.search);
  return useMemo(() => new URLSearchParams(search), [search]);
}

type LinkProps = AnchorHTMLAttributes<HTMLAnchorElement> & { href: string; prefetch?: boolean; scroll?: boolean; replace?: boolean };

export function Link({ href, onClick, replace, ...props }: LinkProps) {
  const rest = { ...props };
  delete rest.prefetch; // Next-only props: not valid on <a>
  delete rest.scroll;
  return (
    <a
      href={href}
      {...rest}
      onClick={(event: MouseEvent<HTMLAnchorElement>) => {
        onClick?.(event);
        if (event.defaultPrevented) return;
        event.preventDefault();
        (replace ? router.replace : router.push)(href);
      }}
    />
  );
}
