import { ButtonLink } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/states";

export default function NotFound() {
  return (
    <EmptyState
      title="Page not found"
      description="This page does not exist in the AutoResilience console."
      action={<ButtonLink href="/">Go to Overview</ButtonLink>}
    />
  );
}
