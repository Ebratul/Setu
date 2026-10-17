import type { components } from "./schema.gen";
import { API_BASE_URL, apiGet, apiPost, apiPostForm, ApiError } from "./client";

type S = components["schemas"];
export type DocumentOut = S["DocumentOut"];
export type DocumentDetail = S["DocumentDetail"];
export type DocumentList = S["DocumentList"];
export type FindingOut = S["FindingOut"];
export type VerdictOut = S["VerdictOut"];
export type HiddenSpan = S["HiddenSpanOut"];
export type HiddenTextOut = S["HiddenTextOut"];
export type UploadResult = S["UploadResult"];
export type DocType = DocumentOut["doc_type"];
export type CheckStatus = DocumentOut["check_status"];

export const DOC_TYPES: DocType[] = [
  "PROFORMA_INVOICE",
  "COMMERCIAL_INVOICE",
  "PACKING_LIST",
  "BILL_OF_LADING",
  "CERTIFICATE_OF_ORIGIN",
  "BILL_OF_ENTRY",
  "PRODUCTION_PHOTO",
  "OTHER",
];

/** What a supplier may upload to its own deal. */
export const SUPPLIER_DOC_TYPES: DocType[] = [
  "PROFORMA_INVOICE",
  "PRODUCTION_PHOTO",
  "BILL_OF_LADING",
  "PACKING_LIST",
  "COMMERCIAL_INVOICE",
];

const enc = encodeURIComponent;
const opts = (signal?: AbortSignal) => ({ signal, cache: "no-store" as const });

export const listDocuments = (dealId: string, signal?: AbortSignal) =>
  apiGet<DocumentList>(`/deals/${enc(dealId)}/documents`, opts(signal));

export const getDocument = (id: string, signal?: AbortSignal) =>
  apiGet<DocumentDetail>(`/documents/${enc(id)}`, opts(signal));

export const getHiddenText = (id: string, signal?: AbortSignal) =>
  apiGet<HiddenTextOut>(`/documents/${enc(id)}/hidden-text`, opts(signal));

export const recheckDocument = (id: string) =>
  apiPost<DocumentDetail>(`/documents/${enc(id)}/recheck`, {});

export function uploadDocument(dealId: string, docType: DocType, file: File) {
  const form = new FormData();
  form.append("doc_type", docType);
  form.append("file", file);
  return apiPostForm<UploadResult>(`/deals/${enc(dealId)}/documents`, form);
}

/** `file_url` is API-relative (e.g. /documents/<id>/file?token=...); only that shape is accepted. */
export function fileHref(fileUrl: string | null): string | null {
  if (!fileUrl || !/^\/documents\/[0-9a-f-]{36}\/file\?token=[\w.%~-]+(&inline=1)?$/i.test(fileUrl)) {
    return null;
  }
  return `${API_BASE_URL}${fileUrl}`;
}

export const acceptReference = (id: string) =>
  apiPost<DocumentDetail>(`/documents/${enc(id)}/accept-reference`, {});

export function isImageMime(mime: string): boolean {
  return mime === "image/png" || mime === "image/jpeg";
}

// --- upload pre-check ---------------------------------------------------------------------

export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
const EXT = /\.(pdf|png|jpe?g)$/i;
const IMAGE_EXT = /\.(png|jpe?g)$/i;
const TYPES = new Set(["application/pdf", "image/png", "image/jpeg"]);

export type FileProblem = "EMPTY_FILE" | "FILE_TOO_LARGE" | "UNSUPPORTED_FILE_TYPE";

/** Friendly pre-check only; the server re-validates by magic bytes. */
export function precheckFile(file: { name: string; size: number; type: string }): FileProblem | null {
  if (file.size === 0) return "EMPTY_FILE";
  if (file.size > MAX_UPLOAD_BYTES) return "FILE_TOO_LARGE";
  if (!EXT.test(file.name) || (file.type && !TYPES.has(file.type))) return "UNSUPPORTED_FILE_TYPE";
  return null;
}

/** Photos must be images, every other type a PDF (as the server enforces). */
export function typeFitsFile(docType: DocType, fileName: string): boolean {
  const image = IMAGE_EXT.test(fileName);
  return docType === "PRODUCTION_PHOTO" ? image : !image;
}

const SUGGEST: [RegExp, DocType][] = [
  [/proforma|(^|[^a-z])pi([^a-z]|$)/i, "PROFORMA_INVOICE"],
  [/packing|(^|[^a-z])pl([^a-z]|$)/i, "PACKING_LIST"],
  [/lading|(^|[^a-z])b[/_-]?l([^a-z]|$)/i, "BILL_OF_LADING"],
  [/origin|(^|[^a-z])coo([^a-z]|$)/i, "CERTIFICATE_OF_ORIGIN"],
  [/entry|(^|[^a-z])boe([^a-z]|$)/i, "BILL_OF_ENTRY"],
  [/photo|(^|[^a-z])img/i, "PRODUCTION_PHOTO"],
  [/commercial|invoice|(^|[^a-z])ci([^a-z]|$)/i, "COMMERCIAL_INVOICE"],
];

export function suggestDocType(fileName: string, allowed: DocType[] = DOC_TYPES): DocType {
  for (const [re, type] of SUGGEST) if (re.test(fileName) && allowed.includes(type)) return type;
  if (IMAGE_EXT.test(fileName) && allowed.includes("PRODUCTION_PHOTO")) return "PRODUCTION_PHOTO";
  return allowed.includes("OTHER") ? "OTHER" : allowed[0];
}

/** i18n key for an upload failure (stable code first, then HTTP status). */
export function uploadErrorKey(error: unknown): string {
  if (error instanceof ApiError) {
    const known = [
      "FILE_TOO_LARGE",
      "UNSUPPORTED_FILE_TYPE",
      "WRONG_FILE_TYPE",
      "EMPTY_FILE",
      "DUPLICATE_DOCUMENT",
      "DEAL_CLOSED",
      "FORBIDDEN",
    ];
    if (error.code && known.includes(error.code)) return `docErr.${error.code}`;
    if (error.status === 413) return "docErr.FILE_TOO_LARGE";
    if (error.status === 415) return "docErr.UNSUPPORTED_FILE_TYPE";
    if (error.status === 409) return "docErr.DUPLICATE_DOCUMENT";
    if (error.status === 403) return "docErr.FORBIDDEN";
    if (error.status === 404) return "docErr.NOT_FOUND";
    if (error.status === 401) return "docErr.SESSION";
  }
  return "docErr.generic";
}

// --- status model ---------------------------------------------------------------------------

export type DocUiStatus = "UPLOADED" | "CHECKING" | "PASSED" | "WARNING" | "FAILED" | "REJECTED";

export function docUiStatus(d: Pick<DocumentOut, "status" | "check_status">): DocUiStatus {
  if (d.status === "REJECTED") return "REJECTED";
  switch (d.check_status) {
    case "PASSED":
    case "WARNING":
    case "FAILED":
      return d.check_status;
    case "PENDING":
      return "CHECKING";
    default:
      return "UPLOADED";
  }
}

export const isChecking = (d: Pick<DocumentOut, "status" | "check_status">) =>
  d.status !== "REJECTED" && (d.check_status === "PENDING" || d.check_status === "NOT_RUN");

export type SupplierStatus = "UPLOADED" | "REVIEW" | "ACCEPTED" | "ATTENTION";

/** The only view a supplier gets: no score, no reasons. */
export function supplierStatus(d: Pick<DocumentOut, "status" | "check_status">): SupplierStatus {
  if (d.status === "IN_REVIEW") return "REVIEW";
  switch (docUiStatus(d)) {
    case "PASSED":
      return "ACCEPTED";
    case "WARNING":
    case "FAILED":
    case "REJECTED":
      return "ATTENTION";
    case "CHECKING":
      return "REVIEW";
    default:
      return "UPLOADED";
  }
}
