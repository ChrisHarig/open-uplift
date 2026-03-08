import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import App from "../App";
import { renderWithRouter, mockFetchResponse } from "../test-utils";

function setupMocks() {
  vi.mocked(fetch).mockImplementation((url) => {
    const urlStr = typeof url === "string" ? url : "";
    if (urlStr.includes("sync/status")) {
      return mockFetchResponse({ last_synced: null });
    }
    if (urlStr.includes("uplift-outputs/summary")) {
      return mockFetchResponse({ total_responses: 0, total_measured_sessions: 0, outputs: [] });
    }
    if (urlStr.includes("uplift/distribution")) {
      return mockFetchResponse({ buckets: [], values: [], stats: { count: 0, avg: 0, median: 0, min: 0, max: 0 } });
    }
    if (urlStr.includes("uplift/by-scaffold")) {
      return mockFetchResponse([]);
    }
    if (urlStr.includes("uplift/by-model")) {
      return mockFetchResponse([]);
    }
    if (urlStr.includes("uplift-outputs/by-session")) {
      return mockFetchResponse({});
    }
    if (urlStr.includes("judge-outputs/summary")) {
      return mockFetchResponse({ fields: [], total_judged_sessions: 0 });
    }
    if (urlStr.includes("sessions")) {
      return mockFetchResponse({ sessions: [], total: 0 });
    }
    if (urlStr.includes("projects")) {
      return mockFetchResponse([]);
    }
    if (urlStr.includes("organizations")) {
      return mockFetchResponse([]);
    }
    if (urlStr.includes("jobs")) {
      return mockFetchResponse([]);
    }
    if (urlStr.includes("overview")) {
      return mockFetchResponse({
        totals: { total_sessions: 0, total_tokens: 0, total_messages: 0, total_tool_calls: 0 },
        daily: [],
        self_reports: { avg_speedup_factor: 0, total_reports: 0 },
      });
    }
    return mockFetchResponse({});
  });
}

describe("App Routing", () => {
  beforeEach(() => {
    vi.mocked(fetch).mockReset();
    setupMocks();
  });

  it("renders without crash", () => {
    renderWithRouter(<App />);
    expect(document.body).toBeInTheDocument();
  });

  it("shows navigation", async () => {
    renderWithRouter(<App />);
    await waitFor(() => {
      const links = screen.getAllByRole("link");
      expect(links.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("renders overview on root path", async () => {
    renderWithRouter(<App />);
    await waitFor(() => {
      // "Overview" appears in both the nav link and the page title
      expect(screen.getAllByText("Overview").length).toBeGreaterThanOrEqual(1);
    });
  });

  it("renders sessions link in nav", async () => {
    renderWithRouter(<App />);
    await waitFor(() => {
      expect(screen.getByText("Sessions")).toBeInTheDocument();
    });
  });

  it("renders projects link in nav", async () => {
    renderWithRouter(<App />);
    await waitFor(() => {
      expect(screen.getByText("Projects")).toBeInTheDocument();
    });
  });

  it("renders settings link in nav", async () => {
    renderWithRouter(<App />);
    await waitFor(() => {
      expect(screen.getByText("Settings")).toBeInTheDocument();
    });
  });
});
