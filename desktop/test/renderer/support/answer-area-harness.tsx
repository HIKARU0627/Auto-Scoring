import { fireEvent, render, type RenderResult } from "@testing-library/react";

import { AnswerAreaEditor } from "../../../src/renderer/features/answer-area-editor/AnswerAreaEditor.js";
import type {
  PageImageState,
  RegionModel,
} from "../../../src/renderer/features/answer-area-editor/answer-area-types.js";
import { ThemeProvider } from "../../../src/renderer/theme/ThemeProvider.js";

const DEFAULT_PAGE = { width_pt: 595, height_pt: 842 };

const DEFAULT_IMAGE: PageImageState = {
  objectUrl: null,
  pixelWidth: 1190,
  pixelHeight: 1684,
};

export function buildRegion(input: {
  regionId: string;
  label?: string;
  kind?: RegionModel["kind"];
  pageIndex?: number;
  x0?: number;
  y0?: number;
  x1?: number;
  y1?: number;
  text?: string | null;
}): RegionModel {
  return {
    region_id: input.regionId,
    kind: input.kind ?? "answer_area",
    page_index: input.pageIndex ?? 0,
    label: input.label ?? "問1",
    confirmed: false,
    text: input.text ?? null,
    bbox: {
      x0: input.x0 ?? 0.1,
      y0: input.y0 ?? 0.1,
      x1: input.x1 ?? 0.5,
      y1: input.y1 ?? 0.3,
    },
  };
}

export function renderAnswerAreaEditor(options: {
  regions: RegionModel[];
  questionNumbers?: string[];
  undetected?: string[];
  absent?: string[];
  conflicts?: (readonly [string, string])[];
  pages?: number;
  readOnly?: boolean;
  onEditNumerically?: (index: number) => void;
  pageImage?: PageImageState;
}): RenderResult & { getRegions: () => RegionModel[] } {
  let current = options.regions;
  const pageCount = options.pages ?? 1;
  const pageImage = options.pageImage ?? DEFAULT_IMAGE;

  const view = render(
    <ThemeProvider>
      <div style={{ width: 600, height: 900 }}>
        <AnswerAreaEditor
          pages={Array.from({ length: pageCount }, () => DEFAULT_PAGE)}
          pageImages={Array.from({ length: pageCount }, () => pageImage)}
          regions={current}
          questionNumbers={options.questionNumbers ?? ["問1", "問2"]}
          undetectedQuestionNumbers={options.undetected ?? []}
          absentQuestionNumbers={options.absent ?? []}
          readingOrderConflicts={options.conflicts ?? []}
          readOnly={options.readOnly ?? false}
          {...(options.onEditNumerically === undefined
            ? {}
            : { onEditNumerically: options.onEditNumerically })}
          onRegionsChanged={(next) => {
            current = next;
            rerender();
          }}
        />
      </div>
    </ThemeProvider>,
  );

  function rerender(): void {
    view.rerender(
      <ThemeProvider>
        <div style={{ width: 600, height: 900 }}>
          <AnswerAreaEditor
            pages={Array.from({ length: pageCount }, () => DEFAULT_PAGE)}
            pageImages={Array.from({ length: pageCount }, () => pageImage)}
            regions={current}
            questionNumbers={options.questionNumbers ?? ["問1", "問2"]}
            undetectedQuestionNumbers={options.undetected ?? []}
            absentQuestionNumbers={options.absent ?? []}
            readingOrderConflicts={options.conflicts ?? []}
            readOnly={options.readOnly ?? false}
            {...(options.onEditNumerically === undefined
              ? {}
              : { onEditNumerically: options.onEditNumerically })}
            onRegionsChanged={(next) => {
              current = next;
              rerender();
            }}
          />
        </div>
      </ThemeProvider>,
    );
  }

  return {
    ...view,
    getRegions: () => current,
  };
}

/** Pointer drag with many small steps, like Flutter's `_dragBy`. */
export async function dragOnElement(
  element: Element,
  startOffset: { x: number; y: number },
  delta: { x: number; y: number },
  steps = 24,
): Promise<void> {
  const layoutWidth = 600;
  const layoutHeight = Math.round(layoutWidth * (842 / 595));
  const bounds = new DOMRect(0, 0, layoutWidth, layoutHeight);
  element.getBoundingClientRect = () => bounds;
  const startX = startOffset.x;
  const startY = startOffset.y;
  fireEvent.pointerDown(element, {
    clientX: startX,
    clientY: startY,
    pointerId: 1,
    pointerType: "mouse",
  });
  for (let step = 1; step <= steps; step += 1) {
    fireEvent.pointerMove(element, {
      clientX: startX + (delta.x * step) / steps,
      clientY: startY + (delta.y * step) / steps,
      pointerId: 1,
      pointerType: "mouse",
    });
  }
  fireEvent.pointerUp(element, {
    clientX: startX + delta.x,
    clientY: startY + delta.y,
    pointerId: 1,
    pointerType: "mouse",
  });
}
