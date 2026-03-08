import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Sessions from "../pages/Sessions";
import { renderWithRouter, mockFetchResponse } from "../test-utils";

const BASE_SESSION = {
  session_id: "s1",
  tool_source: "claude_code",
  project_name: "myproject",
  project_path: "/path/myproject",
  git_branch: "main",
  started_at: "2026-02-20T10:00:00Z",
  ended_at: "2026-02-20T10:30:00Z",
  total_input_tokens: 5000,
  total_output_tokens: 1000,
  message_count: 10,
  tool_call_count: 3,
  model_primary: "claude-sonnet-4-6",
  has_report: 0,
  compaction_current: 0,
  judge_current: 0,
  judge_success: null,
  is_local: 1,
};

function setupMocks(sessionOverrides: Record<string, unknown> = {}, upliftData: Record<string, Record<string, number>> = {}) {
  const mock = vi.mocked(fetch);
  mock.mockImplementation((url) => {
    const urlStr = typeof url === "string" ? url : "";
    if (urlStr.includes("filter-options")) {
      return mockFetchResponse({ models: ["claude-sonnet-4-6"], scaffolds: ["claude_code"], projects: ["myproject"] });
    }
    if (urlStr.includes("organizations")) {
      return mockFetchResponse([]);
    }
    if (urlStr.includes("survey-responses")) {
      return mockFetchResponse([]);
    }
    if (urlStr.includes("uplift")) {
      return mockFetchResponse(upliftData);
    }
    if (urlStr.includes("script-config")) {
      return mockFetchResponse({ compaction: {}, judge: {} });
    }
    if (urlStr.includes("sessions")) {
      return mockFetchResponse({
        sessions: [{ ...BASE_SESSION, ...sessionOverrides }],
        total: 1,
      });
    }
    return mockFetchResponse({});
  });
}

describe("Sessions", () => {
  beforeEach(() => {
    vi.mocked(fetch).mockReset();
    setupMocks();
  });

  it("renders session table", async () => {
    renderWithRouter(<Sessions />);
    await waitFor(() => {
      expect(screen.getByText("myproject")).toBeInTheDocument();
    });
  });

  it("shows filter bar with model dropdown", async () => {
    renderWithRouter(<Sessions />);
    await waitFor(() => {
      expect(screen.getByText("myproject")).toBeInTheDocument();
    });
    // Filter dropdowns are present
    const selects = screen.getAllByRole("combobox");
    expect(selects.length).toBeGreaterThanOrEqual(1);
  });

  it("checkbox selection works", async () => {
    renderWithRouter(<Sessions />);
    await waitFor(() => {
      expect(screen.getByText("myproject")).toBeInTheDocument();
    });

    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes.length).toBeGreaterThanOrEqual(1);
  });

  it("batch action buttons exist", async () => {
    renderWithRouter(<Sessions />);
    await waitFor(() => {
      expect(screen.getByText("myproject")).toBeInTheDocument();
    });

    // Look for batch action buttons
    const compactBtns = screen.queryAllByText(/^Compact/i);
    const judgeBtns = screen.queryAllByText(/^Judge/i);
    expect(compactBtns.length + judgeBtns.length).toBeGreaterThanOrEqual(1);
  });

  it("shows green badge when judge_current=1 with uplift data", async () => {
    setupMocks(
      { judge_current: 1, judge_success: "true" },
      { s1: { "llm-judge": 2.5 } },
    );
    renderWithRouter(<Sessions />);
    await waitFor(() => {
      expect(screen.getByText("myproject")).toBeInTheDocument();
    });
    const badge = screen.getByTitle("Judged (up to date)");
    expect(badge).toBeInTheDocument();
    expect(badge.style.background).toBe("rgb(22, 163, 74)"); // #16a34a
  });

  it("shows yellow/stale badge when judge_current=0 with uplift data", async () => {
    setupMocks(
      { judge_current: 0 },
      { s1: { "llm-judge": 1.8 } },
    );
    renderWithRouter(<Sessions />);
    await waitFor(() => {
      expect(screen.getByText("myproject")).toBeInTheDocument();
    });
    const badge = screen.getByTitle("Judged (stale \u2014 session has new messages)");
    expect(badge).toBeInTheDocument();
    expect(badge.style.background).toBe("rgb(245, 158, 11)"); // #f59e0b
  });

  it("shows empty badge when not judged", async () => {
    setupMocks({ judge_current: 0 });
    renderWithRouter(<Sessions />);
    await waitFor(() => {
      expect(screen.getByText("myproject")).toBeInTheDocument();
    });
    const badge = screen.getByTitle("Not judged");
    expect(badge).toBeInTheDocument();
    expect(badge.style.background).toBe("transparent");
  });

  it("shows stale uplift value as a link without warning icon", async () => {
    setupMocks(
      { judge_current: 0 },
      { s1: { "llm-judge": 3.0 } },
    );
    renderWithRouter(<Sessions />);
    await waitFor(() => {
      expect(screen.getByText("myproject")).toBeInTheDocument();
    });
    const link = screen.getByText("3x");
    expect(link).toBeInTheDocument();
    expect(link.closest("a")).toHaveAttribute("href", "/sessions/s1/transcript#judge");
  });

  it("displays uplift factor as Nx", async () => {
    setupMocks(
      { judge_current: 1 },
      { s1: { "llm-judge": 2.5 } },
    );
    renderWithRouter(<Sessions />);
    await waitFor(() => {
      expect(screen.getByText("2.5x")).toBeInTheDocument();
    });
  });

  it("shows dash when no uplift", async () => {
    setupMocks({ judge_current: 0 });
    renderWithRouter(<Sessions />);
    await waitFor(() => {
      expect(screen.getByText("myproject")).toBeInTheDocument();
    });
    const dash = screen.getByText("—");
    expect(dash).toBeInTheDocument();
    expect(dash).toHaveClass("dash-disabled");
  });
});
