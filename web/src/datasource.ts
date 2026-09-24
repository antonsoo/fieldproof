import type {
  DocumentSummary,
  ExtractionResult,
  ReviewAction,
  ReviewEntry,
} from "./types";

/** Everything the UI needs from a backend - implemented once against the
 * live FastAPI server, and once against bundled fixture JSON for the
 * static Pages demo, so the same view code drives both. */
export interface DataSource {
  readonly kind: "live" | "demo";
  /** Only present in demo mode: the fixed set of sample documents to
   * choose from, since there's no upload endpoint to talk to. */
  listSamples?(): Promise<{ id: string; label: string }[]>;
  loadSample?(id: string): Promise<{ document: DocumentSummary; extraction: ExtractionResult }>;
  listSchemas(): Promise<string[]>;
  uploadDocument(file: File): Promise<DocumentSummary>;
  pageImageUrl(documentId: string, pageNumber: number): string;
  extract(
    documentId: string,
    schemaName: string,
    provider: string,
    fixtureFile: File | null,
  ): Promise<ExtractionResult>;
  review(documentId: string, path: string, action: ReviewAction, value?: unknown): Promise<ReviewEntry>;
  exportUrl(documentId: string, format: "json" | "csv"): string;
}

async function asJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(typeof body.detail === "string" ? body.detail : response.statusText);
  }
  return (await response.json()) as T;
}

/** Talks to `fieldproof serve`'s FastAPI app at relative `/api/...` paths -
 * works whether the built UI is served by FastAPI itself, or by
 * `vite dev` proxying `/api` to a locally running server (see
 * vite.config.ts / README "Development" section). */
export class ApiDataSource implements DataSource {
  readonly kind = "live" as const;

  async listSchemas(): Promise<string[]> {
    const data = await asJson<{ schemas: string[] }>(await fetch("/api/schemas"));
    return data.schemas;
  }

  async uploadDocument(file: File): Promise<DocumentSummary> {
    const form = new FormData();
    form.append("file", file);
    return asJson<DocumentSummary>(await fetch("/api/documents", { method: "POST", body: form }));
  }

  pageImageUrl(documentId: string, pageNumber: number): string {
    return `/api/documents/${documentId}/pages/${pageNumber}.png`;
  }

  async extract(
    documentId: string,
    schemaName: string,
    provider: string,
    fixtureFile: File | null,
  ): Promise<ExtractionResult> {
    const form = new FormData();
    form.append("schema", schemaName);
    form.append("provider", provider);
    if (fixtureFile) form.append("fixture", fixtureFile);
    return asJson<ExtractionResult>(
      await fetch(`/api/documents/${documentId}/extract`, { method: "POST", body: form }),
    );
  }

  async review(
    documentId: string,
    path: string,
    action: ReviewAction,
    value?: unknown,
  ): Promise<ReviewEntry> {
    return asJson<ReviewEntry>(
      await fetch(`/api/documents/${documentId}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path, action, value: value ?? null }),
      }),
    );
  }

  exportUrl(documentId: string, format: "json" | "csv"): string {
    return `/api/documents/${documentId}/export.${format}`;
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

  private storageKey(documentId: string): string {
    return `fieldproof-demo-review:${documentId}`;
  }

  private loadReviewOverlay(documentId: string): Record<string, ReviewEntry> {
    try {
      const raw = localStorage.getItem(this.storageKey(documentId));
      return raw ? (JSON.parse(raw) as Record<string, ReviewEntry>) : {};
    } catch {
      return {};
    }
  }

  private saveReviewOverlay(documentId: string, overlay: Record<string, ReviewEntry>): void {
    try {
      localStorage.setItem(this.storageKey(documentId), JSON.stringify(overlay));
    } catch {
      // Private browsing / storage disabled - review still works for this
      // page view, it just won't survive a reload. Not worth surfacing.
    }
  }

  async listSamples(): Promise<{ id: string; label: string }[]> {
    const res = await fetch(`${import.meta.env.BASE_URL}demo-data/index.json`);
    return asJson(res);
  }

  private async fetchSample(id: string): Promise<DemoDataFile> {
    const cached = this.cache.get(id);
    if (cached) return cached;
    const res = await fetch(`${import.meta.env.BASE_URL}demo-data/${id}/data.json`);
    const data = await asJson<DemoDataFile>(res);
    this.cache.set(id, data);
    return data;
  }

  async loadSample(id: string): Promise<{ document: DocumentSummary; extraction: ExtractionResult }> {
    const data = await this.fetchSample(id);
    const overlay = this.loadReviewOverlay(id);
    return {
      document: data.document,
      extraction: { ...data.extraction, review: { ...data.extraction.review, ...overlay } },
    };
  }

  async listSchemas(): Promise<string[]> {
    return ["invoice", "receipt", "contract"];
  }

  async uploadDocument(): Promise<DocumentSummary> {
    throw new Error("Uploading isn't available in the static demo - see the README to run fieldproof locally.");
  }

  pageImageUrl(documentId: string, pageNumber: number): string {
    return `${import.meta.env.BASE_URL}demo-data/${documentId}/page-${pageNumber}.png`;
  }

  async extract(): Promise<ExtractionResult> {
    throw new Error("Re-extracting isn't available in the static demo.");
  }

  async review(documentId: string, path: string, action: ReviewAction, value?: unknown): Promise<ReviewEntry> {
    const overlay = this.loadReviewOverlay(documentId);
    const entry: ReviewEntry = {
      status: action === "approve" ? "approved" : action === "edit" ? "edited" : action === "reject" ? "rejected" : "pending",
      edited_value: action === "edit" ? ((value as string | number | boolean | null) ?? null) : null,
    };
    overlay[path] = entry;
    this.saveReviewOverlay(documentId, overlay);
    return entry;
  }

  exportUrl(): string {
    // Handled specially by the caller (buildExportBlob) since there's no
    // server route to point at - see view.ts.
    return "";
  }
}

export function createDataSource(): DataSource {
  return import.meta.env.MODE === "demo" ? new DemoDataSource() : new ApiDataSource();
}
