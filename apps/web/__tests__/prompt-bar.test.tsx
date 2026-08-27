import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PromptBar } from "@/components/prompt-bar";
import { ToastProvider } from "@/components/ui/Toast";
import { AGENTS, DEFAULT_AGENT } from "@/lib/agents";

function renderPromptBar() {
  return render(
    <ToastProvider>
      <PromptBar />
    </ToastProvider>,
  );
}

describe("PromptBar", () => {
  it("opens the palette when the floating trigger is clicked", async () => {
    const user = userEvent.setup();
    renderPromptBar();

    expect(screen.queryByRole("dialog", { name: "Prompt bar" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /ask anything/i }));

    expect(screen.getByRole("dialog", { name: "Prompt bar" })).toBeInTheDocument();
  });

  it("opens the palette with Cmd/Ctrl+K from anywhere", async () => {
    const user = userEvent.setup();
    renderPromptBar();

    await user.keyboard("{Meta>}k{/Meta}");

    expect(screen.getByRole("dialog", { name: "Prompt bar" })).toBeInTheDocument();
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    renderPromptBar();

    await user.click(screen.getByRole("button", { name: /ask anything/i }));
    expect(screen.getByRole("dialog", { name: "Prompt bar" })).toBeInTheDocument();

    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog", { name: "Prompt bar" })).not.toBeInTheDocument();
  });

  it("renders all five agents", async () => {
    const user = userEvent.setup();
    renderPromptBar();
    await user.click(screen.getByRole("button", { name: /ask anything/i }));

    for (const agent of AGENTS) {
      expect(screen.getByText(agent.name)).toBeInTheDocument();
    }
    expect(screen.getAllByRole("option")).toHaveLength(5);
  });

  it("moves the active row with arrow keys", async () => {
    const user = userEvent.setup();
    renderPromptBar();
    await user.click(screen.getByRole("button", { name: /ask anything/i }));

    const options = screen.getAllByRole("option");
    options.forEach((option) => expect(option).toHaveAttribute("aria-selected", "false"));

    await user.keyboard("{ArrowDown}");
    expect(screen.getAllByRole("option")[0]).toHaveAttribute("aria-selected", "true");

    await user.keyboard("{ArrowDown}");
    expect(screen.getAllByRole("option")[1]).toHaveAttribute("aria-selected", "true");
    expect(screen.getAllByRole("option")[0]).toHaveAttribute("aria-selected", "false");

    await user.keyboard("{ArrowUp}");
    expect(screen.getAllByRole("option")[0]).toHaveAttribute("aria-selected", "true");
  });

  it("submits the arrow-selected agent on Enter and toasts the routing", async () => {
    const user = userEvent.setup();
    renderPromptBar();
    await user.click(screen.getByRole("button", { name: /ask anything/i }));

    const kaviIndex = AGENTS.findIndex((agent) => agent.id === "kavi");
    await user.type(screen.getByRole("textbox", { name: "Instruction" }), "make 3 more variants");
    for (let i = 0; i <= kaviIndex; i += 1) {
      await user.keyboard("{ArrowDown}");
    }
    await user.keyboard("{Enter}");

    expect(screen.queryByRole("dialog", { name: "Prompt bar" })).not.toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('Routing to Kavi: "make 3 more variants"')).toBeInTheDocument();
    });
  });

  it("routes free text with no explicit selection to a sensible default agent", async () => {
    const user = userEvent.setup();
    renderPromptBar();
    await user.click(screen.getByRole("button", { name: /ask anything/i }));

    await user.type(screen.getByRole("textbox", { name: "Instruction" }), "what's trending in fitness");
    await user.keyboard("{Enter}");

    await waitFor(() => {
      expect(
        screen.getByText(`Routing to ${DEFAULT_AGENT.name}: "what's trending in fitness"`),
      ).toBeInTheDocument();
    });
  });
});
