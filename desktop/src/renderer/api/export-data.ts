/**
 * Export API operations (Issue #23 / #142).
 *
 * Uses the generated OpenAPI client only — no hand-written fetch.
 */

import type { SidecarClient } from "./client.js";
import type { components } from "./generated/schema.js";
import {
  ExportDataError,
  exportConflictFromResponse,
} from "../core/export-conflict.js";

export {
  ExportConflictError,
  ExportDataError,
} from "../core/export-conflict.js";

export type ExportRequestResponse =
  components["schemas"]["ExportRequestResponse"];
export type ExportResponse = components["schemas"]["ExportResponse"];
export type JobResponse = components["schemas"]["JobResponse"];
export type BulkExportResponse = components["schemas"]["BulkExportResponse"];
export type BulkExportItemResponse =
  components["schemas"]["BulkExportItemResponse"];

function exportErrorMessage(body: unknown, fallback: string): string {
  if (typeof body === "object" && body !== null && "message" in body) {
    const message = (body as { message?: unknown }).message;
    if (typeof message === "string") {
      return message;
    }
  }
  return fallback;
}

export async function requestSubmissionExport(
  client: SidecarClient,
  submissionId: string,
): Promise<ExportRequestResponse> {
  const response = await client.POST("/submissions/{submission_id}/export", {
    params: { path: { submission_id: submissionId } },
  });

  if (response.error !== undefined || response.data === undefined) {
    const conflict = exportConflictFromResponse(
      response.response.status,
      response.error,
    );
    if (conflict !== null) {
      throw conflict;
    }
    throw new ExportDataError(
      exportErrorMessage(response.error, "PDF出力の要求に失敗しました"),
    );
  }

  return response.data;
}

export async function listExports(
  client: SidecarClient,
  submissionId: string,
): Promise<readonly ExportResponse[]> {
  const response = await client.GET("/submissions/{submission_id}/exports", {
    params: { path: { submission_id: submissionId } },
  });

  if (response.error !== undefined || response.data === undefined) {
    throw new ExportDataError("出力一覧の取得に失敗しました");
  }

  return response.data;
}

export async function getJob(
  client: SidecarClient,
  jobId: string,
): Promise<JobResponse> {
  const response = await client.GET("/jobs/{job_id}", {
    params: { path: { job_id: jobId } },
  });

  if (response.error !== undefined || response.data === undefined) {
    throw new ExportDataError("ジョブ状態の取得に失敗しました");
  }

  return response.data;
}

export async function retryJob(
  client: SidecarClient,
  jobId: string,
): Promise<JobResponse> {
  const response = await client.POST("/jobs/{job_id}/retry", {
    params: { path: { job_id: jobId } },
  });

  if (response.error !== undefined || response.data === undefined) {
    throw new ExportDataError(
      exportErrorMessage(response.error, "ジョブの再試行に失敗しました"),
    );
  }

  return response.data;
}

export async function cancelJob(
  client: SidecarClient,
  jobId: string,
): Promise<JobResponse> {
  const response = await client.POST("/jobs/{job_id}/cancel", {
    params: { path: { job_id: jobId } },
  });

  if (response.error !== undefined || response.data === undefined) {
    throw new ExportDataError("ジョブの取り消しに失敗しました");
  }

  return response.data;
}

export async function requestBulkExport(
  client: SidecarClient,
  testId: string,
  submissionIds: readonly string[],
): Promise<BulkExportResponse> {
  const response = await client.POST("/tests/{test_id}/export", {
    params: { path: { test_id: testId } },
    body: { submission_ids: [...submissionIds] },
  });

  if (response.error !== undefined || response.data === undefined) {
    throw new ExportDataError(
      exportErrorMessage(response.error, "一括出力の要求に失敗しました"),
    );
  }

  return response.data;
}

export async function getExportFile(
  client: SidecarClient,
  exportId: string,
): Promise<Uint8Array> {
  const response = await client.GET("/exports/{export_id}/file", {
    params: { path: { export_id: exportId } },
    parseAs: "blob",
  });

  if (response.error !== undefined || response.data === undefined) {
    throw new ExportDataError("出力ファイルの取得に失敗しました");
  }

  const blob = response.data as Blob;
  return new Uint8Array(await blob.arrayBuffer());
}
