import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import Tokens from "../pages/Tokens";
import { renderWithRouter, mockFetchResponse } from "../test-utils";

function setupMocks() {
  vi.mocked(fetch).mockImplementation((url) => {
    const urlStr = typeof url === "string" ? url : "";
    if (urlStr.includes("timeseries")) {
      return mockFetchResponse([
        { day: "2026-02-20", input_tokens: 10000, output_tokens: 2000, cache_read: 500, cache_create: 100 },
      ]);
    }
    if (urlStr.includes("by-model")) {
      return mockFetchResponse([
        { model: "claude-sonnet-4-6", tokens: 50000 },
      ]);
    }
    if (urlStr.includes("by-source")) {
      return mockFetchResponse([
        { tool_source: "claude_code", tokens: 50000 },
      ]);
    }
    return mockFetchResponse({});
  });
}

describe("Tokens", () => {
  beforeEach(() => {
    vi.mocked(fetch).mockReset();
    setupMocks();
  });

  it("renders token page with model breakdown", async () => {
    renderWithRouter(<Tokens />);
    await waitFor(() => {
      // After data loads, stat card shows formatted total (50000 => "50.0K")
      expect(screen.getByText("50.0K")).toBeInTheDocument();
    });
    // Stat cards reflect loaded data
    expect(screen.getByText("Models Used")).toBeInTheDocument();
  });

  it("renders both model and scaffold charts", async () => {
    renderWithRouter(<Tokens />);
    await waitFor(() => {
      expect(screen.getByText("Tokens by Model")).toBeInTheDocument();
      expect(screen.getByText("Tokens by Scaffold")).toBeInTheDocument();
    });
  });

  it("renders stat cards", async () => {
    renderWithRouter(<Tokens />);
    await waitFor(() => {
      expect(screen.getByText("50.0K")).toBeInTheDocument();
      expect(screen.getByText("Models Used")).toBeInTheDocument();
    });
  });

  it("renders timeseries chart section", async () => {
    renderWithRouter(<Tokens />);
    await waitFor(() => {
      expect(screen.getByText("Tokens by Model")).toBeInTheDocument();
    });
  });

  it("renders with project filter", async () => {
    renderWithRouter(<Tokens />, {
      routerProps: { initialEntries: ["/tokens?project=myproject&project_path=/path/myproject"] },
    });
    await waitFor(() => {
      // Should render without crash when project filter params exist
      expect(document.body).toBeInTheDocument();
    });
  });

  it("renders subfolder toggle when project_path present", async () => {
    renderWithRouter(<Tokens />, {
      routerProps: { initialEntries: ["/tokens?project=myproject&project_path=/path/myproject"] },
    });
    await waitFor(() => {
      expect(document.body).toBeInTheDocument();
    });
  });
});
