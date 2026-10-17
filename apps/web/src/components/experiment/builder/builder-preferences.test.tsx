import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test } from "vitest";

import { STORAGE_KEY } from "@/lib/preferences";
import { mockApi } from "@/test/api";
import { experiment, services, validation } from "@/test/fixtures";
import { setUrl } from "@/test/navigation";
import { renderWithApi } from "@/test/render";

import { ExperimentBuilder } from "./experiment-builder";

beforeEach(() => localStorage.clear());

describe("Experiment builder with saved defaults", () => {
  test("pre-fills the fault from preferences and sends exactly what is shown to the server", async () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ version: 1, experimentDefaults: { durationSeconds: 45, affectedReplicas: 2, mode: "FORCE" } }),
    );
    setUrl("/experiments/new?namespace=shop&kind=Deployment&name=checkout");
    const blocked = experiment({ state: "VALIDATION_FAILED", affected_replicas: 2, validation_result: validation(false) });
    const api = mockApi()
      .on("GET", "/services", services())
      .on("POST", "/experiments", experiment({ affected_replicas: 2 }))
      .on("POST", `/experiments/${blocked.id}/validate`, blocked);
    const { user } = renderWithApi(<ExperimentBuilder />);

    expect(screen.getByLabelText("Deletion mode")).toHaveValue("FORCE");
    expect(screen.getByLabelText("Duration (seconds)")).toHaveValue(45);
    expect(screen.getByLabelText("Affected replicas")).toHaveValue(2);
    const summary = screen.getByRole("complementary", { name: "Summary" });
    await waitFor(() => expect(summary).toHaveTextContent(/2 of \d+ ready pods? deleted at once/));

    await user.type(screen.getByLabelText("Name"), "defaults run");
    await user.click(screen.getByRole("button", { name: "Check safety" }));

    await waitFor(() => expect(api.requests("POST", "/experiments")).toHaveLength(1));
    expect(api.requests("POST", "/experiments")[0].body).toMatchObject({
      pod_delete_mode: "FORCE",
      duration_seconds: 45,
      affected_replicas: 2,
    });
    // The server, not the preference, decides: its refusal is shown as returned.
    expect(await screen.findByText("Blocked by safety validation")).toBeInTheDocument();
  });
});
