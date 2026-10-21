import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { Modal } from "./Modal";

function Harness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>open</button>
      {open ? (
        <Modal title="Schedule" onClose={() => setOpen(false)}>
          <button>first</button>
          <button>last</button>
        </Modal>
      ) : null}
    </>
  );
}

describe("Modal", () => {
  it("is a labelled modal dialog that takes focus", () => {
    render(<Harness />);
    const opener = screen.getByText("open");
    opener.focus();
    fireEvent.click(opener);
    const dialog = screen.getByRole("dialog", { name: "Schedule" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveFocus();
  });

  it("traps Tab, closes on Escape and returns focus to the opener", () => {
    render(<Harness />);
    const opener = screen.getByText("open");
    opener.focus();
    fireEvent.click(opener);
    screen.getByText("last").focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(screen.getByLabelText("Close")).toHaveFocus();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });
});
