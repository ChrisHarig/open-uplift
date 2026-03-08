import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { render } from "@testing-library/react";
import OrganizationDetail from "../pages/OrganizationDetail";
import { mockFetchResponse } from "../test-utils";

function setupMocks() {
  vi.mocked(fetch).mockImplementation((url) => {
    const urlStr = typeof url === "string" ? url : "";
    if (urlStr.includes("analytics")) {
      return mockFetchResponse({
        totals: { total_sessions: 10, total_tokens: 50000, total_messages: 100, total_tool_calls: 30, total_cost: 1.5 },
        uplift: { count: 3, avg_uplift: 2.8 },
        daily: [],
        uplift_timeseries: [],
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
    if (urlStr.includes("hub-info")) {
      return mockFetchResponse({ members: [], invites: [] });
    }
    if (urlStr.includes("organizations/test-org")) {
      return mockFetchResponse({
        org_id: "test-org",
        name: "Test Organization",
        description: "A test organization",
        is_verified: 1,
        folders: [
          { folder_path: "/path/project1", added_at: "2026-02-20T10:00:00Z" },
          { folder_path: "/path/project2", added_at: "2026-02-20T10:00:00Z" },
        ],
        stats: { total_sessions: 10, total_tokens: 50000, total_messages: 100, total_cost: 1.5 },
      });
    }
    if (urlStr.includes("unassigned")) {
      return mockFetchResponse([]);
    }
    if (urlStr.includes("remote-aggregate")) {
      return mockFetchResponse({ aggregate: null, pulled_at: null });
    }
    if (urlStr.includes("org-memberships")) {
      return mockFetchResponse([]);
    }
    return mockFetchResponse({});
  });
}

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={["/organizations/test-org"]}>
      <Routes>
        <Route path="/organizations/:orgId" element={<OrganizationDetail />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("OrganizationDetail", () => {
  beforeEach(() => {
    vi.mocked(fetch).mockReset();
    setupMocks();
  });

  it("renders org name", async () => {
    renderDetail();
    await waitFor(() => {
      expect(screen.getByText("Test Organization")).toBeInTheDocument();
    });
  });

  it("renders folder table", async () => {
    renderDetail();
    await waitFor(() => {
      expect(screen.getByText("/path/project1")).toBeInTheDocument();
      expect(screen.getByText("/path/project2")).toBeInTheDocument();
    });
  });

  it("renders uplift stat cards", async () => {
    renderDetail();
    await waitFor(() => {
      expect(screen.getAllByText("Uplift", { exact: false }).length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("Local Sessions", { exact: false }).length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("Pushed Sessions", { exact: false }).length).toBeGreaterThanOrEqual(1);
    });
  });

  it("renders session and folder stats", async () => {
    renderDetail();
    await waitFor(() => {
      expect(screen.getAllByText("Sessions", { exact: false }).length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText("Folders")).toBeInTheDocument();
    });
  });

  it("has back button", async () => {
    renderDetail();
    await waitFor(() => {
      expect(screen.getByText("Test Organization")).toBeInTheDocument();
    });
    const buttons = screen.getAllByRole("button");
    expect(buttons.length).toBeGreaterThanOrEqual(1);
  });

  it("shows description", async () => {
    renderDetail();
    await waitFor(() => {
      expect(screen.getByText("A test organization")).toBeInTheDocument();
    });
  });

  it("renders without crash", async () => {
    renderDetail();
    await waitFor(() => {
      expect(screen.getByText("Test Organization")).toBeInTheDocument();
    });
    expect(document.body).toBeInTheDocument();
  });
});
