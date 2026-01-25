const config = window.PA_CONFIG || { base_path: "" };
const basePath = config.base_path || "";

const tagsInput = document.getElementById("tags-input");
const queryInput = document.getElementById("query-input");
const modeSelect = document.getElementById("mode-select");
const limitInput = document.getElementById("limit-input");
const searchBtn = document.getElementById("search-btn");
const refreshTagsBtn = document.getElementById("refresh-tags");
const tagsList = document.getElementById("tags-list");
const resultsGrid = document.getElementById("results-grid");
const resultMeta = document.getElementById("result-meta");

function normalizeTagDisplay(tag) {
  if (!tag) return "";
  let clean = String(tag).trim();
  clean = clean.replace(/^L\\d+-/i, "");
  if (/^[IC]\\d+$/i.test(clean)) {
    return "";
  }
  return clean;
}

if (config.default_match_mode) {
  modeSelect.value = config.default_match_mode;
}
if (config.default_limit) {
  limitInput.value = config.default_limit;
}

function buildUrl(path, params = {}) {
  const url = new URL(`${basePath}${path}`, window.location.origin);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== "") {
      url.searchParams.set(key, value);
    }
  });
  return url.toString();
}

async function fetchTags() {
  tagsList.innerHTML = "<span class=\"meta\">Loading tags...</span>";
  try {
    const res = await fetch(buildUrl("/api/tags"));
    const payload = await res.json();
    if (!payload.ok) throw new Error("Failed to load tags");

    tagsList.innerHTML = "";
    payload.data.slice(0, 30).forEach((item) => {
      const displayTag = normalizeTagDisplay(item.tag);
      if (!displayTag) return;
      const chip = document.createElement("button");
      chip.className = "tag-chip";
      chip.textContent = `${displayTag} (${item.count})`;
      chip.addEventListener("click", () => {
        const existing = tagsInput.value.trim();
        tagsInput.value = existing ? `${existing}, ${displayTag}` : displayTag;
        search();
      });
      tagsList.appendChild(chip);
    });
  } catch (error) {
    tagsList.innerHTML = "<span class=\"meta\">Tag list unavailable.</span>";
  }
}

function renderResults(items) {
  resultsGrid.innerHTML = "";
  if (!items.length) {
    resultsGrid.innerHTML = "<div class=\"meta\">No results. Try different tags.</div>";
    return;
  }

  items.forEach((item) => {
    const card = document.createElement("article");
    card.className = "result-card";

    const title = document.createElement("h3");
    title.textContent = `${item.id || ""} ${item.title || ""}`.trim();

    const link = document.createElement("a");
    link.href = item.url || "#";
    link.textContent = item.url ? "Open problem" : "No link";
    link.target = "_blank";

    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = `${item.source || "unknown"} · difficulty ${item.difficulty || "?"}`;

    const tagsWrap = document.createElement("div");
    tagsWrap.className = "result-tags";
    (item.tags || []).forEach((tag) => {
      const displayTag = normalizeTagDisplay(tag);
      if (!displayTag) return;
      const tagEl = document.createElement("span");
      tagEl.className = "result-tag";
      tagEl.textContent = displayTag;
      tagsWrap.appendChild(tagEl);
    });

    card.appendChild(title);
    card.appendChild(link);
    card.appendChild(meta);
    card.appendChild(tagsWrap);
    resultsGrid.appendChild(card);
  });
}

async function search() {
  resultMeta.textContent = "Searching...";
  const params = {
    tags: tagsInput.value.trim(),
    q: queryInput.value.trim(),
    mode: modeSelect.value,
    limit: limitInput.value,
    sort: "id",
  };

  try {
    const res = await fetch(buildUrl("/api/search", params));
    const payload = await res.json();
    if (!payload.ok) throw new Error("Search failed");

    renderResults(payload.data || []);
    resultMeta.textContent = `Found ${payload.count} result(s). Showing ${payload.data.length}.`;
  } catch (error) {
    resultMeta.textContent = "Search failed. Check the server log.";
    resultsGrid.innerHTML = "";
  }
}

searchBtn.addEventListener("click", search);
refreshTagsBtn.addEventListener("click", fetchTags);

[tagsInput, queryInput].forEach((input) => {
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      search();
    }
  });
});

fetchTags();
search();
