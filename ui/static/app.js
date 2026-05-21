// ── Shared helpers ─────────────────────────────────────────────────────────

function fmt(n) {
  if (n == null) return "—";
  if (n >= 1000) return (n / 1000).toFixed(1) + "k";
  return String(n);
}

function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  const diffDays = Math.floor((Date.now() - d) / 86_400_000);
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7)  return `${diffDays}d ago`;
  const sameYear = d.getFullYear() === new Date().getFullYear();
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", ...(sameYear ? {} : { year: "numeric" }) });
}

function snippet(text, max = 90) {
  if (!text) return "";
  return text.length > max ? text.slice(0, max) + "…" : text;
}

// ── syncState component ─────────────────────────────────────────────────────
// Manages a single pipeline run: start → SSE stream → done.

function syncState() {
  return {
    phase: "idle",    // idle | waiting | running | complete | error
    message: "",
    loginWaiting: false,
    events: [],
    count: 0,
    total: 0,
    _sse: null,
    _dismissTimer: null,

    get isRunning() { return this.phase === "waiting" || this.phase === "running"; },
    get progressPct() {
      return this.total > 0 ? Math.round((this.count / this.total) * 100) : 0;
    },

    async startSync() {
      if (this.isRunning) return;
      if (this._dismissTimer) { clearTimeout(this._dismissTimer); this._dismissTimer = null; }
      this.phase = "waiting";
      this.message = "Starting…";
      this.events = [];
      this.loginWaiting = false;
      this.count = 0;
      this.total = 0;

      let res;
      try {
        res = await fetch("/api/pipeline/start", { method: "POST" });
      } catch (e) {
        this.phase = "error";
        this.message = "Could not reach server.";
        return;
      }

      if (res.status === 409) {
        this.message = "A sync is already running. Reconnecting…";
      } else if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        this.phase = "error";
        this.message = body.detail || "Failed to start sync.";
        return;
      }

      const { run_id } = res.status === 409
        ? await res.json().catch(() => ({}))
        : await res.json();

      if (!run_id) {
        this.phase = "error";
        this.message = "A sync is already in progress. Refresh to check status.";
        return;
      }

      this._openStream(run_id);
    },

    // Upsert an event row by phase — at most one row per phase, updated in-place.
    _upsertEvent(event) {
      const idx = this.events.findIndex(e => e.phase === event.phase);
      if (idx >= 0) {
        this.events.splice(idx, 1, event);
      } else {
        this.events.push(event);
      }
    },

    _scheduleDismiss(delayMs) {
      this._dismissTimer = setTimeout(() => {
        this.phase = "idle";
        this._dismissTimer = null;
      }, delayMs);
    },

    _openStream(run_id) {
      if (this._sse) { this._sse.close(); this._sse = null; }

      const sse = new EventSource(`/api/pipeline/stream/${run_id}`);
      this._sse = sse;

      sse.onmessage = (ev) => {
        let event;
        try { event = JSON.parse(ev.data); } catch { return; }

        this.message = event.message || "";
        if (event.count) this.count = event.count;
        if (event.total) this.total = event.total;

        // Forward post data to table independently of display logic
        if (event.status === "post_ready" && event.post) {
          window.dispatchEvent(new CustomEvent("post-ready", { detail: event.post }));
        }

        if (event.phase === "login" && event.status === "waiting") {
          this.loginWaiting = true;
          this.phase = "waiting";
          this._upsertEvent(event);
        } else if (event.phase === "login" && event.status === "complete") {
          this.loginWaiting = false;
          this.phase = "running";
          this._upsertEvent(event);
        } else if (event.phase === "complete") {
          this.phase = "complete";
          this.loginWaiting = false;
          sse.close();
          this._sse = null;
          this.$dispatch("sync-complete");
          this._scheduleDismiss(4000);
        } else if (event.phase === "error") {
          this.phase = "error";
          this.loginWaiting = false;
          sse.close();
          this._sse = null;
          this._scheduleDismiss(7000);
        } else {
          // scrape / ai progress — upsert so only one row per phase shows
          this._upsertEvent(event);
          this.phase = "running";
        }
      };

      sse.onerror = () => {
        if (this.phase !== "complete" && this.phase !== "error") {
          this.phase = "error";
          this.message = "Lost connection to server.";
          this._scheduleDismiss(7000);
        }
        sse.close();
        this._sse = null;
      };
    },

    destroy() {
      if (this._sse) { this._sse.close(); this._sse = null; }
      if (this._dismissTimer) { clearTimeout(this._dismissTimer); this._dismissTimer = null; }
    },
  };
}

// ── postsTable component ────────────────────────────────────────────────────

function postsTable() {
  return {
    posts: [],
    pagedPosts: [],
    totalPages: 1,
    maxImpressions: 1,
    loading: true,
    error: "",
    page: 1,
    pageSize: 10,
    aiFeedbackEnabled: false,

    _updatePaged() {
      const size = this.pageSize || 20;
      const start = (this.page - 1) * size;
      this.pagedPosts = this.posts.slice(start, start + size);
      this.totalPages = Math.max(1, Math.ceil(this.posts.length / size));
      this.maxImpressions = this.posts.reduce((m, p) => Math.max(m, p.impressions || 0), 1);
    },

    prevPage() { if (this.page > 1) { this.page--; this._updatePaged(); } },
    nextPage() { if (this.page < this.totalPages) { this.page++; this._updatePaged(); } },

    async init() {
      window.addEventListener("post-ready", (e) => this.upsertPost(e.detail));
      try {
        const res = await fetch("/api/settings");
        if (res.ok) {
          const data = await res.json();
          this.aiFeedbackEnabled = data.ai_feedback_enabled;
        }
      } catch { /* use defaults */ }
      await this.load();
    },

    upsertPost(post) {
      const idx = this.posts.findIndex(p => p.url === post.url);
      if (idx >= 0) {
        this.posts.splice(idx, 1, post);
      } else {
        const insertIdx = this.posts.findIndex(p => (p.date_iso || "") < (post.date_iso || ""));
        if (insertIdx >= 0) {
          this.posts.splice(insertIdx, 0, post);
        } else {
          this.posts.push(post);
        }
      }
      this._updatePaged();
    },

    async load() {
      this.loading = true;
      this.error = "";
      this.page = 1;
      try {
        const res = await fetch("/api/posts");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        this.posts = await res.json();
        this._updatePaged();
      } catch (e) {
        this.error = "Could not load posts: " + e.message;
      } finally {
        this.loading = false;
      }
    },

    postDetailUrl(post) {
      return "/post.html?url=" + encodeURIComponent(post.url);
    },

    fmt,
    fmtDate,
    snippet,
  };
}

// ── settingsForm component ──────────────────────────────────────────────────

function settingsForm() {
  return {
    apiKey: "",
    scrapeLimit: 10,
    aiFeedbackEnabled: false,
    linkedinSessionExpires: null,
    verifying: false,
    saving: false,
    resetting: false,
    alert: null,

    async init() {
      try {
        const res = await fetch("/api/settings");
        const data = await res.json();
        // Show placeholder text if key is masked; keep field empty so user can re-enter
        this.apiKey = data.anthropic_api_key || "";
        this.scrapeLimit = data.scrape_limit;
        this.aiFeedbackEnabled = data.ai_feedback_enabled;
        this.linkedinSessionExpires = data.linkedin_session_expires || null;
      } catch {
        this.showAlert("error", "Could not load settings.");
      }
    },

    fmtSessionExpiry() {
      if (!this.linkedinSessionExpires) return null;
      return new Date(this.linkedinSessionExpires).toLocaleDateString(undefined, {
        month: "long", day: "numeric", year: "numeric",
      });
    },

    async verifyKey() {
      if (!this.apiKey) return;
      this.verifying = true;
      this.alert = null;
      try {
        const res = await fetch("/api/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ anthropic_api_key: this.apiKey }),
        });
        if (res.ok) {
          this.showAlert("success", "API key is valid and saved.");
        } else {
          const body = await res.json().catch(() => ({}));
          this.showAlert("error", body.detail || "Invalid API key.");
        }
      } catch {
        this.showAlert("error", "Could not reach server.");
      } finally {
        this.verifying = false;
      }
    },

    async save() {
      this.saving = true;
      this.alert = null;
      try {
        const payload = {
          scrape_limit: Number(this.scrapeLimit),
          ai_feedback_enabled: this.aiFeedbackEnabled,
        };
        const res = await fetch("/api/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (res.ok) {
          this.showAlert("success", "Settings saved.");
        } else {
          const body = await res.json().catch(() => ({}));
          this.showAlert("error", body.detail || "Failed to save settings.");
        }
      } catch {
        this.showAlert("error", "Could not reach server.");
      } finally {
        this.saving = false;
      }
    },

    async reset() {
      if (!confirm("Delete all posts and LinkedIn session? This cannot be undone.")) return;
      this.resetting = true;
      try {
        const res = await fetch("/api/reset", { method: "DELETE" });
        if (res.ok) {
          window.location.href = "/landing.html";
        } else {
          const body = await res.json().catch(() => ({}));
          this.showAlert("error", body.detail || "Reset failed.");
        }
      } catch {
        this.showAlert("error", "Could not reach server.");
      } finally {
        this.resetting = false;
      }
    },

    showAlert(type, message) {
      this.alert = { type, message };
      setTimeout(() => { this.alert = null; }, 5000);
    },
  };
}

// ── postDetail component ────────────────────────────────────────────────────

function postDetail() {
  return {
    post: null,
    loading: true,
    error: "",

    async init() {
      const params = new URLSearchParams(window.location.search);
      const url = params.get("url");
      if (!url) { this.error = "No post URL specified."; this.loading = false; return; }
      try {
        const res = await fetch("/api/posts/" + encodeURIComponent(url));
        if (res.status === 404) { this.error = "Post not found."; return; }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        this.post = await res.json();
      } catch (e) {
        this.error = "Could not load post: " + e.message;
      } finally {
        this.loading = false;
      }
    },

    get hasFeedback() {
      return this.post?.ai_feedback && this.post.ai_feedback.overall_assessment;
    },

    fmt,
    fmtDate,
  };
}
