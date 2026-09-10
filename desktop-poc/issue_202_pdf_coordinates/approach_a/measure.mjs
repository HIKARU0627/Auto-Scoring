/**
 * PoC 6 Approach A: pdf.js as Electron renderer display engine.
 *
 * Acquisition: npm package `pdfjs-dist` (pinned in package.json). Not added to
 * the product root — probe-only under desktop-poc/.
 *
 * Usage (from approach_a/):
 *   node measure.mjs --samples-dir ../samples --scale 2 --jobs jobs.json
 *
 * jobs.json shape:
 * {
 *   "viewport_checks": [{ "fixture": "a4-portrait", "pdf": "...", "expected_width": 595, "expected_height": 842 }],
 *   "round_trips": [{ "fixture": "a4-portrait", "pdf": "...", "nx": 0.12, "ny": 0.15 }]
 * }
 */

import { createCanvas } from "@napi-rs/canvas";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { getDocument } from "pdfjs-dist/legacy/build/pdf.mjs";

const RENDER_SCALE = Number.parseFloat(
  getArg("--scale") ?? process.env.POC6_RENDER_SCALE ?? "2",
);

function getArg(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : undefined;
}

function measureRedCentroid(imageData, width, height) {
  let minX = width;
  let minY = height;
  let maxX = -1;
  let maxY = -1;
  const data = imageData.data;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const offset = (y * width + x) * 4;
      const red = data[offset];
      const green = data[offset + 1];
      if (red - green > 80) {
        minX = Math.min(minX, x);
        minY = Math.min(minY, y);
        maxX = Math.max(maxX, x);
        maxY = Math.max(maxY, y);
      }
    }
  }
  if (maxX < 0) {
    throw new Error("stamped mark not found in pdf.js raster");
  }
  return {
    x: (minX + maxX + 1) / 2 / width,
    y: (minY + maxY + 1) / 2 / height,
  };
}

async function renderPage(pdfPath, scale) {
  const bytes = new Uint8Array(fs.readFileSync(pdfPath));
  const standardFontDataUrl = pathToFileURL(
    path.join(
      path.dirname(new URL(import.meta.url).pathname),
      "node_modules/pdfjs-dist/standard_fonts/",
    ),
  ).href;
  const loadingTask = getDocument({
    data: bytes,
    standardFontDataUrl,
    useSystemFonts: true,
  });
  const pdf = await loadingTask.promise;
  try {
    const page = await pdf.getPage(1);
    const viewport = page.getViewport({ scale });
    const canvas = createCanvas(
      Math.ceil(viewport.width),
      Math.ceil(viewport.height),
    );
    const context = canvas.getContext("2d");
    await page.render({ canvasContext: context, viewport }).promise;
    const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
    return {
      viewportWidth: viewport.width,
      viewportHeight: viewport.height,
      canvasWidth: canvas.width,
      canvasHeight: canvas.height,
      imageData,
    };
  } finally {
    await pdf.destroy();
  }
}

async function main() {
  const jobsPath = getArg("--jobs");
  if (!jobsPath) {
    console.error("missing --jobs path");
    process.exit(2);
  }
  const jobs = JSON.parse(fs.readFileSync(jobsPath, "utf8"));

  const viewportResults = [];
  for (const job of jobs.viewport_checks ?? []) {
    const rendered = await renderPage(job.pdf, 1.0);
    viewportResults.push({
      fixture: job.fixture,
      expected_width: job.expected_width,
      expected_height: job.expected_height,
      pdfjs_width: rendered.viewportWidth,
      pdfjs_height: rendered.viewportHeight,
      width_delta: rendered.viewportWidth - job.expected_width,
      height_delta: rendered.viewportHeight - job.expected_height,
    });
  }

  const roundTripResults = [];
  for (const job of jobs.round_trips ?? []) {
    const rendered = await renderPage(job.pdf, RENDER_SCALE);
    const measured = measureRedCentroid(
      rendered.imageData,
      rendered.canvasWidth,
      rendered.canvasHeight,
    );
    const error = Math.max(
      Math.abs(measured.x - job.nx),
      Math.abs(measured.y - job.ny),
    );
    roundTripResults.push({
      fixture: job.fixture,
      nx: job.nx,
      ny: job.ny,
      measured_x: measured.x,
      measured_y: measured.y,
      error,
    });
  }

  const worstViewport = viewportResults.reduce(
    (acc, row) =>
      Math.max(acc, Math.abs(row.width_delta), Math.abs(row.height_delta)),
    0,
  );
  const worstRoundTrip = roundTripResults.reduce(
    (acc, row) => Math.max(acc, row.error),
    0,
  );

  process.stdout.write(
    JSON.stringify(
      {
        render_scale: RENDER_SCALE,
        pdfjs_version: (
          await import("pdfjs-dist/package.json", { with: { type: "json" } })
        ).default.version,
        viewport_results: viewportResults,
        round_trip_results: roundTripResults,
        worst_viewport_delta_pt: worstViewport,
        worst_round_trip_error: worstRoundTrip,
      },
      null,
      2,
    ),
  );
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
