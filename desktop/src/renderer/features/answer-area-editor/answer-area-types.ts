import type { components } from "../../api/generated/schema.js";

export type RegionModel = components["schemas"]["RegionModel"];
export type PageFormatModel = components["schemas"]["PageFormatModel"];
export type NormalizedBBox = components["schemas"]["NormalizedBBoxModel"];

export interface PageImageState {
  readonly objectUrl: string | null;
  readonly pixelWidth: number | null;
  readonly pixelHeight: number | null;
}
