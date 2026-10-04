import "./fonts/fonts.css";
import "./style.css";
import { createDataSource } from "./datasource";
import { computeExportRows, downloadBlob, rowsToCsv } from "./export";
import type { DocumentSummary, ExtractionResult, FieldStatus, FieldVerification } from "./types";
import { SCHEMA_NAMES } from "./types";
import { parseEditValue, reviewValue } from "./review";
import { validateDocument, validateExtraction } from "./validate";
import { SessionsDialog } from "./sessions";

/** Page images are rendered server- and build-side at 2x the PDF's point
 * size (see render_page_png's default `scale=2.0`); every rect in a
 * field's `rects` is in PDF points from the same top-left origin, so
 * multiplying by this constant maps a rect straight onto the image. */
const PAGE_IMAGE_SCALE = 2;

const ds = createDataSource();

interface AppState {
  document: DocumentSummary | null;
  extraction: ExtractionResult | null;
  currentPage: number;
  zoom: number;
  /** True until the reader manually zooms - while true, the page is
   * rescaled to fit the viewer pane's width on every render instead of
   * respecting `zoom` literally, so a wide page doesn't open scrolled
   * halfway across itself. */
  zoomIsAuto: boolean;
  selectedPath: string | null;
  statusFilter: FieldStatus | "all";
  searchQuery: string;
  editingPath: string | null;
  editingValue: string;
  editError: string | null;
  reviewFilter: "all" | "pending" | "reviewed";
  exportScope: "reviewed" | "all";
  mobilePane: "fields" | "document";
  filtersOpen: boolean;
  schemaName: (typeof SCHEMA_NAMES)[number];
  provider: "fixture" | "anthropic";
  fixtureFile: File | null;
  busy: boolean;
  samples: { id: string; label: string }[];
}

const state: AppState = {
  document: null,
  extraction: null,
  currentPage: 1,
  zoom: 1,
  zoomIsAuto: true,
  selectedPath: null,
  statusFilter: "all",
  searchQuery: "",
  editingPath: null,
  editingValue: "",
  editError: null,
  reviewFilter: "all",
  exportScope: "reviewed",
  mobilePane: "fields",
  filtersOpen: false,
  schemaName: "invoice",
  provider: "fixture",
  fixtureFile: null,
  busy: false,
  samples: [],
};

const app = document.getElementById("app")!;
let operation: AbortController | null = null;
let operationMessage = "";
let operationError = "";
let retryOperation: (() => void) | null = null;
const pendingReviews = new WeakMap<ExtractionResult, Set<string>>();
let renderedExtraction: ExtractionResult | null = null;
const sessionsDialog =
  ds.kind === "live"
    ? new SessionsDialog(ds, {
        current: () => state.document?.id,
        blocked: () =>
          state.busy ||
          !!state.editingPath ||
          !!(state.extraction && pendingReviews.get(state.extraction)?.size),
        open: (id) => void openSession(id),
        removed: (id) => {
          if (state.document?.id === id) resetToStart();
        },
      })
    : null;

function beginOperation(message: string, retry: () => void): AbortController {
  operation?.abort();
  operation = new AbortController();
  operationMessage = message;
  operationError = "";
  retryOperation = retry;
  state.busy = true;
  renderTopbar();
  renderOperationStatus();
  if (state.extraction) renderFieldListOnly();
  return operation;
}

function finishOperation(owner: AbortController, error = ""): boolean {
  if (operation !== owner || owner.signal.aborted) return false;
  operation = null;
  state.busy = false;
  operationError = error;
  renderTopbar();
  renderOperationStatus();
  if (state.extraction) renderFieldListOnly();
  return true;
}

function renderOperationStatus(): void {
  let region = document.getElementById("operation-status");
  if (!region) {
    region = document.createElement("div");
    region.id = "operation-status";
    region.className = "operation-status";
    app.insertBefore(region, app.querySelector(".workbench"));
  }
  region.hidden = !operation && !operationError;
  region.innerHTML = operation
    ? `<span role="status">${esc(operationMessage)}</span><button class="btn" id="cancel-operation" type="button">Cancel</button>`
    : `<span role="alert">${esc(operationError)}</span><button class="btn" id="retry-operation" type="button">Retry</button>`;
  region.querySelector("#cancel-operation")?.addEventListener("click", () => {
    operation?.abort();
    operation = null;
    state.busy = false;
    operationError = "";
    renderTopbar();
    renderOperationStatus();
    renderWorkbench();
    document
      .querySelector<HTMLButtonElement>(".sample-switch .is-active, #new-document, #choose-file")
      ?.focus();
    toast("Operation cancelled.");
  });
  region.querySelector("#retry-operation")?.addEventListener("click", () => retryOperation?.());
}

function resetView(): void {
  state.selectedPath = null;
  state.statusFilter = "all";
  state.reviewFilter = "all";
  state.searchQuery = "";
  state.editingPath = null;
  state.editingValue = "";
  state.editError = null;
  state.currentPage = 1;
  state.zoomIsAuto = true;
  state.mobilePane = "fields";
  state.filtersOpen = false;
}

/** Restore focus to the same control after replacing its view. */
function rememberFocus(): () => void {
  const active = document.activeElement as HTMLElement | null;
  if (!active || !app.contains(active)) return () => {};
  const id = active.id;
  const attributes = [...active.attributes].filter((attr) => attr.name.startsWith("data-"));
  const path = active.closest<HTMLElement>(".field-row")?.dataset.path;
  const cursor = active instanceof HTMLInputElement ? [active.selectionStart, active.selectionEnd] : null;
  return () => {
    const elements = [...app.querySelectorAll<HTMLElement>("button, input, select, [tabindex]")];
    let next = id
      ? document.getElementById(id)
      : elements.find(
          (el) =>
            el.tagName === active.tagName &&
            attributes.length > 0 &&
            attributes.every((attr) => el.getAttribute(attr.name) === attr.value),
        );
    if (!next && path)
      next =
        elements.find((el) => el.dataset.select === path) ??
        elements.find((el) => el.hasAttribute("data-select")) ??
        document.getElementById("review-filter");
    if (next instanceof HTMLButtonElement && next.disabled && path)
      next = elements.find((el) => el.dataset.select === path);
    if (!next) return;
    next.focus({ preventScroll: true });
    if (cursor && next instanceof HTMLInputElement && next.type !== "number") {
      try {
        next.setSelectionRange(cursor[0] ?? null, cursor[1] ?? null);
      } catch {
        /* e.g. a search input */
      }
    }
  };
}

function esc(value: unknown): string {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function statusLabel(status: FieldStatus): string {
  if (status === "needs_review") return "needs review";
  return status;
}

/** Field-name leaves (after stripping any "[n]" list index) treated as
 * currency amounts for display - quantities and counts are numbers, not
 * money, so they're deliberately not in this set. Presentation only: the
 * underlying value and JSON/CSV export both stay the raw machine number. */
const MONEY_FIELD_NAMES = new Set([
  "amount",
  "subtotal",
  "tax",
  "total",
  "unit_price",
  "total_contract_value",
]);

function isMoneyField(path: string): boolean {
  const last = path.split(".").pop() ?? "";
  return MONEY_FIELD_NAMES.has(last.replace(/\[\d+\]$/, ""));
}

function formatDisplayValue(path: string, value: unknown): string {
  if (isMoneyField(path) && typeof value === "number" && Number.isFinite(value)) {
    return value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  return String(value);
}

let toastTimer: number | undefined;
function toast(message: string): void {
  let el = document.getElementById("toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast";
    el.className = "toast";
    el.setAttribute("role", "status");
    el.setAttribute("aria-live", "polite");
    document.body.appendChild(el);
  }
  el.textContent = message;
  el.classList.add("is-visible");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => el?.classList.remove("is-visible"), 2600);
}

/* ---------------------------- theme toggle ---------------------------- */

function currentTheme(): "light" | "dark" {
  const attr = document.documentElement.getAttribute("data-theme");
  if (attr === "light" || attr === "dark") return attr;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function toggleTheme(): void {
  const next = currentTheme() === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  try {
    localStorage.setItem("fieldproof-theme", next);
  } catch {
    /* ignore */
  }
  renderTopbar();
}

/* ------------------------------- topbar -------------------------------- */

function renderTopbar(): void {
  const restoreFocus = rememberFocus();
  let bar = document.querySelector<HTMLElement>(".topbar");
  if (!bar) {
    bar = document.createElement("header");
    bar.className = "topbar";
    app.prepend(bar);
  }

  const counts = state.extraction?.report.counts;
  const countsHtml = counts
    ? `<span class="brand-tag" aria-hidden="true">${counts.verified}&nbsp;verified&ensp;${counts.needs_review}&nbsp;review&ensp;${counts.unsupported}&nbsp;unsupported</span>`
    : `<span class="brand-tag">${ds.kind === "demo" ? "static demo - fixture data" : "grounded document review"}</span>`;

  bar.innerHTML = `
    <div class="brand">
      <h1 class="brand-mark">fieldproof</h1>
      ${countsHtml}
    </div>
    ${sampleSwitchHtml()}
    <div class="topbar-controls">
      ${ds.kind === "live" ? '<button class="btn" id="sessions" type="button">Sessions</button>' : ""}
      ${ds.kind === "live" && state.document ? `<button class="btn" id="new-document" type="button" ${state.editingPath ? 'disabled title="Save or cancel the correction first"' : ""}>New document</button>` : ""}
      ${state.extraction ? exportControlsHtml() : ""}
      <button class="btn" id="theme-toggle" type="button" aria-label="Toggle dark mode">
        ${currentTheme() === "dark" ? "☀️ Light" : "☽ Dark"}
      </button>
    </div>
  `;

  bar.querySelector<HTMLButtonElement>("#theme-toggle")?.addEventListener("click", toggleTheme);
  bar.querySelector<HTMLButtonElement>("#export-json")?.addEventListener("click", () => exportAs("json"));
  bar.querySelector<HTMLButtonElement>("#export-csv")?.addEventListener("click", () => exportAs("csv"));
  bar.querySelector<HTMLButtonElement>("#new-document")?.addEventListener("click", resetToStart);
  bar.querySelector<HTMLButtonElement>("#sessions")?.addEventListener("click", () => sessionsDialog?.show());
  bar.querySelector<HTMLSelectElement>("#export-scope")?.addEventListener("change", (event) => {
    state.exportScope = (event.target as HTMLSelectElement).value as AppState["exportScope"];
    renderTopbar();
  });
  bar.querySelectorAll<HTMLButtonElement>("[data-switch-sample]").forEach((btn) => {
    btn.addEventListener("click", () => {
      // The hash is the single source of truth for which sample is open (deep links, back button).
      const id = btn.dataset.switchSample!;
      if (window.location.hash.slice(1) === id) void loadSample(id);
      else window.location.hash = id;
    });
  });
  restoreFocus();
}

/** Demo mode: one button per sample document, so switching doesn't need a reload. */
function sampleSwitchHtml(): string {
  if (ds.kind !== "demo" || state.samples.length === 0) return "";
  const active = state.document?.id;
  return `
    <nav class="sample-switch" aria-label="Sample documents">
      ${state.samples
        .map(
          (s) =>
            `<button class="sample-switch-btn ${s.id === active ? "is-active" : ""}" type="button" data-switch-sample="${esc(s.id)}" ${s.id === active ? 'aria-current="page"' : ""}>${esc(s.label)}</button>`,
        )
        .join("")}
    </nav>
  `;
}

function resetToStart(): void {
  operation?.abort();
  operation = null;
  operationError = "";
  state.busy = false;
  state.document = null;
  state.extraction = null;
  resetView();
  renderOperationStatus();
  state.fixtureFile = null;
  renderTopbar();
  renderWorkbench();
}

function exportControlsHtml(): string {
  const rows = computeExportRows(state.extraction!, state.exportScope);
  const saving = (pendingReviews.get(state.extraction!)?.size ?? 0) > 0;
  const disabled = state.busy || saving || rows.length === 0;
  return `
    <label class="export-scope">Export
      <select class="select" id="export-scope" aria-label="Export">
        <option value="reviewed" ${state.exportScope === "reviewed" ? "selected" : ""}>Reviewed only (${computeExportRows(state.extraction!, "reviewed").length})</option>
        <option value="all" ${state.exportScope === "all" ? "selected" : ""}>All except rejected (${computeExportRows(state.extraction!, "all").length})</option>
      </select>
    </label>
    <button class="btn" id="export-json" type="button" ${disabled ? "disabled" : ""}>Export JSON</button>
    <button class="btn" id="export-csv" type="button" ${disabled ? "disabled" : ""}>Export CSV</button>
  `;
}

function exportAs(format: "json" | "csv"): void {
  if (!state.document || !state.extraction || state.busy || pendingReviews.get(state.extraction)?.size)
    return;
  const rows = computeExportRows(state.extraction, state.exportScope);
  if (rows.length === 0) return;
  const base = state.document.filename.replace(/\.pdf$/i, "");
  // A download snapshots the decisions visible in this tab. A later server
  // response or a different tab cannot change the file after the click.
  if (format === "json") {
    downloadBlob(`${base}.fieldproof.json`, JSON.stringify(rows, null, 2), "application/json");
  } else {
    downloadBlob(`${base}.fieldproof.csv`, rowsToCsv(rows), "text/csv");
  }
  toast(`Exported ${rows.length} field${rows.length === 1 ? "" : "s"}`);
}

/* ------------------------------ start state ----------------------------- */

function renderStart(): void {
  const workbench = getWorkbench();
  if (ds.kind === "demo") {
    workbench.innerHTML = `
      <div class="start-state">
        <div class="proof-ticks" aria-hidden="true">
          <span class="proof-tick"><span class="proof-dot" style="background:var(--color-verified)"></span>verified</span>
          <span class="proof-tick"><span class="proof-dot" style="background:var(--color-review)"></span>needs review</span>
          <span class="proof-tick"><span class="proof-dot" style="background:var(--color-unsupported)"></span>unsupported</span>
        </div>
        <h1>Every field, traced to its source</h1>
        <p>
          Three synthetic sample documents, grounded and verified by fieldproof's real pipeline.
          The candidate extractions are hand-written fixtures with planted errors, to show what the verifier catches -
          a hallucinated PO number, a total that doesn't match its line items, and a misread date.
        </p>
        <div class="sample-grid">
          ${state.samples.length === 0 ? '<button class="btn btn-primary" id="load-samples" type="button">Load sample documents</button>' : ""}
          ${state.samples
            .map(
              (s) =>
                `<button class="btn btn-primary" type="button" data-sample="${esc(s.id)}">${esc(s.label)}</button>`,
            )
            .join("")}
        </div>
      </div>
    `;
    workbench.querySelectorAll<HTMLButtonElement>("[data-sample]").forEach((btn) => {
      btn.addEventListener("click", () => loadSample(btn.dataset.sample!));
    });
    workbench.querySelector("#load-samples")?.addEventListener("click", () => void bootDemo());
    return;
  }

  workbench.innerHTML = `
    <div class="start-state">
      <h1>Upload a document</h1>
      <p>PDF with a text layer, up to 25 MiB and 64 pages. Extraction runs against the fixture provider or Claude, then every field is grounded and verified against the page.</p>
      <p>Saved documents can be reopened from Sessions while this server is running.</p>
      <button class="dropzone" id="choose-file" type="button">Drop a PDF here, or choose a file</button>
      <input type="file" id="file-input" accept="application/pdf" class="visually-hidden" aria-label="PDF document" tabindex="-1" />
    </div>
  `;
  const input = workbench.querySelector<HTMLInputElement>("#file-input")!;
  const zone = workbench.querySelector<HTMLElement>("#choose-file")!;
  zone.addEventListener("click", () => input.click());
  input.addEventListener("change", () => {
    const file = input.files?.[0];
    input.value = "";
    if (file) void uploadFile(file);
  });
  zone.addEventListener("dragover", (e) => {
    e.preventDefault();
    zone.classList.add("dragover");
  });
  zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("dragover");
    const file = e.dataTransfer?.files?.[0];
    if (file) void uploadFile(file);
  });
}

async function loadSample(id: string): Promise<void> {
  if (!ds.loadSample) return;
  const owner = beginOperation(`Loading ${id}…`, () => void loadSample(id));
  try {
    const loaded = await ds.loadSample(id, owner.signal);
    if (operation !== owner || owner.signal.aborted) return;
    state.document = loaded.document;
    state.extraction = loaded.extraction;
    resetView();
    const flagged = filteredFields().find((f) => f.status !== "verified");
    state.selectedPath = flagged?.path ?? filteredFields()[0]?.path ?? null;
    if (flagged?.page) state.currentPage = flagged.page;
    finishOperation(owner);
    renderWorkbench();
  } catch (err) {
    finishOperation(
      owner,
      err instanceof Error ? `Could not load ${id}: ${err.message}` : `Could not load ${id}`,
    );
  }
}

function requestedSample(): string | undefined {
  let hash = "";
  try {
    hash = decodeURIComponent(window.location.hash.slice(1));
  } catch {
    /* malformed deep link */
  }
  return state.samples.find((sample) => sample.id === hash)?.id ?? state.samples[0]?.id;
}

/** Demo mode opens a sample straight away (the one named in the URL hash, else the first), rather
 * than a landing page with nothing to inspect. */
async function bootDemo(): Promise<void> {
  const owner = beginOperation("Loading sample documents…", () => void bootDemo());
  try {
    const samples = (await ds.listSamples?.(owner.signal)) ?? [];
    if (operation !== owner || owner.signal.aborted) return;
    if (samples.length === 0) throw new Error("No sample documents available.");
    state.samples = samples;
    finishOperation(owner);
    const target = requestedSample();
    if (target) await loadSample(target);
  } catch (err) {
    finishOperation(owner, err instanceof Error ? err.message : "Could not load samples.");
  }
}

window.addEventListener("hashchange", () => {
  if (ds.kind !== "demo") return;
  const id = requestedSample();
  if (id) void loadSample(id);
});

async function uploadFile(file: File): Promise<void> {
  const owner = beginOperation("Loading PDF…", () => void uploadFile(file));
  try {
    const loaded = await ds.uploadDocument(file, owner.signal);
    if (operation !== owner || owner.signal.aborted) return;
    state.document = validateDocument(loaded);
    state.extraction = null;
    state.fixtureFile = null;
    resetView();
    finishOperation(owner);
    renderWorkbench();
  } catch (err) {
    finishOperation(owner, err instanceof Error ? err.message : "Upload failed");
  }
}

async function openSession(id: string): Promise<void> {
  if (!ds.openSession) return;
  const owner = beginOperation("Opening document session…", () => void openSession(id));
  try {
    const loaded = await ds.openSession(id, owner.signal);
    if (operation !== owner || owner.signal.aborted) return;
    state.document = loaded.document;
    state.extraction = loaded.extraction;
    state.fixtureFile = null;
    resetView();
    const fields = loaded.extraction?.report.fields ?? [];
    const selected = fields.find((field) => field.status !== "verified") ?? fields[0];
    state.selectedPath = selected?.path ?? null;
    state.currentPage = selected?.page ?? 1;
    finishOperation(owner);
    renderWorkbench();
  } catch (error) {
    finishOperation(owner, error instanceof Error ? error.message : "Could not open session.");
  }
}

/* --------------------------- configure & extract ------------------------- */

function renderConfigure(): void {
  const workbench = getWorkbench();
  workbench.innerHTML = `
    <div class="start-state">
      <h1>${esc(state.document!.filename)}</h1>
      <p>${state.document!.page_count} page${state.document!.page_count === 1 ? "" : "s"} loaded. Choose a schema and a provider to extract.</p>
      <div style="display:flex; flex-direction:column; gap:12px; text-align:left; max-width:360px; margin:0 auto;">
        <label>
          Schema
          <select class="select" id="schema-select" style="width:100%">
            ${SCHEMA_NAMES.map((s) => `<option value="${s}" ${s === state.schemaName ? "selected" : ""}>${s}</option>`).join("")}
          </select>
        </label>
        <label>
          Provider
          <select class="select" id="provider-select" style="width:100%">
            <option value="fixture" ${state.provider === "fixture" ? "selected" : ""}>fixture (replay stored JSON)</option>
            <option value="anthropic" ${state.provider === "anthropic" ? "selected" : ""}>anthropic (needs ANTHROPIC_API_KEY on the server)</option>
          </select>
        </label>
        <label id="fixture-label" ${state.provider === "fixture" ? "" : "hidden"}>
          Fixture JSON
          <input type="file" class="text-input" id="fixture-input" accept="application/json" style="width:100%" />
        </label>
        <button class="btn btn-primary" id="run-extract" type="button" ${state.busy ? "disabled" : ""}>
          ${state.busy ? "Extracting…" : "Run extraction"}
        </button>
      </div>
    </div>
  `;
  const schemaSelect = workbench.querySelector<HTMLSelectElement>("#schema-select")!;
  const providerSelect = workbench.querySelector<HTMLSelectElement>("#provider-select")!;
  const fixtureLabel = workbench.querySelector<HTMLElement>("#fixture-label")!;
  const fixtureInput = workbench.querySelector<HTMLInputElement>("#fixture-input")!;

  schemaSelect.addEventListener("change", () => {
    state.schemaName = schemaSelect.value as AppState["schemaName"];
  });
  providerSelect.addEventListener("change", () => {
    state.provider = providerSelect.value as AppState["provider"];
    fixtureLabel.hidden = state.provider !== "fixture";
  });
  fixtureInput.addEventListener("change", () => {
    state.fixtureFile = fixtureInput.files?.[0] ?? null;
  });
  workbench.querySelector<HTMLButtonElement>("#run-extract")!.addEventListener("click", runExtract);
}

async function runExtract(): Promise<void> {
  if (!state.document || state.busy) return;
  if (state.provider === "fixture" && !state.fixtureFile) {
    toast("Choose a fixture JSON file first");
    return;
  }
  const document = state.document;
  const owner = beginOperation(
    state.provider === "anthropic"
      ? "Extracting with Claude; verification runs locally…"
      : "Extracting and verifying locally…",
    () => void runExtract(),
  );
  const button = getWorkbench().querySelector<HTMLButtonElement>("#run-extract");
  if (button) button.disabled = true;
  try {
    const extraction = await ds.extract(
      document.id,
      state.schemaName,
      state.provider,
      state.fixtureFile,
      owner.signal,
    );
    if (operation !== owner || owner.signal.aborted || state.document !== document) return;
    state.extraction = validateExtraction(extraction, document);
    resetView();
    state.selectedPath = filteredFields()[0]?.path ?? null;
    finishOperation(owner);
    renderWorkbench();
  } catch (err) {
    if (finishOperation(owner, err instanceof Error ? err.message : "Extraction failed") && button)
      button.disabled = false;
  }
}

/* -------------------------------- workbench ------------------------------ */

function getWorkbench(): HTMLElement {
  let el = document.querySelector<HTMLElement>(".workbench");
  if (!el) {
    el = document.createElement("main");
    el.className = "workbench";
    app.appendChild(el);
  }
  return el;
}

//  Lower sorts first - in the combined "All" view, fields worth a second
//  look surface above fields that already checked out, so a reviewer never
//  has to scroll to find what needs their attention.
const STATUS_SORT_PRIORITY: Record<FieldStatus, number> = {
  unsupported: 0,
  needs_review: 1,
  verified: 2,
};

function filteredFields(): FieldVerification[] {
  const fields = state.extraction?.report.fields ?? [];
  const q = state.searchQuery.trim().toLowerCase();
  const matched = fields.filter((f) => {
    if (state.statusFilter !== "all" && f.status !== state.statusFilter) return false;
    const review = state.extraction?.review[f.path];
    const pending = !review || review.status === "pending";
    if (state.reviewFilter === "pending" && !pending) return false;
    if (state.reviewFilter === "reviewed" && pending) return false;
    if (!q) return true;
    return (
      f.path.toLowerCase().includes(q) ||
      String(f.value).toLowerCase().includes(q) ||
      String(reviewValue(f, review)).toLowerCase().includes(q)
    );
  });
  if (state.statusFilter !== "all") return matched; // already one status - sorting would be a no-op
  return [...matched].sort((a, b) => STATUS_SORT_PRIORITY[a.status] - STATUS_SORT_PRIORITY[b.status]);
}

function renderWorkbench(): void {
  if (!state.document) {
    renderedExtraction = null;
    void renderStart();
    return;
  }
  if (!state.extraction) {
    renderedExtraction = null;
    renderConfigure();
    return;
  }

  const workbench = getWorkbench();
  const restoreFocus = rememberFocus();
  const listScroll =
    renderedExtraction === state.extraction ? (document.getElementById("field-list")?.scrollTop ?? 0) : 0;
  renderedExtraction = state.extraction;
  workbench.dataset.mobilePane = state.mobilePane;
  workbench.dataset.filters = state.filtersOpen ? "open" : "closed";
  workbench.innerHTML = `
    <nav class="mobile-views" aria-label="Review views">
      <button class="btn" type="button" data-mobile-view="fields" aria-pressed="${state.mobilePane === "fields"}">Fields</button>
      <button class="btn" type="button" data-mobile-view="document" aria-pressed="${state.mobilePane === "document"}">Document</button>
      <span>${state.mobilePane === "document" && state.selectedPath ? `Evidence: ${esc(state.selectedPath)}` : "Review and inspect"}</span>
    </nav>
    <section class="viewer-pane" aria-label="Document page">
      <div class="viewer-toolbar">
        <button class="btn" id="prev-page" type="button" aria-label="Previous page" ${state.currentPage <= 1 ? "disabled" : ""}>←</button>
        <span>Page ${state.currentPage} / ${state.document.page_count}</span>
        <button class="btn" id="next-page" type="button" aria-label="Next page" ${state.currentPage >= state.document.page_count ? "disabled" : ""}>→</button>
        <span style="flex:1"></span>
        <button class="btn" id="zoom-out" type="button" aria-label="Zoom out">−</button>
        <span id="zoom-label">${Math.round(state.zoom * 100)}%</span>
        <button class="btn" id="zoom-in" type="button" aria-label="Zoom in">+</button>
        <button class="btn" id="zoom-fit" type="button" aria-pressed="${state.zoomIsAuto}">Fit</button>
      </div>
      <div class="viewer-scroll" id="viewer-scroll" tabindex="0" role="group" aria-label="Document page">
        ${renderPageFrame()}
      </div>
    </section>
    <section class="field-pane" aria-label="Extracted fields">
      ${renderFieldPaneHeader()}
      <ul class="field-list" id="field-list" tabindex="-1" aria-label="Fields">
        ${renderFieldRows()}
      </ul>
    </section>
  `;

  attachWorkbenchEvents();
  if (state.zoomIsAuto) refreshAutoZoom();
  const list = document.getElementById("field-list");
  if (list) list.scrollTop = listScroll;
  restoreFocus();
}

/** Rescales the page to fit the viewer pane's width, so a page wider than
 * the pane opens fully visible instead of overflowing off both edges with
 * the scroll position stuck in the middle. `renderPageFrame` bakes `zoom`
 * directly into the frame/image/rect pixel sizes (not a CSS transform, so
 * flex centering measures the real visual size) - this measures the pane
 * after the first layout pass, and only re-renders the viewer if the fit
 * width actually changed. Runs after every render and on window resize. */
function refreshAutoZoom(): void {
  const scroll = document.getElementById("viewer-scroll");
  const page = state.document?.pages.find((p) => p.number === state.currentPage);
  if (!scroll || !page) return;
  const naturalWidth = page.width * PAGE_IMAGE_SCALE;
  if (scroll.clientWidth <= 48) return;
  const available = scroll.clientWidth - 48; // viewer-scroll padding (24px each side)
  const fit = Math.min(1, Math.max(0.01, available / naturalWidth));
  const nextZoom = Math.floor(fit * 1000) / 1000;
  if (nextZoom === state.zoom) return;
  state.zoom = nextZoom;
  scroll.innerHTML = renderPageFrame();
  // The oversized first pass can leave the container auto-scrolled toward
  // its (now nonexistent) overflow - snap back now that content fits.
  scroll.scrollLeft = 0;
  scroll.scrollTop = 0;
  attachViewerRectEvents();
  const zoomLabel = document.getElementById("zoom-label");
  if (zoomLabel) zoomLabel.textContent = `${Math.round(state.zoom * 100)}%`;
}

window.addEventListener("resize", () => {
  if (state.zoomIsAuto) refreshAutoZoom();
});

function renderPageFrame(): string {
  const page = state.document!.pages.find((p) => p.number === state.currentPage)!;
  const pxPerPoint = PAGE_IMAGE_SCALE * state.zoom;
  const w = Math.round(page.width * pxPerPoint);
  const h = Math.round(page.height * pxPerPoint);
  const rects = (state.extraction?.report.fields ?? [])
    .filter((f) => f.page === state.currentPage)
    .flatMap((f) => f.rects.map((r) => ({ rect: r, field: f })));

  const rectsHtml = rects
    .map(({ rect, field }) => {
      const left = rect.x0 * pxPerPoint;
      const top = rect.top * pxPerPoint;
      const width = (rect.x1 - rect.x0) * pxPerPoint;
      const height = (rect.bottom - rect.top) * pxPerPoint;
      const active = field.path === state.selectedPath ? "is-active" : "";
      return `<div class="highlight-rect ${active}" data-status="${field.status}" data-path="${esc(field.path)}"
        style="left:${left}px; top:${top}px; width:${width}px; height:${height}px"
        title="${esc(field.path)}"></div>`;
    })
    .join("");

  return `
    <div class="page-frame" id="page-frame" style="width:${w}px; height:${h}px;">
      <img src="${ds.pageImageUrl(state.document!.id, state.currentPage)}" width="${w}" height="${h}" alt="Page ${state.currentPage} of ${esc(state.document!.filename)}" />
      ${rectsHtml}
    </div>
  `;
}

function renderFieldPaneHeader(): string {
  const counts = state.extraction!.report.counts;
  const fields = state.extraction!.report.fields;
  const remaining = fields.filter(
    (f) => !state.extraction!.review[f.path] || state.extraction!.review[f.path]!.status === "pending",
  ).length;
  const chip = (status: FieldStatus | "all", label: string, count: number): string => `
    <button class="count-chip ${state.statusFilter === status ? "is-active" : ""}" data-status-filter="${status}"
      data-status="${status === "all" ? "" : status}" type="button" aria-pressed="${state.statusFilter === status}">
      ${esc(label)} ${count}
    </button>
  `;
  return `
    <div class="field-pane-header">
      <div class="review-summary"><p class="review-progress" id="review-progress" role="status">${fields.length - remaining} of ${fields.length} reviewed · ${remaining} pending</p>
        <button class="btn mobile-filter-toggle" id="toggle-filters" type="button" aria-expanded="${state.filtersOpen}" aria-controls="review-filters">Filters</button>
      </div>
      <div class="review-filters" id="review-filters">
      <label class="review-filter">Show
        <select class="select" id="review-filter" aria-label="Show">
          <option value="all" ${state.reviewFilter === "all" ? "selected" : ""}>All decisions</option>
          <option value="pending" ${state.reviewFilter === "pending" ? "selected" : ""}>Pending review</option>
          <option value="reviewed" ${state.reviewFilter === "reviewed" ? "selected" : ""}>Reviewed</option>
        </select>
      </label>
      <div class="counts-strip">
        ${chip("all", "All", state.extraction!.report.fields.length)}
        ${chip("verified", "Verified", counts.verified)}
        ${chip("needs_review", "Needs review", counts.needs_review)}
        ${chip("unsupported", "Unsupported", counts.unsupported)}
      </div>
      </div>
      <div class="filter-row">
        <input class="text-input" id="search-input" type="search" aria-label="Search fields" placeholder="Search fields…" value="${esc(state.searchQuery)}" />
      </div>
      <details class="review-notes"><summary>Evidence and keyboard help</summary>
        <p class="review-help">Select a field; use ↑/↓ to navigate, A to approve, R to reject. Verification and evidence describe the original extraction; corrections are human decisions.</p>
      </details>
      ${
        ds.kind === "demo"
          ? `<p class="demo-note">Synthetic fixture. ${ds.reviewPersistence === "session" ? "Tab only: export before reloading." : "Decisions saved in this browser."}</p>`
          : ""
      }
    </div>
  `;
}

function renderFieldRows(): string {
  const fields = filteredFields();
  if (fields.length === 0) {
    return `<li class="empty-filtered">No fields match this filter.</li>`;
  }
  const focusPath = fields.some((f) => f.path === state.selectedPath) ? state.selectedPath : fields[0]!.path;
  return fields.map((f) => renderFieldRow(f, f.path === focusPath)).join("");
}

function renderFieldRow(f: FieldVerification, navigable: boolean): string {
  const review = state.extraction!.review[f.path] ?? { status: "pending", edited_value: null };
  const selected = f.path === state.selectedPath;
  const displayValue = reviewValue(f, review);
  const corrected = review.edited_value !== null && review.status !== "pending";
  const isEditing = state.editingPath === f.path;
  const saving = pendingReviews.get(state.extraction!)?.has(f.path) ?? false;
  const disabled = saving || state.busy ? "disabled" : "";

  const reasonsHtml =
    f.reasons.length > 0
      ? `<ul class="field-reasons">${f.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>`
      : "";
  const evidenceHtml = f.matched_text
    ? `<div class="field-evidence">“${esc(f.matched_text)}”${f.match_score !== null && f.match_score < 100 ? ` <span style="opacity:.7">(${Math.round(f.match_score)}% match)</span>` : ""}</div>`
    : "";

  const editHtml = isEditing
    ? `<div class="edit-row">
        ${
          typeof f.value === "boolean"
            ? `<select class="select" id="edit-value" aria-label="Correction for ${esc(f.path)}" ${disabled}><option value="true" ${state.editingValue === "true" ? "selected" : ""}>true</option><option value="false" ${state.editingValue === "false" ? "selected" : ""}>false</option></select>`
            : `<input class="text-input" id="edit-value" aria-label="Correction for ${esc(f.path)}" ${typeof f.value === "number" ? 'inputmode="decimal"' : ""} value="${esc(state.editingValue)}" aria-invalid="${!!state.editError}" aria-describedby="edit-error" ${disabled} />`
        }
        <button class="btn btn-primary" type="button" data-save="${esc(f.path)}" ${disabled}>${saving ? "Saving…" : "Save"}</button>
        <button class="btn" type="button" data-cancel-edit ${disabled}>Cancel</button>
      </div><p class="edit-error" id="edit-error" role="alert">${esc(state.editError ?? "")}</p>`
    : "";

  return `
    <li class="field-row ${selected ? "is-selected" : ""}" data-path="${esc(f.path)}" aria-current="${selected ? "true" : "false"}">
      <div class="field-row-top">
        <button class="field-path field-select" type="button" data-select="${esc(f.path)}" tabindex="${navigable ? 0 : -1}" aria-label="Inspect ${esc(f.path)}">${esc(f.path)}</button>
        <span class="status-chip" data-status="${f.status}">${statusLabel(f.status)}</span>
      </div>
      <div class="field-value ${corrected ? "is-edited" : ""}">${esc(formatDisplayValue(f.path, displayValue))}</div>
      ${corrected ? `<p class="original-value">Originally extracted: ${esc(formatDisplayValue(f.path, f.value))}. Correction has not been automatically verified.</p>` : ""}
      ${review.status !== "pending" ? `<span class="review-badge">${review.status}</span>` : ""}
      ${reasonsHtml}
      ${evidenceHtml}
      ${
        isEditing
          ? editHtml
          : `<div class="field-actions">
              <button class="btn" type="button" data-approve="${esc(f.path)}" ${disabled}>Approve</button>
              <button class="btn" type="button" data-edit="${esc(f.path)}" ${disabled}>Edit</button>
              <button class="btn" type="button" data-reject="${esc(f.path)}" ${disabled}>Reject</button>
              ${review.status !== "pending" ? `<button class="btn" type="button" data-reset="${esc(f.path)}" ${disabled}>Reset</button>` : ""}
              ${saving ? '<span role="status">Saving…</span>' : ""}
            </div>`
      }
    </li>
  `;
}

/* ------------------------------ event wiring ----------------------------- */

function attachViewerRectEvents(): void {
  const image = document.querySelector<HTMLImageElement>("#page-frame img");
  image?.addEventListener("error", () => {
    const scroll = document.getElementById("viewer-scroll");
    if (!scroll || !scroll.contains(image) || scroll.querySelector(".page-image-error")) return;
    const error = document.createElement("div");
    error.className = "page-image-error";
    error.innerHTML =
      '<p role="alert">Page image could not load. Field evidence remains available below.</p><button class="btn" type="button">Retry page image</button>';
    error.querySelector("button")!.addEventListener("click", () => {
      scroll.innerHTML = renderPageFrame();
      attachViewerRectEvents();
    });
    scroll.prepend(error);
  });
  document.querySelectorAll<HTMLElement>(".highlight-rect").forEach((rect) => {
    rect.addEventListener("click", () => selectField(rect.dataset.path!, { pulse: true }));
    rect.addEventListener("mouseenter", () => setHoveredRow(rect.dataset.path!, true));
    rect.addEventListener("mouseleave", () => setHoveredRow(rect.dataset.path!, false));
  });
}

function attachWorkbenchEvents(): void {
  const workbench = getWorkbench();
  workbench.querySelector("#toggle-filters")?.addEventListener("click", () => {
    state.filtersOpen = !state.filtersOpen;
    renderWorkbench();
  });
  workbench.querySelectorAll<HTMLButtonElement>("[data-mobile-view]").forEach((button) => {
    button.addEventListener("click", () => {
      state.mobilePane = button.dataset.mobileView as AppState["mobilePane"];
      renderWorkbench();
    });
  });

  workbench.querySelector<HTMLButtonElement>("#prev-page")?.addEventListener("click", () => {
    state.currentPage = Math.max(1, state.currentPage - 1);
    renderWorkbench();
  });
  workbench.querySelector<HTMLButtonElement>("#next-page")?.addEventListener("click", () => {
    state.currentPage = Math.min(state.document!.page_count, state.currentPage + 1);
    renderWorkbench();
  });
  workbench.querySelector<HTMLButtonElement>("#zoom-in")?.addEventListener("click", () => {
    state.zoomIsAuto = false;
    state.zoom = Math.min(3, Math.round((state.zoom + 0.25) * 100) / 100);
    renderWorkbench();
  });
  workbench.querySelector<HTMLButtonElement>("#zoom-out")?.addEventListener("click", () => {
    state.zoomIsAuto = false;
    state.zoom = Math.max(0.35, Math.round((state.zoom - 0.25) * 100) / 100);
    renderWorkbench();
  });

  workbench.querySelector<HTMLButtonElement>("#zoom-fit")?.addEventListener("click", () => {
    state.zoomIsAuto = true;
    renderWorkbench();
  });
  workbench.querySelector<HTMLSelectElement>("#review-filter")?.addEventListener("change", (event) => {
    state.reviewFilter = (event.target as HTMLSelectElement).value as AppState["reviewFilter"];
    renderWorkbench();
  });
  attachViewerRectEvents();

  workbench.querySelectorAll<HTMLElement>(".count-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      state.statusFilter = (chip.dataset.statusFilter as AppState["statusFilter"]) ?? "all";
      renderWorkbench();
    });
  });

  const search = workbench.querySelector<HTMLInputElement>("#search-input");
  search?.addEventListener("input", () => {
    state.searchQuery = search.value;
    renderFieldListOnly();
  });

  const list = workbench.querySelector<HTMLUListElement>("#field-list")!;
  list.addEventListener("click", (e) => onFieldListClick(e));
  list.addEventListener("keydown", (e) => onFieldListKeydown(e));
  list.addEventListener("input", (e) => {
    if ((e.target as HTMLElement).id === "edit-value")
      state.editingValue = (e.target as HTMLInputElement | HTMLSelectElement).value;
  });
}

function onFieldListClick(e: Event): void {
  const target = e.target as HTMLElement;
  const approve = target.closest<HTMLElement>("[data-approve]");
  const edit = target.closest<HTMLElement>("[data-edit]");
  const reject = target.closest<HTMLElement>("[data-reject]");
  const reset = target.closest<HTMLElement>("[data-reset]");
  const save = target.closest<HTMLElement>("[data-save]");
  const cancel = target.closest<HTMLElement>("[data-cancel-edit]");
  const row = target.closest<HTMLElement>(".field-row");

  if (approve) return void reviewField(approve.dataset.approve!, "approve");
  if (reject) return void reviewField(reject.dataset.reject!, "reject");
  if (reset) return void reviewField(reset.dataset.reset!, "reset");
  if (edit) {
    const path = edit.dataset.edit!;
    const field = state.extraction!.report.fields.find((field) => field.path === path)!;
    state.editingPath = path;
    state.editingValue = String(reviewValue(field, state.extraction!.review[path]));
    state.editError = null;
    renderTopbar();
    renderFieldListOnly();
    const input = document.getElementById("edit-value") as HTMLInputElement | HTMLSelectElement;
    input.focus({ preventScroll: true });
    if (input instanceof HTMLInputElement) input.select();
    return;
  }
  if (cancel) {
    state.editingPath = null;
    state.editError = null;
    renderTopbar();
    renderFieldListOnly();
    return;
  }
  if (save) return void saveEdit(save.dataset.save!);
  if (target.closest("input, select")) return;
  if (row) selectField(row.dataset.path!, { pulse: true, focus: true, showDocument: true });
}

function saveEdit(path: string): void {
  const field = state.extraction?.report.fields.find((field) => field.path === path);
  const input = document.getElementById("edit-value") as HTMLInputElement | HTMLSelectElement | null;
  if (!field || !input) return;
  state.editingValue = input.value;
  try {
    const value = parseEditValue(field.value, input.value);
    state.editError = null;
    void reviewField(path, "edit", value);
  } catch (err) {
    state.editError = err instanceof Error ? err.message : "Invalid correction.";
    renderFieldListOnly();
    document.getElementById("edit-value")?.focus({ preventScroll: true });
  }
}

function onFieldListKeydown(e: KeyboardEvent): void {
  const target = e.target as HTMLElement;
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if (target.matches("input, select")) {
    if (e.key === "Enter" && state.editingPath) {
      e.preventDefault();
      saveEdit(state.editingPath);
    }
    if (e.key === "Escape") {
      e.preventDefault();
      state.editingPath = null;
      state.editError = null;
      renderTopbar();
      renderFieldListOnly();
    }
    return;
  }
  if (target !== document.getElementById("field-list") && !target.matches("[data-select]")) return;
  const fields = filteredFields();
  if (fields.length === 0) return;
  const path = target.dataset.select ?? state.selectedPath;
  const currentIndex = fields.findIndex((f) => f.path === path);
  const keys: Record<string, number> = {
    ArrowDown: Math.min(fields.length - 1, currentIndex + 1),
    ArrowUp: Math.max(0, currentIndex - 1),
    Home: 0,
    End: fields.length - 1,
  };
  const index = keys[e.key];
  if (index !== undefined) {
    e.preventDefault();
    selectField(fields[index]!.path, { pulse: true, focus: true });
  } else if (e.key.toLowerCase() === "a" && path) {
    e.preventDefault();
    void reviewField(path, "approve");
  } else if (e.key.toLowerCase() === "r" && path) {
    e.preventDefault();
    void reviewField(path, "reject");
  }
}

function fieldRow(path: string): HTMLElement | undefined {
  return [...document.querySelectorAll<HTMLElement>(".field-row")].find((row) => row.dataset.path === path);
}

function selectField(
  path: string,
  opts: { pulse?: boolean; focus?: boolean; showDocument?: boolean } = {},
): void {
  const field = state.extraction?.report.fields.find((field) => field.path === path);
  if (!field) return;
  state.selectedPath = path;
  const mobileDocument = opts.showDocument && window.matchMedia("(max-width: 860px)").matches;
  if (mobileDocument) state.mobilePane = "document";
  if (field.page) state.currentPage = field.page;
  renderWorkbench();
  const rect = [...document.querySelectorAll<HTMLElement>(".highlight-rect")].find(
    (rect) => rect.dataset.path === path,
  );
  if (rect) {
    const scroll = document.getElementById("viewer-scroll")!;
    scroll.scrollTo({
      top: Math.max(0, rect.offsetTop - scroll.clientHeight / 2),
      left: Math.max(0, rect.offsetLeft - scroll.clientWidth / 2),
    });
  }
  if (opts.pulse && rect && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    rect.classList.add("is-pulsing");
    window.setTimeout(() => rect.classList.remove("is-pulsing"), 1900);
  }
  const row = fieldRow(path);
  if (row) {
    const list = document.getElementById("field-list")!;
    const rowTop = row.offsetTop - list.offsetTop;
    if (rowTop < list.scrollTop) list.scrollTop = rowTop;
    else if (rowTop + row.offsetHeight > list.scrollTop + list.clientHeight)
      list.scrollTop = rowTop + row.offsetHeight - list.clientHeight;
    if (opts.focus && !mobileDocument)
      row.querySelector<HTMLButtonElement>("[data-select]")?.focus({ preventScroll: true });
  }
  if (mobileDocument)
    document
      .querySelector<HTMLButtonElement>('[data-mobile-view="document"]')
      ?.focus({ preventScroll: true });
}

function setHoveredRow(path: string, on: boolean): void {
  fieldRow(path)?.classList.toggle("is-hovered", on);
}

async function reviewField(
  path: string,
  action: "approve" | "edit" | "reject" | "reset",
  value?: string | number | boolean,
): Promise<void> {
  const document = state.document;
  const extraction = state.extraction;
  if (!document || !extraction || state.busy) return;
  const pending = pendingReviews.get(extraction) ?? new Set<string>();
  if (pending.has(path)) return;
  pending.add(path);
  pendingReviews.set(extraction, pending);
  renderTopbar();
  renderFieldListOnly();
  try {
    const entry = await ds.review(document.id, path, action, value);
    extraction.review[path] = entry;
    if (state.document === document && state.extraction === extraction) {
      if (action === "edit" && state.editingPath === path) state.editingPath = null;
      toast(`${path}: ${entry.status}`);
    }
  } catch (err) {
    if (state.document === document && state.extraction === extraction) {
      const message = err instanceof Error ? err.message : "Couldn't update review status";
      if (action === "edit") state.editError = message;
      toast(message);
    }
  } finally {
    pending.delete(path);
    if (state.document === document && state.extraction === extraction) {
      renderTopbar();
      renderFieldListOnly();
    }
  }
}

function renderFieldListOnly(): void {
  const list = document.getElementById("field-list");
  if (!list) return;
  const restoreFocus = rememberFocus();
  const scroll = list.scrollTop;
  const input = document.getElementById("edit-value") as HTMLInputElement | HTMLSelectElement | null;
  if (input && input.closest<HTMLElement>(".field-row")?.dataset.path === state.editingPath)
    state.editingValue = input.value;
  list.innerHTML = renderFieldRows();
  list.scrollTop = scroll;
  const progress = document.getElementById("review-progress");
  const fields = state.extraction!.report.fields;
  const pending = fields.filter(
    (field) =>
      !state.extraction!.review[field.path] || state.extraction!.review[field.path]!.status === "pending",
  ).length;
  if (progress)
    progress.textContent = `${fields.length - pending} of ${fields.length} reviewed · ${pending} pending`;
  const note = document.querySelector(".demo-note");
  if (ds.reviewPersistence === "session" && note)
    note.textContent =
      "Synthetic fixture with planted errors. Browser storage is unavailable. Tab only: export decisions before reloading.";
  restoreFocus();
}

/* --------------------------------- boot ---------------------------------- */

renderTopbar();
if (ds.kind === "demo") void bootDemo();
else void renderStart();
