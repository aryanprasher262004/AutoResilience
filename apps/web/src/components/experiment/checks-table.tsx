import { Badge, type Tone } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import type { ValidationResult } from "@/lib/api/types";

const CHECK_TONE: Record<string, Tone> = {
  PASSED: "success",
  FAILED: "danger",
  ERROR: "warning",
  SKIPPED: "neutral",
};

type Check = ValidationResult["static_checks"][number];

/** Server validation checks, rendered exactly as returned. */
export function ChecksTable({
  title,
  description,
  checks,
}: {
  title: string;
  description: string;
  checks: Check[];
}) {
  return (
    <Card>
      <CardHeader title={title} description={description} />
      <Table>
        <THead>
          <tr>
            <TH className="w-28">Result</TH>
            <TH className="w-64">Check</TH>
            <TH>Server message</TH>
          </tr>
        </THead>
        <TBody>
          {checks.map((check) => (
            <TR key={check.name}>
              <TD>
                <Badge tone={CHECK_TONE[check.status] ?? "neutral"} dot>
                  {check.status}
                </Badge>
              </TD>
              <TD className="font-mono text-xs">{check.name}</TD>
              <TD className="text-xs text-muted">{check.message}</TD>
            </TR>
          ))}
        </TBody>
      </Table>
    </Card>
  );
}
