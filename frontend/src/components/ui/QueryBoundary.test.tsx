import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import * as Tooltip from "@radix-ui/react-tooltip";
import { MemoryRouter } from "react-router-dom";
import { ErrorState } from "./ErrorState";
import { EmptyState } from "./EmptyState";
import { FormField, HelpDisclosure, SectionHelp } from "./HelpDisclosure";
import { QueryBoundary } from "./QueryBoundary";
import { useDeepLinkTab } from "../../hooks/useDeepLinkTab";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./tabs";
import { useState, type ReactNode } from "react";

function withTooltip(ui: ReactNode) {
  return <Tooltip.Provider delayDuration={0}>{ui}</Tooltip.Provider>;
}

describe("ErrorState", () => {
  it("shows retry action when provided", async () => {
    const onRetry = vi.fn();
    const user = userEvent.setup();
    render(<ErrorState message="Boom" onRetry={onRetry} />);
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalled();
  });
});

describe("EmptyState", () => {
  it("renders optional action", () => {
    render(
      <EmptyState title="None" description="Empty" action={<button type="button">Add</button>} />
    );
    expect(screen.getByRole("button", { name: "Add" })).toBeInTheDocument();
  });
});

describe("HelpDisclosure", () => {
  it("progressively discloses help text", async () => {
    const user = userEvent.setup();
    render(
      <HelpDisclosure summary="More info">
        <p>Hidden details</p>
      </HelpDisclosure>
    );
    expect(screen.queryByText("Hidden details")).not.toBeVisible();
    await user.click(screen.getByText("More info"));
    expect(screen.getByText("Hidden details")).toBeVisible();
  });
});

describe("SectionHelp / FieldHelp", () => {
  it("exposes field help via accessible trigger", () => {
    render(
      withTooltip(
        <FormField label="Timezone" htmlFor="tz" help="IANA timezone for scheduling.">
          <input id="tz" />
        </FormField>
      )
    );
    expect(screen.getByLabelText("Timezone")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Help: Timezone" })).toBeInTheDocument();
  });

  it("keeps validation errors visible outside tooltips", () => {
    render(
      withTooltip(
        <FormField label="Name" htmlFor="name" error="Name is required">
          <input id="name" />
        </FormField>
      )
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Name is required");
  });

  it("renders SectionHelp as progressive disclosure", async () => {
    const user = userEvent.setup();
    render(
      <SectionHelp summary="About publishing">
        <p>Secondary copy</p>
      </SectionHelp>
    );
    expect(screen.queryByText("Secondary copy")).not.toBeVisible();
    await user.click(screen.getByText("About publishing"));
    expect(screen.getByText("Secondary copy")).toBeVisible();
  });
});

function FlakyBoundary() {
  const query = useQuery({
    queryKey: ["flaky-boundary"],
    queryFn: async () => {
      throw new Error("nope");
    },
    retry: false,
  });
  return (
    <QueryBoundary query={query} errorMessage="Could not load items.">
      {(data) => <div>{String(data)}</div>}
    </QueryBoundary>
  );
}

describe("QueryBoundary", () => {
  it("renders error with retry instead of spinner after failure", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <FlakyBoundary />
      </QueryClientProvider>
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load items.");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.queryByText(/Loading/i)).not.toBeInTheDocument();
  });
});

function TabDemo() {
  const [tab, setTab] = useDeepLinkTab("tab", ["a", "b"] as const, "a");
  const [draft, setDraft] = useState("unsaved");
  return (
    <div>
      <input aria-label="Draft" value={draft} onChange={(e) => setDraft(e.target.value)} />
      <Tabs value={tab} onValueChange={(v) => setTab(v as "a" | "b")}>
        <TabsList>
          <TabsTrigger value="a">A</TabsTrigger>
          <TabsTrigger value="b">B</TabsTrigger>
        </TabsList>
        <TabsContent value="a" forceMount hidden={tab !== "a"}>
          Panel A
        </TabsContent>
        <TabsContent value="b" forceMount hidden={tab !== "b"}>
          Panel B
        </TabsContent>
      </Tabs>
      <p>Active:{tab}</p>
    </div>
  );
}

describe("deep-link tabs", () => {
  it("keeps unsaved form values across keyboard tab changes", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/?tab=a"]}>
        <TabDemo />
      </MemoryRouter>
    );
    const draft = screen.getByLabelText("Draft");
    await user.clear(draft);
    await user.type(draft, "kept");
    await user.click(screen.getByRole("tab", { name: "B" }));
    expect(screen.getByText("Active:b")).toBeInTheDocument();
    expect(screen.getByLabelText("Draft")).toHaveValue("kept");
    await user.keyboard("{ArrowLeft}");
    expect(screen.getByText("Active:a")).toBeInTheDocument();
    expect(screen.getByLabelText("Draft")).toHaveValue("kept");
  });
});
