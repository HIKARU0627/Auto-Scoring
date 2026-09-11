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
