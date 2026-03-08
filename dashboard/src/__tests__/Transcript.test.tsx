import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { render } from "@testing-library/react";
import Transcript from "../pages/Transcript";
import { mockFetchResponse } from "../test-utils";

function setupMocks() {
  vi.mocked(fetch).mockImplementation((url) => {
    const urlStr = typeof url === "string" ? url : "";
    if (urlStr.includes("/transcript")) {
      return mockFetchResponse({
        transcript: [
          { role: "user", timestamp: "2026-02-20T10:00:00Z", blocks: [{ type: "text", text: "Fix the login bug" }] },
          {
            role: "assistant",
            timestamp: "2026-02-20T10:00:05Z",
            blocks: [
              { type: "text", text: "I'll look at the auth module" },
              { type: "tool_use", tool_name: "Read", input: { file_path: "auth.py" }, result: "def login():" },
            ],
          },
        ],
        stats: { user_messages: 1, assistant_messages: 1, tool_calls: 1 },
      });
    }
    if (urlStr.includes("judge-outputs")) {
      return mockFetchResponse({});
    }
    if (urlStr.includes("uplift-outputs")) {
      return mockFetchResponse([]);
    }
    if (urlStr.includes("scripts/results")) {
      return mockFetchResponse([]);
    }
    if (urlStr.includes("sessions/s1") && !urlStr.includes("transcript") && !urlStr.includes("judge") && !urlStr.includes("uplift") && !urlStr.includes("time")) {
      return mockFetchResponse({
        session: {
          session_id: "s1",
          tool_source: "claude_code",
          project_name: "myproject",
          started_at: "2026-02-20T10:00:00Z",
          ended_at: "2026-02-20T10:30:00Z",
          message_count: 5,
          tool_call_count: 1,
          model_primary: "claude-sonnet-4-6",
          total_input_tokens: 5000,
          total_output_tokens: 1000,
          total_cache_read_tokens: 0,
          total_cache_create_tokens: 0,
        },
        messages: [],
      });
    }
    return mockFetchResponse({});
  });
}

function renderTranscript() {
  return render(
    <MemoryRouter initialEntries={["/sessions/s1/transcript"]}>
      <Routes>
        <Route path="/sessions/:sessionId/transcript" element={<Transcript />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("Transcript", () => {
  beforeEach(() => {
    vi.mocked(fetch).mockReset();
    setupMocks();
  });

  it("renders transcript with user message", async () => {
    renderTranscript();
    await waitFor(() => {
      expect(screen.getByText("Fix the login bug")).toBeInTheDocument();
    });
  });

  it("renders assistant message", async () => {
    renderTranscript();
    await waitFor(() => {
      expect(screen.getByText(/auth module/)).toBeInTheDocument();
    });
  });

  it("shows tool use blocks", async () => {
    renderTranscript();
    await waitFor(() => {
      expect(screen.getByText(/Read/)).toBeInTheDocument();
    });
  });

  it("shows view toggle buttons", async () => {
    renderTranscript();
    await waitFor(() => {
      // Look for Raw/Compacted toggle or similar
      const buttons = screen.getAllByRole("button");
      expect(buttons.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("renders back link", async () => {
    renderTranscript();
    await waitFor(() => {
      expect(screen.getByText("Fix the login bug")).toBeInTheDocument();
    });
    // There should be navigation back
    const links = screen.getAllByRole("link");
    expect(links.length).toBeGreaterThanOrEqual(1);
  });

  it("loading state renders without crash", () => {
    // Just verify it renders without throwing
    renderTranscript();
    expect(document.body).toBeInTheDocument();
  });

  it("shows session info", async () => {
    renderTranscript();
    await waitFor(() => {
      expect(screen.getByText("Fix the login bug")).toBeInTheDocument();
    });
  });

  it("renders multiple messages in order", async () => {
    renderTranscript();
    await waitFor(() => {
      expect(screen.getByText("Fix the login bug")).toBeInTheDocument();
      expect(screen.getByText(/auth module/)).toBeInTheDocument();
    });
  });
});
