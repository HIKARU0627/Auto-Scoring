import type {
  SidecarFetchRequest,
  SidecarFetchResponse,
} from "../shared/sidecar-fetch.js";
import { readE2eEnv } from "./e2e-env.js";
import {
  assertLoopbackConnection,
  type InternalSidecarConnection,
} from "./sidecar-connection.js";

function headersToRecord(headers: Headers): Readonly<Record<string, string>> {
  const record: Record<string, string> = {};
  headers.forEach((value, key) => {
    record[key] = value;
  });
  return record;
}

/** E2E-only switch that makes grading jobs report progress then success. */
const E2E_GRADING_JOBS_STUB_ENV = "AUTO_SCORING_E2E_STUB_GRADING_JOBS";

/**
 * E2E-only switch that serves the bulk-export endpoints from a stub.
 *
 * The PDF engine resolves only Windows-shipped Japanese fonts
 * (`adapters/pdf/pdfium_pypdf_engine.py`), so a real export cannot render on a
 * non-Windows E2E runner. This stub lets the spec exercise the part under test
 * -- `chooseFolder` and the main-process file write -- without the renderer.
 * Never active in a packaged build (`readE2eEnv`).
 */
const E2E_BULK_EXPORT_STUB_ENV = "AUTO_SCORING_E2E_STUB_BULK_EXPORT";

/**
 * How many times a submission's job list is served as "running" before the
 * E2E stub reports it finished. More than one so a spec can enter the review
 * screen, observe the in-progress state, and then see it settle without any
 * user action (Issue #319). Four reads is ~8s at the screen's 2s poll, wide
 * enough that the assertion does not race the transition.
 */
const E2E_GRADING_JOBS_RUNNING_READS = 4;

const e2eGradingJobsReads = new Map<string, number>();

/**
 * Raised when the request fails before the sidecar answers. The message is a
 * fixed string on purpose: a transport failure's own text can name the URL, the
 * port, or the token, and none of those may reach a log or an error banner
 * (INV-204).
 */
export class SidecarTransportError extends Error {
  constructor() {
    super("sidecar request failed");
    this.name = "SidecarTransportError";
  }
}

/**
 * Performs an HTTP request against the sidecar from the main process.
 * Authorization is attached here so the renderer never sees the token.
 *
 * The connection is checked against loopback first (INV-203), and any
 * transport failure is collapsed into a sanitized {@link SidecarTransportError}
 * (INV-204) rather than rethrown with its host, port, or token.
 */
function maybeStubCriteriaExtract(
  request: SidecarFetchRequest,
): SidecarFetchResponse | null {
  if (readE2eEnv("AUTO_SCORING_E2E_STUB_CRITERIA_EXTRACT") === undefined) {
    return null;
  }
  const match = /^\/tests\/([^/]+)\/criteria\/extract$/.exec(request.urlPath);
  if (request.method !== "POST" || match === null) {
    return null;
  }
  const testId = match[1];
  const body = {
    test_id: testId,
    status: "draft",
    revision: 1,
    extracted: true,
    questions: [
      {
        number: "問1",
        points: 10,
        model_answer: "模範解答",
        criteria: [],
        source_pages: [1],
      },
    ],
    declared_total_points: null,
    unreadable_pages: [],
    note: null,
    totals: {
      known_points: 10,
      unknown_count: 0,
      declared_total_points: null,
      declared_difference: null,
      is_complete: true,
    },
  };
  return {
    status: 200,
    statusText: "OK",
    headers: { "content-type": "application/json" },
    bodyBase64: Buffer.from(JSON.stringify(body)).toString("base64"),
  };
}

function jsonResponse(status: number, body: unknown): SidecarFetchResponse {
  return {
    status,
    statusText: status === 200 ? "OK" : String(status),
    headers: { "content-type": "application/json" },
    bodyBase64: Buffer.from(JSON.stringify(body)).toString("base64"),
  };
}

/**
 * Serves `POST /tests/{id}/export` and `GET /exports/{id}/file` from the E2E
 * bulk-export stub. Reusing an already-exported file is what the real API
 * returns when nothing changed, so the runner skips its job polling and goes
 * straight to the write this spec is about.
 */
function maybeStubBulkExport(
  request: SidecarFetchRequest,
): SidecarFetchResponse | null {
  if (readE2eEnv(E2E_BULK_EXPORT_STUB_ENV) === undefined) {
    return null;
  }
  if (request.method === "POST") {
    const match = /^\/tests\/([^/]+)\/export$/.exec(request.urlPath);
    if (match === null) {
      return null;
    }
    let submissionIds: string[] = [];
    try {
      const body = JSON.parse(
        Buffer.from(request.bodyBase64 ?? "", "base64").toString("utf8"),
      ) as { submission_ids?: unknown };
      if (Array.isArray(body.submission_ids)) {
        submissionIds = body.submission_ids.filter(
          (id): id is string => typeof id === "string",
        );
      }
    } catch {
      return null;
    }
    return jsonResponse(200, {
      test_id: match[1],
      items: submissionIds.map((submissionId) => ({
        submission_id: submissionId,
        status: "reused",
        export: {
          id: `e2e-export-${submissionId}`,
          job_id: `e2e-job-${submissionId}`,
          submission_id: submissionId,
          file_path: `exports/${submissionId}_corrected.pdf`,
          file_sha256: "0".repeat(64),
          created_at: "2026-01-01T00:00:00Z",
        },
      })),
    });
  }
  if (request.method === "GET") {
    const match = /^\/exports\/([^/]+)\/file$/.exec(request.urlPath);
    if (match === null) {
      return null;
    }
    const bytes = Buffer.from("%PDF-1.4\n% e2e stub\n%%EOF\n", "utf8");
    return {
      status: 200,
      statusText: "OK",
      headers: { "content-type": "application/pdf" },
      bodyBase64: bytes.toString("base64"),
    };
  }
  return null;
}

/**
 * Rewrites a real `GET /submissions/{id}/jobs` body so grading appears to take
 * a moment, without calling an external AI. Only the job `state`/`usable`
 * fields are changed; the submission, its questions and the real file store
 * are all genuine, so the review screen's own polling is what the E2E
 * exercises. No-op unless `AUTO_SCORING_E2E_STUB_GRADING_JOBS` is set.
 */
function maybeRewriteGradingJobs(
  request: SidecarFetchRequest,
  body: Buffer,
): Buffer {
  if (readE2eEnv(E2E_GRADING_JOBS_STUB_ENV) === undefined) {
    return body;
  }
  if (request.method !== "GET") {
    return body;
  }
  const match = /^\/submissions\/([^/]+)\/jobs$/.exec(request.urlPath);
  if (match === null) {
    return body;
  }
  const submissionId = match[1] ?? "";
  const reads = (e2eGradingJobsReads.get(submissionId) ?? 0) + 1;
  e2eGradingJobsReads.set(submissionId, reads);
  const running = reads <= E2E_GRADING_JOBS_RUNNING_READS;

  let parsed: unknown;
  try {
    parsed = JSON.parse(body.toString("utf8"));
  } catch {
    return body;
  }
  if (!Array.isArray(parsed)) {
    return body;
  }
  const rewritten = parsed.map((job) => {
    if (job === null || typeof job !== "object") {
      return job;
    }
    return running
      ? { ...job, state: "running", usable: null }
      : { ...job, state: "succeeded", usable: true };
  });
  return Buffer.from(JSON.stringify(rewritten), "utf8");
}

export async function sidecarFetch(
  connection: InternalSidecarConnection,
  request: SidecarFetchRequest,
): Promise<SidecarFetchResponse> {
  const stubbed = maybeStubCriteriaExtract(request);
  if (stubbed !== null) {
    return stubbed;
  }

  const stubbedExport = maybeStubBulkExport(request);
  if (stubbedExport !== null) {
    return stubbedExport;
  }

  assertLoopbackConnection(connection);

  const url = `http://${connection.host}:${connection.port}${request.urlPath}`;
  const headers = new Headers(request.headers ?? {});
  headers.set("Authorization", `Bearer ${connection.token}`);

  const fetchInit: RequestInit = {
    method: request.method,
    headers,
  };
  if (request.bodyBase64 !== undefined && request.bodyBase64.length > 0) {
    fetchInit.body = Buffer.from(request.bodyBase64, "base64");
  }

  let response: Response;
  let responseBuffer: Buffer;
  try {
    response = await fetch(url, fetchInit);
    responseBuffer = Buffer.from(await response.arrayBuffer());
  } catch {
    // The cause is deliberately dropped: it can carry the host and port.
    throw new SidecarTransportError();
  }
  responseBuffer = maybeRewriteGradingJobs(request, responseBuffer);

  return {
    status: response.status,
    statusText: response.statusText,
    headers: headersToRecord(response.headers),
    bodyBase64: responseBuffer.toString("base64"),
  };
}
