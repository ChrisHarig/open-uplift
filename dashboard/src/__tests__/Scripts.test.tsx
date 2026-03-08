import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import Scripts from "../pages/Scripts";
import { renderWithRouter, mockFetchResponse } from "../test-utils";

function setupMocks() {
  vi.mocked(fetch).mockImplementation((url) => {
    const urlStr = typeof url === "string" ? url : "";
    if (urlStr.includes("script-config")) {
      return mockFetchResponse({
        compaction: {
          provider: "anthropic",
          model: "claude-haiku-4-5-20251001",
          prompt_id: "compaction-default",
        },
        judge: {
          provider: "anthropic",
          model: "claude-sonnet-4-6",
          prompt_id: "judge-default",
        },
      });
    }
    if (urlStr.includes("prompts")) {
      return mockFetchResponse([
        { prompt_id: "judge-default", category: "judge", name: "Default Judge", description: "", system_prompt: "...", is_default: 1 },
        { prompt_id: "compaction-default", category: "compaction", name: "Default Compaction", description: "", system_prompt: "...", is_default: 1 },
      ]);
    }
    if (urlStr.includes("api-keys")) {
      return mockFetchResponse([]);
    }
    return mockFetchResponse({});
  });
}

describe("Judge (Scripts)", () => {
  beforeEach(() => {
    vi.mocked(fetch).mockReset();
    setupMocks();
  });

  it("renders Judge page with configuration form", async () => {
    renderWithRouter(<Scripts />);
    await waitFor(() => {
      expect(screen.getAllByText("Judge").length).toBeGreaterThan(0);
      expect(screen.getByText("Save Configuration")).toBeInTheDocument();
    });
  });

  it("renders test runner section", async () => {
    renderWithRouter(<Scripts />);
    await waitFor(() => {
      expect(screen.getByText("Test Script")).toBeInTheDocument();
    });
  });
});
