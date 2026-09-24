import "./style.css";
import { createDataSource } from "./datasource";
import { computeExportRows, downloadBlob, rowsToCsv } from "./export";
import type {
  DocumentSummary,
  ExtractionResult,
  FieldStatus,
  FieldVerification,
} from "./types";
import { SCHEMA_NAMES } from "./types";

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
  schemaName: "invoice",
  provider: "fixture",
  fixtureFile: null,
  busy: false,
  samples: [],
};

const app = document.getElementById("app")!;

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
  if (isMoneyField(path)) {
    const num = typeof value === "number" ? value : Number(value);
    if (Number.isFinite(num)) {
      return num.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
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
      <span class="brand-mark">fieldproof</span>
      ${countsHtml}
    </div>
    <div class="topbar-controls">
      ${state.extraction ? exportControlsHtml() : ""}
      <button class="btn" id="theme-toggle" type="button" aria-label="Toggle dark mode">
        ${currentTheme() === "dark" ? "☀️ Light" : "☽ Dark"}
      </button>
    </div>
  `;

  bar.querySelector<HTMLButtonElement>("#theme-toggle")?.addEventListener("click", toggleTheme);
  bar.querySelector<HTMLButtonElement>("#export-json")?.addEventListener("click", () => exportAs("json"));
  bar.querySelector<HTMLButtonElement>("#export-csv")?.addEventListener("click", () => exportAs("csv"));
}

function exportControlsHtml(): string {
  return `
    <button class="btn" id="export-json" type="button">Export JSON</button>
    <button class="btn" id="export-csv" type="button">Export CSV</button>
  `;
}

async function exportAs(format: "json" | "csv"): Promise<void> {
  if (!state.document || !state.extraction) return;
  const base = state.document.filename.replace(/\.pdf$/i, "");
  if (ds.kind === "live") {
    window.open(ds.exportUrl(state.document.id, format), "_blank");
    return;
  }
  const rows = computeExportRows(state.extraction);
  if (format === "json") {
    downloadBlob(`${base}.fieldproof.json`, JSON.stringify(rows, null, 2), "application/json");
  } else {
    downloadBlob(`${base}.fieldproof.csv`, rowsToCsv(rows), "text/csv");
  }
  toast(`Exported ${rows.length} field${rows.length === 1 ? "" : "s"}`);
}

/* ------------------------------ start state ----------------------------- */

async function renderStart(): Promise<void> {
  const workbench = getWorkbench();
  if (ds.kind === "demo") {
    if (state.samples.length === 0) {
      state.samples = (await ds.listSamples?.()) ?? [];
    }
    workbench.innerHTML = `
      <div class="start-state">
        <div class="proof-ticks" aria-hidden="true">
          <span class="proof-tick"><span class="proof-dot" style="background:var(--color-verified)"></span>verified</span>
          <span class="proof-tick"><span class="proof-dot" style="background:var(--color-review)"></span>needs review</span>
          <span class="proof-tick"><span class="proof-dot" style="background:var(--color-unsupported)"></span>unsupported</span>
        </div>
        <h1>Every field, traced to its source</h1>
        <p>
          Three synthetic sample documents, pre-extracted by an LLM and pre-verified by fieldproof.
          Candidate extractions are fixtures with planted errors, to show what the verifier catches -
          a hallucinated PO number, a total that doesn't match its line items, and a misread date.
        </p>
        <div class="sample-grid">
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
    return;
  }

  workbench.innerHTML = `
    <div class="start-state">
      <h1>Upload a document</h1>
      <p>PDF with a text layer. Extraction runs against the fixture provider or Claude, then every field is grounded and verified against the page.</p>
      <label class="dropzone" id="dropzone" for="file-input">
        Drop a PDF here, or click to choose one
      </label>
      <input type="file" id="file-input" accept="application/pdf" class="visually-hidden" />
    </div>
  `;
  const input = workbench.querySelector<HTMLInputElement>("#file-input")!;
  const zone = workbench.querySelector<HTMLElement>("#dropzone")!;
  input.addEventListener("change", () => {
    if (input.files?.[0]) void uploadFile(input.files[0]);
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
  const { document: doc, extraction } = await ds.loadSample(id);
  state.document = doc;
  state.extraction = extraction;
  state.currentPage = 1;
  state.zoomIsAuto = true;
  state.selectedPath = null;
  state.statusFilter = "all";
  state.searchQuery = "";
  renderTopbar();
  renderWorkbench();
}

async function uploadFile(file: File): Promise<void> {
  try {
    state.document = await ds.uploadDocument(file);
    state.extraction = null;
    state.currentPage = 1;
    state.zoomIsAuto = true;
    renderTopbar();
    renderWorkbench();
  } catch (err) {
    toast(err instanceof Error ? err.message : "Upload failed");
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
  if (!state.document) return;
  if (state.provider === "fixture" && !state.fixtureFile) {
    toast("Choose a fixture JSON file first");
    return;
  }
  state.busy = true;
  renderConfigure();
  try {
    state.extraction = await ds.extract(state.document.id, state.schemaName, state.provider, state.fixtureFile);
    state.currentPage = 1;
    state.zoomIsAuto = true;
    renderTopbar();
  } catch (err) {
    toast(err instanceof Error ? err.message : "Extraction failed");
  } finally {
    state.busy = false;
    renderWorkbench();
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
    if (!q) return true;
    return f.path.toLowerCase().includes(q) || String(f.value).toLowerCase().includes(q);
  });
  if (state.statusFilter !== "all") return matched; // already one status - sorting would be a no-op
  return [...matched].sort(
    (a, b) => STATUS_SORT_PRIORITY[a.status] - STATUS_SORT_PRIORITY[b.status],
  );
}

function renderWorkbench(): void {
  if (!state.document) {
    void renderStart();
    return;
  }
  if (!state.extraction) {
    renderConfigure();
    return;
  }

  const workbench = getWorkbench();
  workbench.innerHTML = `
    <section class="viewer-pane" aria-label="Document page">
      <div class="viewer-toolbar">
        <button class="btn" id="prev-page" type="button" ${state.currentPage <= 1 ? "disabled" : ""}>←</button>
        <span>Page ${state.currentPage} / ${state.document.page_count}</span>
        <button class="btn" id="next-page" type="button" ${state.currentPage >= state.document.page_count ? "disabled" : ""}>→</button>
        <span style="flex:1"></span>
        <button class="btn" id="zoom-out" type="button" aria-label="Zoom out">−</button>
        <span id="zoom-label">${Math.round(state.zoom * 100)}%</span>
        <button class="btn" id="zoom-in" type="button" aria-label="Zoom in">+</button>
      </div>
      <div class="viewer-scroll" id="viewer-scroll">
        ${renderPageFrame()}
      </div>
    </section>
    <section class="field-pane" aria-label="Extracted fields">
      ${renderFieldPaneHeader()}
      <ul class="field-list" id="field-list" tabindex="0" aria-label="Fields (arrow keys to navigate, a to approve, r to reject)">
        ${renderFieldRows()}
      </ul>
    </section>
  `;

  attachWorkbenchEvents();
  if (state.zoomIsAuto) refreshAutoZoom();
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
  const available = scroll.clientWidth - 48; // viewer-scroll padding (24px each side)
  const fit = Math.min(1, Math.max(0.35, available / naturalWidth));
  const nextZoom = Math.round(fit * 100) / 100;
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
  const chip = (status: FieldStatus | "all", label: string, count: number): string => `
    <button class="count-chip ${state.statusFilter === status ? "is-active" : ""}" data-status-filter="${status}"
      data-status="${status === "all" ? "" : status}" type="button">
      ${esc(label)} ${count}
    </button>
  `;
  return `
    <div class="field-pane-header">
      <div class="counts-strip">
        ${chip("all", "All", state.extraction!.report.fields.length)}
        ${chip("verified", "Verified", counts.verified)}
        ${chip("needs_review", "Needs review", counts.needs_review)}
        ${chip("unsupported", "Unsupported", counts.unsupported)}
      </div>
      <div class="filter-row">
        <input class="text-input" id="search-input" type="search" placeholder="Search fields…" value="${esc(state.searchQuery)}" />
      </div>
    </div>
  `;
}

function renderFieldRows(): string {
  const fields = filteredFields();
  if (fields.length === 0) {
    return `<li class="empty-filtered">No fields match this filter.</li>`;
  }
  return fields.map((f) => renderFieldRow(f)).join("");
}

function renderFieldRow(f: FieldVerification): string {
  const review = state.extraction!.review[f.path] ?? { status: "pending", edited_value: null };
  const selected = f.path === state.selectedPath;
  const displayValue = review.status === "edited" ? review.edited_value : f.value;
  const isEditing = state.editingPath === f.path;

  const reasonsHtml =
    f.reasons.length > 0
      ? `<ul class="field-reasons">${f.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>`
      : "";
  const evidenceHtml = f.matched_text
    ? `<div class="field-evidence">“${esc(f.matched_text)}”${f.match_score !== null && f.match_score < 100 ? ` <span style="opacity:.7">(${Math.round(f.match_score)}% match)</span>` : ""}</div>`
    : "";

  const editHtml = isEditing
    ? `<div class="edit-row">
        <input class="text-input" id="edit-input-${esc(f.path)}" value="${esc(displayValue)}" />
        <button class="btn btn-primary" type="button" data-save="${esc(f.path)}">Save</button>
        <button class="btn" type="button" data-cancel-edit>Cancel</button>
      </div>`
    : "";

  return `
    <li class="field-row ${selected ? "is-selected" : ""}" data-path="${esc(f.path)}" aria-current="${selected ? "true" : "false"}">
      <div class="field-row-top">
        <span class="field-path">${esc(f.path)}</span>
        <span class="status-chip" data-status="${f.status}">${statusLabel(f.status)}</span>
      </div>
      <div class="field-value ${review.status === "edited" ? "is-edited" : ""}">${esc(formatDisplayValue(f.path, displayValue))}</div>
      ${review.status !== "pending" ? `<span class="review-badge">${review.status}</span>` : ""}
      ${reasonsHtml}
      ${evidenceHtml}
      ${
        isEditing
          ? editHtml
          : `<div class="field-actions">
              <button class="btn" type="button" data-approve="${esc(f.path)}">Approve</button>
              <button class="btn" type="button" data-edit="${esc(f.path)}">Edit</button>
              <button class="btn" type="button" data-reject="${esc(f.path)}">Reject</button>
              ${review.status !== "pending" ? `<button class="btn" type="button" data-reset="${esc(f.path)}">Reset</button>` : ""}
            </div>`
      }
    </li>
  `;
}

/* ------------------------------ event wiring ----------------------------- */

function attachViewerRectEvents(): void {
  document.querySelectorAll<HTMLElement>(".highlight-rect").forEach((rect) => {
    rect.addEventListener("click", () => selectField(rect.dataset.path!, { pulse: true }));
    rect.addEventListener("mouseenter", () => setHoveredRow(rect.dataset.path!, true));
    rect.addEventListener("mouseleave", () => setHoveredRow(rect.dataset.path!, false));
  });
}

function attachWorkbenchEvents(): void {
  const workbench = getWorkbench();

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
    state.editingPath = edit.dataset.edit!;
    renderFieldListOnly();
    return;
  }
  if (cancel) {
    state.editingPath = null;
    renderFieldListOnly();
    return;
  }
  if (save) {
    const path = save.dataset.save!;
    const input = document.getElementById(`edit-input-${cssEscape(path)}`) as HTMLInputElement | null;
    void reviewField(path, "edit", input?.value ?? "");
    state.editingPath = null;
    return;
  }
  if (row) {
    selectField(row.dataset.path!, { pulse: true });
  }
}

function cssEscape(s: string): string {
  return s.replace(/[^a-zA-Z0-9_-]/g, "_");
}

function onFieldListKeydown(e: KeyboardEvent): void {
  const target = e.target as HTMLElement;
  if (target.tagName === "INPUT") return; // typing in search or an edit box

  const fields = filteredFields();
  if (fields.length === 0) return;
  const currentIndex = fields.findIndex((f) => f.path === state.selectedPath);

  if (e.key === "ArrowDown" || e.key === "j") {
    e.preventDefault();
    const next = fields[Math.min(fields.length - 1, currentIndex + 1)] ?? fields[0];
    selectField(next!.path, { pulse: true });
  } else if (e.key === "ArrowUp" || e.key === "k") {
    e.preventDefault();
    const prev = fields[Math.max(0, currentIndex - 1)] ?? fields[0];
    selectField(prev!.path, { pulse: true });
  } else if (e.key === "a" && state.selectedPath) {
    void reviewField(state.selectedPath, "approve");
  } else if (e.key === "r" && state.selectedPath) {
    void reviewField(state.selectedPath, "reject");
  }
}

function selectField(path: string, opts: { pulse?: boolean } = {}): void {
  const field = state.extraction!.report.fields.find((f) => f.path === path);
  state.selectedPath = path;
  if (field?.page) state.currentPage = field.page;
  renderWorkbench();

  const rect = document.querySelector<HTMLElement>(`.highlight-rect[data-path="${cssAttrEscape(path)}"]`);
  rect?.scrollIntoView({ block: "center", inline: "center", behavior: "smooth" });
  if (opts.pulse && rect) {
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!prefersReducedMotion) {
      rect.classList.add("is-pulsing");
      window.setTimeout(() => rect.classList.remove("is-pulsing"), 1900);
    }
  }
  // renderWorkbench() just rebuilt #field-list from scratch (fresh scroll
  // position 0), regardless of what selected `path` - always re-settle it
  // on the selected row, not just for keyboard nav, or clicking a highlight
  // rect for a field below the fold silently scrolls the list back to top.
  document
    .querySelector<HTMLElement>(`.field-row[data-path="${cssAttrEscape(path)}"]`)
    ?.scrollIntoView({ block: "nearest" });
}

function cssAttrEscape(s: string): string {
  return s.replace(/"/g, '\\"');
}

function setHoveredRow(path: string, on: boolean): void {
  document
    .querySelector<HTMLElement>(`.field-row[data-path="${cssAttrEscape(path)}"]`)
    ?.classList.toggle("is-hovered", on);
}

async function reviewField(path: string, action: "approve" | "edit" | "reject" | "reset", value?: string): Promise<void> {
  if (!state.document) return;
  try {
    const entry = await ds.review(state.document.id, path, action, value);
    state.extraction!.review[path] = entry;
    renderFieldListOnly();
  } catch (err) {
    toast(err instanceof Error ? err.message : "Couldn't update review status");
  }
}

function renderFieldListOnly(): void {
  // Deliberately leaves the <ul id="field-list"> element and the search
  // input in place (only their contents/value change) so the delegated
  // click/keydown listeners on the list and focus/cursor in the search box
  // both survive a keystroke or a review action - only the counts strip
  // (which reflects verification, not review, status) never needs this.
  const list = document.getElementById("field-list");
  if (!list) return;
  list.innerHTML = renderFieldRows();
}

/* --------------------------------- boot ---------------------------------- */

renderTopbar();
void renderStart();
