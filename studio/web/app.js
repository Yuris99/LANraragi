const $ = (selector, root = document) => root.querySelector(selector);
const state = { page: 1, view: "library", provider: "", query: "", sort: "added", direction: "desc", detail: null, reader: null };
let settings;
try { settings = JSON.parse(localStorage.getItem("studio-view") || "{}"); } catch { settings = {}; }
settings = { size: "medium", limit: 48, layout: "grid", direction: "ltr", ...settings };
const providerName = { ehentai: "E-Hentai", hitomi: "Hitomi", nhentai: "nHentai" };
const statusName = { queued: "대기 중", running: "진행 중", complete: "완료", failed: "실패", blocked: "확인 필요" };
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (s) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[s]));
function toast(message) { const el = $("#toast"); el.textContent = message; el.hidden = false; clearTimeout(toast.timer); toast.timer = setTimeout(() => { el.hidden = true; }, 5500); }
async function api(path, data) {
    const response = await fetch(path, data === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
    const value = await response.json();
    if (!response.ok) throw new Error(value.error || "요청을 처리하지 못했습니다.");
    return value;
}
function saveSettings() { localStorage.setItem("studio-view", JSON.stringify(settings)); applySettings(); }
function applySettings() {
    document.documentElement.style.setProperty("--card-width", { small: "150px", medium: "185px", large: "230px" }[settings.size] || "185px");
    $("#grid").classList.toggle("list", settings.layout === "list");
    $("#card-size").value = settings.size; $("#page-size").value = String(settings.limit); $("#read-direction").value = settings.direction;
}
function sources(work) { return work.sources.map((s) => `<span class="source-pill ${s.provider}">${providerName[s.provider]} · ${esc(s.external_id)}</span>`).join(""); }
function cover(work) {
    return `<div class="cover">${work.lrr_id ? `<img src="/api/media/${work.lrr_id}/thumbnail" loading="lazy" decoding="async" alt="${esc(work.title)} 표지">` : `<div class="placeholder"><span>▤</span><small>METADATA ONLY</small></div>`}<span class="pages">${work.pages} P</span>${work.favorite ? `<span class="favorite-star">★</span>` : ""}</div>`;
}
let requestNumber = 0;
async function load() {
    const request = ++requestNumber;
    const query = new URLSearchParams({ q: state.query, sort: state.sort, direction: state.direction, page: state.page, limit: settings.limit, provider: state.provider, favorite: state.view === "favorite" ? "1" : "0", unread: state.view === "unread" ? "1" : "0" });
    const result = await api(`/api/works?${query}`);
    if (request !== requestNumber) return;
    $("#total").textContent = `${result.total.toLocaleString()} 작품`;
    $("#grid").innerHTML = result.items.map((work) => `<article class="card" data-id="${work.id}" tabindex="0" role="button" aria-label="${esc(work.title)} 상세 보기">${cover(work)}<div><h3>${esc(work.title)}</h3><div class="card-artist">${esc(work.artist || "작가 미등록")}</div></div><div class="card-sources">${sources(work)}</div></article>`).join("");
    $("#empty").hidden = result.items.length > 0;
    $("#previous").disabled = state.page === 1; $("#next").disabled = state.page * settings.limit >= result.total;
    $("#page-number").textContent = `${state.page} / ${Math.max(1, Math.ceil(result.total / settings.limit))} 페이지`;
}
async function showDetail(id) {
    const work = await api(`/api/works/${id}`); state.detail = work;
    $("#detail-content").innerHTML = `<div class="detail-layout">${cover(work)}<div><div class="eyebrow">COLLECTION ENTRY</div><h2>${esc(work.title)}</h2><div class="card-artist">${esc(work.artist || "작가 미등록")}</div><div class="detail-meta"><span>${work.pages} 페이지</span><span>${(work.bytes / 1048576).toFixed(1)} MiB</span><span>${work.last_read ? `최근 열람 ${new Date(work.last_read * 1000).toLocaleDateString("ko-KR")}` : "열람 기록 없음"}</span></div><div class="rating" aria-label="별점">${[1, 2, 3, 4, 5].map((n) => `<button data-rating="${n}" aria-label="${n}점">${n <= work.rating ? "★" : "☆"}</button>`).join("")}<button data-rating="0" aria-label="별점 지우기">×</button></div><div class="detail-actions"><button class="primary" id="read-work" ${work.lrr_id ? "" : "disabled"}>▷ 읽기</button><button class="quiet" id="favorite-work">${work.favorite ? "★ 즐겨찾기 해제" : "☆ 즐겨찾기"}</button>${work.lrr_id ? `<a class="quiet" href="/api/media/${work.lrr_id}/download" download>↓ PC로 받기</a>` : ""}<button class="quiet" id="edit-work">제목·태그 수정</button></div><p class="muted">${work.lrr_id ? "라이브러리에 저장된 파일" : "메타데이터만 등록됨 · 파일을 동기화하면 읽을 수 있습니다."}</p></div></div>
    <section class="detail-section"><h3>통합 태그</h3><div class="tags">${work.all_tags.map((tag) => `<button class="tag" data-tag="${esc(tag)}">${esc(tag)}</button>`).join("") || `<span class="muted">등록된 태그가 없습니다.</span>`}</div></section>
    <section class="detail-section"><h3>연결된 출처 <span class="muted">번호를 누르면 원본 페이지로 이동합니다.</span></h3>${work.sources.map((s) => `<div class="source-row"><div class="source-header"><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${providerName[s.provider]} #${esc(s.external_id)} ↗</a><button class="quiet" data-fetch="${s.id}">태그 가져오기</button></div><small>${s.status === "fetched" ? `수집 ${new Date(s.fetched * 1000).toLocaleString("ko-KR")}` : "수동 등록 · 원격 정보 미확인"} · 태그 ${s.tags.length} · 댓글 ${s.comments.length}</small><div class="tags">${s.tags.map((tag) => `<span class="tag">${esc(tag)}</span>`).join("")}</div>${s.comments.length ? `<details><summary>보관한 댓글 ${s.comments.length}개</summary>${s.comments.map((c) => `<div class="comment"><small>${esc(c.author)} · ${esc(c.posted_at)}</small>${esc(c.text)}</div>`).join("")}</details>` : ""}</div>`).join("") || `<p class="muted">같은 작품이 있는 사이트의 URL을 각각 연결하세요.</p>`}
    <details class="detail-section"><summary>출처 연결 · 태그·댓글 가져오기</summary><form id="source-form" class="source-form"><label>작품 URL<input name="url" type="url" required placeholder="https://…"></label><label>원본 태그<input name="tags" placeholder="쉼표로 구분 (선택)"></label><label>댓글 JSON (선택)<textarea name="comments" placeholder='[{"id":"1","author":"작성자","text":"댓글","posted_at":"2026-01-01"}]'></textarea></label><p class="muted">사이트별 정보를 따로 보존합니다. 댓글 자동 수집은 아직 연결되지 않았으며, 내보낸 댓글 JSON을 가져올 수 있습니다.</p><button class="primary">출처 저장</button></form></details></section>`;
    if (!$("#detail").open) $("#detail").showModal();
}
async function showJobs() {
    const jobs = await api("/api/jobs"); $("#job-count").textContent = jobs.filter((j) => ["queued", "running"].includes(j.state)).length;
    $("#jobs").innerHTML = jobs.length ? jobs.map((j) => `<article class="job"><div><div class="job-state">${statusName[j.state] || esc(j.state)} · ${j.engine === "lanraragi" ? "서버 플러그인" : "외부 엔진"}</div><div class="job-url">${esc(j.url)}</div><div class="job-message">${esc(j.message || (j.engine === "command" && j.state === "queued" ? "대상 기기의 다운로드 작업자가 가져가기를 기다립니다." : "서버 작업 대기 중"))}</div></div><div class="job-target">${j.target === "nas" ? "NAS" : "내 PC"}${["failed", "blocked"].includes(j.state) ? `<p><button class="quiet" data-retry="${j.id}">다시 시도</button></p>` : ""}</div></article>`).join("") : `<div class="empty"><span>↓</span><h2>대기 중인 다운로드가 없습니다.</h2><p>작품 URL과 저장할 기기를 선택해 주세요.</p></div>`;
}
async function view(value) {
    state.view = value; state.page = 1;
    $("#library-view").hidden = value === "jobs"; $("#jobs-view").hidden = value !== "jobs";
    $("#page-title").textContent = { library: "전체 보관함", favorite: "즐겨찾기", unread: "아직 읽지 않은 작품", jobs: "다운로드" }[value];
    document.querySelectorAll("[data-view]").forEach((b) => b.classList.toggle("active", b.dataset.view === value));
    await (value === "jobs" ? showJobs() : load());
}
async function sync() { $("#sync").disabled = true; try { const r = await api("/api/sync", {}); toast(`${r.synced}개 작품을 동기화했습니다.`); await load(); } finally { $("#sync").disabled = false; } }
function pageUrl(url, id) {
    const parsed = new URL(url.replace("/page&", "/page?"), location.origin);
    if (parsed.origin !== location.origin || parsed.pathname !== `/api/archives/${id}/page`) throw new Error("페이지 URL 형식이 올바르지 않습니다.");
    return `/api/media/${id}/page${parsed.search}`;
}
async function readWork() {
    const work = state.detail; const result = await api(`/api/media/${work.lrr_id}/files`);
    if (!Array.isArray(result.pages) || !result.pages.length) throw new Error("페이지 준비 중입니다. 잠시 후 다시 시도해 주세요.");
    state.reader = { work, pages: result.pages.map((url) => pageUrl(url, work.lrr_id)), page: Math.max(0, Math.min(result.pages.length - 1, work.progress - 1)) };
    $("#reader-title").textContent = work.title; $("#reader").showModal(); renderPage();
}
function renderPage() {
    const reader = state.reader; const image = $("#reader-image");
    image.onload = () => { api(`/api/works/${reader.work.id}/progress`, { page: reader.page + 1 }).catch((e) => toast(e.message)); };
    image.onerror = () => toast("페이지를 아직 불러오지 못했습니다. 추출 상태를 확인한 뒤 다시 열어 주세요.");
    image.src = reader.pages[reader.page]; $("#reader-position").textContent = `${reader.page + 1} / ${reader.pages.length}`;
    $("#reader-prev").disabled = reader.page === 0; $("#reader-next").disabled = reader.page + 1 === reader.pages.length;
    if (reader.pages[reader.page + 1]) { const next = new Image(); next.src = reader.pages[reader.page + 1]; }
}
function turnPage(delta) { if (!state.reader) return; const n = state.reader.page + delta; if (n >= 0 && n < state.reader.pages.length) { state.reader.page = n; renderPage(); } }
function guard(fn) { return (...args) => Promise.resolve().then(() => fn(...args)).catch((e) => toast(e.message)); }
document.addEventListener("click", guard(async (event) => {
    const button = event.target.closest("button,a,.card"); if (!button) return;
    if (button.dataset.close !== undefined) button.closest("dialog").close();
    if (button.dataset.view) await view(button.dataset.view);
    const provider = button.dataset.provider ?? button.dataset.filter;
    if (provider !== undefined) { state.provider = provider; state.page = 1; document.querySelectorAll("[data-filter]").forEach((b) => b.classList.toggle("selected", b.dataset.filter === provider)); await view("library"); }
    if (button.dataset.id) await showDetail(button.dataset.id);
    if (button.dataset.rating) { await api(`/api/works/${state.detail.id}`, { rating: Number(button.dataset.rating) }); await showDetail(state.detail.id); }
    if (button.dataset.fetch) { button.disabled = true; try { await api(`/api/works/${state.detail.id}/sources/${button.dataset.fetch}/fetch`, {}); await showDetail(state.detail.id); toast("출처 태그를 갱신했습니다."); } finally { button.disabled = false; } }
    if (button.dataset.retry) { await api(`/api/jobs/${button.dataset.retry}/retry`, {}); await showJobs(); }
    if (button.dataset.tag) { state.query = button.dataset.tag; $("#search").value = state.query; $("#detail").close(); await load(); }
}));
$("#grid").addEventListener("keydown", guard(async (e) => { if (e.key === "Enter" && e.target.dataset.id) await showDetail(e.target.dataset.id); }));
document.addEventListener("submit", guard(async (event) => {
    event.preventDefault(); const form = event.target; const data = Object.fromEntries(new FormData(form));
    if (form.id === "editor-form") { const work = await api("/api/works", { title: data.title, artist: data.artist }); if (data.url) await api(`/api/works/${work.id}/sources`, { url: data.url }); form.closest("dialog").close(); form.reset(); await load(); await showDetail(work.id); }
    if (form.id === "source-form") { const value = { url: data.url }; if (data.tags) value.tags = data.tags; if (data.comments) value.comments = JSON.parse(data.comments); await api(`/api/works/${state.detail.id}/sources`, value); await showDetail(state.detail.id); await load(); }
    if (form.id === "download-form") { await api("/api/jobs", data); form.closest("dialog").close(); await view("jobs"); }
}));
$("#detail").addEventListener("click", guard(async (e) => {
    if (e.target.closest("#favorite-work")) { await api(`/api/works/${state.detail.id}`, { favorite: !state.detail.favorite }); await showDetail(state.detail.id); await load(); }
    if (e.target.closest("#read-work")) await readWork();
    if (e.target.closest("#edit-work")) {
        const section = document.createElement("section"); section.className = "detail-section";
        section.innerHTML = `<form id="work-form"><label>제목<input name="title" required value="${esc(state.detail.title)}"></label><label>작가<input name="artist" value="${esc(state.detail.artist)}"></label><label>내 태그<input name="tags" value="${esc(state.detail.tags.join(", "))}"></label><p class="muted">저장하면 제목을 잠가 다음 동기화에서 덮어쓰지 않습니다.</p><button class="primary">저장</button></form>`;
        $("#detail-content").append(section); $("#edit-work").disabled = true;
    }
}));
document.addEventListener("submit", guard(async (e) => { if (e.target.id === "work-form") { const data = Object.fromEntries(new FormData(e.target)); await api(`/api/works/${state.detail.id}`, { ...data, title_locked: true }); await showDetail(state.detail.id); await load(); } }));
$("#sync").onclick = guard(sync); $("#empty-sync").onclick = guard(sync);
$("#add").onclick = () => $("#editor").showModal(); $("#queue").onclick = () => $("#download-dialog").showModal();
$("#close-detail").onclick = () => $("#detail").close(); $("#close-reader").onclick = () => $("#reader").close();
$("#settings-button").onclick = () => $("#settings").showModal();
$("#card-size").onchange = (e) => { settings.size = e.target.value; saveSettings(); };
$("#page-size").onchange = guard(async (e) => { settings.limit = Number(e.target.value); state.page = 1; saveSettings(); await load(); });
$("#read-direction").onchange = (e) => { settings.direction = e.target.value; saveSettings(); };
$("#layout").onclick = () => { settings.layout = settings.layout === "list" ? "grid" : "list"; saveSettings(); };
$("#direction").onclick = guard(async () => { state.direction = state.direction === "desc" ? "asc" : "desc"; $("#direction").textContent = state.direction === "desc" ? "↓" : "↑"; await load(); });
$("#sort").onchange = guard(async (e) => { state.sort = e.target.value; state.page = 1; await load(); });
$("#search").oninput = () => { clearTimeout(state.searchTimer); state.searchTimer = setTimeout(guard(async () => { state.query = $("#search").value; state.page = 1; await load(); }), 250); };
$("#previous").onclick = guard(async () => { state.page -= 1; await load(); }); $("#next").onclick = guard(async () => { state.page += 1; await load(); });
$("#reader-prev").onclick = () => turnPage(-1); $("#reader-next").onclick = () => turnPage(1);
document.addEventListener("keydown", (e) => { if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) return; if (e.key === "/" && !$("#detail").open && !$("#reader").open) { e.preventDefault(); $("#search").focus(); } if ($("#reader").open && ["ArrowLeft", "ArrowRight"].includes(e.key)) { e.preventDefault(); turnPage((e.key === "ArrowRight" ? 1 : -1) * (settings.direction === "rtl" ? -1 : 1)); } });
applySettings();
guard(load)(); guard(showJobs)();
guard(async () => { const health = await api("/api/health"); $("#connection-dot").classList.add(health.lanraragi_connected ? "online" : "offline"); $("#connection-text").innerHTML = health.lanraragi_connected ? `서버 연결됨<small>LANraragi ${esc(health.version)} · 개인 라이브러리</small>` : "서버 연결 필요<small>작품 정보는 로컬에 보존됩니다.</small>"; })();
setInterval(guard(async () => { if (state.view === "jobs" && !document.hidden) await showJobs(); }), 5000);
