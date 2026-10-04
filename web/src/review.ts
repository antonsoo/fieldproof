import type { FieldVerification, ReviewAction, ReviewEntry } from "./types";

export type FieldValue = FieldVerification["value"];

export function validEditValue(original: FieldValue, value: unknown): value is FieldValue {
  return (
    typeof value === typeof original &&
    (typeof value === "number"
      ? Number.isFinite(value)
      : typeof value === "string" || typeof value === "boolean")
  );
}

/** Text controls must not turn machine numbers or booleans into strings. */
export function parseEditValue(original: FieldValue, input: string): FieldValue {
  if (typeof original === "string") return input;
  const text = input.trim();
  if (typeof original === "boolean") {
    if (text === "true") return true;
    if (text === "false") return false;
    throw new Error("Choose true or false.");
  }
  if (!/^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(text) || !Number.isFinite(Number(text))) {
    throw new Error("Enter a finite number, without currency signs or separators.");
  }
  return Number(text);
}

export function reviewValue(field: FieldVerification, review?: ReviewEntry): FieldValue {
  return review && review.status !== "pending" && validEditValue(field.value, review.edited_value)
    ? review.edited_value
    : field.value;
}

export function nextReview(
  original: FieldValue,
  current: ReviewEntry | undefined,
  action: ReviewAction,
  value?: unknown,
): ReviewEntry {
  if (action === "reset") return { status: "pending", edited_value: null };
  if (action === "edit") {
    if (!validEditValue(original, value))
      throw new Error(`Correction must be a finite ${typeof original} value.`);
    return { status: "edited", edited_value: value };
  }
  return {
    status: action === "approve" ? "approved" : "rejected",
    edited_value: current && validEditValue(original, current.edited_value) ? current.edited_value : null,
  };
}

/** A storage entry is an untrusted overlay, never a replacement extraction. */
export function validatedOverlay(raw: unknown, fields: FieldVerification[]): Record<string, ReviewEntry> {
  const result: Record<string, ReviewEntry> = Object.create(null);
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return result;
  for (const field of fields) {
    if (!Object.hasOwn(raw, field.path)) continue;
    const entry = (raw as Record<string, unknown>)[field.path];
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) continue;
    const { status, edited_value } = entry as Record<string, unknown>;
    if (typeof status !== "string" || !["pending", "approved", "edited", "rejected"].includes(status))
      continue;
    if (status === "pending" && edited_value !== null) continue;
    if (
      status === "edited"
        ? !validEditValue(field.value, edited_value)
        : edited_value !== null && !validEditValue(field.value, edited_value)
    )
      continue;
    result[field.path] = {
      status: status as ReviewEntry["status"],
      edited_value: edited_value as ReviewEntry["edited_value"],
    };
  }
  return result;
}
