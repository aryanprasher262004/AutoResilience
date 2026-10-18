import { Card } from "@/components/ui/card";
import { RichText } from "@/components/ui/rich-text";
import { ONBOARDING_FACTS, TOUR_TARGET } from "@/lib/help-content";

/** What onboarding means and what it allows; the same text as Help and the tours. */
export function AboutOnboarding({ defaultOpen = true }: { defaultOpen?: boolean }) {
  return (
    <Card data-tour={TOUR_TARGET.applicationsAbout}>
      <details open={defaultOpen} className="group">
        <summary className="flex cursor-pointer items-center justify-between gap-3 px-4 py-3 text-sm text-fg">
          <span>
            About onboarding{" "}
            <span className="text-xs text-muted">read-only: nothing is installed or changed in the cluster</span>
          </span>
          <span aria-hidden className="text-xs text-faint group-open:rotate-180 motion-safe:transition-transform">
            ▾
          </span>
        </summary>
        <dl className="grid gap-x-6 gap-y-3 border-t border-line px-4 py-3 sm:grid-cols-2 xl:grid-cols-3">
          {ONBOARDING_FACTS.map((fact) => (
            <div key={fact.title}>
              <dt className="text-xs font-medium text-fg">{fact.title}</dt>
              <dd className="mt-0.5 text-xs leading-relaxed text-muted">
                <RichText text={fact.body} />
              </dd>
            </div>
          ))}
        </dl>
      </details>
    </Card>
  );
}
