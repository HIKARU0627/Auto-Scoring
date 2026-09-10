/**
 * Normalized coordinates per docs/sidecar-api.md §7.
 *
 * The only divisors allowed are the returned image's pixel width and height.
 * Geometry endpoint values are for layout and paging, never for this math.
 */

export interface PixelSize {
  readonly width: number;
  readonly height: number;
}

export interface NormalizedPoint {
  readonly x: number;
  readonly y: number;
}

/** Image pixel dimensions from geometry × scale, using ceil as the sidecar does. */
export function geometryToImagePixelSize(
  displayedWidth: number,
  displayedHeight: number,
  scale: number,
): PixelSize {
  return {
    width: Math.ceil(displayedWidth * scale),
    height: Math.ceil(displayedHeight * scale),
  };
}

export function pixelToNormalized(
  pixelX: number,
  pixelY: number,
  imagePixelSize: PixelSize,
): NormalizedPoint {
  return {
    x: clamp01(pixelX / imagePixelSize.width),
    y: clamp01(pixelY / imagePixelSize.height),
  };
}

export function normalizedToPixel(
  normX: number,
  normY: number,
  imagePixelSize: PixelSize,
): { x: number; y: number } {
  return {
    x: normX * imagePixelSize.width,
    y: normY * imagePixelSize.height,
  };
}

/**
 * Maps a pointer position on the uniformly scaled page surface to normalized
 * coordinates via the image's pixel dimensions (docs/sidecar-api.md §7).
 */
export function layoutPointToNormalized(
  localX: number,
  localY: number,
  renderSize: PixelSize,
  imagePixelSize: PixelSize,
): NormalizedPoint {
  const pixelX = (localX / renderSize.width) * imagePixelSize.width;
  const pixelY = (localY / renderSize.height) * imagePixelSize.height;
  return pixelToNormalized(pixelX, pixelY, imagePixelSize);
}

/**
 * Maps normalized coordinates back to layout pixels for overlay positioning.
 */
export function normalizedToLayoutPoint(
  normX: number,
  normY: number,
  renderSize: PixelSize,
  imagePixelSize: PixelSize,
): { x: number; y: number } {
  const pixel = normalizedToPixel(normX, normY, imagePixelSize);
  return {
    x: (pixel.x / imagePixelSize.width) * renderSize.width,
    y: (pixel.y / imagePixelSize.height) * renderSize.height,
  };
}

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}
