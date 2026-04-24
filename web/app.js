const PERSON_TARGET = "person";
const GENERAL_TARGET = "general";

const SEARCH_CONFIG = {
  [PERSON_TARGET]: {
    viewId: "personSearchView",
    textQueryId: "personTextQuery",
    textTopKId: "personTextTopK",
    textGroupId: "personTextGroupByPerson",
    imageInputId: "personQueryImage",
    imageNameId: "personQueryImageName",
    imageTopKId: "personImageTopK",
    imageGroupId: "personImageGroupByPerson",
    resultsGridId: "personResultsGrid",
    metaId: "personSearchMeta",
    clearId: "clearPersonResults",
    backendStatusId: "personBackendStatus",
    emptyMessage: "Waiting for a person retrieval task.",
  },
  [GENERAL_TARGET]: {
    viewId: "generalSearchView",
    textQueryId: "generalTextQuery",
    textTopKId: "generalTextTopK",
    imageInputId: "generalQueryImage",
    imageNameId: "generalQueryImageName",
    imageTopKId: "generalImageTopK",
    resultsGridId: "generalResultsGrid",
    metaId: "generalSearchMeta",
    clearId: "clearGeneralResults",
    backendStatusId: "generalBackendStatus",
    emptyMessage: "Waiting for a general retrieval task.",
  },
};

const state = {
  user: null,
  currentView: SEARCH_CONFIG[PERSON_TARGET].viewId,
  galleryPage: 1,
  searchTargetType: PERSON_TARGET,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.add("show");
  window.clearTimeout(el._timer);
  el._timer = window.setTimeout(() => el.classList.remove("show"), 3200);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function targetTypeForView(viewId) {
  if (viewId === SEARCH_CONFIG[GENERAL_TARGET].viewId) {
    return GENERAL_TARGET;
  }
  return PERSON_TARGET;
}

function viewIdForTarget(targetType) {
  return SEARCH_CONFIG[targetType]?.viewId || SEARCH_CONFIG[PERSON_TARGET].viewId;
}

function currentSearchTarget() {
  return state.searchTargetType || PERSON_TARGET;
}

function resultElements(targetType) {
  const config = SEARCH_CONFIG[targetType] || SEARCH_CONFIG[PERSON_TARGET];
  return {
    grid: $(`#${config.resultsGridId}`),
    meta: $(`#${config.metaId}`),
  };
}

function clearResults(targetType) {
  const config = SEARCH_CONFIG[targetType] || SEARCH_CONFIG[PERSON_TARGET];
  $(`#${config.resultsGridId}`).innerHTML = "";
  $(`#${config.metaId}`).textContent = config.emptyMessage;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "include",
    headers: {
      ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(options.headers || {}),
    },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `Request failed: ${response.status}`);
  }
  return data;
}

function setAuthVisible(authed) {
  $("#authScreen").classList.toggle("hidden", authed);
  $("#mainApp").classList.toggle("hidden", !authed);
}

function updateUser() {
  $("#userEmail").textContent = state.user ? `${state.user.email} | ${state.user.role}` : "-";
  $("#adminNav").classList.toggle("hidden", state.user?.role !== "admin");
}

function formatBackendStatus(label, data, targetType) {
  const actual = data[`${targetType}_backend`];
  const requested = data[`${targetType}_backend_requested`];
  const fallback = data[`${targetType}_backend_fallback`];
  const semantic = data[`${targetType}_semantic_text`];
  if (fallback) {
    return `${label}: ${actual} fallback (requested ${requested}, semantic=${semantic ? "yes" : "no"})`;
  }
  return `${label}: ${actual} (semantic=${semantic ? "yes" : "no"})`;
}

async function refreshHealth() {
  const data = await api("/api/health");
  const personSummary = formatBackendStatus("person", data, PERSON_TARGET);
  const generalSummary = formatBackendStatus("general", data, GENERAL_TARGET);
  $("#healthBadge").textContent = `${personSummary} | ${generalSummary} | ${data.image_count} images`;
  $(`#${SEARCH_CONFIG[PERSON_TARGET].backendStatusId}`).textContent = personSummary;
  $(`#${SEARCH_CONFIG[GENERAL_TARGET].backendStatusId}`).textContent = generalSummary;
}

function showView(viewId) {
  state.currentView = viewId;
  if (viewId === SEARCH_CONFIG[PERSON_TARGET].viewId || viewId === SEARCH_CONFIG[GENERAL_TARGET].viewId) {
    state.searchTargetType = targetTypeForView(viewId);
  }

  $$(".view").forEach((view) => view.classList.toggle("active-view", view.id === viewId));
  $$(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.view === viewId));

  const titles = {
    personSearchView: ["Person Search", "Pedestrian Retrieval Workbench"],
    generalSearchView: ["General Search", "General Retrieval Workbench"],
    galleryView: ["Gallery", "Gallery"],
    uploadView: ["Upload", "Upload and Index"],
    historyView: ["History", "Search History"],
    adminView: ["Admin", "System Admin"],
    videoView: ["Video", "Video Queue"],
  };
  const [eyebrow, title] = titles[viewId] || titles.personSearchView;
  $("#viewEyebrow").textContent = eyebrow;
  $("#viewTitle").textContent = title;

  if (viewId === "galleryView") {
    loadGallery().catch((err) => toast(err.message));
  }
  if (viewId === "historyView") {
    loadHistory().catch((err) => toast(err.message));
  }
  if (viewId === "adminView") {
    loadInvites().catch((err) => toast(err.message));
  }
  if (viewId === "videoView") {
    loadVideos().catch((err) => toast(err.message));
  }
}

function imageCard(image, options = {}) {
  const score = image.similarity_pct;
  const searchTargetType = options.targetType || currentSearchTarget();
  const chips = [
    image.dataset ? `<span class="chip">${escapeHtml(image.dataset)}</span>` : "",
    image.person_key ? `<span class="chip">ID ${escapeHtml(image.person_key)}</span>` : "",
    score != null ? `<span class="chip">${score}%</span>` : "",
  ].join("");
  const searchButton = options.searchButton
    ? `<button class="secondary-button image-id-search" data-image-id="${image.id}" data-target-type="${searchTargetType}" type="button">Search by Image</button>`
    : "";
  const deleteButton = options.deleteButton && image.can_delete
    ? `<button class="ghost-button image-delete" data-image-id="${image.id}" type="button">Delete</button>`
    : "";
  const actions = [searchButton, deleteButton].filter(Boolean).join("");

  return `
    <article class="image-card">
      <img src="${image.thumbnail_url || image.url}" alt="${escapeHtml(image.original_filename)}" loading="lazy" />
      <div class="image-info">
        <strong title="${escapeHtml(image.original_filename)}">${escapeHtml(image.original_filename)}</strong>
        <div class="meta-line">${chips}</div>
        ${score != null ? `<div class="score-bar"><span style="width:${score}%"></span></div>` : ""}
        ${actions ? `<div class="card-actions">${actions}</div>` : ""}
      </div>
    </article>
  `;
}

function renderResults(data, targetType) {
  const resolvedTargetType = targetType || data.target_type || currentSearchTarget();
  const { grid, meta } = resultElements(resolvedTargetType);
  const metaParts = [
    `${data.latency_ms} ms`,
    `backend: ${data.backend}`,
    `target: ${resolvedTargetType}`,
    data.grouped_by_person ? "grouped by person" : "top similar images",
    data.matched_person_key ? `matched person: ${data.matched_person_key}` : "",
    data.translated_query && data.translated_query !== data.query ? `query: ${data.translated_query}` : "",
  ].filter(Boolean);

  meta.textContent = `${metaParts.join(" | ")} | ${data.results.length} results`;
  grid.innerHTML = data.results.length
    ? data.results
      .map((item) => imageCard(item, { searchButton: true, deleteButton: true, targetType: resolvedTargetType }))
      .join("")
    : `<p class="muted">No results yet. Upload images first and then retry.</p>`;
}

async function runTextSearch(targetType) {
  const config = SEARCH_CONFIG[targetType];
  const text = $(`#${config.textQueryId}`).value.trim();
  if (!text) {
    toast("Please enter a text query.");
    return;
  }
  const payload = {
    text,
    top_k: Number($(`#${config.textTopKId}`).value || 24),
    group_by_person: targetType === PERSON_TARGET
      ? $(`#${config.textGroupId}`).checked
      : false,
    target_type: targetType,
  };
  const data = await api("/api/search/text", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  renderResults(data, targetType);
  await refreshHealth();
}

async function runAttributeSearch() {
  const attributes = {
    gender: $("#personAttrGender").value,
    top_color: $("#personAttrTopColor").value,
    top_type: $("#personAttrTopType").value,
    bottom_color: $("#personAttrBottomColor").value,
    bottom_type: $("#personAttrBottomType").value,
    accessory: $("#personAttrAccessory").value,
    extra: $("#personAttrExtra").value,
  };
  const data = await api("/api/search/attributes", {
    method: "POST",
    body: JSON.stringify({
      attributes,
      top_k: Number($("#personTextTopK").value || 24),
      group_by_person: $("#personTextGroupByPerson").checked,
      target_type: PERSON_TARGET,
    }),
  });
  renderResults(data, PERSON_TARGET);
}

async function runImageSearch(targetType) {
  const config = SEARCH_CONFIG[targetType];
  const file = $(`#${config.imageInputId}`).files[0];
  if (!file) {
    toast("Please select a query image.");
    return;
  }
  const form = new FormData();
  form.append("file", file);
  form.append("top_k", $(`#${config.imageTopKId}`).value || "24");
  form.append(
    "group_by_person",
    targetType === PERSON_TARGET && $(`#${config.imageGroupId}`).checked ? "true" : "false",
  );
  form.append("target_type", targetType);
  const data = await api("/api/search/image", { method: "POST", body: form });
  renderResults(data, targetType);
}

async function runImageIdSearch(imageId, targetType) {
  const resolvedTargetType = targetType || currentSearchTarget();
  const config = SEARCH_CONFIG[resolvedTargetType];
  const data = await api("/api/search/image-id", {
    method: "POST",
    body: JSON.stringify({
      image_id: Number(imageId),
      top_k: Number($(`#${config.imageTopKId}`).value || 24),
      group_by_person: resolvedTargetType === PERSON_TARGET
        ? $(`#${config.imageGroupId}`).checked
        : false,
      target_type: resolvedTargetType,
    }),
  });
  renderResults(data, resolvedTargetType);
  showView(viewIdForTarget(resolvedTargetType));
}

async function checkSession() {
  try {
    const data = await api("/api/auth/me");
    state.user = data.user;
    setAuthVisible(true);
    updateUser();
    await refreshHealth();
    showView(state.currentView);
  } catch {
    setAuthVisible(false);
  }
}

async function loadGallery() {
  const params = new URLSearchParams({
    q: $("#gallerySearch").value.trim(),
    dataset: $("#datasetFilter").value,
    page: String(state.galleryPage),
    page_size: "72",
  });
  const data = await api(`/api/images?${params}`);
  $("#galleryCount").textContent = `${data.total} images | ${data.visibility_scope === "all" ? "all uploads" : "my uploads only"}`;
  $("#galleryGrid").innerHTML = data.images.length
    ? data.images
      .map((item) => imageCard(item, { searchButton: true, deleteButton: true, targetType: currentSearchTarget() }))
      .join("")
    : `<p class="muted">No visible images in the gallery yet.</p>`;

  const currentDataset = $("#datasetFilter").value;
  $("#datasetFilter").innerHTML = `<option value="">all datasets</option>` + data.datasets
    .map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`)
    .join("");
  $("#datasetFilter").value = currentDataset;
}

async function uploadImages() {
  const folderFiles = Array.from($("#uploadFiles").files);
  const flatFiles = Array.from($("#uploadFlatFiles").files);
  const files = [...folderFiles, ...flatFiles];
  if (!files.length) {
    toast("Please choose images to upload.");
    return;
  }
  const form = new FormData();
  files.forEach((file) => form.append("files", file, file.webkitRelativePath || file.name));
  form.append("dataset", $("#uploadDataset").value || "demo");
  form.append("person_key", $("#uploadPersonKey").value || "");
  form.append("tags", $("#uploadTags").value || "");
  form.append("infer_person", $("#uploadInferPerson").checked ? "true" : "false");

  $("#uploadButton").disabled = true;
  $("#uploadButton").textContent = "Uploading...";
  try {
    const data = await api("/api/images/upload", { method: "POST", body: form });
    $("#uploadReport").innerHTML = `
      <div class="history-item">
        <strong>Uploaded ${data.count} images</strong>
        ${data.errors.length ? `<p class="muted">Partial failures: ${data.errors.map(escapeHtml).join(" ; ")}</p>` : ""}
      </div>
    `;
    await refreshHealth();
    if (state.currentView === "galleryView") {
      await loadGallery();
    }
    toast("Upload complete.");
  } finally {
    $("#uploadButton").disabled = false;
    $("#uploadButton").textContent = "Upload and Index";
  }
}

async function deleteImage(imageId) {
  const confirmed = window.confirm("Delete this image from the gallery?");
  if (!confirmed) {
    return;
  }
  await api(`/api/images/${imageId}`, { method: "DELETE" });
  await refreshHealth();
  if (state.currentView === "galleryView") {
    await loadGallery();
  }
  if (state.currentView === SEARCH_CONFIG[PERSON_TARGET].viewId) {
    clearResults(PERSON_TARGET);
  }
  if (state.currentView === SEARCH_CONFIG[GENERAL_TARGET].viewId) {
    clearResults(GENERAL_TARGET);
  }
  toast("Image deleted.");
}

async function loadHistory() {
  const data = await api("/api/search/history");
  $("#historyList").innerHTML = data.history.length
    ? data.history.map((item) => `
      <article class="history-item">
        <header>
          <strong>${escapeHtml(item.mode)} | ${escapeHtml(item.query_text || "")}</strong>
          <span class="muted">${item.latency_ms} ms | ${escapeHtml(item.backend)}</span>
        </header>
        ${item.translated_text ? `<p class="muted">${escapeHtml(item.translated_text)}</p>` : ""}
        <div class="history-strip">
          ${(item.results || []).map((result) => `<img src="${result.thumbnail_url}" alt="result ${result.id}" />`).join("")}
        </div>
      </article>
    `).join("")
    : `<p class="muted">No search history yet.</p>`;
}

async function loadInvites() {
  const data = await api("/api/admin/invites");
  $("#inviteList").innerHTML = data.invites.length
    ? data.invites.map((invite) => `
      <article class="history-item">
        <header>
          <strong>${escapeHtml(invite.code)}</strong>
          <span class="muted">${invite.used_count}/${invite.max_uses}</span>
        </header>
        <p class="muted">${escapeHtml(invite.label || "no label")} ${invite.expires_at ? `| expires ${escapeHtml(invite.expires_at)}` : ""}</p>
      </article>
    `).join("")
    : `<p class="muted">No invite codes yet.</p>`;
}

async function createInvite() {
  const expires = $("#inviteDays").value.trim();
  await api("/api/admin/invites", {
    method: "POST",
    body: JSON.stringify({
      label: $("#inviteLabel").value,
      max_uses: Number($("#inviteUses").value || 1),
      expires_days: expires ? Number(expires) : null,
    }),
  });
  toast("Invite created.");
  await loadInvites();
}

async function reindex() {
  $("#reindexButton").disabled = true;
  $("#reindexReport").textContent = "Rebuilding embeddings...";
  try {
    const data = await api("/api/admin/reindex", { method: "POST", body: JSON.stringify({}) });
    $("#reindexReport").textContent = `${data.backend} | ${data.count} images | ${data.latency_ms} ms`;
    await refreshHealth();
  } finally {
    $("#reindexButton").disabled = false;
  }
}

async function uploadVideo() {
  const file = $("#videoFile").files[0];
  if (!file) {
    toast("Please select a video file.");
    return;
  }
  const form = new FormData();
  form.append("file", file);
  form.append("dataset", $("#videoDataset").value || "video-demo");
  await api("/api/videos/upload", { method: "POST", body: form });
  toast("Video queued.");
  await loadVideos();
}

async function loadVideos() {
  const data = await api("/api/videos");
  $("#videoList").innerHTML = data.videos.length
    ? data.videos.map((video) => `
      <article class="history-item">
        <header>
          <strong>${escapeHtml(video.original_filename)}</strong>
          <span class="muted">${escapeHtml(video.status)}</span>
        </header>
        <p class="muted">${escapeHtml(video.message || "")}</p>
      </article>
    `).join("")
    : `<p class="muted">No queued videos yet.</p>`;
}

function bindFileLabel(inputId, labelId, fallbackText) {
  $(`#${inputId}`).addEventListener("change", (event) => {
    $(`#${labelId}`).textContent = event.target.files[0]?.name || fallbackText;
  });
}

function bindEvents() {
  $$(".tab-button").forEach((button) => {
    button.addEventListener("click", () => {
      const isLogin = button.dataset.authTab === "login";
      $$(".tab-button").forEach((item) => item.classList.toggle("active", item === button));
      $("#loginForm").classList.toggle("hidden", !isLogin);
      $("#registerForm").classList.toggle("hidden", isLogin);
    });
  });

  $("#loginForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const data = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify(Object.fromEntries(form)),
    });
    state.user = data.user;
    setAuthVisible(true);
    updateUser();
    showView(SEARCH_CONFIG[PERSON_TARGET].viewId);
    await refreshHealth();
  });

  $("#registerForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const data = await api("/api/auth/register", {
      method: "POST",
      body: JSON.stringify(Object.fromEntries(form)),
    });
    state.user = data.user;
    setAuthVisible(true);
    updateUser();
    showView(SEARCH_CONFIG[PERSON_TARGET].viewId);
    await refreshHealth();
  });

  $("#logoutButton").addEventListener("click", async () => {
    await api("/api/auth/logout", { method: "POST", body: JSON.stringify({}) });
    state.user = null;
    setAuthVisible(false);
  });

  $$(".nav-item").forEach((button) => {
    button.addEventListener("click", () => showView(button.dataset.view));
  });

  $("#runPersonTextSearch").addEventListener("click", () => runTextSearch(PERSON_TARGET).catch((err) => toast(err.message)));
  $("#runGeneralTextSearch").addEventListener("click", () => runTextSearch(GENERAL_TARGET).catch((err) => toast(err.message)));
  $("#runPersonAttributeSearch").addEventListener("click", () => runAttributeSearch().catch((err) => toast(err.message)));
  $("#runPersonImageSearch").addEventListener("click", () => runImageSearch(PERSON_TARGET).catch((err) => toast(err.message)));
  $("#runGeneralImageSearch").addEventListener("click", () => runImageSearch(GENERAL_TARGET).catch((err) => toast(err.message)));

  $(`#${SEARCH_CONFIG[PERSON_TARGET].clearId}`).addEventListener("click", () => clearResults(PERSON_TARGET));
  $(`#${SEARCH_CONFIG[GENERAL_TARGET].clearId}`).addEventListener("click", () => clearResults(GENERAL_TARGET));

  bindFileLabel("personQueryImage", "personQueryImageName", "No file selected");
  bindFileLabel("generalQueryImage", "generalQueryImageName", "No file selected");

  $("#uploadFiles").addEventListener("change", (event) => {
    $("#uploadFolderCount").textContent = `${event.target.files.length} files`;
  });
  $("#uploadFlatFiles").addEventListener("change", (event) => {
    $("#uploadFileCount").textContent = `${event.target.files.length} files`;
  });
  $("#videoFile").addEventListener("change", (event) => {
    $("#videoFileName").textContent = event.target.files[0]?.name || "No file selected";
  });

  $("#uploadButton").addEventListener("click", () => uploadImages().catch((err) => toast(err.message)));
  $("#refreshGallery").addEventListener("click", () => loadGallery().catch((err) => toast(err.message)));
  $("#gallerySearch").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      loadGallery().catch((err) => toast(err.message));
    }
  });
  $("#datasetFilter").addEventListener("change", () => loadGallery().catch((err) => toast(err.message)));
  $("#refreshHistory").addEventListener("click", () => loadHistory().catch((err) => toast(err.message)));
  $("#createInvite").addEventListener("click", () => createInvite().catch((err) => toast(err.message)));
  $("#reindexButton").addEventListener("click", () => reindex().catch((err) => toast(err.message)));
  $("#uploadVideoButton").addEventListener("click", () => uploadVideo().catch((err) => toast(err.message)));

  document.body.addEventListener("click", (event) => {
    const searchButton = event.target.closest(".image-id-search");
    if (searchButton) {
      runImageIdSearch(
        searchButton.dataset.imageId,
        searchButton.dataset.targetType || currentSearchTarget(),
      ).catch((err) => toast(err.message));
    }

    const deleteButton = event.target.closest(".image-delete");
    if (deleteButton) {
      deleteImage(deleteButton.dataset.imageId).catch((err) => toast(err.message));
    }
  });
}

bindEvents();
clearResults(PERSON_TARGET);
clearResults(GENERAL_TARGET);
checkSession();
