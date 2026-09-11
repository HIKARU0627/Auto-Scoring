import { test, expect, _electron as electron } from "@playwright/test";

import {
  closeElectronApp,
  electronLaunchArgs,
  isolatedSidecarLaunchEnv,
} from "./electron-launch";

/**
 * Issue #264 acceptance: blob URLs are allowed by img-src so page and answer
 * images rendered via URL.createObjectURL can load in the renderer.
 */
test("blob image URLs load in the renderer", async () => {
  test.setTimeout(60_000);

  const app = await electron.launch({
    args: electronLaunchArgs(),
    env: isolatedSidecarLaunchEnv(),
  });

  try {
    const page = await app.firstWindow();
    await page.waitForTimeout(2_000);

    const result = await page.evaluate(async () => {
      const bytes = Uint8Array.from(
        atob(
          "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8AAAwAB/AF+lVQZAAAAAElFTkSuQmCC",
        ),
        (character) => character.charCodeAt(0),
      );
      const url = URL.createObjectURL(new Blob([bytes], { type: "image/png" }));
      const loaded = await new Promise<{ naturalWidth: number }>((resolve) => {
        const image = new Image();
        image.onload = () => resolve({ naturalWidth: image.naturalWidth });
        image.onerror = () => resolve({ naturalWidth: 0 });
        image.src = url;
        document.body.appendChild(image);
        setTimeout(() => resolve({ naturalWidth: 0 }), 2_500);
      });
      return loaded;
    });

    expect(result.naturalWidth).toBeGreaterThan(0);
  } finally {
    await closeElectronApp(app);
  }
});
