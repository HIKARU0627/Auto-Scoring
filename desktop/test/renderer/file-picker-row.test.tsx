import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { FilePickerRow } from "../../src/renderer/features/intake/FilePickerRow.js";

describe("FilePickerRow (UG-13)", () => {
  it("truncates long file names beside the button", () => {
    render(
      <FilePickerRow
        buttonLabel="フォルダを選ぶ"
        fileName={
          "C:\\Users\\Teacher\\VeryLongFolderNameThatWouldOverflow\\answers.pdf"
        }
        onPressed={() => undefined}
      />,
    );
    const name = screen.getByTestId("file-picker-name");
    expect(name.className).toContain("truncate");
    expect(name.textContent).toContain("answers.pdf");
  });

  it("keeps the button in place (shrink-0) while the name flexes and truncates", () => {
    // UG-13: the failure was the long name pushing the button off-screen. The
    // button must refuse to shrink; the name must take the leftover width and
    // clip. Removing any of the three classes lets the row overflow again.
    render(
      <FilePickerRow
        buttonTestId="picker-button"
        buttonLabel="フォルダを選ぶ"
        fileName={"C:\\VeryLong\\" + "nested\\".repeat(40) + "answers.pdf"}
        onPressed={() => undefined}
      />,
    );
    const button = screen.getByTestId("picker-button");
    const name = screen.getByTestId("file-picker-name");
    expect(button.className).toContain("shrink-0");
    expect(name.className).toContain("min-w-0");
    expect(name.className).toContain("flex-1");
    expect(name.className).toContain("truncate");
  });
});
