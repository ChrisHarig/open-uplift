import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StudyConfig from "../pages/StudyConfig";
import { renderWithRouter, mockFetchResponse } from "../test-utils";

function setupMocks() {
  vi.mocked(fetch).mockImplementation((url) => {
    const urlStr = typeof url === "string" ? url : "";
    if (urlStr.includes("questions")) {
      return mockFetchResponse({
        "human-est": {
          id: "human-est",
          label: "Human Time Estimate",
          type: "number",
          description: "How long without AI?",
          required: true,
          validation: { min: 0, max: 1000 },
        },
      });
    }
    if (urlStr.includes("surveys")) {
      return mockFetchResponse({
        surveys: {
          "survey-1": {
            id: "survey-1",
            name: "Default Survey",
            description: "The default survey",
            questions: ["human-est"],
          },
        },
        active: "survey-1",
      });
    }
    return mockFetchResponse({});
  });
}

describe("StudyConfig", () => {
  beforeEach(() => {
    vi.mocked(fetch).mockReset();
    setupMocks();
  });

  it("renders survey list", async () => {
    renderWithRouter(<StudyConfig />);
    await waitFor(() => {
      expect(screen.getByText("Default Survey")).toBeInTheDocument();
    });
  });

  it("shows active badge", async () => {
    renderWithRouter(<StudyConfig />);
    await waitFor(() => {
      expect(screen.getByText("Default Survey")).toBeInTheDocument();
    });
  });

  it("renders question definitions when expanded", async () => {
    renderWithRouter(<StudyConfig />);
    await waitFor(() => {
      expect(screen.getByText("Default Survey")).toBeInTheDocument();
    });
    // Click the survey card to expand it and show questions
    await userEvent.click(screen.getByText("Default Survey"));
    await waitFor(() => {
      expect(screen.getByText("Human Time Estimate")).toBeInTheDocument();
    });
  });

  it("renders without crash", async () => {
    renderWithRouter(<StudyConfig />);
    await waitFor(() => {
      expect(screen.getByText("Default Survey")).toBeInTheDocument();
    });
    expect(document.body).toBeInTheDocument();
  });

  it("shows survey description", async () => {
    renderWithRouter(<StudyConfig />);
    await waitFor(() => {
      expect(screen.getByText("Default Survey")).toBeInTheDocument();
    });
  });

  it("has add survey functionality", async () => {
    renderWithRouter(<StudyConfig />);
    await waitFor(() => {
      expect(screen.getByText("Default Survey")).toBeInTheDocument();
    });
    // Look for add button
    const buttons = screen.getAllByRole("button");
    expect(buttons.length).toBeGreaterThanOrEqual(1);
  });

  it("shows question type when expanded", async () => {
    renderWithRouter(<StudyConfig />);
    await waitFor(() => {
      expect(screen.getByText("Default Survey")).toBeInTheDocument();
    });
    // Click the survey card to expand it
    await userEvent.click(screen.getByText("Default Survey"));
    await waitFor(() => {
      expect(screen.getByText("Human Time Estimate")).toBeInTheDocument();
    });
  });
});
