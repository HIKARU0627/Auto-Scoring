import { describe, expect, it } from "vitest";

import {
  geometryToImagePixelSize,
  layoutPointToNormalized,
  normalizedToLayoutPoint,
  normalizedToPixel,
  pixelToNormalized,
} from "../src/renderer/core/normalized-coordinates.js";

describe("normalized coordinates (docs/sidecar-api.md §7)", () => {
  it("uses image pixel dimensions only for normalization", () => {
    const imagePixelSize = { width: 201, height: 401 };
    const point = pixelToNormalized(100.5, 200.5, imagePixelSize);
    expect(point.x).toBeCloseTo(100.5 / 201, 12);
    expect(point.y).toBeCloseTo(200.5 / 401, 12);
  });

  it("round-trips through layout when ceil makes pixel size differ from geometry×scale", () => {
    const displayedWidth = 100.3;
    const displayedHeight = 200.7;
    const scale = 2;
    const imagePixelSize = geometryToImagePixelSize(
      displayedWidth,
      displayedHeight,
      scale,
    );
    expect(imagePixelSize.width).toBe(201);
    expect(imagePixelSize.height).toBe(402);

    const renderSize = { width: 400, height: 800 };
    const click = { x: 123.4, y: 234.5 };
    const normalized = layoutPointToNormalized(
      click.x,
      click.y,
      renderSize,
      imagePixelSize,
    );
    const layoutBack = normalizedToLayoutPoint(
      normalized.x,
      normalized.y,
      renderSize,
      imagePixelSize,
    );
    expect(layoutBack.x).toBeCloseTo(click.x, 9);
    expect(layoutBack.y).toBeCloseTo(click.y, 9);
  });

  it("rejects geometry×scale as the normalization divisor when ceil changes pixel size", () => {
    const displayedWidth = 595.28;
    const displayedHeight = 421.37;
    const scale = 2;
    const imagePixelSize = geometryToImagePixelSize(
      displayedWidth,
      displayedHeight,
      scale,
    );
    const geometryPixelSize = {
      width: displayedWidth * scale,
      height: displayedHeight * scale,
    };
    expect(imagePixelSize.width).not.toBe(geometryPixelSize.width);

    const renderSize = {
      width: imagePixelSize.width,
      height: imagePixelSize.height,
    };
    const click = { x: 417, y: 421 };
    const correct = layoutPointToNormalized(
      click.x,
      click.y,
      renderSize,
      imagePixelSize,
    );

    // Wrong pattern: scale pointer into geometry pixels, then divide by actual
    // image pixels — the double interpretation docs/sidecar-api.md §7 forbids.
    const wrongPixelX = (click.x / renderSize.width) * geometryPixelSize.width;
    const wrongPixelY =
      (click.y / renderSize.height) * geometryPixelSize.height;
    const wrong = pixelToNormalized(wrongPixelX, wrongPixelY, imagePixelSize);

    expect(wrong.x).not.toBeCloseTo(correct.x, 8);
    expect(wrong.y).not.toBeCloseTo(correct.y, 8);
  });

  it("fails the contract when geometry pixel size is used instead of image pixels", () => {
    const displayedWidth = 595.28;
    const scale = 2;
    const imagePixelSize = geometryToImagePixelSize(displayedWidth, 842, scale);
    const geometryPixelWidth = displayedWidth * scale;
    expect(imagePixelSize.width).toBe(Math.ceil(geometryPixelWidth));
    expect(imagePixelSize.width).not.toBe(geometryPixelWidth);

    const pixelX = 417;
    const correct = pixelToNormalized(pixelX, 100, imagePixelSize).x;
    const wrong = pixelX / geometryPixelWidth;
    expect(correct).not.toBeCloseTo(wrong, 8);
  });

  it("maps normalized values back to pixel coordinates", () => {
    const imagePixelSize = { width: 1190, height: 1684 };
    const pixel = normalizedToPixel(0.25, 0.5, imagePixelSize);
    expect(pixel.x).toBeCloseTo(297.5, 6);
    expect(pixel.y).toBeCloseTo(842, 6);
  });
});
