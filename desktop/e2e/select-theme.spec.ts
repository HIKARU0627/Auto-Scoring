import { test, expect } from "@playwright/test";

import { closeElectronApp, launchElectronApp } from "./electron-launch";
import { waitForHomeReady } from "./registration-helpers";

/**
 * Issue #381: the theme must reach the opened list, not just the closed
 * control. Chromium's `appearance: base-select` turns the popup into a
 * page-drawn `::picker(select)`; this drives the real Electron renderer
 * (Chromium 152) and reads the computed colours back, because jsdom cannot
 * evaluate the pseudo-element.
 */
test("select はアプリのテーマで描画され、開いたリストもテーマ色になる", async () => {
  test.setTimeout(180_000);

  const app = await launchElectronApp();

  try {
    const page = await app.firstWindow();
    await waitForHomeReady(page);

    await page.getByTestId("home-open-settings").click();
    const select = page.getByTestId("settings-template-picker");
    await expect(select).toBeVisible({ timeout: 20_000 });

    expect(
      await page.evaluate(() => CSS.supports("appearance", "base-select")),
      "renderer が appearance: base-select に対応している",
    ).toBe(true);

    // Open the picker: it is a page top-layer box, so it stays in this Document.
    await select.click();
    await expect
      .poll(() =>
        page.evaluate(() =>
          (
            document.querySelector(
              '[data-testid="settings-template-picker"]',
            ) as HTMLSelectElement
          ).matches(":open"),
        ),
      )
      .toBe(true);

    const styles = await page.evaluate(() => {
      const element = document.querySelector(
        '[data-testid="settings-template-picker"]',
      ) as HTMLSelectElement;
      const reference = (token: string) => {
        const probe = document.createElement("div");
        probe.style.color = `var(${token})`;
        probe.style.backgroundColor = `var(${token})`;
        document.body.appendChild(probe);
        const computed = getComputedStyle(probe);
        const value = {
          color: computed.color,
          backgroundColor: computed.backgroundColor,
        };
        probe.remove();
        return value;
      };
      const closed = getComputedStyle(element);
      const picker = getComputedStyle(element, "::picker(select)");
      const icon = getComputedStyle(element, "::picker-icon");
      const selected = getComputedStyle(
        element.options[element.selectedIndex]!,
      );
      return {
        appearance: closed.appearance,
        color: closed.color,
        background: closed.backgroundColor,
        pickerAppearance: picker.appearance,
        pickerColor: picker.color,
        pickerBackground: picker.backgroundColor,
        iconColor: icon.color,
        selectedColor: selected.color,
        selectedBackground: selected.backgroundColor,
        onSurface: reference("--color-on-surface"),
        surfaceHigh: reference("--color-surface-container-high"),
        onSurfaceVariant: reference("--color-on-surface-variant"),
        onPrimaryContainer: reference("--color-on-primary-container"),
        primaryContainer: reference("--color-primary-container"),
      };
    });

    // Closed control.
    expect(styles.appearance).toBe("base-select");
    expect(styles.color).toBe(styles.onSurface.color);
    expect(styles.background).toBe(styles.surfaceHigh.backgroundColor);

    // Opened list: the page-drawn picker, not the OS default.
    expect(styles.pickerAppearance).toBe("base-select");
    expect(styles.pickerColor).toBe(styles.onSurface.color);
    expect(styles.pickerBackground).toBe(styles.surfaceHigh.backgroundColor);

    // Arrow icon.
    expect(styles.iconColor).toBe(styles.onSurfaceVariant.color);

    // Selected option.
    expect(styles.selectedColor).toBe(styles.onPrimaryContainer.color);
    expect(styles.selectedBackground).toBe(
      styles.primaryContainer.backgroundColor,
    );

    await page.keyboard.press("Escape");
  } finally {
    await closeElectronApp(app);
  }
});
