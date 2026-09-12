import type { SidecarClient } from "../api/client.js";
import type { components } from "../api/generated/schema.js";
import type { PageImageState } from "./page-image.js";
import { geometryToImagePixelSize } from "./normalized-coordinates.js";

/**
 * Data loaders for the material window (Issue #415).
 *
 * The list comes from `GET /tests/{test_id}/materials`, which existed already
 * and answers "which file became which role?". The **content** comes from
 * `GET /tests/{test_id}/materials/{material_id}/pages[/image]`, added in the
 * same Issue and deliberately identical in shape to the answer page images
 * (`api.page_image_router`): the sidecar rasterizes the PDF and the renderer
 * only ever sees PNGs, so no raw document byte reaches the renderer
 * (`docs/sidecar-api.md` §7.5).
 *
 * A material that is not a PDF has no pages to rasterize. The sidecar answers
 * 415 and this file turns that into `MaterialPreviewUnsupportedError` -- a
 * distinct type, so the window can say "this format has no in-app preview"
 * rather than the generic failure, and never silently show an empty viewer.
 */

export type MaterialResponse = components["schemas"]["TestMaterialResponse"];
export type MaterialPageGeometry =
  components["schemas"]["PageGeometryResponse"];

export class MaterialDataError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "MaterialDataError";
  }
}

export class MaterialPreviewUnsupportedError extends MaterialDataError {
  constructor() {
    super("この形式の資料はアプリ内でプレビューできません");
    this.name = "MaterialPreviewUnsupportedError";
  }
}

const DEFAULT_IMAGE_SCALE = 2;

export interface MaterialPageState {
  readonly geometry: MaterialPageGeometry;
  readonly image: PageImageState;
}

export async function loadMaterials(
  client: SidecarClient,
  testId: string,
): Promise<MaterialResponse[]> {
  const result = await client.GET("/tests/{test_id}/materials", {
    params: { path: { test_id: testId } },
  });
  if (result.error !== undefined) {
    throw new MaterialDataError("資料一覧を取得できません");
  }
  return result.data;
}

async function loadMaterialPageImage(
  client: SidecarClient,
  testId: string,
  materialId: string,
  pageIndex: number,
  geometry: MaterialPageGeometry,
): Promise<PageImageState> {
  const result = await client.GET(
    "/tests/{test_id}/materials/{material_id}/pages/{page_index}/image",
    {
      params: {
        path: {
          test_id: testId,
          material_id: materialId,
          page_index: pageIndex,
        },
        query: { scale: DEFAULT_IMAGE_SCALE },
      },
      parseAs: "blob",
    },
  );
  if (result.error !== undefined) {
    return { objectUrl: null, pixelWidth: null, pixelHeight: null };
  }
  const blob = result.data as Blob;
  const objectUrl = URL.createObjectURL(blob);
  const expected = geometryToImagePixelSize(
    geometry.displayed_width,
    geometry.displayed_height,
    DEFAULT_IMAGE_SCALE,
  );
  return {
    objectUrl,
    pixelWidth: expected.width,
    pixelHeight: expected.height,
  };
}

export async function loadMaterialPages(
  client: SidecarClient,
  testId: string,
  materialId: string,
): Promise<readonly MaterialPageState[]> {
  const pagesResult = await client.GET(
    "/tests/{test_id}/materials/{material_id}/pages",
    {
      params: { path: { test_id: testId, material_id: materialId } },
    },
  );
  if (pagesResult.error !== undefined) {
    if (pagesResult.response.status === 415) {
      throw new MaterialPreviewUnsupportedError();
    }
    throw new MaterialDataError("資料のページ情報を取得できません");
  }
  const pages: MaterialPageState[] = [];
  for (let i = 0; i < pagesResult.data.pages.length; i += 1) {
    const geometry = pagesResult.data.pages[i];
    if (geometry == null) {
      continue;
    }
    const image = await loadMaterialPageImage(
      client,
      testId,
      materialId,
      i,
      geometry,
    );
    pages.push({ geometry, image });
  }
  return pages;
}
