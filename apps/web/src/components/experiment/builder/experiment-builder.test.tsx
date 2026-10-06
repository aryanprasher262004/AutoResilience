import { act, screen, waitFor } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { apiError, deferred, json, mockApi } from "@/test/api";
import { ID, experiment, services, validation } from "@/test/fixtures";
import { router, setUrl } from "@/test/navigation";
import { renderWithApi } from "@/test/render";

import { ExperimentBuilder } from "./experiment-builder";

const CREATED = experiment({ name: "checkout pod-delete" });
const VALIDATED = experiment({ name: "checkout pod-delete", state: "BASELINING", validation_result: validation(true) });
const BLOCKED = experiment({
  name: "checkout pod-delete",
  state: "VALIDATION_FAILED",
  affected_replicas: 3,
  validation_result: validation(false),
});
const STARTED = experiment({ ...VALIDATED, orchestration: { mode: "auto", requested_at: "2026-10-06T15:04:37Z" } });

function setup() {
  setUrl("/experiments/new");
  const api = mockApi().on("GET", "/services", services());
  return { api, ...renderWithApi(<ExperimentBuilder />) };
}

async function fill(user: UserEvent) {
  await user.type(screen.getByLabelText("Name"), "checkout pod-delete");
  await user.type(screen.getByLabelText("Namespace"), "shop");
  await user.type(screen.getByLabelText("Workload name"), "checkout");
}

const checkSafety = () => screen.getByRole("button", { name: "Check safety" });

describe("Experiment builder", () => {
  test("required fields are flagged locally and nothing is sent", async () => {
    const { api, user } = setup();

    await user.click(checkSafety());

    expect(screen.getAllByText("Required")).toHaveLength(3);
    expect(screen.getByLabelText("Name")).toHaveAttribute("aria-invalid", "true");
    expect(api.requests("POST", "/experiments")).toHaveLength(0);
  });

  test("server 422 errors are shown on the field they belong to", async () => {
    const { api, user } = setup();
    api.on("POST", "/experiments", () =>
      apiError(422, [
        {
          type: "string_pattern_mismatch",
          loc: ["body", "target", "namespace"],
          msg: "String should match pattern '^[a-z0-9]([-a-z0-9]*[a-z0-9])?$'",
        },
      ]),
    );
    await fill(user);
    await user.clear(screen.getByLabelText("Namespace"));
    await user.type(screen.getByLabelText("Namespace"), "Shop_NS");

    await user.click(checkSafety());

    expect(await screen.findByText("String should match pattern '^[a-z0-9]([-a-z0-9]*[a-z0-9])?$'")).toBeInTheDocument();
    expect(screen.getByLabelText("Namespace")).toHaveAttribute("aria-invalid", "true");
    expect(api.requests("POST", `/experiments/${ID}/validate`)).toHaveLength(0);
    expect(checkSafety()).toBeInTheDocument(); // still on Configure
  });

  test("passed validation shows the server's checks and allows continuing", async () => {
    const { api, user } = setup();
    api.on("POST", "/experiments", () => json(CREATED, 201)).on("POST", `/experiments/${ID}/validate`, VALIDATED);
    await fill(user);

    await user.click(checkSafety());

    expect(await screen.findByText("All safety checks passed")).toBeInTheDocument();
    expect(screen.getByText("2 ready - 1 affected = 1 remaining >= minimum 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue to review" })).toBeEnabled();
    expect(api.requests("POST", "/experiments")[0].body).toEqual({
      name: "checkout pod-delete",
      description: null,
      target: { namespace: "shop", name: "checkout", kind: "Deployment" },
      fault_type: "pod-delete",
      pod_delete_mode: "GRACEFUL",
      duration_seconds: 60,
      affected_replicas: 1,
    });
  });

  test("blocked validation shows the failed check and offers no way forward", async () => {
    const { api, user } = setup();
    api.on("POST", "/experiments", () => json(CREATED, 201)).on("POST", `/experiments/${ID}/validate`, BLOCKED);
    await fill(user);
    await user.clear(screen.getByLabelText("Affected replicas"));
    await user.type(screen.getByLabelText("Affected replicas"), "3");

    await user.click(checkSafety());

    expect(await screen.findByText("Blocked by safety validation")).toBeInTheDocument();
    expect(screen.getByText("Affected replicas 3 > limit 1")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Continue to review" })).not.toBeInTheDocument();
  });

  test("starting requires explicit confirmation, then navigates to the experiment room", async () => {
    const { api, user } = setup();
    api
      .on("POST", "/experiments", () => json(CREATED, 201))
      .on("POST", `/experiments/${ID}/validate`, VALIDATED)
      .on("POST", `/experiments/${ID}/run`, STARTED);
    await fill(user);
    await user.click(checkSafety());
    await user.click(await screen.findByRole("button", { name: "Continue to review" }));

    const start = screen.getByRole("button", { name: "Start experiment" });
    expect(start).toBeDisabled();
    await user.click(start);
    expect(api.requests("POST", `/experiments/${ID}/run`)).toHaveLength(0);

    await user.click(screen.getByRole("checkbox", { name: /I understand this will delete 1 pod of shop\/checkout/ }));
    await user.click(screen.getByRole("button", { name: "Start experiment" }));

    await waitFor(() => expect(router.push).toHaveBeenCalledWith(`/experiments/${ID}`));
    expect(api.requests("POST", `/experiments/${ID}/run`)).toHaveLength(1);
  });

  test("a failed start is reported and does not navigate", async () => {
    const { api, user } = setup();
    api
      .on("POST", "/experiments", () => json(CREATED, 201))
      .on("POST", `/experiments/${ID}/validate`, VALIDATED)
      .on("POST", `/experiments/${ID}/run`, () => apiError(409, "Experiment is already running"));
    await fill(user);
    await user.click(checkSafety());
    await user.click(await screen.findByRole("button", { name: "Continue to review" }));
    await user.click(screen.getByRole("checkbox"));

    await user.click(screen.getByRole("button", { name: "Start experiment" }));

    expect(await screen.findByText("Conflict (409): Experiment is already running")).toBeInTheDocument();
    expect(router.push).not.toHaveBeenCalled();
  });

  test("double submission creates one experiment and starts it once", async () => {
    const { api, user } = setup();
    const created = deferred();
    const started = deferred();
    api
      .on("POST", "/experiments", () => created.promise)
      .on("POST", `/experiments/${ID}/validate`, VALIDATED)
      .on("POST", `/experiments/${ID}/run`, () => started.promise);
    await fill(user);

    // Two submits in the same tick, before React can disable the button (fast double
    // click / Enter): only the in-flight guard stops the second one.
    const form = checkSafety().closest("form")!;
    act(() => {
      form.requestSubmit();
      form.requestSubmit();
    });
    await user.click(screen.getByRole("button", { name: "Checking…" })); // and while it is pending
    expect(api.requests("POST", "/experiments")).toHaveLength(1);
    created.resolve(json(CREATED, 201));

    await user.click(await screen.findByRole("button", { name: "Continue to review" }));
    await user.click(screen.getByRole("checkbox"));
    const start = screen.getByRole("button", { name: "Start experiment" });
    act(() => {
      start.click();
      start.click();
    });
    expect(screen.getByRole("button", { name: "Starting…" })).toBeDisabled();
    started.resolve(json(STARTED));

    await waitFor(() => expect(router.push).toHaveBeenCalledTimes(1));
    expect(api.requests("POST", "/experiments")).toHaveLength(1);
    expect(api.requests("POST", `/experiments/${ID}/validate`)).toHaveLength(1);
    expect(api.requests("POST", `/experiments/${ID}/run`)).toHaveLength(1);
  });

  test("a discovered workload fills the target; manual entry stays possible", async () => {
    const { user } = setup();

    const option = await screen.findByRole("option", { name: "shop/checkout · Deployment · 2/2 ready" });
    await user.selectOptions(screen.getByLabelText("Discovered workload"), option);

    expect(screen.getByLabelText("Namespace")).toHaveValue("shop");
    expect(screen.getByLabelText("Workload name")).toHaveValue("checkout");
    await user.clear(screen.getByLabelText("Workload name"));
    await user.type(screen.getByLabelText("Workload name"), "frontend");
    expect(screen.getByLabelText("Discovered workload")).toHaveValue("");
  });
});
