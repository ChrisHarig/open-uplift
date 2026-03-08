import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import InfoTip from "../components/InfoTip";

describe("InfoTip", () => {
  it("renders the info icon", () => {
    render(<InfoTip text="Test tooltip" />);
    expect(screen.getByLabelText("info")).toBeInTheDocument();
    expect(screen.getByText("i")).toBeInTheDocument();
  });

  it("shows tooltip on hover and hides on leave", async () => {
    const user = userEvent.setup();
    render(<InfoTip text="Helpful explanation" />);

    // Tooltip should not be visible initially
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();

    // Hover over the icon
    await user.hover(screen.getByLabelText("info"));
    expect(screen.getByRole("tooltip")).toBeInTheDocument();
    expect(screen.getByText("Helpful explanation")).toBeInTheDocument();

    // Move away
    await user.unhover(screen.getByLabelText("info"));
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });
});
