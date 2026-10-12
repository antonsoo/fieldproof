import type { DataSource } from "./datasource";
import type { SessionList } from "./types";

function esc(value: unknown): string {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export class SessionsDialog {
  private dialog = document.createElement("dialog");
  private request: AbortController | null = null;
  private data: SessionList | null = null;
  private removing: string | null = null;
  private pendingDelete = false;
  private loading = false;

  constructor(
    private source: DataSource,
    private callbacks: {
      current: () => string | undefined;
      blocked: () => boolean;
      open: (id: string) => void;
      removed: (id: string) => void;
    },
  ) {
    this.dialog.className = "sessions-dialog";
    this.dialog.setAttribute("aria-labelledby", "sessions-title");
    this.dialog.addEventListener("close", () => {
      this.request?.abort();
      this.request = null;
    });
    this.dialog.addEventListener("cancel", (event) => {
      if (this.pendingDelete) event.preventDefault();
    });
    document.body.append(this.dialog);
  }

  show(): void {
    if (this.dialog.open) return;
    this.removing = null;
    this.render();
    this.dialog.showModal();
    void this.load();
  }

  private shell(content: string): void {
    this.dialog.innerHTML = `
      <div class="sessions-heading"><h2 id="sessions-title">Document sessions</h2>
        <button class="btn" id="close-sessions" type="button" ${this.pendingDelete ? "disabled" : ""}>Close</button>
      </div>
      <p>PDFs and saved decisions stay in this server until you remove them or restart it.
      Save a review archive to resume later, or export the values you need before removing a session.</p>
      ${content}
    `;
    this.dialog.querySelector("#close-sessions")?.addEventListener("click", () => this.dialog.close());
  }

  private render(message = ""): void {
    const data = this.data;
    const editingBlocked = this.callbacks.blocked();
    const blocked = editingBlocked || this.loading;
    this.shell(`
      ${message ? `<p role="alert">${esc(message)}</p>` : ""}
      ${editingBlocked ? "<p>Finish or cancel the current operation or correction before opening or removing sessions.</p>" : ""}
      ${this.loading && data ? '<p role="status">Refreshing sessions…</p>' : ""}
      ${
        !data
          ? '<p role="status">Loading sessions…</p>'
          : `
        <p class="session-capacity">${data.documents.length} of ${data.max_sessions} document slots in use ·
        up to ${Math.floor(data.max_pdf_bytes / 1024 / 1024)} MiB and ${data.max_pages} pages per PDF</p>
        ${
          !data.documents.length
            ? "<p>No documents stored yet.</p>"
            : `<ul class="session-list">${data.documents
                .map(
                  (entry) => `
          <li data-session="${esc(entry.id)}">
            <div><strong>${esc(entry.filename)}</strong>
              ${entry.id === this.callbacks.current() ? "<span class='session-current'>Open now</span>" : ""}
              <span>${entry.page_count} page${entry.page_count === 1 ? "" : "s"} · ${Math.max(1, Math.ceil(entry.pdf_bytes / 1024)).toLocaleString()} KiB ·
              ${entry.has_extraction ? `${entry.reviewed_count} of ${entry.field_count} reviewed` : "Ready to extract"}
              ${entry.busy ? " · Extraction running" : ""}</span>
            </div>
            ${
              this.removing === entry.id
                ? `
              <p>Remove this PDF and all saved decisions? This cannot be undone.</p>
              <button class="btn" data-keep="${esc(entry.id)}" type="button" ${this.pendingDelete ? "disabled" : ""}>Keep session</button>
              <button class="btn btn-danger" data-confirm="${esc(entry.id)}" type="button" ${this.pendingDelete ? "disabled" : ""}>${this.pendingDelete ? "Removing…" : "Remove permanently"}</button>
            `
                : `
              <button class="btn" data-open="${esc(entry.id)}" type="button" ${blocked || entry.busy ? "disabled" : ""}>Open</button>
              <button class="btn" data-remove="${esc(entry.id)}" type="button" ${blocked || entry.busy ? "disabled" : ""}>Remove</button>
            `
            }
          </li>`,
                )
                .join("")}</ul>`
        }
      `
      }
      <button class="btn" id="refresh-sessions" type="button" ${this.pendingDelete ? "disabled" : ""}>Refresh</button>
    `);
    this.dialog.querySelector("#refresh-sessions")?.addEventListener("click", () => void this.load());
    this.dialog.querySelectorAll<HTMLButtonElement>("[data-open]").forEach((button) => {
      button.addEventListener("click", () => {
        if (this.callbacks.blocked()) {
          this.render();
          return;
        }
        this.dialog.close();
        this.callbacks.open(button.dataset.open!);
      });
    });
    this.dialog.querySelectorAll<HTMLButtonElement>("[data-remove]").forEach((button) => {
      button.addEventListener("click", () => {
        this.removing = button.dataset.remove!;
        this.render();
        this.dialog.querySelector<HTMLButtonElement>("[data-keep]")?.focus();
      });
    });
    this.dialog.querySelector("[data-keep]")?.addEventListener("click", () => {
      const id = this.removing;
      this.removing = null;
      this.render();
      [...this.dialog.querySelectorAll<HTMLButtonElement>("[data-remove]")]
        .find((button) => button.dataset.remove === id)
        ?.focus();
    });
    this.dialog.querySelector("[data-confirm]")?.addEventListener("click", () => void this.remove());
  }

  private async load(): Promise<void> {
    this.request?.abort();
    const owner = new AbortController();
    this.request = owner;
    this.removing = null;
    this.loading = true;
    this.render();
    try {
      const data = await this.source.listSessions!(owner.signal);
      if (this.request !== owner || !this.dialog.open) return;
      this.data = data;
      this.loading = false;
      this.render();
    } catch (error) {
      if (this.request === owner && this.dialog.open) {
        this.loading = false;
        this.render(error instanceof Error ? error.message : "Could not load sessions.");
      }
    }
    this.dialog.querySelector<HTMLButtonElement>("#close-sessions")?.focus();
  }

  private async remove(): Promise<void> {
    if (!this.removing || this.pendingDelete || this.callbacks.blocked()) {
      this.render();
      return;
    }
    const id = this.removing;
    this.pendingDelete = true;
    this.render();
    try {
      await this.source.deleteSession!(id);
      if (this.data)
        this.data = { ...this.data, documents: this.data.documents.filter((entry) => entry.id !== id) };
      this.callbacks.removed(id);
      this.pendingDelete = false;
      this.removing = null;
      await this.load();
    } catch (error) {
      this.pendingDelete = false;
      this.render(error instanceof Error ? error.message : "Could not remove session.");
      this.dialog.querySelector<HTMLButtonElement>("[data-keep]")?.focus();
    }
  }
}
