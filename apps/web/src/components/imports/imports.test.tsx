import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { apiError, json, mockApi } from "@/test/api";
import { APP_ID, IMPORT_ID, blocked, capabilities, importRead, preview } from "@/test/import-fixtures";
import { router } from "@/test/navigation";
import { renderWithApi } from "@/test/render";

import { ImportRoom } from "./import-room";
import { ImportWizard } from "./import-wizard";

const COMPOSE = "services:\n  web:\n    image: nginx:1.27-alpine\n";

async function loadFile(user: ReturnType<typeof renderWithApi>["user"], content = COMPOSE, name = "shop.compose.yaml") {
  const file = new File([content], name, { type: "application/yaml" });
  await user.upload(screen.getByLabelText("Compose file (compose.yaml)"), file);
  await waitFor(() => expect(screen.getByLabelText("Or paste it")).toHaveValue(content));
}

describe("Import wizard", () => {
  test("checks the file, shows the security review, then the plan; saving deploys nothing", async () => {
    const api = mockApi()
      .on("GET", "/imports/capabilities", capabilities())
      .on("POST", "/imports/preview", preview())
      .on("POST", "/imports", () => json(importRead(), 201));
    const { user } = renderWithApi(<ImportWizard />);
    await loadFile(user);
    expect(screen.getByLabelText("Import name")).toHaveValue("shop");
    await user.click(screen.getByRole("button", { name: "Check it" }));

    const [sent] = api.requests("POST", "/imports/preview");
    expect(sent.body).toEqual({
      name: "shop",
      traffic: [],
      source: { kind: "compose", filename: "shop.compose.yaml", content: COMPOSE },
    });
    const review = await screen.findByRole("heading", { name: "Security review" });
    const card = within(review.closest("section")!);
    expect(card.getByText("0 blocking")).toBeInTheDocument();
    expect(card.getByText(/environment variable\(s\) are not set/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Review the plan" }));
    expect(screen.getByRole("heading", { name: "Deployment plan" })).toBeInTheDocument();
    expect(screen.getByText(/Nothing outside ar-imp-shop is created or changed/)).toBeInTheDocument();
    expect(screen.getByText(/start order only, not evidence that they talk to each other/)).toBeInTheDocument();
    expect(screen.getByText(/Saving deploys nothing/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Save reviewed import" }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith(`/applications/imports/${IMPORT_ID}`));
    expect(api.requests("POST", `/imports/${IMPORT_ID}/deploy`)).toHaveLength(0);
  });

  test("blocking findings stop the wizard with their reasons and fixes", async () => {
    mockApi().on("GET", "/imports/capabilities", capabilities()).on("POST", "/imports/preview", blocked());
    const { user } = renderWithApi(<ImportWizard />);
    await loadFile(user, "services: {}", "unsafe-compose.yaml");
    await user.click(screen.getByRole("button", { name: "Check it" }));
    expect(await screen.findByText(/Docker socket would give the container control of the host/)).toBeInTheDocument();
    expect(screen.getByText("Not deployable as it is")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review the plan" })).toBeDisabled();
    expect(screen.getAllByText("Blocking").length).toBeGreaterThan(3);
  });

  test("load targets are chosen from the import's own Services and update the plan before saving", async () => {
    const api = mockApi().on("GET", "/imports/capabilities", capabilities()).on("POST", "/imports/preview", preview());
    const { user } = renderWithApi(<ImportWizard />);
    await loadFile(user);
    await user.click(screen.getByRole("button", { name: "Check it" }));
    await user.click(await screen.findByRole("button", { name: "Review the plan" }));
    const picker = within(screen.getByRole("heading", { name: "Load generator (optional)" }).closest("section")!);
    expect(picker.getAllByRole("checkbox").map((c) => c.closest("label")!.textContent)).toEqual(["api", "web"]);
    await user.click(picker.getByRole("checkbox", { name: "api" }));
    await user.clear(picker.getByRole("textbox", { name: "HTTP path for api" }));
    await user.type(picker.getByRole("textbox", { name: "HTTP path for api" }), "/version");
    expect(screen.getByRole("button", { name: "Save reviewed import" })).toBeDisabled();
    await user.click(picker.getByRole("button", { name: "Update the plan" }));
    await waitFor(() => expect(api.requests("POST", "/imports/preview")).toHaveLength(2));
    expect(api.requests("POST", "/imports/preview")[1].body).toMatchObject({
      traffic: [{ service: "api", port: 9898, path: "/version" }],
    });
    await waitFor(() => expect(screen.getByRole("button", { name: "Save reviewed import" })).toBeEnabled());
  });

  test("an engine that cannot deploy still lets the plan be reviewed and saved, and says why", async () => {
    mockApi().on("GET", "/imports/capabilities", capabilities(false)).on("POST", "/imports/preview", preview());
    const { user } = renderWithApi(<ImportWizard />);
    await loadFile(user);
    await user.click(screen.getByRole("button", { name: "Check it" }));
    await user.click(await screen.findByRole("button", { name: "Review the plan" }));
    expect(screen.getByText("Deployment is not available on this engine")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save reviewed import" })).toBeEnabled();
  });

  test("offers the read-only Kubernetes connection instead", async () => {
    mockApi().on("GET", "/imports/capabilities", capabilities());
    renderWithApi(<ImportWizard />);
    expect(screen.getByRole("link", { name: /Kubernetes connection/ })).toHaveAttribute("href", "/applications/new");
  });

  test("server field errors are shown on the field", async () => {
    mockApi()
      .on("GET", "/imports/capabilities", capabilities())
      .on("POST", "/imports/preview", () =>
        apiError(422, [{ loc: ["body", "name"], msg: "use 1-30 lowercase letters", type: "value_error" }]),
      );
    const { user } = renderWithApi(<ImportWizard />);
    await loadFile(user);
    await user.click(screen.getByRole("button", { name: "Check it" }));
    expect(await screen.findByText("use 1-30 lowercase letters", { selector: "p" })).toBeInTheDocument();
  });
});

describe("Import page", () => {
  test("a saved import is deployed only after confirming the exact plan", async () => {
    const api = mockApi()
      .on("GET", `/imports/${IMPORT_ID}`, importRead())
      .on("GET", "/imports/capabilities", capabilities())
      .on("POST", `/imports/${IMPORT_ID}/deploy`, importRead("DEPLOYING"))
      .on("POST", `/imports/${IMPORT_ID}/refresh`, importRead("DEPLOYING"));
    const { user } = renderWithApi(<ImportRoom id={IMPORT_ID} />);
    expect(await screen.findByText("Reviewed · not deployed")).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Deploy" }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent(`digest ${preview().plan!.digest.slice(0, 12)}`);
    expect(dialog).toHaveTextContent("No experiment starts");
    expect(api.requests("POST", `/imports/${IMPORT_ID}/deploy`)).toHaveLength(0);
    await user.click(within(dialog).getByRole("button", { name: "Deploy this plan" }));
    await waitFor(() => expect(api.requests("POST", `/imports/${IMPORT_ID}/deploy`)).toHaveLength(1));
    expect(api.requests("POST", `/imports/${IMPORT_ID}/deploy`)[0].body).toEqual({
      plan_digest: preview().plan!.digest,
      confirm: true,
    });
    expect(await screen.findByText("Deploying")).toBeInTheDocument();
  });

  test("deploying shows each workload's progress from read-only health checks", async () => {
    const deploying = importRead("DEPLOYING");
    deploying.deployment.workloads = [
      { name: "web", kind: "Deployment", state: "READY", ready: 2, desired: 2, detail: "2/2 ready" },
      { name: "api", kind: "Deployment", state: "PROGRESSING", ready: 0, desired: 1, detail: "0/1 ready" },
    ];
    const api = mockApi()
      .on("GET", `/imports/${IMPORT_ID}`, deploying)
      .on("GET", "/imports/capabilities", capabilities())
      .on("POST", `/imports/${IMPORT_ID}/refresh`, deploying);
    renderWithApi(<ImportRoom id={IMPORT_ID} />);
    expect(await screen.findByText("Starting 0/1")).toBeInTheDocument();
    expect(screen.getByText("Ready 2/2")).toBeInTheDocument();
    expect(api.requests("POST", `/imports/${IMPORT_ID}/refresh`).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "Deploy" })).not.toBeInTheDocument();
  });

  test("a failure says what happened and what to do, and offers retry and removal", async () => {
    const failed = importRead("FAILED", {});
    failed.deployment.error = "Image pull failed: ErrImagePull: ghcr.io/example/missing:1.0";
    failed.deployment.recovery = "Check that the image name and tag exist and are public.";
    mockApi().on("GET", `/imports/${IMPORT_ID}`, failed).on("GET", "/imports/capabilities", capabilities());
    renderWithApi(<ImportRoom id={IMPORT_ID} />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("ErrImagePull");
    expect(alert).toHaveTextContent("image name and tag exist");
    expect(screen.getByRole("button", { name: "Retry deployment" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Remove deployment" })).toBeEnabled();
  });

  test("ready: the topology opens; removal needs the typed name", async () => {
    const api = mockApi()
      .on("GET", `/imports/${IMPORT_ID}`, importRead("READY"))
      .on("GET", "/imports/capabilities", capabilities())
      .on("POST", `/imports/${IMPORT_ID}/remove`, importRead("REMOVING"))
      .on("POST", `/imports/${IMPORT_ID}/refresh`, importRead("REMOVING"));
    const { user } = renderWithApi(<ImportRoom id={IMPORT_ID} />);
    expect(await screen.findByRole("link", { name: "Open topology" })).toHaveAttribute("href", `/applications/${APP_ID}`);
    await user.click(screen.getByRole("button", { name: "Remove deployment" }));
    const dialog = within(screen.getByRole("dialog"));
    expect(dialog.getByText(/only after the engine verifies that the namespace/)).toBeInTheDocument();
    const confirm = dialog.getByRole("button", { name: "Remove" });
    expect(confirm).toBeDisabled();
    await user.type(dialog.getByLabelText("Type shop to confirm"), "shop");
    await user.click(confirm);
    await waitFor(() => expect(api.requests("POST", `/imports/${IMPORT_ID}/remove`)).toHaveLength(1));
    expect(api.requests("POST", `/imports/${IMPORT_ID}/remove`)[0].body).toEqual({ confirm_name: "shop" });
  });

  test("without a provisioner, deploying is disabled with the reason", async () => {
    mockApi().on("GET", `/imports/${IMPORT_ID}`, importRead()).on("GET", "/imports/capabilities", capabilities(false));
    renderWithApi(<ImportRoom id={IMPORT_ID} />);
    expect(await screen.findByText("Deployment is not available on this engine")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Deploy" })).toBeDisabled());
  });
});
