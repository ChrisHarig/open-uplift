import { describe, it, expect, vi, beforeEach } from "vitest";
import { api, fmt } from "../api";
import { mockFetchResponse } from "../test-utils";

beforeEach(() => {
  vi.mocked(fetch).mockReset();
});

describe("api.overview", () => {
  it("fetches overview data", async () => {
    const data = {
      totals: { total_sessions: 5, total_tokens: 100, total_messages: 20, total_tool_calls: 10 },
      daily: [],
      self_reports: { avg_speedup_factor: 2.5, total_reports: 3 },
    };
    vi.mocked(fetch).mockResolvedValueOnce(mockFetchResponse(data) as any);
    const result = await api.overview();
    expect(result.totals.total_sessions).toBe(5);
    expect(fetch).toHaveBeenCalledWith("/api/overview?days=30");
  });
});

describe("api.sessions", () => {
  it("fetches sessions with default params", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      mockFetchResponse({ sessions: [], total: 0 }) as any
    );
    await api.sessions(50, 0);
    expect(fetch).toHaveBeenCalledWith("/api/sessions?limit=50&offset=0");
  });

  it("includes filter params when provided", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      mockFetchResponse({ sessions: [], total: 0 }) as any
    );
    await api.sessions(10, 0, { model: "claude-sonnet-4-6", has_survey: "true" });
    const url = vi.mocked(fetch).mock.calls[0][0] as string;
    expect(url).toContain("model=claude-sonnet-4-6");
    expect(url).toContain("has_survey=true");
  });
});

describe("api.surveyResponses", () => {
  it("fetches survey responses", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(mockFetchResponse([]) as any);
    const result = await api.surveyResponses();
    expect(result).toEqual([]);
    expect(fetch).toHaveBeenCalledWith("/api/survey-responses");
  });
});

describe("api.jobs", () => {
  it("fetches jobs with status filter", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(mockFetchResponse([]) as any);
    await api.jobs("pending,running");
    expect(fetch).toHaveBeenCalledWith("/api/jobs?status=pending%2Crunning");
  });
});

describe("api.runBatchAsync", () => {
  it("posts batch run request", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      mockFetchResponse({ job_id: "j1" }) as any
    );
    const result = await api.runBatchAsync(["transcript-compact"], ["s1"]);
    expect(result.job_id).toBe("j1");
    expect(fetch).toHaveBeenCalledWith(
      "/api/scripts/run-batch",
      expect.objectContaining({ method: "POST" })
    );
  });
});

describe("api error handling", () => {
  it("throws on non-ok response", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: () => Promise.resolve({ error: "Server error" }),
    } as Response);
    await expect(api.overview()).rejects.toThrow();
  });
});

describe("fmt", () => {
  it("formats billions", () => expect(fmt(1_500_000_000)).toBe("1.5B"));
  it("formats millions", () => expect(fmt(2_300_000)).toBe("2.3M"));
  it("formats thousands", () => expect(fmt(4_500)).toBe("4.5K"));
  it("formats small numbers", () => expect(fmt(42)).toBe("42"));
});
