import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import Overview from "../pages/Overview";
import { renderWithRouter, mockFetchResponse } from "../test-utils";

function setupMocks() {
  vi.mocked(fetch).mockImplementation((url) => {
    const urlStr = typeof url === "string" ? url : "";
    if (urlStr.includes("sync/status")) {
      return mockFetchResponse({ last_synced: new Date().toISOString() });
    }
    if (urlStr.includes("/api/overview")) {
      return mockFetchResponse({
        totals: { total_sessions: 20, total_tokens: 100000, total_messages: 50, total_tool_calls: 30 },
        daily: [],
        self_reports: { avg_speedup_factor: 0, total_reports: 0 },
      });
    }
    if (urlStr.includes("uplift-outputs/summary")) {
      return mockFetchResponse({
        total_responses: 10,
        total_measured_sessions: 12,
        outputs: [
          { output_id: "llm-judge", avg_uplift: 3.0, count: 12 },
        ],
      });
    }
    if (urlStr.includes("uplift/distribution")) {
      return mockFetchResponse({ buckets: [], values: [], stats: {} });
    }
    if (urlStr.includes("uplift/by-scaffold")) {
      return mockFetchResponse([]);
    }
    if (urlStr.includes("uplift/by-model")) {
      return mockFetchResponse([]);
    }
    if (urlStr.includes("judge-outputs/summary")) {
      return mockFetchResponse({ fields: [], total_judged_sessions: 0 });
    }
    if (urlStr.includes("uplift-outputs/by-session")) {
      return mockFetchResponse({});
    }
    if (urlStr.includes("sessions")) {
      return mockFetchResponse({
        sessions: [
          {
            session_id: "s1",
            tool_source: "claude-code",
            project_path: "/test",
            project_name: "test-project",
            git_branch: null,
            started_at: "2026-02-20T10:00:00Z",
            ended_at: null,
            total_input_tokens: 1000,
            total_output_tokens: 2000,
            total_cache_read_tokens: 0,
            total_cache_create_tokens: 0,
            message_count: 5,
            tool_call_count: 2,
            model_primary: "claude-sonnet-4-6",
            has_report: 1,
            compaction_current: 0,
            judge_current: 0,
          },
        ],
        total: 1,
      });
    }
    if (urlStr.includes("projects")) {
      return mockFetchResponse([
        {
          project_name: "test-project",
          project_path: "/test",
          session_count: 5,
          total_tokens: 50000,
          total_messages: 20,
          total_tool_calls: 10,
          last_active: "2026-02-20T10:00:00Z",
          org_id: null,
          org_name: null,
          org_is_verified: null,
        },
      ]);
    }
    if (urlStr.includes("organizations")) {
      return mockFetchResponse([]);
    }
    return mockFetchResponse({});
  });
}

describe("Overview (Dashboard)", () => {
  beforeEach(() => {
    vi.mocked(fetch).mockReset();
    setupMocks();
  });

  it("renders uplift stats and recent sections", async () => {
    renderWithRouter(<Overview />);
    await waitFor(() => {
      expect(screen.getByText("3.00x")).toBeInTheDocument();
    });
    expect(screen.getByText("Avg Uplift")).toBeInTheDocument();
    expect(screen.getByText("Recent Sessions")).toBeInTheDocument();
    expect(screen.getByText("Recent Projects")).toBeInTheDocument();
  });

  it("shows sync button", async () => {
    renderWithRouter(<Overview />);
    await waitFor(() => {
      expect(screen.getByText("Sync Now")).toBeInTheDocument();
    });
  });
});
