import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { apiError, mockApi } from "@/test/api";
import { router } from "@/test/navigation";
import { renderWithApi } from "@/test/render";
import { APP_ID, DISCOVERY, EXECUTION, application, namespaces, topology } from "@/test/topology-fixtures";

import { ApplicationRoom } from "./application-room";
import { ApplicationsView } from "./applications-view";
import { Onboarding } from "./onboarding";

vi.mock("@/components/topology/topology-graph", () => ({ TopologyGraph: () => <div data-testid="graph" /> }));

function clusters() {
  return mockApi().on("GET", "/clusters", { items: [EXECUTION, DISCOVERY] });
}

describe("Onboarding", () => {
  it("walks cluster → namespaces → workloads and saves exactly what was chosen", async () => {
    const api = clusters()
      .on("GET", "/clusters/namespaces", (r) =>
        Response.json(r.url.searchParams.get("context") === "kind-staging" ? namespaces(DISCOVERY) : namespaces()),
      )
      .on("GET", "/topology", topology(DISCOVERY))
      .on("POST", "/applications", () => Response.json(application({ context: "kind-staging", cluster: DISCOVERY }), { status: 201 }));
    const { user } = renderWithApi(<Onboarding />);

    await user.click(await screen.findByRole("radio", { name: /kind-staging/ }));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByRole("checkbox", { name: /payments/ })).toBeDisabled(); // 403
    expect(screen.getByRole("button", { name: "Discover workloads" })).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: /shop/ }));
    await user.click(screen.getByRole("button", { name: "Discover workloads" }));

    expect(await screen.findByText("Discovered workloads")).toBeInTheDocument();
    expect(await screen.findAllByText("checkout")).toHaveLength(2); // the workload and its Service
    expect(screen.queryByRole("link", { name: "New experiment" })).not.toBeInTheDocument();
    expect(screen.getByText("read-only")).toBeInTheDocument();
    const [topologyRequest] = api.requests("GET", "/topology");
    expect(topologyRequest.url.search).toBe("?context=kind-staging&namespace=shop");

    await user.click(screen.getByRole("button", { name: "Save and open topology" }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith(`/applications/${APP_ID}`));
    expect(api.requests("POST", "/applications")[0].body).toEqual({
      name: "shop",
      context: "kind-staging",
      namespaces: ["shop"],
    });
  });

  it("hands supported targets on the execution cluster to the experiment builder", async () => {
    clusters().on("GET", "/clusters/namespaces", namespaces()).on("GET", "/topology", topology());
    const { user } = renderWithApi(<Onboarding />);
    await user.click(await screen.findByRole("button", { name: "Continue" }));
    await user.click(await screen.findByRole("checkbox", { name: /shop/ }));
    await user.click(screen.getByRole("button", { name: "Discover workloads" }));
    expect(await screen.findByRole("link", { name: "New experiment" })).toHaveAttribute(
      "href",
      "/experiments/new?namespace=shop&kind=Deployment&name=checkout",
    );
  });

  it("maps the engine's validation errors back onto the form", async () => {
    clusters()
      .on("GET", "/clusters/namespaces", namespaces())
      .on("GET", "/topology", topology())
      .on("POST", "/applications", () =>
        apiError(422, [{ loc: ["body", "namespaces"], msg: "Not found or not readable with the engine's access: shop", type: "value_error" }]),
      );
    const { user } = renderWithApi(<Onboarding />);
    await user.click(await screen.findByRole("button", { name: "Continue" }));
    await user.click(await screen.findByRole("checkbox", { name: /shop/ }));
    await user.click(screen.getByRole("button", { name: "Discover workloads" }));
    await user.click(await screen.findByRole("button", { name: "Save and open topology" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Not found or not readable");
    expect(router.push).not.toHaveBeenCalled();
  });

  it("shows why a cluster cannot be read", async () => {
    clusters().on("GET", "/clusters/namespaces", () => apiError(503, "Kubernetes API unreachable: connection refused"));
    const { user } = renderWithApi(<Onboarding />);
    await user.click(await screen.findByRole("button", { name: "Continue" }));
    expect(await screen.findByText("Could not read namespaces")).toBeInTheDocument();
    expect(screen.getByText(/connection refused/)).toBeInTheDocument();
  });
});

describe("Applications", () => {
  it("lists applications and flags ones whose cluster is no longer authorized", async () => {
    mockApi().on("GET", "/applications", {
      items: [application(), application({ id: "x", name: "Staging", context: "kind-staging", cluster: null })],
    });
    renderWithApi(<ApplicationsView />);
    expect(await screen.findByText("Staging")).toBeInTheDocument();
    expect(screen.getByText("Execution cluster")).toBeInTheDocument();
    expect(screen.getByText("No longer authorized")).toBeInTheDocument();
  });

  it("does not read a cluster that is no longer authorized", async () => {
    const api = mockApi().on("GET", `/applications/${APP_ID}`, application({ cluster: null }));
    renderWithApi(<ApplicationRoom id={APP_ID} />);
    expect(await screen.findByText("This cluster is no longer authorized for the engine")).toBeInTheDocument();
    expect(api.requests("GET", `/applications/${APP_ID}/topology`)).toHaveLength(0);
  });

  it("forgets an application without touching anything else", async () => {
    const api = mockApi()
      .on("GET", `/applications/${APP_ID}`, application())
      .on("GET", `/applications/${APP_ID}/topology`, topology())
      .on("DELETE", `/applications/${APP_ID}`, () => new Response(null, { status: 204 }));
    const { user } = renderWithApi(<ApplicationRoom id={APP_ID} />);
    expect(await screen.findByTestId("graph")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Forget application" }));
    expect(screen.getByText(/Nothing in the cluster changes/)).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "Forget application" }).at(-1)!);
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/applications"));
    expect(api.requests("DELETE", `/applications/${APP_ID}`)).toHaveLength(1);
  });

  it("reports a missing application", async () => {
    mockApi().on("GET", `/applications/${APP_ID}`, () => apiError(404, "Application not found"));
    renderWithApi(<ApplicationRoom id={APP_ID} />);
    expect(await screen.findByText("Application not found")).toBeInTheDocument();
  });
});
