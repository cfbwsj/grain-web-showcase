const state = {
  user: null,
  currentView: "searchView",
  galleryPage: 1,
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
    throw new Error(data.detail || `请求失败：${response.status}`);
  }
  return data;
}

function setAuthVisible(authed) {
  $("#authScreen").classList.toggle("hidden", authed);
  $("#mainApp").classList.toggle("hidden", !authed);
}

function updateUser() {
  $("#userEmail").textContent = state.user ? `${state.user.email} · ${state.user.role}` : "-";
  $("#adminNav").classList.toggle("hidden", state.user?.role !== "admin");
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

async function refreshHealth() {
  const data = await api("/api/health");
  $("#healthBadge").textContent = `${data.backend} · ${data.image_count} images`;
}

function showView(viewId) {
  state.currentView = viewId;
  $$(".view").forEach((view) => view.classList.toggle("active-view", view.id === viewId));
  $$(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.view === viewId));

  const titles = {
    searchView: ["Search", "检索工作台"],
    galleryView: ["Gallery", "图库数据"],
    uploadView: ["Upload", "上传与建库"],
    historyView: ["History", "检索历史"],
    adminView: ["Admin", "系统管理"],
    videoView: ["Video", "视频接口"],
  };
  const [eyebrow, title] = titles[viewId] || titles.searchView;
  $("#viewEyebrow").textContent = eyebrow;
  $("#viewTitle").textContent = title;

  if (viewId === "galleryView") loadGallery();
  if (viewId === "historyView") loadHistory();
  if (viewId === "adminView") loadInvites();
  if (viewId === "videoView") loadVideos();
}

function imageCard(image, options = {}) {
  const score = image.similarity_pct;
  const chips = [
    image.dataset ? `<span class="chip">${escapeHtml(image.dataset)}</span>` : "",
    image.person_key ? `<span class="chip">ID ${escapeHtml(image.person_key)}</span>` : "",
    score != null ? `<span class="chip">${score}%</span>` : "",
  ].join("");
  const button = options.searchButton
    ? `<button class="secondary-button image-id-search" data-image-id="${image.id}">以此图检索</button>`
    : "";
  return `
    <article class="image-card">
      <img src="${image.thumbnail_url || image.url}" alt="${escapeHtml(image.original_filename)}" loading="lazy" />
      <div class="image-info">
        <strong title="${escapeHtml(image.original_filename)}">${escapeHtml(image.original_filename)}</strong>
        <div class="meta-line">${chips}</div>
        ${score != null ? `<div class="score-bar"><span style="width:${score}%"></span></div>` : ""}
        ${button}
      </div>
    </article>
  `;
}

function renderResults(data) {
  const meta = [
    `${data.latency_ms} ms`,
    `backend: ${data.backend}`,
    data.matched_person_key ? `matched person: ${data.matched_person_key}` : "",
    data.translated_query && data.translated_query !== data.query ? `query: ${data.translated_query}` : "",
  ].filter(Boolean);
  $("#searchMeta").textContent = `${meta.join(" · ")} · ${data.results.length} results`;
  $("#resultsGrid").innerHTML = data.results.length
    ? data.results.map((item) => imageCard(item, { searchButton: true })).join("")
    : `<p class="muted">没有命中结果，先上传图片集再试。</p>`;
}

async function runTextSearch() {
  const text = $("#textQuery").value.trim();
  if (!text) return toast("请输入检索文本");
  const data = await api("/api/search/text", {
    method: "POST",
    body: JSON.stringify({
      text,
      top_k: Number($("#textTopK").value || 24),
      group_by_person: $("#textGroupByPerson").checked,
    }),
  });
  renderResults(data);
  await refreshHealth();
}

async function runAttributeSearch() {
  const attributes = {
    gender: $("#attrGender").value,
    top_color: $("#attrTopColor").value,
    top_type: $("#attrTopType").value,
    bottom_color: $("#attrBottomColor").value,
    bottom_type: $("#attrBottomType").value,
    accessory: $("#attrAccessory").value,
    extra: $("#attrExtra").value,
  };
  const data = await api("/api/search/attributes", {
    method: "POST",
    body: JSON.stringify({
      attributes,
      top_k: Number($("#textTopK").value || 24),
      group_by_person: $("#textGroupByPerson").checked,
    }),
  });
  renderResults(data);
}

async function runImageSearch() {
  const file = $("#queryImage").files[0];
  if (!file) return toast("请选择查询图片");
  const form = new FormData();
  form.append("file", file);
  form.append("top_k", $("#imageTopK").value || "24");
  form.append("group_by_person", $("#imageGroupByPerson").checked ? "true" : "false");
  const data = await api("/api/search/image", { method: "POST", body: form });
  renderResults(data);
}

async function runImageIdSearch(imageId) {
  const data = await api("/api/search/image-id", {
    method: "POST",
    body: JSON.stringify({
      image_id: Number(imageId),
      top_k: Number($("#imageTopK").value || 24),
      group_by_person: $("#imageGroupByPerson").checked,
    }),
  });
  renderResults(data);
  showView("searchView");
}

async function loadGallery() {
  const params = new URLSearchParams({
    q: $("#gallerySearch").value.trim(),
    dataset: $("#datasetFilter").value,
    page: String(state.galleryPage),
    page_size: "72",
  });
  const data = await api(`/api/images?${params}`);
  $("#galleryCount").textContent = `${data.total} images`;
  $("#galleryGrid").innerHTML = data.images.length
    ? data.images.map((item) => imageCard(item, { searchButton: true })).join("")
    : `<p class="muted">图库为空，请先上传图片。</p>`;

  const currentDataset = $("#datasetFilter").value;
  $("#datasetFilter").innerHTML = `<option value="">全部数据集</option>` + data.datasets
    .map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`)
    .join("");
  $("#datasetFilter").value = currentDataset;
}

async function uploadImages() {
  const folderFiles = Array.from($("#uploadFiles").files);
  const flatFiles = Array.from($("#uploadFlatFiles").files);
  const files = [...folderFiles, ...flatFiles];
  if (!files.length) return toast("请选择图片");
  const form = new FormData();
  files.forEach((file) => form.append("files", file, file.webkitRelativePath || file.name));
  form.append("dataset", $("#uploadDataset").value || "demo");
  form.append("person_key", $("#uploadPersonKey").value || "");
  form.append("tags", $("#uploadTags").value || "");
  form.append("infer_person", $("#uploadInferPerson").checked ? "true" : "false");
  $("#uploadButton").disabled = true;
  $("#uploadButton").textContent = "上传中...";
  try {
    const data = await api("/api/images/upload", { method: "POST", body: form });
    $("#uploadReport").innerHTML = `
      <div class="history-item">
        <strong>已上传 ${data.count} 张图片</strong>
        ${data.errors.length ? `<p class="muted">部分失败：${data.errors.map(escapeHtml).join("；")}</p>` : ""}
      </div>
    `;
    await refreshHealth();
    toast("图片已入库");
  } finally {
    $("#uploadButton").disabled = false;
    $("#uploadButton").textContent = "上传并建立索引";
  }
}

async function loadHistory() {
  const data = await api("/api/search/history");
  $("#historyList").innerHTML = data.history.length
    ? data.history.map((item) => `
      <article class="history-item">
        <header>
          <strong>${escapeHtml(item.mode)} · ${escapeHtml(item.query_text || "")}</strong>
          <span class="muted">${item.latency_ms} ms · ${escapeHtml(item.backend)}</span>
        </header>
        ${item.translated_text ? `<p class="muted">${escapeHtml(item.translated_text)}</p>` : ""}
        <div class="history-strip">
          ${(item.results || []).map((result) => `<img src="${result.thumbnail_url}" alt="result ${result.id}" />`).join("")}
        </div>
      </article>
    `).join("")
    : `<p class="muted">还没有检索历史。</p>`;
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
        <p class="muted">${escapeHtml(invite.label || "无备注")} ${invite.expires_at ? "· expires " + escapeHtml(invite.expires_at) : ""}</p>
      </article>
    `).join("")
    : `<p class="muted">暂无邀请码。</p>`;
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
  toast("邀请码已生成");
  await loadInvites();
}

async function reindex() {
  $("#reindexButton").disabled = true;
  $("#reindexReport").textContent = "正在重建索引...";
  try {
    const data = await api("/api/admin/reindex", { method: "POST", body: JSON.stringify({}) });
    $("#reindexReport").textContent = `${data.backend} · ${data.count} images · ${data.latency_ms} ms`;
    await refreshHealth();
  } finally {
    $("#reindexButton").disabled = false;
  }
}

async function uploadVideo() {
  const file = $("#videoFile").files[0];
  if (!file) return toast("请选择视频文件");
  const form = new FormData();
  form.append("file", file);
  form.append("dataset", $("#videoDataset").value || "video-demo");
  await api("/api/videos/upload", { method: "POST", body: form });
  toast("视频已进入预留队列");
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
    : `<p class="muted">暂无视频任务。</p>`;
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
    showView("searchView");
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
    showView("searchView");
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

  $("#runTextSearch").addEventListener("click", () => runTextSearch().catch((err) => toast(err.message)));
  $("#runAttributeSearch").addEventListener("click", () => runAttributeSearch().catch((err) => toast(err.message)));
  $("#runImageSearch").addEventListener("click", () => runImageSearch().catch((err) => toast(err.message)));
  $("#clearResults").addEventListener("click", () => {
    $("#resultsGrid").innerHTML = "";
    $("#searchMeta").textContent = "等待检索任务。";
  });

  $("#queryImage").addEventListener("change", (event) => {
    $("#queryImageName").textContent = event.target.files[0]?.name || "未选择文件";
  });
  $("#uploadFiles").addEventListener("change", (event) => {
    $("#uploadFolderCount").textContent = `${event.target.files.length} files`;
  });
  $("#uploadFlatFiles").addEventListener("change", (event) => {
    $("#uploadFileCount").textContent = `${event.target.files.length} files`;
  });
  $("#videoFile").addEventListener("change", (event) => {
    $("#videoFileName").textContent = event.target.files[0]?.name || "未选择文件";
  });

  $("#uploadButton").addEventListener("click", () => uploadImages().catch((err) => toast(err.message)));
  $("#refreshGallery").addEventListener("click", () => loadGallery().catch((err) => toast(err.message)));
  $("#gallerySearch").addEventListener("keydown", (event) => {
    if (event.key === "Enter") loadGallery().catch((err) => toast(err.message));
  });
  $("#datasetFilter").addEventListener("change", () => loadGallery().catch((err) => toast(err.message)));
  $("#refreshHistory").addEventListener("click", () => loadHistory().catch((err) => toast(err.message)));
  $("#createInvite").addEventListener("click", () => createInvite().catch((err) => toast(err.message)));
  $("#reindexButton").addEventListener("click", () => reindex().catch((err) => toast(err.message)));
  $("#uploadVideoButton").addEventListener("click", () => uploadVideo().catch((err) => toast(err.message)));

  document.body.addEventListener("click", (event) => {
    const button = event.target.closest(".image-id-search");
    if (button) runImageIdSearch(button.dataset.imageId).catch((err) => toast(err.message));
  });
}

bindEvents();
checkSession();
