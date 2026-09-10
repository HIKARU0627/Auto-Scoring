import { readFile } from "node:fs/promises";
import * as path from "node:path";

import {
  PDF_CONTENT_TYPE,
  type SidecarMultipartRequest,
  type SidecarMultipartResponse,
} from "../shared/sidecar-upload.js";

/**
 * Performs a multipart upload from disk paths. File bytes never reach the
 * renderer — only paths cross IPC.
 */
export async function sidecarMultipartUpload(
  request: SidecarMultipartRequest,
): Promise<SidecarMultipartResponse> {
  const { connection, method, urlPath, fileFields, formFields } = request;
  const formData = new FormData();

  if (formFields !== undefined) {
    for (const key of Object.keys(formFields)) {
      const value = formFields[key];
      if (value === undefined) {
        continue;
      }
      if (typeof value === "string") {
        formData.append(key, value);
        continue;
      }
      for (const entry of value) {
        formData.append(key, entry);
      }
    }
  }

  for (const field of fileFields) {
    const bytes = await readFile(field.filePath);
    const contentType = field.contentType ?? PDF_CONTENT_TYPE;
    const blob = new Blob([new Uint8Array(bytes)], { type: contentType });
    formData.append(field.fieldName, blob, path.basename(field.filePath));
  }

  const url = `http://${connection.host}:${connection.port}${urlPath}`;
  const response = await fetch(url, {
    method,
    headers: {
      Authorization: `Bearer ${connection.token}`,
    },
    body: formData,
  });

  const text = await response.text();
  let body: unknown = null;
  if (text.length > 0) {
    try {
      body = JSON.parse(text) as unknown;
    } catch {
      body = text;
    }
  }

  return { status: response.status, body };
}
