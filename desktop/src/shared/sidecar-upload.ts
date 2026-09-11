/**
 * Helpers for multipart uploads to the sidecar.
 *
 * Kept in `src/shared` so both main (actual upload) and tests (INV-134/135)
 * can import without crossing the renderer boundary.
 */

export type MaterialRole =
  | "student_answer"
  | "grading_criteria"
  | "annotation_resource"
  | "annotation_sample"
  | "reference"
  | "ignore";

/** Wire name the sidecar expects (INV-134). */
export function materialRoleWireValue(role: MaterialRole): string {
  return role;
}

/** PDF uploads must declare application/pdf (INV-135). */
export const PDF_CONTENT_TYPE = "application/pdf";

export interface SidecarFileField {
  readonly fieldName: string;
  readonly filePath: string;
  readonly contentType?: string;
}

export interface SidecarMultipartRequest {
  readonly method: "POST" | "PUT";
  readonly urlPath: string;
  readonly fileFields: readonly SidecarFileField[];
  readonly formFields?: Readonly<Record<string, string | readonly string[]>>;
}

export interface SidecarMultipartResponse {
  readonly status: number;
  readonly body: unknown;
}
