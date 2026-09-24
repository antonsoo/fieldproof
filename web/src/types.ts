// Mirrors the JSON shapes produced by fieldproof's Python side
// (fieldproof.verify.engine, fieldproof.server.app) - kept as plain types
// rather than generated, since the surface is small and stable.

export type FieldStatus = "verified" | "needs_review" | "unsupported";

export interface Rect {
  x0: number;
  top: number;
  x1: number;
  bottom: number;
}

export interface FieldVerification {
  path: string;
  value: string | number | boolean;
  status: FieldStatus;
  reasons: string[];
  match_score: number | null;
  matched_text: string | null;
  page: number | null;
  rects: Rect[];
}

export interface CrossFieldIssue {
  fields: string[];
  message: string;
}

export interface VerificationReport {
  fields: FieldVerification[];
  cross_field_issues: CrossFieldIssue[];
  counts: Record<FieldStatus, number>;
}

export type ReviewStatus = "pending" | "approved" | "edited" | "rejected";

export interface ReviewEntry {
  status: ReviewStatus;
  edited_value: string | number | boolean | null;
}

export interface DocumentPage {
  number: number;
  width: number;
  height: number;
}

export interface DocumentSummary {
  id: string;
  filename: string;
  page_count: number;
  pages: DocumentPage[];
}

export interface ExtractionResult {
  schema: string;
  provider: string;
  model: string | null;
  data: unknown;
  report: VerificationReport;
  review: Record<string, ReviewEntry>;
}

export type ReviewAction = "approve" | "edit" | "reject" | "reset";

export const SCHEMA_NAMES = ["invoice", "receipt", "contract"] as const;
export type SchemaName = (typeof SCHEMA_NAMES)[number];
