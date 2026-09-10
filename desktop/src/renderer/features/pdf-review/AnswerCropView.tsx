import type { JSX } from "react";

export interface AnswerCropViewProps {
  readonly imageUrl: string | null;
  readonly nearlyBlank?: boolean;
}

export function AnswerCropView({
  imageUrl,
  nearlyBlank = false,
}: AnswerCropViewProps): JSX.Element {
  return (
    <section data-testid="review-answer-crop" className="flex flex-col gap-sm">
      <h3 className="text-title-small font-medium">AIが見た画像</h3>
      {imageUrl != null ? (
        <img
          src={imageUrl}
          alt="AIが見た回答欄の切り出し"
          className="max-w-full border border-outline-variant"
        />
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
