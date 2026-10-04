import type {
  DocumentSummary,
  ExtractionResult,
  ReviewAction,
  ReviewEntry,
  SessionList,
  SessionSummary,
} from "./types";
import { nextReview, validatedOverlay } from "./review";
import { validateDocument, validateExtraction, validateSessions } from "./validate";

/** Everything the UI needs from a backend - implemented once against the
 * live FastAPI server, and once against bundled fixture JSON for the
 * static Pages demo, so the same view code drives both. */
export interface DataSource {
  readonly kind: "live" | "demo";
  readonly reviewPersistence?: "browser" | "session";
  /** Only present in demo mode: the fixed set of sample documents to
   * choose from, since there's no upload endpoint to talk to. */
  listSamples?(signal?: AbortSignal): Promise<{ id: string; label: string }[]>;
  loadSample?(
    id: string,
    signal?: AbortSignal,
  ): Promise<{ document: DocumentSummary; extraction: ExtractionResult }>;
  listSchemas(): Promise<string[]>;
  listSessions?(signal?: AbortSignal): Promise<SessionList>;
  openSession?(
    id: string,
    signal?: AbortSignal,
  ): Promise<{ document: DocumentSummary; extraction: ExtractionResult | null }>;
  deleteSession?(id: string): Promise<void>;
  uploadDocument(file: File, signal?: AbortSignal): Promise<DocumentSummary>;
  pageImageUrl(documentId: string, pageNumber: number): string;
  extract(
    documentId: string,
    schemaName: string,
    provider: string,
    fixtureFile: File | null,
    signal?: AbortSignal,
  ): Promise<ExtractionResult>;
  review(documentId: string, path: string, action: ReviewAction, value?: unknown): Promise<ReviewEntry>;
}

async function asJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(
      (typeof body?.detail === "string" ? body.detail : response.statusText) ||
        `Request failed (${response.status}).`,
    );
  }
  return (await response.json()) as T;
}

/** Talks to `fieldproof serve`'s FastAPI app at relative `/api/...` paths -
 * works whether the built UI is served by FastAPI itself, or by
 * `vite dev` proxying `/api` to a locally running server (see
 * vite.config.ts / README "Development" section). */
export class ApiDataSource implements DataSource {
  readonly kind = "live" as const;

  async listSessions(signal?: AbortSignal): Promise<SessionList> {
    return validateSessions(await asJson<unknown>(await fetch("/api/documents", { signal: signal ?? null })));
  }

  async openSession(
    id: string,
    signal?: AbortSignal,
  ): Promise<{ document: DocumentSummary; extraction: ExtractionResult | null }> {
    const raw = await asJson<SessionSummary>(
      await fetch(`/api/documents/${encodeURIComponent(id)}`, { signal: signal ?? null }),
    );
    const document = validateDocument(raw);
    const extraction = raw.has_extraction
      ? validateExtraction(
          await asJson<unknown>(
            await fetch(`/api/documents/${encodeURIComponent(id)}/report`, { signal: signal ?? null }),
          ),
          document,
        )
      : null;
    return { document, extraction };
  }

  async deleteSession(id: string): Promise<void> {
    const response = await fetch(`/api/documents/${encodeURIComponent(id)}`, { method: "DELETE" });
    if (!response.ok) await asJson<unknown>(response);
  }

  async listSchemas(): Promise<string[]> {
    const data = await asJson<{ schemas: string[] }>(await fetch("/api/schemas"));
    return data.schemas;
  }

  async uploadDocument(file: File, signal?: AbortSignal): Promise<DocumentSummary> {
    if (file.size > 25 * 1024 * 1024) throw new Error("PDF exceeds the 25 MiB upload limit.");
    const form = new FormData();
    form.append("file", file);
    return asJson<DocumentSummary>(
      await fetch("/api/documents", { method: "POST", body: form, signal: signal ?? null }),
    );
  }

  pageImageUrl(documentId: string, pageNumber: number): string {
    return `/api/documents/${encodeURIComponent(documentId)}/pages/${pageNumber}.png`;
  }

  async extract(
    documentId: string,
    schemaName: string,
    provider: string,
    fixtureFile: File | null,
    signal?: AbortSignal,
  ): Promise<ExtractionResult> {
    if (fixtureFile && fixtureFile.size > 2 * 1024 * 1024)
      throw new Error("Fixture JSON exceeds the 2 MiB limit.");
    const form = new FormData();
    form.append("schema", schemaName);
    form.append("provider", provider);
    if (fixtureFile) form.append("fixture", fixtureFile);
    return asJson<ExtractionResult>(
      await fetch(`/api/documents/${encodeURIComponent(documentId)}/extract`, {
        method: "POST",
        body: form,
        signal: signal ?? null,
      }),
    );
  }

  async review(
    documentId: string,
    path: string,
    action: ReviewAction,
    value?: unknown,
  ): Promise<ReviewEntry> {
    return asJson<ReviewEntry>(
      await fetch(`/api/documents/${encodeURIComponent(documentId)}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path, action, value: value ?? null }),
      }),
    );
  }
}

interface DemoDataFile {
  document: DocumentSummary;
  extraction: ExtractionResult;
}

/** No backend: reads the fixture JSON + page PNGs that
 * `scripts/build_demo_data.py` writes into web/public/demo-data/ at build
 * time. Review decisions persist per-browser in localStorage (there's
 * nowhere else to put them); export builds the file client-side. */
export class DemoDataSource implements DataSource {
  readonly kind = "demo" as const;
  private cache = new Map<string, DemoDataFile>();
  private overlays = new Map<string, Record<string, ReviewEntry>>();
  reviewPersistence: "browser" | "session" = "browser";

  private storageKey(documentId: string): string {
    return `fieldproof-demo-review:${encodeURIComponent(documentId)}`;
  }

  private loadReviewOverlay(documentId: string, data: DemoDataFile): Record<string, ReviewEntry> {
    const cached = this.overlays.get(documentId);
    if (cached) return cached;
    let overlay: Record<string, ReviewEntry> = {};
    let raw: string | null = null;
    try {
      raw = localStorage.getItem(this.storageKey(documentId));
    } catch {
      this.reviewPersistence = "session";
    }
    if (raw) {
      try {
        overlay = validatedOverlay(JSON.parse(raw), data.extraction.report.fields);
      } catch {
        /* Damaged stored JSON is discarded; page-session decisions remain usable. */
      }
    }
    this.overlays.set(documentId, overlay);
    return overlay;
  }

  private saveReviewOverlay(documentId: string, overlay: Record<string, ReviewEntry>): void {
    try {
      localStorage.setItem(this.storageKey(documentId), JSON.stringify(overlay));
    } catch {
      this.reviewPersistence = "session";
    }
  }

  async listSamples(signal?: AbortSignal): Promise<{ id: string; label: string }[]> {
    const res = await fetch(`${import.meta.env.BASE_URL}demo-data/index.json`, { signal: signal ?? null });
    const data = await asJson<unknown>(res);
    const ids = new Set<string>();
    if (!Array.isArray(data) || data.length === 0) throw new Error("Invalid sample document index.");
    for (const sample of data) {
      if (
        !sample ||
        typeof sample !== "object" ||
        typeof sample.id !== "string" ||
        !/^[a-z0-9_-]+$/.test(sample.id) ||
        ids.has(sample.id) ||
        typeof sample.label !== "string" ||
        !sample.label.trim()
      ) {
        throw new Error("Invalid sample document index.");
      }
      ids.add(sample.id);
    }
    return data;
  }

  private async fetchSample(id: string, signal?: AbortSignal): Promise<DemoDataFile> {
    const cached = this.cache.get(id);
    if (cached) return cached;
    const res = await fetch(`${import.meta.env.BASE_URL}demo-data/${encodeURIComponent(id)}/data.json`, {
      signal: signal ?? null,
    });
    const raw = await asJson<DemoDataFile>(res);
    const document = validateDocument(raw?.document);
    const extraction = validateExtraction(raw?.extraction, document);
    const data = { document, extraction };
    this.cache.set(id, data);
    return data;
  }

  async loadSample(
    id: string,
    signal?: AbortSignal,
  ): Promise<{ document: DocumentSummary; extraction: ExtractionResult }> {
    const data = await this.fetchSample(id, signal);
    const overlay = this.loadReviewOverlay(id, data);
    return {
      document: data.document,
      extraction: { ...data.extraction, review: { ...data.extraction.review, ...overlay } },
    };
  }

  async listSchemas(): Promise<string[]> {
    return ["invoice", "receipt", "contract"];
  }

  async uploadDocument(): Promise<DocumentSummary> {
    throw new Error(
      "Uploading isn't available in the static demo - see the README to run fieldproof locally.",
    );
  }

  pageImageUrl(documentId: string, pageNumber: number): string {
    return `${import.meta.env.BASE_URL}demo-data/${encodeURIComponent(documentId)}/page-${pageNumber}.png`;
  }

  async extract(): Promise<ExtractionResult> {
    throw new Error("Re-extracting isn't available in the static demo.");
  }

  async review(
    documentId: string,
    path: string,
    action: ReviewAction,
    value?: unknown,
  ): Promise<ReviewEntry> {
    const data = await this.fetchSample(documentId);
    const field = data.extraction.report.fields.find((field) => field.path === path);
    if (!field) throw new Error("Unknown field.");
    const overlay = this.loadReviewOverlay(documentId, data);
    const entry = nextReview(field.value, overlay[path], action, value);
    overlay[path] = entry;
    this.saveReviewOverlay(documentId, overlay);
    return entry;
  }
}

export function createDataSource(): DataSource {
  return import.meta.env.MODE === "demo" ? new DemoDataSource() : new ApiDataSource();
}
