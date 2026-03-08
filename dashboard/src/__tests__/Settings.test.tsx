import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import Settings from "../pages/Settings";
import { renderWithRouter, mockFetchResponse } from "../test-utils";

function setupMocks() {
  vi.mocked(fetch).mockImplementation((url) => {
    const urlStr = typeof url === "string" ? url : "";
    if (urlStr.includes("sync/status")) {
      return mockFetchResponse({ last_synced: "2026-02-20T10:00:00Z" });
    }
    if (urlStr.includes("api-keys")) {
      return mockFetchResponse([]);
    }
    if (urlStr.includes("scaffolds")) {
      return mockFetchResponse([]);
    }
    if (urlStr.includes("user-profile")) {
      return mockFetchResponse({
        experience_description: "",
      });
    }
    if (urlStr.includes("run-modes")) {
      return mockFetchResponse({
        enabled: false,
        start_hour: 2,
        frequency_hours: 24.0,
      });
    }
    if (urlStr.includes("organizations")) {
      return mockFetchResponse([]);
    }
    if (urlStr.includes("org-memberships")) {
      return mockFetchResponse([]);
    }
    // Catch-all for any other API calls
    return mockFetchResponse({});
  });
}

describe("Settings", () => {
  beforeEach(() => {
    vi.mocked(fetch).mockReset();
    setupMocks();
  });

  it("renders sync button", async () => {
    renderWithRouter(<Settings />);
    await waitFor(() => {
      expect(screen.getByText(/Sync Now/i)).toBeInTheDocument();
    });
  });

  it("renders sync options section", async () => {
    renderWithRouter(<Settings />);
    await waitFor(() => {
      expect(screen.getByText(/Sync Now/i)).toBeInTheDocument();
      expect(screen.getByText(/Scheduled batch/i)).toBeInTheDocument();
    });
  });

  it("renders API key section", async () => {
    renderWithRouter(<Settings />);
    // API Keys heading is always rendered
    expect(screen.getByText("API Keys")).toBeInTheDocument();
  });

  it("renders developer profile section", async () => {
    renderWithRouter(<Settings />);
    expect(screen.getByText("Developer Profile")).toBeInTheDocument();
  });
});
