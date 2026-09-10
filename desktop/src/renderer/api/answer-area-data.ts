import type { SidecarClient } from "./client.js";
import type { components } from "./generated/schema.js";
import type { PageImageState } from "../features/answer-area-editor/answer-area-types.js";

export type ProfileResponse = components["schemas"]["ProfileResponse"];
export type AnswerLayoutResponse =
  components["schemas"]["AnswerLayoutResponse"];

export class AnswerAreaDataError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AnswerAreaDataError";
  }
}

export interface AnswerAreaEditorData {
  readonly profile: ProfileResponse | null;
  readonly layout: AnswerLayoutResponse | null;
  readonly pageImages: readonly PageImageState[];
}

const DEFAULT_IMAGE_SCALE = 2;

/**
 * Loads profile, layout metadata, and page images for the answer-area editor.
 * Uses the generated OpenAPI client only — no hand-written fetch.
 */
export async function loadAnswerAreaEditorData(
  client: SidecarClient,
  testId: string,
): Promise<AnswerAreaEditorData> {
  const [profileResult, layoutResult] = await Promise.all([
    client.GET("/tests/{test_id}/profile", {
      params: { path: { test_id: testId } },
    }),
    client.GET("/tests/{test_id}/answer-layout", {
      params: { path: { test_id: testId } },
    }),
  ]);

  if (
    profileResult.error !== undefined &&
    profileResult.response.status !== 404
  ) {
    throw new AnswerAreaDataError("プロファイルを取得できません");
  }
  if (
    layoutResult.error !== undefined &&
    layoutResult.response.status !== 404
  ) {
    throw new AnswerAreaDataError("答案レイアウトを取得できません");
  }

  const profile = profileResult.error === undefined ? profileResult.data : null;
  const layout = layoutResult.error === undefined ? layoutResult.data : null;

  const pageCount = profile?.pages.length ?? layout?.page_count ?? 0;
  const pageImages: PageImageState[] = [];

  for (let pageIndex = 0; pageIndex < pageCount; pageIndex += 1) {
    const imageResult = await client.GET(
      "/tests/{test_id}/answer-layout/pages/{page_index}/image",
      {
        params: {
          path: { test_id: testId, page_index: pageIndex },
          query: { scale: DEFAULT_IMAGE_SCALE },
        },
        parseAs: "blob",
      },
    );
    if (imageResult.error !== undefined) {
      pageImages.push({
        objectUrl: null,
        pixelWidth: null,
        pixelHeight: null,
      });
      continue;
    }
    const blob = imageResult.data as Blob;
    const objectUrl = URL.createObjectURL(blob);
    const pixelSize = await readImagePixelSize(objectUrl);
    pageImages.push({
      objectUrl,
      pixelWidth: pixelSize.width,
      pixelHeight: pixelSize.height,
    });
  }

  return { profile, layout, pageImages };
}

async function readImagePixelSize(
  objectUrl: string,
): Promise<{ width: number; height: number }> {
  return await new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => {
      resolve({ width: image.naturalWidth, height: image.naturalHeight });
    };
    image.onerror = () => {
      reject(new AnswerAreaDataError("ページ画像を読み込めません"));
    };
    image.src = objectUrl;
  });
}
