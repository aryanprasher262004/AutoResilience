import { describe, expect, test } from "vitest";

import { countBySeverity, groupFindings, suggestName } from "./imports";

describe("imports presentation", () => {
  test.each([
    ["compose.yaml", "my-app"],
    ["docker-compose.yml", "my-app"],
    ["shop.compose.yaml", "shop"],
    ["unsafe-compose.yaml", "unsafe"],
    ["ResilienceMart.yaml", "resiliencemart"],
    ["../../etc/9passwd", "etc-9passwd"],
    [null, "my-app"],
  ])("suggests a valid import name for %s", (file, name) => {
    expect(suggestName(file)).toBe(name);
    expect(suggestName(file)).toMatch(/^[a-z]([-a-z0-9]{0,28}[a-z0-9])?$/);
  });

  test("groups and counts findings without changing their order", () => {
    const f = (severity: "blocking" | "warning" | "info", subject: string | null) => ({ severity, code: "x", message: "m", subject });
    const findings = [f("blocking", "service a"), f("warning", "service b"), f("info", "service a"), f("info", null)];
    expect(groupFindings(findings).map((g) => [g.subject, g.items.length])).toEqual([
      ["service a", 2],
      ["service b", 1],
      ["The file", 1],
    ]);
    expect(countBySeverity(findings)).toEqual({ blocking: 1, warning: 1, info: 2 });
  });
});
