"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { useApplications } from "@/lib/api/queries";
import { formatRelative } from "@/lib/format";

import { ClusterRoleBadge, contextLabel } from "./cluster-badge";

export const applicationHref = (id: string) => `/applications/${encodeURIComponent(id)}`;

export function ApplicationsView() {
  const router = useRouter();
  const { data, isPending, isError, error, refetch } = useApplications();

  if (isPending) return <Card><LoadingState rows={4} label="Loading applications" /></Card>;
  if (isError) return <Card><ErrorState title="Could not load applications" message={error.message} onRetry={() => refetch()} /></Card>;
  if (!data.items.length)
    return (
      <Card>
        <EmptyState
          title="No applications onboarded yet"
          description="Onboarding picks a cluster the engine is authorized to read and the namespaces your application runs in, then shows its live topology. Nothing is written to the cluster."
          action={<ButtonLink href="/applications/new" variant="primary" size="sm">Onboard application</ButtonLink>}
        />
      </Card>
    );

  return (
    <Card>
      <Table>
        <THead>
          <tr>
            <TH>Application</TH>
            <TH>Cluster</TH>
            <TH>Namespaces</TH>
            <TH>Onboarded</TH>
          </tr>
        </THead>
        <TBody>
          {data.items.map((a) => (
            <TR key={a.id} className="cursor-pointer" onClick={() => router.push(applicationHref(a.id))}>
              <TD>
                <Link href={applicationHref(a.id)} className="font-medium hover:text-accent" onClick={(e) => e.stopPropagation()}>
                  {a.name}
                </Link>
              </TD>
              <TD>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-muted">{contextLabel(a.context)}</span>
                  <ClusterRoleBadge cluster={a.cluster} />
                </div>
              </TD>
              <TD className="font-mono text-xs text-muted">{a.namespaces.join(", ")}</TD>
              <TD className="text-xs text-muted">{formatRelative(a.created_at)}</TD>
            </TR>
          ))}
        </TBody>
      </Table>
    </Card>
  );
}
