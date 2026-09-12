import { beforeAll, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { SidecarClient } from "../../src/renderer/api/client.js";
import type { MaterialResponse } from "../../src/renderer/core/material-data.js";
import { MaterialWindowBody } from "../../src/renderer/features/materials/MaterialWindowPage.js";

/**
 * The material window (Issue #415) is the only place a reviewer sees an
 * imported material's contents. These tests pin the behaviour the acceptance
 * conditions name: the list shows each file's **role**, choosing one shows its
 * pages, paging works, and the two "nothing to show" cases (an empty list, a
 * Word/Excel material with no in-app preview) say so instead of rendering an
 * empty viewer.
 */

beforeAll(() => {
  // jsdom does not implement the object-URL store the viewer feeds `<img>`;
  // the loaders call it for real PNG blobs, so the test provides the two
  // methods rather than the component guarding around their absence.
  for (const name of ["createObjectURL", "revokeObjectURL"] as const) {
    if (typeof URL[name] !== "function") {
      Object.defineProperty(URL, name, {
        configurable: true,
        writable: true,
        value: vi.fn(
          name === "createObjectURL" ? () => "blob:material" : () => {},
        ),
      });
    }
  }
});

function buildMaterial(input: {
  id: string;
  role: MaterialResponse["role"];
  filename?: string | null;
}): MaterialResponse {
  return {
    id: input.id,
    test_id: "t1",
    role: input.role,
    sha256: "a".repeat(64),
    size_bytes: 1234,
    original_filename:
      input.filename === undefined ? `${input.id}.pdf` : input.filename,
    created_at: "2026-01-01T00:00:00Z",
  };
}

interface MaterialClientOptions {
  materials: readonly MaterialResponse[];
  pageCounts?: Readonly<Record<string, number>>;
  unsupportedIds?: readonly string[];
  failListOnce?: boolean;
}

function createMaterialClient(options: MaterialClientOptions): SidecarClient {
  let listCalls = 0;
  const GET = vi.fn(
    async (
      path: string,
      init?: { params?: { path?: Record<string, string> } },
    ) => {
      const path_params = init?.params?.path ?? {};
      if (path === "/tests/{test_id}/materials") {
        listCalls += 1;
        if (options.failListOnce === true && listCalls === 1) {
          return {
            data: undefined,
            response: new Response(null, { status: 500 }),
            error: { message: "boom" },
          };
        }
        return {
          data: options.materials,
          response: new Response(),
          error: undefined,
        };
      }
      if (path === "/tests/{test_id}/materials/{material_id}/pages") {
        const materialId = path_params["material_id"] ?? "";
        if ((options.unsupportedIds ?? []).includes(materialId)) {
          return {
            data: undefined,
            response: new Response(null, { status: 415 }),
            error: { message: "unsupported" },
          };
        }
        const count = options.pageCounts?.[materialId] ?? 1;
        return {
          data: {
            page_count: count,
            pages: Array.from({ length: count }, (_, index) => ({
              page_index: index,
              displayed_width: 595,
              displayed_height: 842,
              rotation: 0,
            })),
          },
          response: new Response(),
          error: undefined,
        };
      }
      if (
        path ===
        "/tests/{test_id}/materials/{material_id}/pages/{page_index}/image"
      ) {
        return {
          data: new Blob([new Uint8Array([137, 80, 78, 71])], {
            type: "image/png",
          }),
          response: new Response(),
          error: undefined,
        };
      }
      return {
        data: undefined,
        response: new Response(null, { status: 404 }),
        error: { message: "not found" },
      };
    },
  );
  return { GET } as unknown as SidecarClient;
}

function renderBody(
  options: MaterialClientOptions,
  selection: { testId: string; materialId?: string | null } = {
    testId: "t1",
  },
) {
  return render(
    <MaterialWindowBody
      client={createMaterialClient(options)}
      selection={{
        testId: selection.testId,
        materialId: selection.materialId ?? null,
      }}
      selectionLoaded
    />,
  );
}

describe("material window list", () => {
  it("lists every material with the role it was registered under", async () => {
    renderBody({
      materials: [
        buildMaterial({
          id: "m-criteria",
          role: "grading_criteria",
          filename: "criteria.pdf",
        }),
        buildMaterial({
          id: "m-sample",
          role: "annotation_sample",
          filename: "sample.pdf",
        }),
        buildMaterial({
          id: "m-resource",
          role: "annotation_resource",
          filename: "resource.xlsx",
        }),
      ],
    });

    expect(await screen.findByTestId("material-item-m-criteria")).toBeDefined();
    expect(screen.getByTestId("material-role-m-criteria").textContent).toBe(
      "採点基準",
    );
    expect(screen.getByTestId("material-role-m-sample").textContent).toBe(
      "添削サンプル",
    );
    expect(screen.getByTestId("material-role-m-resource").textContent).toBe(
      "添削資料",
    );
    // "which file became the 採点基準?" stays answerable by name.
    expect(screen.getByText("criteria.pdf")).toBeDefined();
  });

  it("says so when the test has no materials, instead of an empty viewer", async () => {
    renderBody({ materials: [] });

    expect(await screen.findByTestId("material-empty")).toBeDefined();
  });

  it("names a list failure and recovers when retried", async () => {
    renderBody({
      materials: [buildMaterial({ id: "m-1", role: "grading_criteria" })],
      failListOnce: true,
    });

    expect(await screen.findByTestId("material-list-error")).toBeDefined();
    expect(screen.queryByTestId("material-empty")).toBeNull();

    fireEvent.click(screen.getByTestId("material-list-retry"));

    expect(await screen.findByTestId("material-item-m-1")).toBeDefined();
    expect(screen.queryByTestId("material-list-error")).toBeNull();
  });

  it("says no test was selected rather than showing another test's list", async () => {
    render(
      <MaterialWindowBody
        client={createMaterialClient({ materials: [] })}
        selection={null}
        selectionLoaded
      />,
    );

    expect(await screen.findByTestId("material-no-selection")).toBeDefined();
    expect(screen.queryByTestId("material-list")).toBeNull();
  });
});

describe("material window viewer", () => {
  it("shows the first page and pages through the rest", async () => {
    renderBody({
      materials: [buildMaterial({ id: "m-1", role: "grading_criteria" })],
      pageCounts: { "m-1": 3 },
    });

    expect(await screen.findByTestId("material-page-image")).toBeDefined();
    expect(screen.getByTestId("material-page-indicator").textContent).toContain(
      "1 / 3",
    );

    fireEvent.click(screen.getByTestId("material-page-next"));
    expect(screen.getByTestId("material-page-indicator").textContent).toContain(
      "2 / 3",
    );

    fireEvent.click(screen.getByTestId("material-page-prev"));
    expect(screen.getByTestId("material-page-indicator").textContent).toContain(
      "1 / 3",
    );
  });

  it("opens the material the request named, not only the first", async () => {
    renderBody(
      {
        materials: [
          buildMaterial({ id: "m-1", role: "grading_criteria" }),
          buildMaterial({ id: "m-2", role: "annotation_sample" }),
        ],
        pageCounts: { "m-1": 1, "m-2": 1 },
      },
      { testId: "t1", materialId: "m-2" },
    );

    expect(await screen.findByTestId("material-item-m-2")).toBeDefined();
    await waitFor(() => {
      expect(
        screen.getByTestId("material-item-m-2").getAttribute("aria-pressed"),
      ).toBe("true");
    });
  });

  it("says a Word/Excel material has no in-app preview, not an empty page", async () => {
    renderBody({
      materials: [
        buildMaterial({
          id: "m-x",
          role: "annotation_resource",
          filename: "notes.xlsx",
        }),
      ],
      unsupportedIds: ["m-x"],
    });

    expect(await screen.findByTestId("material-unsupported")).toBeDefined();
    expect(screen.queryByTestId("material-page-image")).toBeNull();
  });
});
