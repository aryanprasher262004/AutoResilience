"use client";

import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/states";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { useImports } from "@/lib/api/queries";
import { formatRelative } from "@/lib/format";
import { SOURCE_META, STATUS_META, importHref } from "@/lib/imports";

/** Imported applications (P7); hidden until there is one, so onboarding stays the default. */
export function ImportsList() {
  const { data, isError, error, refetch } = useImports();
  if (isError)
    return (
      <Card>
        <ErrorState title="Could not load imports" message={error.message} onRetry={() => refetch()} />
      </Card>
    );
  if (!data?.items.length) return null;
  return (
    <Card>
      <CardHeader
        title="Imported applications"
        description="Test deployments created from a file you reviewed, each in its own ar-imp-* namespace."
      />
      <Table>
        <THead>
          <tr>
            <TH>Import</TH>
            <TH>Status</TH>
            <TH>Source</TH>
            <TH>Namespace</TH>
            <TH>Saved</TH>
          </tr>
        </THead>
        <TBody>
          {data.items.map((i) => (
            <TR key={i.id}>
              <TD>
                <Link href={importHref(i.id)} className="font-medium hover:text-accent">
                  {i.name}
                </Link>
              </TD>
              <TD>
                <Badge tone={STATUS_META[i.status].tone} dot>
                  {STATUS_META[i.status].label}
                </Badge>
              </TD>
              <TD className="text-xs text-muted">{SOURCE_META[i.source].short}</TD>
              <TD className="font-mono text-xs text-muted">{i.namespace}</TD>
              <TD className="text-xs text-muted">{formatRelative(i.created_at)}</TD>
            </TR>
          ))}
        </TBody>
      </Table>
    </Card>
  );
}
