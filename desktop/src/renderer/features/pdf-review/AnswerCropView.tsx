import type { JSX } from "react";

import type { BoundingBoxResponse } from "../../core/unreadable-spans.js";

export interface AnswerCropViewProps {
  readonly imageUrl: string | null;
  readonly nearlyBlank?: boolean;
  readonly unreadableBoxes?: readonly BoundingBoxResponse[];
}

export function AnswerCropView({
  imageUrl,
  nearlyBlank = false,
  unreadableBoxes = [],
}: AnswerCropViewProps): JSX.Element {
  return (
    <section data-testid="review-answer-crop" className="flex flex-col gap-sm">
      <h3 className="text-ui-label font-semibold text-on-surface">
        AIが見た画像
      </h3>
      {imageUrl != null ? (
        <div className="relative inline-block max-w-full">
          <img
            src={imageUrl}
            alt="AIが見た回答欄の切り出し"
            className="max-w-full"
          />
          {unreadableBoxes.map((box, index) => (
            <div
              key={`${box.x}-${box.y}-${index}`}
              data-testid={`review-unreadable-box-${index}`}
              className="pointer-events-none absolute border-2 border-attention bg-attention/20"
              style={{
                left: `${box.x * 100}%`,
                top: `${box.y * 100}%`,
                width: `${box.width * 100}%`,
                height: `${box.height * 100}%`,
              }}
              aria-hidden
            />
          ))}
        </div>
      ) : (
        <p className="text-body-medium text-on-surface-variant">
          画像を取得できませんでした
        </p>
      )}
      {nearlyBlank ? (
        <p
          data-testid="review-answer-image-blank"
          className="text-body-medium text-on-surface"
        >
          AIは、この切り出し画像に解答欄に何も書かれていないと報告しました。本当に無記入ならこの0点は正しく、切り出しがずれている場合はテスト設定の回答欄を見直してください。
        </p>
      ) : null}
    </section>
  );
}
