import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import JobProgress from "../components/JobProgress";
import { renderWithRouter, mockFetchResponse } from "../test-utils";

describe("JobProgress", () => {
  beforeEach(() => {
    vi.mocked(fetch).mockReset();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders progress bar for running job", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      await mockFetchResponse({
        id: "j1",
        status: "running",
        job_type: "script-batch",
        progress: { total: 10, completed: 5, failed: 0, current_session_id: "s1" },
        payload: {},
        created_at: "2026-01-01",
      })
    );

    await act(async () => {
      renderWithRouter(<JobProgress jobId="j1" />);
    });

    await waitFor(() => {
      expect(screen.getByText(/5\/10/)).toBeInTheDocument();
    });
  });

  it("shows cancel button for non-completed jobs", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      await mockFetchResponse({
        id: "j1",
        status: "running",
        job_type: "script-batch",
        progress: { total: 10, completed: 3, failed: 0, current_session_id: null },
        payload: {},
        created_at: "2026-01-01",
      })
    );

    await act(async () => {
      renderWithRouter(<JobProgress jobId="j1" />);
    });

    await waitFor(() => {
      expect(screen.getByText("Cancel")).toBeInTheDocument();
    });
  });

  it("shows completed state", async () => {
    const onComplete = vi.fn();
    vi.mocked(fetch).mockResolvedValueOnce(
      await mockFetchResponse({
        id: "j1",
        status: "completed",
        job_type: "script-batch",
        progress: { total: 5, completed: 5, failed: 0, current_session_id: null },
        payload: {},
        created_at: "2026-01-01",
      })
    );

    await act(async () => {
      renderWithRouter(<JobProgress jobId="j1" onComplete={onComplete} />);
    });

    await waitFor(() => {
      expect(screen.getByText(/Completed 5 sessions/)).toBeInTheDocument();
    });
    expect(onComplete).toHaveBeenCalled();
  });

  it("hides cancel button when completed", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      await mockFetchResponse({
        id: "j1",
        status: "completed",
        job_type: "script-batch",
        progress: { total: 5, completed: 5, failed: 0, current_session_id: null },
        payload: {},
        created_at: "2026-01-01",
      })
    );

    await act(async () => {
      renderWithRouter(<JobProgress jobId="j1" />);
    });

    await waitFor(() => {
      expect(screen.getByText(/Completed/)).toBeInTheDocument();
    });
    expect(screen.queryByText("Cancel")).not.toBeInTheDocument();
  });
});
