const $ = (selector, root = document) => root.querySelector(selector);
const selectedWorks = new Set();
let tagTargets = [];
const state = { page: 1, view: "library", provider: "", query: "", tag: "", sort: "added", direction: "desc", detail: null, reader: null };
let settings;
try { settings = JSON.parse(localStorage.getItem("studio-view") || "{}"); } catch { settings = {}; }
settings = { size: "medium", limit: 48, layout: "grid", direction: "ltr", ...settings };
if (typeof settings.thumbnailBlur !== "boolean") settings.thumbnailBlur = settings.thumbnailMosaic !== false;
delete settings.mosaic;
delete settings.thumbnailMosaic;
// Keep old original-view bookmarks usable; normal visits use the saved choice.
if (/^\/unsen\/?$/.test(location.pathname)) settings.thumbnailBlur = false;
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
const workShortIds = new Map(), shortWorkIds = new Map(), workAliases = new Map();
function cacheWork(work) {
    for (const alias of workAliases.get(work.id) || []) if (shortWorkIds.get(alias) === work.id) shortWorkIds.delete(alias);
    const aliases = new Set([work.short_id, `L${work.local_number}`]);
    for (const source of work.sources || []) {
        const prefix = { hitomi: "", ehentai: "E", nhentai: "N" }[source.provider];
        if (prefix !== undefined && /^[0-9]{1,32}$/.test(source.external_id)) aliases.add(prefix + source.external_id);
    }
    for (const alias of aliases) if (alias) shortWorkIds.set(alias, work.id);
    workShortIds.set(work.id, work.short_id); workAliases.set(work.id, aliases);
}
const libraryViews = ["library", "favorite"];
function libraryState(value = {}) {
    const integer = (n, fallback, max) => Number.isSafeInteger(Number(n)) && Number(n) >= 1 && Number(n) <= max ? Number(n) : fallback;
    return { view: libraryViews.includes(value.view) ? value.view : "library", page: integer(value.page, 1, 1000000),
        query: String(value.query || "").slice(0, 1024), tag: String(value.tag || "").slice(0, 120), allTag: String(value.allTag || "").slice(0, 300),
        provider: ["ehentai", "hitomi", "nhentai"].includes(value.provider) ? value.provider : "", sort: ["added", "title", "artist", "pages", "bytes", "rating", "last_read", "random"].includes(value.sort) ? value.sort : "added",
        direction: value.direction === "asc" ? "asc" : "desc", limit: [24, 48, 96].includes(Number(value.limit)) ? Number(value.limit) : 48,
        scroll: Number.isFinite(value.scroll) && value.scroll >= 0 ? value.scroll : 0 };
}
let libraryContext = libraryState({ limit: settings.limit });
let libraryKey = "", routeHref = "", routeTask = Promise.resolve(), routeRevision = 0, progressTask = Promise.resolve(), pendingReader = null;
history.scrollRestoration = "manual";
function routeHash(route) {
    if (route.kind === "jobs") return "#/downloads";
    const short = workShortIds.get(route.id) || route.short;
    if (route.kind === "detail") return short ? `#/${short}` : `#/works/${route.id}`;
    if (route.kind === "reader") return short ? `#/${short}/${route.page}` : `#/works/${route.id}/read/${route.page}`;
    const value = libraryState(route.library), params = new URLSearchParams();
    for (const [key, field, fallback] of [["view", "view", "library"], ["page", "page", 1], ["q", "query", ""], ["tag", "tag", ""], ["all_tag", "allTag", ""], ["provider", "provider", ""], ["sort", "sort", "added"], ["direction", "direction", "desc"], ["limit", "limit", 48]]) {
        if (value[field] !== fallback) params.set(key, value[field]);
    }
    return "#/library" + (params.size ? "?" + params : "");
}
function addressRoute() {
    const raw = location.hash.slice(1), split = raw.indexOf("?"), path = split < 0 ? raw : raw.slice(0, split);
    if (!raw || raw === "/") return { kind: "library", library: libraryState({ limit: settings.limit }) };
    if (path === "/library") {
        const p = new URLSearchParams(split < 0 ? "" : raw.slice(split + 1));
        return { kind: "library", library: libraryState({ view: p.get("view"), page: p.get("page"), query: p.get("q"), tag: p.get("tag"), allTag: p.get("all_tag"), provider: p.get("provider"), sort: p.get("sort"), direction: p.get("direction"), limit: p.get("limit") }) };
    }
    if (raw === "/downloads") return { kind: "jobs" };
    const short = /^\/([ENL]?[0-9]{1,32})(?:\/([0-9]+))?$/.exec(raw.toUpperCase());
    if (short && (!short[2] || (Number.isSafeInteger(Number(short[2])) && Number(short[2]) <= 1000000))) return { kind: short[2] ? "reader" : "detail", short: short[1], page: Math.max(1, Number(short[2]) || 1) };
    const match = /^\/works\/([a-f0-9]{32})(?:\/read\/(\d+))?$/.exec(raw);
    if (match && (!match[2] || (Number.isSafeInteger(Number(match[2])) && Number(match[2]) <= 1000000))) return { kind: match[2] ? "reader" : "detail", id: match[1], page: Math.max(1, Number(match[2]) || 1) };
    return { kind: "library", library: libraryContext, invalid: true };
}
function setAddress(route, replace = false) {
    const current = addressRoute();
    if (current.kind === "library") libraryContext = { ...current.library, scroll: window.scrollY };
    history.replaceState({ ...history.state, studioLibrary: libraryContext }, "");
    const context = route.kind === "library" ? libraryState(route.library) : libraryContext;
    const target = routeHash(route), metadata = { studioLibrary: context };
    if (replace || location.hash === target) history.replaceState(metadata, "", target);
    else history.pushState(metadata, "", target);
    libraryContext = context;
}
function currentLibrary() { return libraryState({ ...state, limit: settings.limit, scroll: window.scrollY }); }
function updateView() {
    $("#library-view").hidden = state.view === "jobs"; $("#jobs-view").hidden = state.view !== "jobs";
    $("#page-title").textContent = { library: "전체 보관함", favorite: "즐겨찾기", jobs: "다운로드" }[state.view];
    document.querySelectorAll("[data-view]").forEach((button) => button.classList.toggle("active", button.dataset.view === state.view));
    document.querySelectorAll("[data-filter]").forEach((button) => button.classList.toggle("selected", button.dataset.filter === state.provider));
    $("#search").value = state.query; $("#sort").value = state.sort;
    const activeTag = state.allTag || state.tag;
    $("#active-tag").hidden = !activeTag; $("#active-tag-name").textContent = activeTag ? `태그: ${activeTag}` : "";
    $("#direction").textContent = state.direction === "desc" ? "↓" : "↑";
}
async function navigateRoute(route, { replace = false, refresh = false } = {}) {
    clearTimeout(state.searchTimer); setAddress(route, replace); return applyRoute(refresh);
}
function navigateLibrary() { return navigateRoute({ kind: "library", library: { ...currentLibrary(), scroll: 0 } }); }
async function applyRoute(refresh = false) {
    if (!refresh && routeHref === location.href) return routeTask;
    routeHref = location.href;
    const revision = ++routeRevision, route = addressRoute();
    routeTask = (async () => {
        if (route.invalid) toast("주소 형식을 확인하세요. 보관함으로 돌아갑니다.");
        libraryContext = route.kind === "library" ? libraryState({ ...route.library, scroll: history.state?.studioLibrary?.scroll }) : libraryState(history.state?.studioLibrary || libraryContext);
        for (const dialog of document.querySelectorAll("dialog[open]")) if (dialog.id !== "detail" && dialog.id !== "reader") dialog.close();
        if (route.kind === "library" || route.kind === "jobs") {
            $("#reader").close(); $("#detail").close(); state.reader = null; state.detail = null;
        } else if (route.kind === "detail") { $("#reader").close(); state.reader = null; }
        Object.assign(state, libraryContext); settings.limit = libraryContext.limit;
        if (route.kind === "jobs") state.view = "jobs";
        updateView(); applySettings();
        if (route.kind === "jobs") { document.title = "다운로드 · Library Studio"; await showJobs(); return; }
        if (route.kind === "library") {
            document.title = $("#page-title").textContent + " · Library Studio";
            if (location.hash !== routeHash(route)) { setAddress(route, true); routeHref = location.href; }
            await load({ fromRoute: true });
            if (revision === routeRevision) requestAnimationFrame(() => { if (revision === routeRevision) window.scrollTo(0, libraryContext.scroll); });
            return;
        }
        if (libraryKey !== routeHash({ kind: "library", library: libraryContext })) await load({ fromRoute: true });
        if (revision !== routeRevision) return;
        if (route.short) {
            route.id = shortWorkIds.get(route.short);
            if (!route.id) {
                const work = await api(`/api/short/${encodeURIComponent(route.short)}`);
                if (revision !== routeRevision) return;
                cacheWork(work); state.detail = work; route.id = work.id;
            }
        }
        if (refresh || state.detail?.id !== route.id) {
            const work = await api(`/api/works/${route.id}`);
            if (revision !== routeRevision) return;
            state.detail = work;
        }
        cacheWork(state.detail);
        if (route.kind === "detail") {
            const actual = { kind: "detail", id: state.detail.id };
            if (location.hash !== routeHash(actual)) { setAddress(actual, true); routeHref = location.href; }
            renderDetail(state.detail); document.title = state.detail.title + " · Library Studio"; return; }
        if (!state.detail.lrr_id) throw new Error("이 작품에는 아직 읽을 파일이 없습니다.");
        if (state.reader?.work.id !== route.id) {
            const result = await api(`/api/media/${state.detail.lrr_id}/files`);
            if (revision !== routeRevision) return;
            if (!Array.isArray(result.pages) || !result.pages.length) throw new Error("페이지 준비 중입니다. 잠시 후 다시 열어 주세요.");
            state.reader = { work: state.detail, pages: result.pages.map((url) => pageUrl(url, state.detail.lrr_id)), page: 0 };
        }
        pendingReader = null;
        state.reader.page = Math.min(state.reader.pages.length, route.page) - 1;
        const actualRoute = { ...route, page: state.reader.page + 1 };
        if (location.hash !== routeHash(actualRoute)) { setAddress(actualRoute, true); routeHref = location.href; }
        // Reader URLs can open directly, without placing an extra detail dialog below them.
        $("#detail").close(); if (!$("#reader").open) $("#reader").showModal(); renderPage();
    })().catch(async (error) => {
        if (revision !== routeRevision) return;
        toast(error.message);
        if (route.kind === "reader" && state.detail?.id === route.id) {
            // Extraction may still be preparing. Retry from detail at the
            // originally requested page instead of losing the book in the list.
            $("#reader").close(); state.reader = null; pendingReader = { id: route.id, page: route.page };
            setAddress({ kind: "detail", id: route.id }, true); routeHref = location.href;
            renderDetail(state.detail); document.title = state.detail.title + " · Library Studio";
            return;
        }
        if (route.kind === "reader" || route.kind === "detail") {
            $("#reader").close(); $("#detail").close(); state.reader = null; state.detail = null;
            setAddress({ kind: "library", library: libraryContext }, true); routeHref = ""; await applyRoute();
        }
    });
    return routeTask;
}
window.addEventListener("popstate", () => { clearTimeout(state.searchTimer); applyRoute(); });
window.addEventListener("hashchange", () => { clearTimeout(state.searchTimer); applyRoute(); });
function showDetail(id) { return navigateRoute({ kind: "detail", id }, { refresh: addressRoute().kind === "detail" && state.detail?.id === id }); }
function closeDetail() { return navigateRoute({ kind: "library", library: libraryContext }); }
function closeReader() { return state.reader && navigateRoute({ kind: "detail", id: state.reader.work.id }); }

function saveSettings() { localStorage.setItem("studio-view", JSON.stringify(settings)); applySettings(); }
function applySettings() {
    document.documentElement.classList.toggle("media-masked", settings.thumbnailBlur);
    $("#privacy-state").textContent = settings.thumbnailBlur ? "목록 썸네일 블러 켜짐 · 작품을 열면 원본 표시" : "목록 썸네일 원본 표시";
    $("#privacy-route").textContent = settings.thumbnailBlur ? "블러 끄기" : "블러 켜기";
    $("#privacy-route").setAttribute("aria-pressed", String(settings.thumbnailBlur));
    $("#thumbnail-blur").checked = settings.thumbnailBlur;
    document.documentElement.style.setProperty("--card-width", { small: "150px", medium: "185px", large: "230px" }[settings.size] || "185px");
    $("#grid").classList.toggle("list", settings.layout === "list");
    $("#card-size").value = settings.size; $("#page-size").value = String(settings.limit); $("#read-direction").value = settings.direction;
}
function sources(work) { return work.sources.map((s) => `<span class="source-pill ${s.provider}">${providerName[s.provider]} · ${esc(s.external_id)}</span>`).join(""); }
function cover(work) {
    return `<div class="cover">${work.lrr_id ? `<img src="/api/media/${work.lrr_id}/thumbnail" loading="lazy" decoding="async" alt="${esc(work.title)} 표지">` : `<div class="placeholder"><span>▤</span><small>METADATA ONLY</small></div>`}<span class="pages">${work.pages} P</span>${work.favorite ? `<span class="favorite-star">★</span>` : ""}</div>`;
}
let requestNumber = 0;
async function load({ fromRoute = false } = {}) {
    const displayedLibrary = currentLibrary();
    if (!fromRoute && addressRoute().kind === "library") { setAddress({ kind: "library", library: displayedLibrary }); routeHref = location.href; }
    const request = ++requestNumber;
    const query = new URLSearchParams({ q: state.query, tag: state.tag, all_tag: state.allTag || "", sort: state.sort, direction: state.direction, page: state.page, limit: settings.limit, provider: state.provider, favorite: state.view === "favorite" ? "1" : "0", unread: state.view === "unread" ? "1" : "0" });
    const result = await api(`/api/works?${query}`);
    if (request !== requestNumber) return;
    result.items.forEach(cacheWork);
    $("#total").textContent = `${result.total.toLocaleString()} 작품`;
    selectedWorks.clear();
    $("#grid").innerHTML = result.items.map((work) => `<article class="card" data-id="${work.id}" data-short-id="${esc(work.short_id)}" tabindex="0" role="button" aria-label="${esc(work.title)} 상세 보기"><label class="card-select"><input type="checkbox" data-select-work="${work.id}" aria-label="${esc(work.title)} 선택"></label>${cover(work)}<div><h3>${esc(work.title)}</h3><div class="card-artist">${esc(work.artist || "작가 미등록")}</div></div><div class="card-sources">${sources(work)}</div></article>`).join("");
    updateSelection();
    $("#empty").hidden = result.items.length > 0;
    $("#previous").disabled = state.page === 1; $("#next").disabled = state.page * settings.limit >= result.total;
    $("#page-number").textContent = `${state.page} / ${Math.max(1, Math.ceil(result.total / settings.limit))} 페이지`;
    libraryKey = routeHash({ kind: "library", library: displayedLibrary });
    await refreshLibraryStatus();
}
async function refreshLibraryStatus() {
    try {
        const status = await api("/api/library/status");
        $("#library-status").textContent = status.folder_archives ? `NAS 폴더에서 ${status.folder_archives.toLocaleString()}권 등록됨 · 나머지 폴더는 추가 등록 후 표시됩니다. NAS 자료는 PC에서 다시 업로드할 필요가 없습니다.${status.pending_archives ? ` · 색인 대기 ${status.pending_archives}개` : ""}` : "NAS에 있는 자료는 폴더 등록으로 추가할 수 있습니다. 파일 업로드는 PC 자료를 직접 추가할 때 사용하세요.";
    } catch { $("#library-status").textContent = "NAS 자료는 폴더 등록으로 추가합니다. 파일 업로드는 선택 사항입니다."; }
}
function renderDetail(work) {
    $("#detail-content").innerHTML = `<div class="detail-layout">${cover(work)}<div><div class="eyebrow">COLLECTION ENTRY</div><h2>${esc(work.title)}</h2><div class="card-artist">${esc(work.artist || "작가 미등록")}</div><div class="detail-meta"><span>번호 ${esc(work.short_id)}</span><span>${work.pages} 페이지</span><span>${(work.bytes / 1048576).toFixed(1)} MiB</span><span>${work.last_read ? `최근 열람 ${new Date(work.last_read * 1000).toLocaleDateString("ko-KR")}` : "열람 기록 없음"}</span></div><div class="rating" aria-label="별점">${[1, 2, 3, 4, 5].map((n) => `<button data-rating="${n}" aria-label="${n}점">${n <= work.rating ? "★" : "☆"}</button>`).join("")}<button data-rating="0" aria-label="별점 지우기">×</button></div><div class="detail-actions"><button class="primary" id="read-work" ${work.lrr_id ? "" : "disabled"}>▷ 읽기</button><button class="quiet" id="favorite-work">${work.favorite ? "★ 즐겨찾기 해제" : "☆ 즐겨찾기"}</button>${work.lrr_id ? `<a class="quiet" href="/api/media/${work.lrr_id}/download" download>↓ PC로 받기</a>` : ""}<button class="quiet" id="edit-work">제목·작가 수정</button></div><p class="muted">${work.lrr_id ? "라이브러리에 저장된 파일" : "메타데이터만 등록됨 · 파일을 동기화하면 읽을 수 있습니다."}</p></div></div>
    <section class="detail-section"><h3>내 태그 <button class="quiet" id="edit-user-tags">추가·삭제</button></h3><div class="tags">${work.user_tags.map((tag) => `<span class="tag"><button data-user-filter="${esc(tag)}">${esc(tag)}</button><button data-remove-user-tag="${esc(tag)}" aria-label="${esc(tag)} 제거">×</button></span>`).join("") || '<span class="muted">사용자 태그가 없습니다.</span>'}</div></section>
    <section class="detail-section"><h3>통합 태그</h3><div class="tags">${work.all_tags.map((tag) => `<button class="tag" data-tag="${esc(tag)}">${esc(tag)}</button>`).join("") || `<span class="muted">등록된 태그가 없습니다.</span>`}</div></section>
    <section class="detail-section"><h3>연결된 출처 <span class="muted">번호를 누르면 원본 페이지로 이동합니다.</span></h3>${work.sources.map((s) => `<div class="source-row"><div class="source-header"><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${providerName[s.provider]} #${esc(s.external_id)} ↗</a><button class="quiet" data-fetch="${s.id}">태그 가져오기</button><button class="quiet" data-comments="${s.id}">댓글 갱신</button></div><small>${s.status === "fetched" ? `수집 ${new Date(s.fetched * 1000).toLocaleString("ko-KR")}` : "수동 등록 · 원격 정보 미확인"} · 태그 ${s.tags.length} · 댓글 ${s.comments.length}</small><div class="tags">${s.tags.map((tag) => `<span class="tag">${esc(tag)}</span>`).join("")}</div>${s.comments.length ? `<details><summary>보관한 댓글 ${s.comments.length}개</summary>${s.comments.map((c) => `<div class="comment"><small>${esc(c.author)} · ${esc(c.posted_at)}</small>${esc(c.text)}</div>`).join("")}</details>` : ""}</div>`).join("") || `<p class="muted">같은 작품이 있는 사이트의 URL을 각각 연결하세요.</p>`}
    <details class="detail-section"><summary>출처 연결 · 태그·댓글 가져오기</summary><form id="source-form" class="source-form"><label>작품 URL<input name="url" type="url" required placeholder="https://…"></label><label>원본 태그<input name="tags" placeholder="쉼표로 구분 (선택)"></label><label>댓글 JSON (선택)<textarea name="comments" placeholder='[{"id":"1","author":"작성자","text":"댓글","posted_at":"2026-01-01"}]'></textarea></label><p class="muted">사이트별 정보를 따로 보존합니다. nHentai 공개 댓글 API 수집기는 실사이트 미검증입니다. E-Hentai·Hitomi 댓글은 JSON 가져오기를 사용하세요. 로그인·접근 제한은 우회하지 않습니다.</p><button class="primary">출처 저장</button></form></details></section>`;
    if (!$("#detail").open) $("#detail").showModal();
}
function jobDetails(job) {
    try { const result = JSON.parse(job.result || "{}"); return [result.directory ? `출력 폴더: ${result.directory}` : "", result.remote_job ? `원격 작업: ${result.remote_job}` : "", result.submission === "pending" ? "원격 접수 여부 확인 필요 · 자동 재제출 중지" : ""].filter(Boolean).map(esc).join(" · "); } catch { return ""; }
}
async function showJobs() {
    const jobs = await api("/api/jobs"); $("#job-count").textContent = jobs.filter((j) => ["queued", "running"].includes(j.state)).length;
    $("#jobs").innerHTML = jobs.length ? jobs.map((j) => `<article class="job"><div><div class="job-state">${statusName[j.state] || esc(j.state)} · ${j.engine === "lanraragi" ? "서버 플러그인" : "외부 엔진"}</div><div class="job-url">${esc(j.url)}</div><div class="job-message">${esc(j.message || (j.engine === "command" && j.state === "queued" ? "대상 기기의 다운로드 작업자가 가져가기를 기다립니다." : "서버 작업 대기 중"))}</div><small class="muted">${jobDetails(j)}</small></div><div class="job-target">${j.target === "nas" ? "NAS" : "내 PC"}${["failed", "blocked"].includes(j.state) ? `<p><button class="quiet" data-retry="${j.id}">${j.engine === "lanraragi" ? "상태 확인 · 재시도" : "다시 시도"}</button></p>` : ""}</div></article>`).join("") : `<div class="empty"><span>↓</span><h2>대기 중인 다운로드가 없습니다.</h2><p>작품 URL과 저장할 기기를 선택해 주세요.</p></div>`;
}
async function view(value) {
    if (value === "jobs") return navigateRoute({ kind: "jobs" });
    state.view = value; state.page = 1; return navigateLibrary();
}
async function sync() { $("#sync").disabled = true; try { const r = await api("/api/sync", {}); toast(`${r.synced}개 작품을 동기화했습니다.`); await load(); } finally { $("#sync").disabled = false; } }
function pageUrl(url, id) {
    const parsed = new URL(url.replace("/page&", "/page?"), location.origin);
    if (parsed.origin !== location.origin || parsed.pathname !== `/api/archives/${id}/page`) throw new Error("페이지 URL 형식이 올바르지 않습니다.");
    return `/api/media/${id}/page${parsed.search}`;
}
function readWork() {
    if (state.detail) return navigateRoute({ kind: "reader", id: state.detail.id, page: pendingReader?.id === state.detail.id ? pendingReader.page : Math.max(1, state.detail.progress || 1) });
}
function renderPage() {
    const reader = state.reader; const image = $("#reader-image");
    const displayedPage = reader.page + 1;
    image.onload = () => {
        if (state.reader !== reader || reader.page + 1 !== displayedPage) return;
        reader.work.progress = displayedPage;
        progressTask = progressTask.catch(() => {}).then(() => api(`/api/works/${reader.work.id}/progress`, { page: displayedPage })).catch((error) => toast(error.message));
    };
    image.onerror = () => toast("페이지를 아직 불러오지 못했습니다. 추출 상태를 확인한 뒤 다시 열어 주세요.");
    image.src = reader.pages[reader.page]; $("#reader-position").textContent = `${reader.page + 1} / ${reader.pages.length}`;
    $("#reader-prev").disabled = reader.page === 0; $("#reader-next").disabled = reader.page + 1 === reader.pages.length;
    $("#reader-page").max = String(reader.pages.length); $("#reader-page").value = String(displayedPage);
    document.title = `${displayedPage} / ${reader.pages.length} · ${reader.work.title} · Library Studio`;
    if (reader.pages[reader.page + 1]) { const next = new Image(); next.src = reader.pages[reader.page + 1]; }
}
function turnPage(delta) { if (!state.reader) return; const n = state.reader.page + delta; if (n >= 0 && n < state.reader.pages.length) { return navigateRoute({ kind: "reader", id: state.reader.work.id, page: n + 1 }); } }
function guard(fn) { return (...args) => Promise.resolve().then(() => fn(...args)).catch((e) => toast(e.message)); }
document.addEventListener("click", guard(async (event) => {
    if (event.target.closest(".card-select")) return;
    const button = event.target.closest("button,a,.card"); if (!button) return;
    if (button.dataset.close !== undefined) button.closest("dialog").close();
    if (button.dataset.view) await view(button.dataset.view);
    const provider = button.dataset.provider ?? button.dataset.filter;
    if (provider !== undefined) { state.provider = provider; state.page = 1; document.querySelectorAll("[data-filter]").forEach((b) => b.classList.toggle("selected", b.dataset.filter === provider)); await view("library"); }
    if (button.dataset.uploadWork) { $("#upload-dialog").close(); await showDetail(button.dataset.uploadWork); }
    if (button.dataset.id) await showDetail(button.dataset.id);
    if (button.dataset.rating) { await api(`/api/works/${state.detail.id}`, { rating: Number(button.dataset.rating) }); await showDetail(state.detail.id); }
    if (button.dataset.fetch) { button.disabled = true; try { await api(`/api/works/${state.detail.id}/sources/${button.dataset.fetch}/fetch`, {}); await showDetail(state.detail.id); toast("출처 태그를 갱신했습니다."); } finally { button.disabled = false; } }
    if (button.dataset.comments) { button.disabled = true; try { const result = await api(`/api/works/${state.detail.id}/sources/${button.dataset.comments}/comments/fetch`, {}); await showDetail(state.detail.id); toast(result.message); } finally { button.disabled = false; } }
    if (button.dataset.retry) { await api(`/api/jobs/${button.dataset.retry}/retry`, {}); await showJobs(); }
    if (button.dataset.userFilter) { state.tag = button.dataset.userFilter; state.allTag = ""; state.query = ""; $("#search").value = ""; state.page = 1; await navigateLibrary(); toast("사용자 태그: " + state.tag + " · 검색하면 필터가 해제됩니다."); }
    if (button.dataset.removeUserTag) { await api("/api/tags/batch", {work_ids:[state.detail.id],remove:[button.dataset.removeUserTag]}); await showDetail(state.detail.id); await load(); }
    if (button.id === "edit-user-tags") await openTagEditor([state.detail.id]);
    if (button.dataset.tag || button.dataset.filterTag) {
        state.allTag = button.dataset.filterTag || button.dataset.tag; state.tag = ""; state.page = 1;
        await navigateLibrary();
    }
}));
$("#grid").addEventListener("keydown", guard(async (e) => { if (e.key === "Enter" && e.target.dataset.id) await showDetail(e.target.dataset.id); }));
document.addEventListener("submit", guard(async (event) => {
    event.preventDefault(); const form = event.target; const data = Object.fromEntries(new FormData(form));
    if (form.id === "short-form") {
        const short = String(data.number || "").trim().toUpperCase();
        if (!/^[ENL]?[0-9]{1,32}$/.test(short)) throw new Error("히토미 숫자, E번호, N번호 또는 L번호를 입력하세요.");
        await navigateRoute({ kind: "detail", short });
    }
    if (form.id === "reader-jump") {
        if (!state.reader) return;
        const page = Number($("#reader-page").value);
        if (!Number.isInteger(page) || page < 1 || page > state.reader.pages.length) throw new Error("이동할 쪽 번호를 확인하세요.");
        await navigateRoute({ kind: "reader", id: state.reader.work.id, page });
    }
    if (form.id === "editor-form") { const work = await api("/api/works", { title: data.title, artist: data.artist }); if (data.url) await api(`/api/works/${work.id}/sources`, { url: data.url }); form.closest("dialog").close(); form.reset(); await load(); await showDetail(work.id); }
    if (form.id === "source-form") { const value = { url: data.url }; if (data.tags) value.tags = data.tags; if (data.comments) value.comments = JSON.parse(data.comments); await api(`/api/works/${state.detail.id}/sources`, value); await showDetail(state.detail.id); await load(); }
    if (form.id === "download-form") {
        $("#download-submit").disabled = true;
        try {
            const result = await api("/api/downloads", data);
            form.closest("dialog").close();
            if (result.state === "available") { await showDetail(result.work_id); toast("이미 보관함에 있습니다. 읽기 또는 PC로 받기를 이용하세요."); }
            else { await view("jobs"); toast("다운로드 대기열에 추가했습니다. 진행 상태를 확인하세요."); }
        } finally { $("#download-submit").disabled = false; }
    }
}));
$("#detail").addEventListener("click", guard(async (e) => {
    if (e.target.closest("#favorite-work")) { await api(`/api/works/${state.detail.id}`, { favorite: !state.detail.favorite }); await showDetail(state.detail.id); await load(); }
    if (e.target.closest("#read-work")) await readWork();
    if (e.target.closest("#edit-work")) {
        const section = document.createElement("section"); section.className = "detail-section";
        section.innerHTML = `<form id="work-form"><label>제목<input name="title" required value="${esc(state.detail.title)}"></label><label>작가<input name="artist" value="${esc(state.detail.artist)}"></label><p class="muted">저장하면 제목을 잠가 다음 동기화에서 덮어쓰지 않습니다.</p><button class="primary">저장</button></form>`;
        $("#detail-content").append(section); $("#edit-work").disabled = true;
    }
}));
document.addEventListener("submit", guard(async (e) => { if (e.target.id === "work-form") { const data = Object.fromEntries(new FormData(e.target)); await api(`/api/works/${state.detail.id}`, { ...data, title_locked: true }); await showDetail(state.detail.id); await load(); } }));
$("#sync").onclick = guard(sync); $("#empty-sync").onclick = guard(sync);
$("#add").onclick = () => $("#editor").showModal();
$("#queue").onclick = $("#download-open").onclick = () => $("#download-dialog").showModal();
let downloadRevision = 0;
function resetDownloadPreview() {
    downloadRevision++; $("#download-resolution").textContent = "";
    const provider = $("#download-form [name=provider]").value;
    $("#download-reference-help").textContent = provider === "ehentai" ? "E-Hentai는 처음 등록할 때 전체 URL이 필요합니다. 저장된 출처는 번호만 입력해도 됩니다." : "선택한 사이트의 작품 번호 또는 전체 URL을 입력하세요.";
}
$("#download-form [name=reference]").oninput = resetDownloadPreview;
$("#download-form [name=provider]").onchange = resetDownloadPreview;
$("#download-form [name=target]").onchange = () => {
    const pc = $("#download-form [name=target]").value === "pc";
    $("#download-form [name=engine] option[value=lanraragi]").disabled = pc;
    if (pc) $("#download-form [name=engine]").value = "command";
};
$("#download-preview").onclick = guard(async () => {
    const revision = downloadRevision;
    const data = Object.fromEntries(new FormData($("#download-form")));
    const result = await api("/api/downloads/resolve", data);
    if (revision !== downloadRevision) return;
    $("#download-resolution").textContent = `${providerName[result.provider]} #${result.external_id} · ${result.available ? "이미 보관함에 있음" : result.origin === "saved" ? "저장된 원본 URL 사용" : "입력 확인됨 · 원격 접근 미확인"}`;
});
$("#close-detail").onclick = guard(closeDetail); $("#close-reader").onclick = guard(closeReader);
$("#detail").addEventListener("cancel", (event) => { event.preventDefault(); closeDetail(); });
$("#reader").addEventListener("cancel", (event) => { event.preventDefault(); closeReader(); });
async function refreshTagFilter() {
    const query = $("#filter-tag-search").value;
    const tags = await api(`/api/library/tags?q=${encodeURIComponent(query)}`);
    if (query !== $("#filter-tag-search").value) return;
    $("#filter-tag-list").innerHTML = tags.map((item) => `<button class="tag" type="button" data-filter-tag="${esc(item.tag)}">${esc(item.tag)} · ${item.count}</button>`).join("") || '<p class="muted">일치하는 태그가 없습니다.</p>';
}
$("#filter-tags-nav").onclick = guard(async () => { $("#tag-filter").showModal(); await refreshTagFilter(); });
$("#filter-tag-search").oninput = () => { clearTimeout(state.filterTagTimer); state.filterTagTimer = setTimeout(guard(refreshTagFilter), 200); };
$("#clear-tag").onclick = guard(async () => { state.tag = ""; state.allTag = ""; state.page = 1; await navigateLibrary(); });
$("#open-number").onclick = () => $("#short-open").showModal();
$("#settings-button").onclick = () => $("#settings").showModal();
$("#thumbnail-blur").onchange = (e) => { settings.thumbnailBlur = e.target.checked; saveSettings(); };
$("#privacy-route").onclick = () => { settings.thumbnailBlur = !settings.thumbnailBlur; saveSettings(); };
$("#card-size").onchange = (e) => { settings.size = e.target.value; saveSettings(); };
$("#page-size").onchange = guard(async (e) => { settings.limit = Number(e.target.value); state.page = 1; saveSettings(); await load(); });
$("#read-direction").onchange = (e) => { settings.direction = e.target.value; saveSettings(); };
$("#layout").onclick = () => { settings.layout = settings.layout === "list" ? "grid" : "list"; saveSettings(); };
$("#direction").onclick = guard(async () => { state.direction = state.direction === "desc" ? "asc" : "desc"; $("#direction").textContent = state.direction === "desc" ? "↓" : "↑"; await load(); });
$("#sort").onchange = guard(async (e) => { state.sort = e.target.value; state.page = 1; await load(); });
$("#search").oninput = () => { clearTimeout(state.searchTimer); state.searchTimer = setTimeout(guard(async () => { state.tag = ""; state.query = $("#search").value; state.page = 1; await load(); }), 250); };
$("#previous").onclick = guard(async () => { state.page -= 1; await load(); }); $("#next").onclick = guard(async () => { state.page += 1; await load(); });
$("#reader-prev").onclick = () => turnPage(-1); $("#reader-next").onclick = () => turnPage(1);
document.addEventListener("keydown", (e) => { if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) return; if (e.key === "/" && !$("#detail").open && !$("#reader").open) { e.preventDefault(); $("#search").focus(); } if ($("#reader").open && ["ArrowLeft", "ArrowRight"].includes(e.key)) { e.preventDefault(); turnPage((e.key === "ArrowRight" ? 1 : -1) * (settings.direction === "rtl" ? -1 : 1)); } });
applySettings();
applyRoute(); guard(showJobs)();
guard(async () => { const health = await api("/api/health"); $("#connection-dot").classList.add(health.lanraragi_connected ? "online" : "offline"); $("#connection-text").innerHTML = health.lanraragi_connected ? `서버 연결됨<small>LANraragi ${esc(health.version)} · 개인 라이브러리</small>` : "서버 연결 필요<small>작품 정보는 로컬에 보존됩니다.</small>"; })();
setInterval(guard(async () => { if (state.view === "jobs" && !document.hidden) await showJobs(); }), 5000);

let uploadBusy = false;
let uploadSelection = null;
let uploadLimit = 512 * 1024 * 1024;
async function refreshUploads(sync = false) {
    if (sync) { try { await api("/api/uploads/sync", {}); } catch { /* Saved uploads remain downloadable while indexing is unavailable. */ } }
    const result = await api("/api/uploads"); uploadLimit = result.max_bytes;
    $("#upload-limit").textContent = result.enabled ? `파일당 최대 ${Math.floor(uploadLimit / 1048576)} MiB · 한 번에 최대 20개` : "업로드 전용 저장소를 먼저 연결해야 합니다.";
    $("#upload-start").disabled = uploadBusy || !result.enabled;
    $("#upload-list").innerHTML = result.items.map((file) => `<div class="upload-row"><div>${esc(file.original_name)}<small>${(file.bytes / 1048576).toFixed(1)} MiB · ${file.work_id ? "보관함 등록 완료" : file.state === "conflict" ? "보관함 ID 충돌 · 파일은 별도 보존됨" : "저장 완료 · 색인 대기"}</small></div><a class="quiet" href="/api/uploads/${file.sha256}/download" download>↓ 받기</a>${file.work_id ? `<button class="quiet" data-upload-work="${file.work_id}">열기</button>` : ""}</div>`).join("");
}
function uploadFile(file) {
    return new Promise((resolve, reject) => {
        const request = new XMLHttpRequest();
        request.open("POST", `/api/uploads?filename=${encodeURIComponent(file.name)}&tags=${encodeURIComponent(JSON.stringify(splitTags($("#upload-tags").value)))}`);
        request.setRequestHeader("Content-Type", "application/octet-stream");
        request.upload.onprogress = (event) => { if (event.lengthComputable) $("#upload-progress").value = event.loaded * 100 / event.total; };
        request.onload = () => { try { const value = JSON.parse(request.responseText); if (request.status >= 200 && request.status < 300) resolve(value); else reject(new Error(value.error || "업로드 실패")); } catch (error) { reject(error); } };
        request.onerror = () => reject(new Error("연결이 끊겼습니다. 업로드 목록을 확인한 뒤 다시 시도하세요."));
        request.send(file);
    });
}
$("#upload").onclick = guard(async () => { $("#upload-dialog").showModal(); await refreshUploads(); });
$("#upload-start").onclick = guard(async () => {
    if (uploadBusy) return;
    const files = uploadSelection || [...$("#upload-files").files];
    if (!files.length || files.length > 20) throw new Error("파일을 1~20개 선택하세요.");
    if (files.some((file) => !/\.(cbz|zip|pdf)$/i.test(file.name) || file.size < 1 || file.size > uploadLimit)) throw new Error("파일 형식과 크기 한도를 확인하세요.");
    uploadBusy = true; $("#upload-start").disabled = true; $("#upload-files").disabled = true; $("#upload-progress").hidden = false;
    try {
        for (const [index, file] of files.entries()) {
            $("#upload-status").textContent = `${index + 1}/${files.length} · ${file.name} 전송 중`;
            $("#upload-progress").value = 0;
            const result = await uploadFile(file);
            $("#upload-status").textContent = result.duplicate ? "이미 저장된 파일입니다." : "파일 저장 완료 · 보관함 색인 대기";
            await refreshUploads(true);
        }
        $("#upload-files").value = ""; $("#upload-folder").value = ""; uploadSelection = null; await load();
    } catch (error) { $("#upload-status").textContent = error.message; throw error; }
    finally { uploadBusy = false; $("#upload-start").disabled = false; $("#upload-files").disabled = false; await refreshUploads(); }
});
setInterval(guard(async () => { if ($("#upload-dialog").open && !uploadBusy && !document.hidden) { await refreshUploads(true); await load(); } }), 5000);

function updateSelection() {
    $("#selected-count").textContent = selectedWorks.size + "개 선택";
    $("#batch-tags").disabled = !selectedWorks.size;
    const boxes = [...document.querySelectorAll("[data-select-work]")];
    $("#select-page").checked = !!boxes.length && boxes.every((box) => selectedWorks.has(box.dataset.selectWork));
    $("#select-page").indeterminate = selectedWorks.size > 0 && !$("#select-page").checked;
}
document.addEventListener("change", (event) => {
    const box = event.target;
    if (box.dataset.selectWork) { if (box.checked) selectedWorks.add(box.dataset.selectWork); else selectedWorks.delete(box.dataset.selectWork); updateSelection(); }
});
$("#select-page").onchange = (event) => {
    document.querySelectorAll("[data-select-work]").forEach((box) => { box.checked = event.target.checked; if (box.checked) selectedWorks.add(box.dataset.selectWork); else selectedWorks.delete(box.dataset.selectWork); }); updateSelection();
};
async function tagSuggestions(query = "", prefix = "") {
    const rows = await api("/api/tags?q=" + encodeURIComponent(query));
    $("#tag-suggestions").innerHTML = rows.map((row) => `<option value="${esc(prefix + row.tag)}"></option>`).join("");
    return rows;
}
async function openTagEditor(ids) {
    tagTargets = [...ids]; $("#tag-form").reset(); $("#tag-dialog-title").textContent = ids.length + "개 작품 태그 편집";
    $("#tag-dialog").showModal(); await tagSuggestions();
}
$("#batch-tags").onclick = guard(() => openTagEditor([...selectedWorks]));
const splitTags = (value) => value.split(",").map((tag) => tag.trim()).filter(Boolean);
document.addEventListener("input", (event) => {
    if (event.target.getAttribute("list") !== "tag-suggestions") return;
    const value = event.target.value, cut = value.lastIndexOf(","), prefix = cut >= 0 ? value.slice(0, cut + 1) + " " : "";
    clearTimeout(state.tagTimer); state.tagTimer = setTimeout(guard(() => tagSuggestions(value.slice(cut + 1).trim(), prefix)), 200);
});
async function renderTagCatalog() {
    const rows = await tagSuggestions($("#tag-search").value);
    $("#tag-catalog").innerHTML = rows.map((row) => `<button type="button" class="tag" data-manage-tag="${esc(row.tag)}">${esc(row.tag)} · ${row.count} 작품</button>`).join("") || '<p class="muted">사용자 태그가 없습니다.</p>';
}
$("#manage-tags").onclick = guard(async () => { $("#tag-manager").showModal(); await renderTagCatalog(); });
$("#tag-search").oninput = () => { clearTimeout(state.catalogTimer); state.catalogTimer = setTimeout(guard(renderTagCatalog),200); };
$("#tag-catalog").onclick = (event) => { const button = event.target.closest("[data-manage-tag]"); if (button) $("#rename-tag-form").elements.source.value = button.dataset.manageTag; };
let renameTags;
document.addEventListener("submit", guard(async (event) => {
    if (event.target.id === "tag-form") {
        const form = event.target;
        await api("/api/tags/batch", {work_ids:tagTargets,add:splitTags(form.elements.add.value),remove:splitTags(form.elements.remove.value)});
        $("#tag-dialog").close(); if ($("#detail").open) await showDetail(state.detail.id); await load(); toast("사용자 태그를 저장했습니다.");
    }
    if (event.target.id === "rename-tag-form") {
        renameTags = Object.fromEntries(new FormData(event.target));
        $("#rename-summary").textContent = `‘${renameTags.source}’ 태그를 모든 작품에서 ‘${renameTags.target}’로 변경합니다. 출처 원본은 유지됩니다.`;
        $("#rename-confirm").showModal();
    }
}));
$("#rename-apply").onclick = guard(async () => {
    $("#rename-apply").disabled = true;
    try { const result = await api("/api/tags/rename", renameTags); if (state.tag === renameTags.source) state.tag = renameTags.target; $("#rename-confirm").close(); await renderTagCatalog(); if ($("#detail").open) await showDetail(state.detail.id); await load(); toast(result.updated + "개 작품의 태그를 변경했습니다."); }
    finally { $("#rename-apply").disabled = false; }
});

function chooseUploadFiles(files) {
    if (uploadBusy) return;
    uploadSelection = [...files].filter((file) => /\.(cbz|zip|pdf)$/i.test(file.name));
    $("#upload-status").textContent = uploadSelection.length + "개 압축 파일·PDF 선택됨 · 폴더 구조는 저장하지 않습니다.";
}
$("#upload-files").onchange = (event) => chooseUploadFiles(event.target.files);
$("#upload-folder").onchange = (event) => chooseUploadFiles(event.target.files);
$("#upload-drop").ondragover = (event) => { event.preventDefault(); };
$("#upload-drop").ondrop = (event) => { event.preventDefault(); chooseUploadFiles(event.dataTransfer.files); };
