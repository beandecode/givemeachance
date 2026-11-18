import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type Schemas = components["schemas"];

/** `data` of a JSON operation's success envelope, for responses defined inline (not as components). */
export type OkData<
  P extends keyof paths,
  M extends "get" | "post" | "put" | "patch" | "delete",
> = paths[P][M] extends {
  responses: infer R;
}
  ? R[keyof R & (200 | 201 | 202)] extends { content: { "application/json": { data: infer D } } }
    ? D
    : never
  : never;

export type Task = Schemas["Task"];
export type JobSummary = Schemas["JobSummary"];
export type JobDetail = OkData<"/api/v1/jobs/{job_id}", "get">;
export type ApplicationStatus = JobSummary["application_status"];
export type JobPage = OkData<"/api/v1/jobs", "get">;
export type Journey = OkData<"/api/v1/journey", "get">;
export type JobJourney = JobDetail["journey"];
export type Preferences = OkData<"/api/v1/preferences", "get">;
export type DocumentKind = "resume" | "cover_letter";

/** Typed client for /api/v1, generated from docs/openapi.json (`npm run gen:api`). */
export const client = createClient<paths>({
  // Absolute same-origin URLs (also lets tests run under jsdom, whose fetch can't resolve relative ones).
  baseUrl: window.location.origin,
  credentials: "same-origin",
  // Look fetch up per call, so test interceptors installed after import still apply.
  fetch: (request) => globalThis.fetch(request),
});

interface ErrorBody {
  error_code?: number;
  message?: string;
  correlation_id?: string;
  details?: { field: string; message: string }[] | null;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: number | null;
  readonly correlationId: string | null;
  readonly details: { field: string; message: string }[];

  constructor(status: number, body: ErrorBody | null, fallbackMessage: string) {
    super(body?.message ?? fallbackMessage);
    this.name = "ApiError";
    this.status = status;
    this.code = body?.error_code ?? null;
    this.correlationId = body?.correlation_id ?? null;
    this.details = body?.details ?? [];
  }
}

interface Envelope<T> {
  data: T;
}

interface FetchResult<T> {
  data?: Envelope<T>;
  error?: unknown;
  response: Response;
}

function errorBody(error: unknown): ErrorBody | null {
  return typeof error === "object" && error !== null ? error : null;
}

/** Await an openapi-fetch call and return the envelope's `data`, or throw an {@link ApiError}. */
export async function unwrap<T>(request: Promise<FetchResult<T>>): Promise<T> {
  let result: FetchResult<T>;
  try {
    result = await request;
  } catch {
    throw new ApiError(0, null, "network error");
  }
  if (result.response.ok && result.data !== undefined) {
    return result.data.data;
  }
  throw new ApiError(result.response.status, errorBody(result.error), result.response.statusText);
}

export function exportUrl(kind: DocumentKind, documentId: number, format: "pdf" | "docx"): string {
  return `/api/v1/documents/${kind}/${String(documentId)}/export?format=${format}`;
}
