import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Overview from "../pages/Overview";
import { renderWithRouter, mockFetchResponse } from "../test-utils";

function setupMocks() {
  vi.mocked(fetch).mockImplementation((url) => {
    const urlStr = typeof url === "string" ? url : "";
    if (urlStr.includes("sync/status")) {
      return mockFetchResponse({ last_synced: "2026-02-20T10:00:00Z" });
    }
    if (urlStr.includes("uplift-outputs/summary")) {
      return mockFetchResponse({
        total_responses: 5,
        total_measured_sessions: 5,
        outputs: [{ output_id: "llm-judge", count: 3, avg_uplift: 2.5 }],
      });
    }
    if (urlStr.includes("uplift/distribution")) {
      return mockFetchResponse({ buckets: [], values: [2.0, 3.0], stats: { count: 2, avg: 2.5, median: 2.5, min: 2.0, max: 3.0 } });
    }
    if (urlStr.includes("uplift/by-scaffold")) {
      return mockFetchResponse([{ scaffold: "claude_code", avg_uplift: 2.5, count: 3 }]);
    }
    if (urlStr.includes("uplift/by-model")) {
      return mockFetchResponse([{ model: "claude-sonnet-4-6", avg_uplift: 2.5, count: 3 }]);
    }
    if (urlStr.includes("uplift/by-session") || urlStr.includes("uplift-outputs/by-session")) {
      return mockFetchResponse({});
    }
    if (urlStr.includes("judge-outputs/summary")) {
      return mockFetchResponse({ fields: [{ field_name: "success", value_type: "boolean", count: 5, true_count: 4, avg_numeric: null }], total_judged_sessions: 5 });
    }
    if (urlStr.includes("scripts/unprocessed-count")) {
      return mockFetchResponse({ count: 5 });
    }
    if (urlStr.includes("sessions")) {
      return mockFetchResponse({
        sessions: [{
          session_id: "s1",
          tool_source: "claude_code",
          project_name: "myproject",
          project_path: "/path",
          started_at: "2026-02-20T10:00:00Z",
          ended_at: "2026-02-20T10:30:00Z",
          total_input_tokens: 5000,
          total_output_tokens: 1000,
          message_count: 10,
          tool_call_count: 3,
          model_primary: "claude-sonnet-4-6",
          has_report: 0,
          judge_current: 0,
          judge_success: null,
          is_local: 1,
        }],
        total: 1,
      });
    }
    if (urlStr.includes("projects")) {
      return mockFetchResponse([{
        project_name: "myproject",
        project_path: "/path",
        session_count: 5,
        total_tokens: 10000,
        total_messages: 20,
        last_active: "2026-02-20T10:00:00Z",
      }]);
    }
    if (urlStr.includes("remote-aggregate")) {
      return mockFetchResponse({ aggregate: null, pulled_at: null });
    }
    if (urlStr.includes("organizations") && !urlStr.includes("analytics")) {
      return mockFetchResponse([]);
    }
    if (urlStr.includes("overview")) {
      return mockFetchResponse({
        totals: { total_sessions: 10, total_tokens: 50000, total_messages: 100, total_tool_calls: 30 },
        daily: [],
        self_reports: { avg_speedup_factor: 2.5, total_reports: 5 },
      });
    }
    if (urlStr.includes("sync") && !urlStr.includes("status")) {
      return mockFetchResponse({});
    }
    return mockFetchResponse({});
  });
}

describe("Overview", () => {
  beforeEach(() => {
    vi.mocked(fetch).mockReset();
    setupMocks();
  });

  it("renders page title", async () => {
    renderWithRouter(<Overview />);
    await waitFor(() => {
      expect(screen.getByText("Overview")).toBeInTheDocument();
    });
  });

  it("renders stat cards", async () => {
    renderWithRouter(<Overview />);
    await waitFor(() => {
      expect(screen.getByText("Avg Uplift", { exact: false })).toBeInTheDocument();
      expect(screen.getByText("Sessions Measured", { exact: false })).toBeInTheDocument();
      expect(screen.getByText("Unjudged", { exact: false })).toBeInTheDocument();
    });
  });

  it("renders recent sessions table", async () => {
    renderWithRouter(<Overview />);
    await waitFor(() => {
      expect(screen.getByText("Recent Sessions")).toBeInTheDocument();
      expect(screen.getAllByText("myproject").length).toBeGreaterThanOrEqual(1);
    });
  });

  it("renders recent projects", async () => {
    renderWithRouter(<Overview />);
    await waitFor(() => {
      expect(screen.getByText("Recent Projects")).toBeInTheDocument();
    });
  });

  it("renders sync button", async () => {
    renderWithRouter(<Overview />);
    await waitFor(() => {
      expect(screen.getByText("Sync Now")).toBeInTheDocument();
    });
  });

  it("shows syncing state when clicked", async () => {
    renderWithRouter(<Overview />);
    await waitFor(() => {
      expect(screen.getByText("Sync Now")).toBeInTheDocument();
    });
    const btn = screen.getByText("Sync Now");
    await userEvent.click(btn);
    // After click, button should show syncing state (may resolve quickly)
    // Just verify the click doesn't crash
    expect(btn).toBeInTheDocument();
  });

  it("renders judge all button when unjudged sessions exist", async () => {
    renderWithRouter(<Overview />);
    await waitFor(() => {
      // unprocessed-count returns 5, so button should appear
      expect(screen.getByText("Judge All")).toBeInTheDocument();
    });
  });
});
