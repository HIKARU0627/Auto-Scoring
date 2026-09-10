import type { JSX } from "react";

/**
 * Folder/file picker row with ellipsis for long names (UG-13).
 */
export function FilePickerRow({
  buttonTestId,
  buttonLabel,
  fileName,
  onPressed,
  emptyLabel = "未選択",
}: {
  buttonTestId?: string;
  buttonLabel: string;
  fileName: string | null;
  onPressed: (() => void) | null;
  emptyLabel?: string;
}): JSX.Element {
  return (
    <div className="flex min-w-0 items-center gap-md">
      <button
        type="button"
        data-testid={buttonTestId}
        className="shrink-0 rounded-md border border-outline px-md py-sm text-ui-label"
        onClick={onPressed ?? undefined}
        disabled={onPressed === null}
      >
        {buttonLabel}
      </button>
      <p
        data-testid="file-picker-name"
        className="min-w-0 flex-1 truncate text-body-medium text-on-surface-variant"
      >
        {fileName ?? emptyLabel}
      </p>
    </div>
  );
}
