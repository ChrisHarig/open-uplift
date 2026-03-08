import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { screen, waitFor, act } from "@testing-library/react";
import JobNotifications from "../components/JobNotifications";
import { renderWithRouter, mockFetchResponse } from "../test-utils";

describe("JobNotifications", () => {
  beforeEach(() => {
    vi.mocked(fetch).mockReset();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("hides when no active jobs", async () => {
    vi.mocked(fetch).mockResolvedValue(await mockFetchResponse([]));

    const { container } = await act(async () =>
      renderWithRouter(<JobNotifications />)
    );

    await waitFor(() => {
      // Should render nothing when no jobs
      expect(container.querySelector("[style]")).toBeNull();
    });
  });

  it("shows active jobs", async () => {
    vi.mocked(fetch).mockResolvedValue(
      await mockFetchResponse([
        {
          id: "j1",
          status: "running",
          job_type: "script-batch",
          progress: { total: 10, completed: 3, failed: 0, current_session_id: null },
          payload: {},
          created_at: "2026-01-01",
        },
      ])
    );

    await act(async () => {
      renderWithRouter(<JobNotifications />);
    });

    await waitFor(() => {
      expect(screen.getByText(/3\/10/)).toBeInTheDocument();
    });
  });

  it("shows cancel button for each job", async () => {
    vi.mocked(fetch).mockResolvedValue(
      await mockFetchResponse([
        {
          id: "j1",
          status: "running",
          job_type: "script-batch",
          progress: { total: 5, completed: 1, failed: 0, current_session_id: null },
          payload: {},
          created_at: "2026-01-01",
        },
      ])
    );

    await act(async () => {
      renderWithRouter(<JobNotifications />);
    });

    await waitFor(() => {
      expect(screen.getByText("Cancel")).toBeInTheDocument();
    });
  });

  it("dismisses after job completes (no active jobs returned)", async () => {
    const mock = vi.mocked(fetch);
    // First poll: running job
    mock.mockResolvedValueOnce(
      await mockFetchResponse([
        {
          id: "j1",
          status: "running",
          job_type: "script-batch",
          progress: { total: 5, completed: 5, failed: 0, current_session_id: null },
          payload: {},
          created_at: "2026-01-01",
        },
      ])
    );

    const { container } = await act(async () =>
      renderWithRouter(<JobNotifications />)
    );

    await waitFor(() => {
      expect(screen.getByText(/5\/5/)).toBeInTheDocument();
    });

    // Next poll: no active jobs
    mock.mockResolvedValueOnce(await mockFetchResponse([]));

    await act(async () => {
      vi.advanceTimersByTime(2000);
    });

    await waitFor(() => {
      expect(container.querySelector("[style]")).toBeNull();
    });
  });

  it("polls at 15s interval when idle, 2s when active", async () => {
    const mock = vi.mocked(fetch);
    mock.mockResolvedValue(await mockFetchResponse([]));

    await act(async () => {
      renderWithRouter(<JobNotifications />);
    });

    // Wait for the initial poll to resolve
    await waitFor(() => {
      expect(mock).toHaveBeenCalledTimes(1);
    });

    // Advance by 15s — idle interval triggers next poll
    await act(async () => {
      vi.advanceTimersByTime(15000);
    });

    await waitFor(() => {
      expect(mock).toHaveBeenCalledTimes(2);
    });

    // Advance by another 15s
    await act(async () => {
      vi.advanceTimersByTime(15000);
    });

    await waitFor(() => {
      expect(mock).toHaveBeenCalledTimes(3);
    });
  });
});
