"use strict";

const $ = (id) => document.getElementById(id);
const state = {
  csrf: "",
  documents: [],
  stats: {},
  query: "rollback",
  filter: "",
  searchSequence: 0,
  source: null,
  sourceStart: 1,
  sourceEnd: 1,
  pageStart: 1,
};
let toastTimer;
let confirmationAction;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.classList.add("icon");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", "#i-" + name);
  svg.append(use);
  return svg;
}

function actionButton(text, className, action, iconName) {
  const button = element("button", className);
  button.type = "button";
  if (iconName) button.append(icon(iconName));
  button.append(document.createTextNode(text));
  button.addEventListener("click", action);
  return button;
}

function formatBytes(bytes) {
  return bytes < 1024 ? `${bytes} bytes` : `${(bytes / 1024).toFixed(1)} KiB`;
}

function toast(message) {
  clearTimeout(toastTimer);
  $("toast").textContent = message;
  $("toast").hidden = false;
  toastTimer = setTimeout(() => {
    $("toast").hidden = true;
  }, 5000);
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.method && options.method !== "GET") {
    headers.set("Content-Type", "application/json");
    headers.set("X-CSRF-Token", state.csrf);
  }
  const response = await fetch(path, {
    ...options,
    headers,
    credentials: "same-origin",
    cache: "no-store",
  });
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error(
      "The workbench could not read the response. Please try again.",
    );
  }
  if (!response.ok)
    throw new Error(data.error || "This request could not be completed.");
  return data;
}

function view(name) {
  $("search-view").hidden = name !== "search";
  $("sources-view").hidden = name !== "sources";
  for (const item of ["search", "sources"]) {
    $("nav-" + item).classList.toggle("active", item === name);
    if (item === name) $("nav-" + item).setAttribute("aria-current", "page");
    else $("nav-" + item).removeAttribute("aria-current");
  }
  $("breadcrumb-view").textContent =
    name === "search" ? "Evidence search" : "All sources";
  if (name === "search") $("search-input").focus({ preventScroll: true });
}

function updateCollection(data) {
  if (data.documents) state.documents = data.documents;
  if (data.stats) state.stats = data.stats;
  $("nav-count").textContent = state.stats.documents ?? "0";
  $("source-count").textContent = state.stats.documents ?? "0";
  $("stat-sources").textContent = state.stats.documents ?? "0";
  $("stat-passages").textContent = state.stats.passages ?? "0";
  $("library-summary").textContent =
    `${state.stats.documents} sources · ${state.stats.passages} indexed passages · ${formatBytes(state.stats.bytes || 0)} of 2 MiB`;
  const sidebar = document.createDocumentFragment();
  const library = document.createDocumentFragment();
  const filter = document.createDocumentFragment();
  const all = element("option", "", "All sources");
  all.value = "";
  filter.append(all);
  for (const doc of state.documents) {
    const button = element("button", "sidebar-source");
    button.type = "button";
    button.append(icon("file"));
    const labels = element("span", "sidebar-source-text");
    labels.append(element("strong", "", doc.title));
    labels.append(
      element(
        "small",
        "",
        `${doc.passages} passages${doc.sample ? " · Sample source" : " · Uploaded source"}`,
      ),
    );
    button.append(labels);
    button.title = `Open ${doc.filename}`;
    button.addEventListener("click", () => openSource(doc.id));
    sidebar.append(button);

    const row = element("article", "library-row");
    const file = element("span", "library-file-icon");
    file.append(icon("file"));
    const source = element("button", "library-row-main");
    source.append(element("strong", "", doc.title));
    source.append(
      element(
        "small",
        "",
        `${doc.filename} · ${doc.passages} passages · ${formatBytes(doc.bytes)}`,
      ),
    );
    source.addEventListener("click", () => openSource(doc.id));
    const remove = actionButton(
      "",
      "icon-button",
      () => confirmDelete(doc),
      "trash",
    );
    remove.setAttribute("aria-label", "Delete " + doc.filename);
    row.append(file, source);
    if (doc.sample) row.append(element("span", "sample-pill", "SAMPLE"));
    row.append(remove);
    library.append(row);

    const option = element("option", "", doc.title);
    option.value = doc.id;
    filter.append(option);
  }
  if (!state.documents.length) {
    sidebar.append(
      element(
        "p",
        "sidebar-loading muted",
        "No sources yet. Add your first document.",
      ),
    );
    const empty = element("div", "empty-state");
    empty.append(
      element("h3", "", "Your collection is empty."),
      element(
        "p",
        "",
        "Upload a text or Markdown source to start finding evidence.",
      ),
    );
    empty.append(actionButton("Add a source", "secondary", openUpload, "plus"));
    library.append(empty);
  }
  $("sidebar-sources").replaceChildren(sidebar);
  $("library-list").replaceChildren(library);
  $("source-filter").replaceChildren(filter);
  if (!state.documents.some((doc) => doc.id === state.filter))
    state.filter = "";
  $("source-filter").value = state.filter;
}

async function refreshCollection() {
  updateCollection(await api("/api/documents"));
}

function renderEmpty(title, description, error = false) {
  const empty = element("div", "empty-state");
  const mark = element("span", "empty-icon");
  mark.append(icon(error ? "info" : "search"));
  empty.append(mark, element("h3", "", title), element("p", "", description));
  empty.append(
    actionButton(
      error ? "Try again" : "Add a relevant source",
      "secondary",
      error ? () => runSearch() : openUpload,
      error ? "reset" : "plus",
    ),
  );
  $("results").replaceChildren(empty);
}

function renderResults(data) {
  $("results-heading").textContent =
    data.status === "matched" ? "Retrieved evidence" : "No matching evidence";
  $("results-summary").textContent =
    `${data.matchCount} ${data.matchCount === 1 ? "passage" : "passages"} · ${data.documentCount} ${data.documentCount === 1 ? "source" : "sources"} · ${data.elapsedMs} ms`;
  if (!data.evidence.length) {
    renderEmpty(
      "No supporting passage found.",
      "No passage contains all of these search terms. Try fewer words or add a relevant source. BriefLedger does not generate an answer when evidence is missing.",
    );
    return;
  }
  const cards = document.createDocumentFragment();
  for (const hit of data.evidence) {
    const card = element("article", "evidence-card");
    const heading = element("div", "evidence-head");
    heading.append(
      element("span", "rank-number", String(hit.rank).padStart(2, "0")),
    );
    const source = element("div", "evidence-source");
    source.append(
      element(
        "h3",
        "",
        hit.heading === "Document text" ? hit.title : hit.heading,
      ),
    );
    const meta = element("div", "evidence-source-meta");
    meta.append(
      icon("file"),
      element("span", "filename", hit.filename),
      element("span", "", "·"),
      element("span", "", "Source passage"),
    );
    source.append(meta);
    heading.append(source, element("span", "match-label", "LEXICAL MATCH"));
    const excerpt = element("p", "excerpt");
    for (const segment of hit.segments)
      excerpt.append(
        element(segment.match ? "mark" : "span", "", segment.text),
      );
    const footer = element("div", "evidence-footer");
    const location = element("span", "evidence-location");
    location.append(
      icon("lines"),
      document.createTextNode(`Lines ${hit.lineStart}–${hit.lineEnd}`),
    );
    const open = actionButton("View source", "text-button", () =>
      openSource(hit.documentId, hit.lineStart, hit.lineEnd),
    );
    open.append(icon("external"));
    footer.append(location, open);
    card.append(heading, excerpt, footer);
    cards.append(card);
  }
  if (data.truncated)
    cards.append(
      element(
        "p",
        "library-hint",
        "Showing the top 24 matching passages. Narrow your search to see a smaller result set.",
      ),
    );
  $("results").replaceChildren(cards);
}

async function runSearch() {
  const query = $("search-input").value.trim();
  if (!query || !state.csrf) return;
  const sequence = ++state.searchSequence;
  state.query = query;
  $("search-button").disabled = true;
  $("results").setAttribute("aria-busy", "true");
  $("results-summary").textContent = "Searching source text…";
  try {
    const params = new URLSearchParams({ q: query });
    if (state.filter) params.set("documentId", state.filter);
    const data = await api("/api/search?" + params);
    if (sequence === state.searchSequence) renderResults(data);
  } catch (error) {
    if (sequence === state.searchSequence) {
      $("results-summary").textContent = "Search could not finish";
      renderEmpty("Let’s check that search.", error.message, true);
    }
  } finally {
    if (sequence === state.searchSequence) {
      $("search-button").disabled = false;
      $("results").setAttribute("aria-busy", "false");
    }
  }
}

async function openSource(id, lineStart = 1, lineEnd = 0) {
  try {
    state.source = await api("/api/documents/" + encodeURIComponent(id));
    state.sourceStart = lineStart;
    state.sourceEnd = lineEnd;
    state.pageStart = Math.max(1, lineStart - 8);
    $("source-title").textContent = state.source.title;
    $("source-filename").textContent =
      `${state.source.filename}${state.source.sample ? " · Synthetic sample document" : " · Uploaded document"}`;
    $("source-line-label").textContent = lineEnd
      ? `Evidence location · lines ${lineStart}–${lineEnd}`
      : "Original text · line-numbered";
    renderSourceLines();
    if (!$("source-dialog").open) $("source-dialog").showModal();
  } catch (error) {
    toast(error.message);
  }
}

function renderSourceLines() {
  if (!state.source) return;
  const total = state.source.lines.length;
  const end = Math.min(total, state.pageStart + 219);
  const content = document.createDocumentFragment();
  for (let number = state.pageStart; number <= end; number++) {
    const line = element("div", "source-line");
    if (number >= state.sourceStart && number <= state.sourceEnd)
      line.classList.add("highlighted");
    line.append(
      element("span", "source-line-number", number),
      element("span", "source-line-text", state.source.lines[number - 1]),
    );
    content.append(line);
  }
  $("source-lines").replaceChildren(content);
  $("source-lines").scrollTop = 0;
  $("source-previous").disabled = state.pageStart <= 1;
  $("source-next").disabled = end >= total;
  $("source-page-label").textContent =
    `Lines ${state.pageStart}–${end} of ${total}`;
}

function confirmAction(title, description, label, callback) {
  $("confirm-title").textContent = title;
  $("confirm-description").textContent = description;
  $("confirm-submit").textContent = label;
  $("confirm-error").hidden = true;
  confirmationAction = callback;
  $("confirm-dialog").showModal();
}

function confirmDelete(doc) {
  confirmAction(
    "Delete this source?",
    `“${doc.filename}” and its indexed passages will be removed from this browser collection. This cannot be undone.`,
    "Delete source",
    async () => {
      await api("/api/documents/" + encodeURIComponent(doc.id), {
        method: "DELETE",
      });
      if (state.source?.id === doc.id && $("source-dialog").open)
        $("source-dialog").close();
      await refreshCollection();
      await runSearch();
      toast("Source and indexed passages deleted.");
    },
  );
}

function openUpload() {
  if (!state.csrf) return;
  $("upload-error").hidden = true;
  if (!$("upload-dialog").open) $("upload-dialog").showModal();
}

async function loadFile(file) {
  if (!file) return;
  try {
    if (!/\.(txt|md)$/i.test(file.name))
      throw new Error("Choose a .txt or .md file.");
    if (file.size > 131072)
      throw new Error("Each source must be at most 128 KiB.");
    let content;
    try {
      content = new TextDecoder("utf-8", { fatal: true }).decode(
        await file.arrayBuffer(),
      );
    } catch {
      throw new Error("This file is not valid UTF-8 text.");
    }
    $("filename").value = file.name;
    $("source-content").value = content;
    $("upload-size").textContent = formatBytes(
      new TextEncoder().encode(content).length,
    );
    $("upload-error").hidden = true;
    $("source-content").focus();
  } catch (error) {
    $("upload-error").textContent = error.message;
    $("upload-error").hidden = false;
  }
}

$("nav-search").addEventListener("click", () => view("search"));
$("nav-sources").addEventListener("click", () => view("sources"));
for (const id of ["sidebar-add", "library-add", "main-add"])
  $(id)?.addEventListener("click", openUpload);
for (const id of ["about-button", "method-link"])
  $(id).addEventListener("click", () => $("about-dialog").showModal());
for (const button of document.querySelectorAll("[data-close]"))
  button.addEventListener("click", () => $(button.dataset.close).close());
for (const dialog of document.querySelectorAll("dialog"))
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) {
      const rect = dialog.getBoundingClientRect();
      if (
        event.clientX < rect.left ||
        event.clientX > rect.right ||
        event.clientY < rect.top ||
        event.clientY > rect.bottom
      )
        dialog.close();
    }
  });
$("search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  runSearch();
});
$("source-filter").addEventListener("change", (event) => {
  state.filter = event.target.value;
  runSearch();
});
for (const button of document.querySelectorAll("[data-query]"))
  button.addEventListener("click", () => {
    $("search-input").value = button.dataset.query;
    state.filter = "";
    $("source-filter").value = "";
    view("search");
    runSearch();
  });
document.addEventListener("keydown", (event) => {
  if (
    event.key === "/" &&
    !document.querySelector("dialog[open]") &&
    !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)
  ) {
    event.preventDefault();
    view("search");
    $("search-input").focus();
  }
});
$("source-previous").addEventListener("click", () => {
  state.pageStart = Math.max(1, state.pageStart - 200);
  renderSourceLines();
});
$("source-next").addEventListener("click", () => {
  state.pageStart = Math.min(state.source.lines.length, state.pageStart + 200);
  renderSourceLines();
});
$("source-delete").addEventListener("click", () => {
  if (state.source) confirmDelete(state.source);
});
const resetCollection = () =>
  confirmAction(
    "Reset your collection?",
    "This replaces every source in this browser collection, including uploads, with the four synthetic sample documents. Other visitors’ collections are not affected.",
    "Reset collection",
    async () => {
      updateCollection(
        await api("/api/reset", {
          method: "POST",
          body: JSON.stringify({ confirm: true }),
        }),
      );
      if ($("source-dialog").open) $("source-dialog").close();
      state.filter = "";
      $("source-filter").value = "";
      $("search-input").value = "rollback";
      await runSearch();
      toast("Your sample collection has been restored.");
    },
  );
for (const id of ["reset-button", "library-reset"])
  $(id).addEventListener("click", resetCollection);
$("confirm-submit").addEventListener("click", async () => {
  if (!confirmationAction) return;
  $("confirm-submit").disabled = true;
  try {
    await confirmationAction();
    $("confirm-dialog").close();
  } catch (error) {
    $("confirm-error").textContent = error.message;
    $("confirm-error").hidden = false;
  } finally {
    $("confirm-submit").disabled = false;
  }
});
$("choose-file").addEventListener("click", () => $("file-input").click());
$("file-input").addEventListener("change", (event) =>
  loadFile(event.target.files[0]),
);
$("choose-file").addEventListener("dragover", (event) => {
  event.preventDefault();
  $("choose-file").classList.add("dragover");
});
$("choose-file").addEventListener("dragleave", () =>
  $("choose-file").classList.remove("dragover"),
);
$("choose-file").addEventListener("drop", (event) => {
  event.preventDefault();
  $("choose-file").classList.remove("dragover");
  loadFile(event.dataTransfer.files[0]);
});
$("source-content").addEventListener("input", () => {
  $("upload-size").textContent = formatBytes(
    new TextEncoder().encode($("source-content").value).length,
  );
});
$("upload-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("upload-submit").disabled = true;
  $("upload-error").hidden = true;
  try {
    const result = await api("/api/documents", {
      method: "POST",
      body: JSON.stringify({
        filename: $("filename").value.trim(),
        content: $("source-content").value,
      }),
    });
    await refreshCollection();
    $("upload-dialog").close();
    $("upload-form").reset();
    $("upload-size").textContent = "0 bytes";
    await runSearch();
    toast(`${result.document.filename} added and indexed.`);
  } catch (error) {
    $("upload-error").textContent = error.message;
    $("upload-error").hidden = false;
  } finally {
    $("upload-submit").disabled = false;
  }
});

async function start() {
  try {
    const data = await api("/api/session");
    state.csrf = data.csrfToken;
    updateCollection(data);
    if (data.storage === "ephemeral") {
      $("hosting-notice").hidden = false;
      $("hosting-notice-text").textContent = data.storageNotice;
      $("privacy-detail").textContent = "Demo storage · may reset on restart";
      $("about-storage").textContent =
        data.storageNotice +
        " Collections can disappear before their seven-day expiry.";
    }
    for (const id of [
      "sidebar-add",
      "reset-button",
      "library-reset",
      "search-button",
      "main-add",
    ])
      if ($(id)) $(id).disabled = false;
    $("search-input").value = state.query;
    await runSearch();
  } catch (error) {
    $("results").setAttribute("aria-busy", "false");
    $("results-summary").textContent = "Collection unavailable";
    renderEmpty("The collection could not open.", error.message, true);
    const retry = $("results").querySelector("button");
    if (retry)
      retry.replaceWith(
        actionButton(
          "Reconnect",
          "secondary",
          () => location.reload(),
          "reset",
        ),
      );
  }
}
start();
