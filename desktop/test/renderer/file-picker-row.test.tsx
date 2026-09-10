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
});
