import { useEffect, useMemo, useRef, useState, type JSX } from "react";

import type { SidecarStatus } from "../../../shared/bridge.js";
import type { MaterialWindowSelection } from "../../../shared/material-window.js";
import { createSidecarClient, type SidecarClient } from "../../api/client.js";
import {
  loadMaterialPages,
  loadMaterials,
  MaterialPreviewUnsupportedError,
  type MaterialPageState,
  type MaterialResponse,
} from "../../core/material-data.js";
import { materialRoleLabel } from "../../core/material-role-labels.js";
import { SidecarStartupOverlay } from "../startup/SidecarStartupOverlay.js";
import { ErrorNotice, Spinner, secondaryButtonClass } from "../ui/screen-ui.js";

/**
 * The separate material window (Issue #415).
 *
 * The owner asked for imported materials in **another window**, so the main
 * process owns a single `BrowserWindow` and points it at the same renderer
 * with `?window=material` (`main.ts`). This component is what that window
 * mounts: the same sidecar bootstrap as `App`, then a master-detail view --
 * the test's materials on the left, the selected material's pages on the
 * right. Re-using the window just changes the selection it is handed.
 */

function selectedMaterialOf(
  materials: readonly MaterialResponse[],
  materialId: string | null,
): MaterialResponse | null {
  if (materials.length === 0) {
    return null;
  }
  return (
    materials.find((material) => material.id === materialId) ??
    materials[0] ??
    null
  );
}

export function MaterialWindowBody({
  client,
  selection,
  selectionLoaded,
}: {
  client: SidecarClient | null;
  selection: MaterialWindowSelection | null;
  selectionLoaded: boolean;
}): JSX.Element {
  const testId = selection?.testId ?? null;
  const [materials, setMaterials] = useState<
    readonly MaterialResponse[] | null
  >(null);
  const [listError, setListError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [pickedId, setPickedId] = useState<string | null>(null);

  // A new request (the window being reused for another test, or another
  // material) replaces what is shown instead of leaving the old list around.
  useEffect(() => {
    setPickedId(selection?.materialId ?? null);
    setMaterials(null);
    setListError(null);
  }, [selection?.testId, selection?.materialId]);

  useEffect(() => {
    if (client === null || testId === null) {
      return undefined;
    }
    let active = true;
    setMaterials(null);
    setListError(null);
    loadMaterials(client, testId)
      .then((items) => {
        if (active) {
          setMaterials(items);
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setListError(
            error instanceof Error ? error.message : "資料一覧を取得できません",
          );
        }
      });
    return () => {
      active = false;
    };
  }, [client, testId, reloadKey]);

  const selected = useMemo(
    () => (materials === null ? null : selectedMaterialOf(materials, pickedId)),
    [materials, pickedId],
  );

  if (selectionLoaded && testId === null) {
    return (
      <p data-testid="material-no-selection" className="text-body-medium">
        表示するテストが指定されていません。
      </p>
    );
  }

  return (
    <div
      data-testid="material-window"
      className="flex min-h-screen flex-col gap-lg bg-surface p-lg text-on-surface"
    >
      <header className="flex flex-wrap items-center justify-between gap-md">
        <div className="min-w-0">
          <h1 className="text-title-medium font-medium leading-ui">資料</h1>
          <p className="mt-xs text-body-small text-on-surface-variant">
            取り込んだ資料と、採点基準などの役割を確認できます。
          </p>
        </div>
        <button
          type="button"
          data-testid="material-close-button"
          className={secondaryButtonClass()}
          onClick={() => window.close()}
        >
          閉じる
        </button>
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-lg md:flex-row">
        <MaterialList
          materials={materials}
          error={listError}
          selectedId={selected?.id ?? null}
          onSelect={setPickedId}
          onRetry={() => {
            setReloadKey((key) => key + 1);
          }}
        />
        <MaterialViewer
          client={client}
          testId={testId}
          material={selected}
          loading={materials === null && listError === null}
        />
      </div>
    </div>
  );
}

function MaterialList({
  materials,
  error,
  selectedId,
  onSelect,
  onRetry,
}: {
  materials: readonly MaterialResponse[] | null;
  error: string | null;
  selectedId: string | null;
  onSelect: (materialId: string) => void;
  onRetry: () => void;
}): JSX.Element {
  return (
    <nav
      aria-label="資料一覧"
      data-testid="material-list"
      className="w-full shrink-0 md:w-80"
    >
      {error !== null ? (
        <ErrorNotice
          testId="material-list-error"
          action={
            <button
              type="button"
              data-testid="material-list-retry"
              className={secondaryButtonClass()}
              onClick={onRetry}
            >
              再読み込み
            </button>
          }
        >
          {error}
        </ErrorNotice>
      ) : null}
      {error === null && materials === null ? (
        <p
          data-testid="material-list-loading"
          className="flex items-center gap-sm text-body-medium text-on-surface-variant"
        >
          <Spinner />
          資料一覧を読み込んでいます…
        </p>
      ) : null}
      {error === null && materials !== null && materials.length === 0 ? (
        <p data-testid="material-empty" className="text-body-medium">
          このテストにはまだ資料がありません。
        </p>
      ) : null}
      {error === null && materials !== null && materials.length > 0 ? (
        <ul className="flex flex-col gap-sm">
          {materials.map((material) => {
            const active = material.id === selectedId;
            return (
              <li key={material.id}>
                <button
                  type="button"
                  data-testid={`material-item-${material.id}`}
                  aria-pressed={active}
                  onClick={() => onSelect(material.id)}
                  className={`w-full rounded-lg p-md text-left transition-colors ${
                    active
                      ? "bg-primary-container text-on-primary-container"
                      : "bg-surface-container text-on-surface hover:bg-surface-container-high"
                  } focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary`}
                >
                  <span
                    data-testid={`material-role-${material.id}`}
                    className="block text-ui-label"
                  >
                    {materialRoleLabel(material.role)}
                  </span>
                  <span className="mt-xs block truncate text-body-small text-on-surface-variant">
                    {material.original_filename ?? "（ファイル名なし）"}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </nav>
  );
}

function MaterialViewer({
  client,
  testId,
  material,
  loading,
}: {
  client: SidecarClient | null;
  testId: string | null;
  material: MaterialResponse | null;
  loading: boolean;
}): JSX.Element {
  const [pageState, setPageState] = useState<
    | { readonly status: "idle" }
    | { readonly status: "loading" }
    | { readonly status: "error"; readonly message: string }
    | { readonly status: "unsupported" }
    | { readonly status: "ready"; readonly pages: readonly MaterialPageState[] }
  >({ status: "idle" });
  const [pageIndex, setPageIndex] = useState(0);
  const objectUrlsRef = useRef<string[]>([]);

  const materialId = material?.id ?? null;

  useEffect(() => {
    if (materialId === null || testId === null || client === null) {
      setPageState({ status: "idle" });
      return undefined;
    }
    let active = true;
    const created: string[] = [];
    setPageState({ status: "loading" });
    setPageIndex(0);
    loadMaterialPages(client, testId, materialId)
      .then((pages) => {
        for (const page of pages) {
          if (page.image.objectUrl !== null) {
            created.push(page.image.objectUrl);
          }
        }
        if (!active) {
          for (const url of created) {
            URL.revokeObjectURL(url);
          }
          return;
        }
        objectUrlsRef.current = created;
        setPageState({ status: "ready", pages });
      })
      .catch((error: unknown) => {
        if (!active) {
          return;
        }
        if (error instanceof MaterialPreviewUnsupportedError) {
          setPageState({ status: "unsupported" });
          return;
        }
        setPageState({
          status: "error",
          message:
            error instanceof Error
              ? error.message
              : "資料の中身を取得できません",
        });
      });
    return () => {
      active = false;
      for (const url of created) {
        URL.revokeObjectURL(url);
      }
    };
  }, [client, testId, materialId]);

  useEffect(() => {
    const urls = objectUrlsRef.current;
    return () => {
      for (const url of urls) {
        URL.revokeObjectURL(url);
      }
    };
  }, []);

  const pages = pageState.status === "ready" ? pageState.pages : null;
  const current = pages?.[pageIndex] ?? null;

  return (
    <section
      data-testid="material-viewer"
      aria-label="資料の中身"
      className="flex min-h-0 min-w-0 flex-1 flex-col gap-md rounded-xl bg-surface-container p-lg"
    >
      {material === null ? (
        <p data-testid="material-viewer-empty" className="text-body-medium">
          {loading
            ? "資料を選んでください。"
            : "資料を選ぶと中身が表示されます。"}
        </p>
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-sm">
            <p className="min-w-0 text-ui-label">
              {materialRoleLabel(material.role)}
            </p>
            {pages !== null && pages.length > 1 ? (
              <div className="flex items-center gap-sm">
                <PageNavButton
                  testId="material-page-prev"
                  label="前のページ"
                  disabled={pageIndex <= 0}
                  onClick={() => {
                    setPageIndex((index) => Math.max(0, index - 1));
                  }}
                />
                <span
                  data-testid="material-page-indicator"
                  aria-live="polite"
                  className="tabular-nums text-body-medium"
                >
                  {pageIndex + 1} / {pages.length}
                </span>
                <PageNavButton
                  testId="material-page-next"
                  label="次のページ"
                  disabled={pageIndex >= pages.length - 1}
                  onClick={() => {
                    setPageIndex((index) =>
                      Math.min(pages.length - 1, index + 1),
                    );
                  }}
                />
              </div>
            ) : null}
          </div>

          <div className="min-h-0 flex-1 overflow-auto">
            {pageState.status === "loading" ? (
              <p
                data-testid="material-viewer-loading"
                className="flex items-center gap-sm text-body-medium text-on-surface-variant"
              >
                <Spinner />
                資料を読み込んでいます…
              </p>
            ) : null}
            {pageState.status === "unsupported" ? (
              <p
                data-testid="material-unsupported"
                className="text-body-medium"
              >
                {MaterialUnsupportedMessage}
              </p>
            ) : null}
            {pageState.status === "error" ? (
              <p
                data-testid="material-viewer-error"
                className="text-body-medium"
              >
                {pageState.message}
              </p>
            ) : null}
            {current !== null && current.image.objectUrl !== null ? (
              <img
                data-testid="material-page-image"
                src={current.image.objectUrl}
                alt={`${materialRoleLabel(material.role)} の ${pageIndex + 1} ページ目`}
                className="mx-auto block max-w-full"
              />
            ) : null}
            {current !== null && current.image.objectUrl === null ? (
              <p
                data-testid="material-page-unavailable"
                className="text-body-medium"
              >
                このページを読み込めませんでした。
              </p>
            ) : null}
          </div>
        </>
      )}
    </section>
  );
}

const MaterialUnsupportedMessage =
  "この形式の資料（Word / Excel など）はアプリ内でプレビューできません。資料一覧の役割とファイル名は確認できます。";

function PageNavButton({
  testId,
  label,
  disabled,
  onClick,
}: {
  testId: string;
  label: string;
  disabled: boolean;
  onClick: () => void;
}): JSX.Element {
  return (
    <button
      type="button"
      data-testid={testId}
      aria-label={label}
      className={secondaryButtonClass()}
      disabled={disabled}
      onClick={onClick}
    >
      <span aria-hidden>{testId === "material-page-prev" ? "‹" : "›"}</span>
      {label}
    </button>
  );
}

function Overlay({
  status,
  logPath,
  children,
}: {
  status: SidecarStatus;
  logPath: string | null;
  children: JSX.Element;
}): JSX.Element {
  return (
    <SidecarStartupOverlay
      status={status}
      onRestart={() => {
        void window.autoScoring?.restartSidecar();
      }}
      logPath={logPath}
    >
      {children}
    </SidecarStartupOverlay>
  );
}

export function MaterialWindowApp(): JSX.Element {
  const [status, setStatus] = useState<SidecarStatus>({ kind: "starting" });
  const [logPath, setLogPath] = useState<string | null>(null);
  const [selection, setSelection] = useState<MaterialWindowSelection | null>(
    null,
  );
  const [selectionLoaded, setSelectionLoaded] = useState(false);

  useEffect(() => {
    const bridge = window.autoScoring;
    if (bridge === undefined) {
      return undefined;
    }
    void bridge.getSidecarStatus().then(setStatus);
    void bridge.getSidecarLogPath().then(setLogPath);
    void bridge.getMaterialSelection().then((current) => {
      setSelection(current);
      setSelectionLoaded(true);
    });
    const unsubscribeStatus = bridge.onSidecarStatusChange(setStatus);
    const unsubscribeSelection = bridge.onMaterialSelectionChange(setSelection);
    return () => {
      unsubscribeStatus();
      unsubscribeSelection();
    };
  }, []);

  const client = useMemo(() => {
    if (status.kind !== "ready") {
      return null;
    }
    return createSidecarClient(status.connection);
  }, [status]);

  return (
    <Overlay status={status} logPath={logPath}>
      <MaterialWindowBody
        client={client}
        selection={selection}
        selectionLoaded={selectionLoaded}
      />
    </Overlay>
  );
}
