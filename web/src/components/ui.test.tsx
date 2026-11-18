import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { Button, SegmentedControl } from "./ui";

describe("Button", () => {
  it("cannot be pressed again while it is busy, even when disabled is explicitly false", () => {
    render(
      <Button busy disabled={false}>
        Search job board
      </Button>,
    );

    expect(screen.getByRole("button", { name: "Search job board" })).toBeDisabled();
  });

  it("stays disabled when asked to, and is enabled otherwise", () => {
    const { rerender } = render(<Button disabled>Save</Button>);
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();

    rerender(<Button>Save</Button>);
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
  });
});

describe("SegmentedControl", () => {
  it("moves the choice and focus with the arrow keys", async () => {
    const user = userEvent.setup();
    const seen: string[] = [];
    function Harness() {
      const [value, setValue] = useState("resume");
      return (
        <SegmentedControl
          label="Document"
          options={[
            { value: "resume", label: "Résumé" },
            { value: "cover", label: "Cover letter" },
          ]}
          value={value}
          onChange={(next) => {
            seen.push(next);
            setValue(next);
          }}
        />
      );
    }
    render(<Harness />);

    await user.tab();
    expect(screen.getByRole("radio", { name: "Résumé" })).toHaveFocus();
    await user.keyboard("{ArrowRight}");

    expect(seen).toEqual(["cover"]);
    expect(screen.getByRole("radio", { name: "Cover letter" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Cover letter" })).toHaveFocus();
  });
});
