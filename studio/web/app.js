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
const providerName = { ehentai: "E-Hentai", exhentai: "ExHentai", hitomi: "Hitomi", nhentai: "nHentai" };
const visibleTag = (tag) => !/^(date_added|timestamp|source):/i.test(tag);
const sourceMatchCandidates = new Map();
let autoSourceRequest = 0;
async function refreshAutomaticSources() {
    if (!state.detail || !$('#auto-source-state')) return;
    const workId = state.detail.id, request = ++autoSourceRequest;
    const value = await api(`/api/works/${workId}/source-linking`);
    if (state.detail?.id !== workId || request !== autoSourceRequest || !$('#auto-source-state')) return;
    const labels = {no_source:'기준 출처 URL 하나를 연결하면 자동으로 시작합니다.',queued:'다른 사이트의 작품 정보를 자동 확인할 예정입니다.',running:'다른 사이트의 같은 판본을 찾고 있습니다.',scanning:'저장한 검색 위치부터 다음 묶음을 자동 확인합니다.',waiting:'일부 사이트의 정상 접근·인증을 기다립니다. 자동으로 다시 확인합니다.',blocked:'반복 실패로 대기 중입니다. 로그인 상태가 바뀌면 자동으로 다시 확인합니다.',review:'확실하지 않은 후보는 아래에서 같은 판본인지 확인하세요.',complete:'연결된 출처 확인을 마쳤습니다.'};
    const sites = value.result?.sites || [];
    const names = {connected:'연결됨',session_required:'로그인 필요',service_update_required:'로그인 서비스 업데이트 대기',service_unavailable:'로그인 서비스 연결 대기',access_required:'접근 제한',unavailable:'연결 확인 필요',partial:'일부 확인 실패',scanning:'다음 묶음 확인 중',search_limit:'검색 범위 검토 필요',review:'판본 확인 필요',ownership_conflict:'다른 작품에 연결된 출처',no_candidates:'이번 검색 범위에 후보 없음',needs_artist:'작가 정보 필요'};
    $('#auto-source-state').textContent = (labels[value.state] || value.state) + ' ' + sites.map(site => `${providerName[site.provider]}: ${names[site.status] || site.status}`).join(' · ');
    const items = sites.filter(site => site.status !== 'connected').flatMap(site => site.items || []);
    sourceMatchCandidates.set(workId,items);
    const otherLanguagesOpen = $('#counterpart-results details')?.open || false;
    $('#counterpart-results').innerHTML = counterpartRows(items, state.detail);
    if ($('#counterpart-results details')) $('#counterpart-results details').open = otherLanguagesOpen;
    if (value.updated && state.detail.autoLinkUpdated !== value.updated) {
        const work = await api(`/api/works/${workId}`);
        if (state.detail?.id !== workId || request !== autoSourceRequest) return;
        state.detail = {...work,autoLinkUpdated:value.updated}; cacheWork(work);
        // Refresh source data only; never replace an open editor or media player.
        if ($('#connected-source-list')) $('#connected-source-list').innerHTML = sourceRows(work.sources);
        if ($('#combined-source-tags')) $('#combined-source-tags').innerHTML = work.all_tags.map(tag => `<button class="tag" data-tag="${esc(tag)}">${esc(tag)}</button>`).join('');
    }
}
const statusName = { queued: "대기 중", running: "진행 중", complete: "완료", failed: "실패", blocked: "확인 필요" };
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (s) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[s]));
function counterpartRows(items, work) {
    const languageNames = {korean:'한국어',japanese:'일본어',english:'영어',chinese:'중국어'};
    const languages = values => values.map(value => languageNames[value] || value).join(', ') || '미확인';
    const baseline = work.sources?.find(source => source.metadata?.languages?.length)?.metadata;
    const row = (item, index) => {
        const meta = item.metadata, match = item.comparison;
        let url = '';
        try {
            const parsed = new URL(meta.url);
            const host = {ehentai:'e-hentai.org',exhentai:'exhentai.org',hitomi:'hitomi.la',nhentai:'nhentai.net'}[meta.provider];
            if (parsed.protocol === 'https:' && parsed.hostname === host && !parsed.username && !parsed.password && !parsed.port) url = parsed.href;
        } catch {}
        const sameLanguage = match.language_match === true;
        const languageNote = sameLanguage ? '언어 일치' : baseline?.languages?.length && meta.languages.length ? '언어 다름 · 별도 판본' : '언어 미확인';
        const pageNote = match.page_match ? '페이지 일치' : baseline?.pages != null && meta.pages != null ? `페이지 다름 (${baseline.pages} / ${meta.pages})` : '페이지 미확인';
        return `<div class="source-row"><div class="source-header"><strong>${esc(item.display_title || meta.title)}</strong>${url ? `<a class="quiet" href="${esc(url)}" target="_blank" rel="noopener noreferrer">원문 열기</a>` : '<span class="muted">원문 주소 확인 필요</span>'}</div><p>${esc(providerName[meta.provider])} · ${esc(languages(meta.languages))} · ${languageNote}</p><small>제목 유사도 ${Math.round(match.title_similarity*100)}% · 작가 ${match.artist_match ? '일치' : '미확인'} · ${pageNote} · 태그 유사도 ${Math.round(match.tag_similarity*100)}%</small><p><button type="button" class="quiet" data-counterpart-select="${index}" ${sameLanguage && url ? '' : 'disabled'}>이 판본에 출처 연결</button></p></div>`;
    };
    const same = [], other = [];
    items.forEach((item,index) => (item.comparison.language_match ? same : other).push(row(item,index)));
    return `<p class="muted">기준 언어: ${esc(languages(baseline?.languages || []))}. 제목·작가·언어·페이지·태그를 비교한 후보이며, 검색이 끝난 뒤 조건을 모두 만족하는 유일 후보만 자동 연결합니다.</p>${same.join('') || '<p class="muted">같은 언어의 후보를 아직 확인하지 못했습니다.</p>'}${other.length ? `<details><summary>다른 언어·언어 미확인 후보 ${other.length}개</summary>${other.join('')}</details>` : ''}`;
}
// Modal dialogs live above normal z-index layers. Keep notices in the active
// dialog, and use a manual popover to avoid clipping in scrolling dialogs.
const toastDialogs = [];
function placeToast() {
    const el = $("#toast");
    for (const dialog of document.querySelectorAll("dialog[open]")) {
        if (!toastDialogs.includes(dialog)) toastDialogs.push(dialog);
    }
    for (let i = toastDialogs.length - 1; i >= 0; i--) {
        if (!toastDialogs[i].open) toastDialogs.splice(i, 1);
    }
    const parent = toastDialogs.at(-1) || document.body;
    if (typeof el.hidePopover === "function" && el.matches(":popover-open")) el.hidePopover();
    if (el.parentElement !== parent) parent.append(el);
    if (!el.hidden && typeof el.showPopover === "function") el.showPopover();
}
new MutationObserver(placeToast).observe(document.body, { subtree: true, attributes: true, attributeFilter: ["open"] });
function toast(message) {
    const el = $("#toast");
    el.textContent = message; el.hidden = false; placeToast();
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => {
        if (typeof el.hidePopover === "function" && el.matches(":popover-open")) el.hidePopover();
        el.hidden = true;
    }, 5500);
}
async function api(path, data, options = {}) {
    const response = await fetch(path, { ...(data === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }), ...options });
    let value;
    try { value = await response.json(); }
    catch (error) {
        if (error.name === 'AbortError') throw error;
        throw new Error(`Studio 서버 응답을 확인할 수 없습니다 (HTTP ${response.status}). 연결 상태를 확인하세요.`);
    }
    if (!response.ok) throw new Error(value.error || "요청을 처리하지 못했습니다.");
    return value;
}
const workShortIds = new Map(), shortWorkIds = new Map(), workAliases = new Map();
function cacheWork(work) {
    for (const alias of workAliases.get(work.id) || []) if (shortWorkIds.get(alias) === work.id) shortWorkIds.delete(alias);
    const aliases = new Set([work.short_id, `L${work.local_number}`]);
    for (const source of work.sources || []) {
        const prefix = { hitomi: "", ehentai: "E", exhentai: "X", nhentai: "N" }[source.provider];
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
        provider: ["ehentai", "exhentai", "hitomi", "nhentai"].includes(value.provider) ? value.provider : "", sort: ["added", "title", "artist", "pages", "bytes", "rating", "last_read", "random"].includes(value.sort) ? value.sort : "added",
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
    const short = /^\/([EXNL]?[0-9]{1,32})(?:\/([0-9]+))?$/.exec(raw.toUpperCase());
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
            renderDetail(state.detail); document.title = (state.detail.display_title || state.detail.title) + " · Library Studio"; return; }
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
            renderDetail(state.detail); document.title = (state.detail.display_title || state.detail.title) + " · Library Studio";
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
function workCoverURL(work) { return work.cover_asset_id ? `/api/voice/assets/${work.cover_asset_id}` : work.lrr_id ? `/api/media/${work.lrr_id}/thumbnail` : null; }
function cover(work) {
    const thumbnail = workCoverURL(work); const editionKind = (work.edition_summary || work.edition)?.kind || "comic";
    return `<div class="cover">${thumbnail ? `<img src="${thumbnail}" loading="lazy" decoding="async" alt="${esc(work.display_title || work.title)} 표지">` : `<div class="placeholder"><small>${editionKind === "comic" ? "파일 없음 · 정보만 등록" : "보이스코믹"}</small></div>`}<span class="pages">${editionKind === "comic" ? work.pages + " P" : editionKind === "voice_video" ? "보이스 · 영상" : "보이스 · 음성"}</span>${work.favorite ? `<span class="favorite-star" title="즐겨찾기"><svg class="icon" aria-hidden="true"><use href="#i-star"/></svg><span class="sr-only">즐겨찾기</span></span>` : ""}</div>`;
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
    $("#grid").innerHTML = result.items.map((work) => `<article class="card" data-id="${work.id}" data-short-id="${esc(work.short_id)}" tabindex="0" role="button" aria-label="${esc(work.display_title || work.title)} 상세 보기"><label class="card-select"><input type="checkbox" data-select-work="${work.id}" aria-label="${esc(work.display_title || work.title)} 선택"></label>${cover(work)}<div><h3>${esc(work.display_title || work.title)}</h3><div class="card-artist">${esc(work.artist || "작가 미등록")}</div>${work.edition_summary && (work.edition_summary.language || work.edition_summary.label) ? `<div class="muted">${esc([work.edition_summary.language,work.edition_summary.label].filter(Boolean).join(" · "))}</div>` : ""}</div><div class="card-sources">${sources(work)}</div></article>`).join("");
    updateSelection();
    $("#empty").hidden = result.items.length > 0;
    const filtered = Boolean(state.query || state.tag || state.allTag || state.provider || state.view === "favorite");
    $("#empty h2").textContent = filtered ? "조건에 맞는 작품이 없습니다" : "보관함을 채워 보세요";
    $("#empty p").textContent = filtered ? "검색어·태그·출처 필터를 바꾸거나 해제해 보세요." : "LANraragi 라이브러리를 동기화하거나 작품을 추가해 출처를 연결할 수 있습니다.";
    $("#empty-sync").hidden = filtered;
    $("#previous").disabled = state.page === 1; $("#next").disabled = state.page * settings.limit >= result.total;
    $("#page-number").textContent = `${state.page} / ${Math.max(1, Math.ceil(result.total / settings.limit))} 페이지`;
    libraryKey = routeHash({ kind: "library", library: displayedLibrary });
    refreshTagStrip().catch(() => {});
    await refreshLibraryStatus();
}
// Quick tag filter on the library screen: user tags first, then source tags by count.
let tagStripRequest = 0;
async function refreshTagStrip() {
    const request = ++tagStripRequest, tags = await api("/api/library/tags?q=");
    if (request !== tagStripRequest) return;
    const active = state.allTag || state.tag;
    let shown = [...tags.filter((t) => !t.tag.includes(":")), ...tags.filter((t) => t.tag.includes(":"))].slice(0, 14);
    if (active && !shown.some((t) => t.tag === active)) shown = [{ tag: active, count: null }, ...shown];
    const label = (tag) => { const i = tag.indexOf(":"); return i > 0 ? `<span class="ns">${esc(tag.slice(0, i + 1))}</span>${esc(tag.slice(i + 1))}` : esc(tag); };
    $("#tag-strip").innerHTML = shown.map((t) => `<button type="button" class="tag-chip${t.tag === active ? " selected" : ""}" data-strip-tag="${esc(t.tag)}" aria-pressed="${t.tag === active}">${label(t.tag)}${t.count == null ? "" : `<span class="count">${t.count}</span>`}${t.tag === active ? '<span aria-hidden="true">×</span>' : ""}</button>`).join("") + `<button type="button" class="tag-chip more" id="tag-strip-more">모든 태그</button>`;
    $("#tag-strip").hidden = !shown.length;
}
$("#tag-strip").addEventListener("click", guard(async (event) => {
    if (event.target.closest("#tag-strip-more")) { $("#tag-filter").showModal(); await refreshTagFilter(); return; }
    const chip = event.target.closest("[data-strip-tag]"); if (!chip) return;
    const tag = chip.dataset.stripTag;
    if (tag === (state.allTag || state.tag)) { state.tag = ""; state.allTag = ""; } else { state.allTag = tag; state.tag = ""; }
    state.page = 1; await navigateLibrary();
}));
async function refreshLibraryStatus() {
    try {
        const status = await api("/api/library/status");
        const counts = [`등록된 파일 ${status.indexed_archives.toLocaleString()}권`];
        if (status.uploaded_archives) counts.push(`업로드 기록이 연결된 파일 ${status.uploaded_archives.toLocaleString()}권`);
        if (status.voice_editions) counts.push(`보이스코믹 파일 ${status.voice_editions}판본`);
        if (status.metadata_only) counts.push(`정보만 등록 ${status.metadata_only.toLocaleString()}권`);
        if (status.pending_archives) counts.push(`업로드 색인 대기 ${status.pending_archives.toLocaleString()}개`);
        $("#library-status").textContent = `${counts.join(" · ")}. 연결된 NAS의 CBZ는 다시 업로드할 필요가 없습니다. 새 파일이 안 보이면 동기화하세요.`;
    } catch { $("#library-status").textContent = "라이브러리 상태를 확인하지 못했습니다. 잠시 후 동기화로 다시 확인하세요."; }
}
function sourceRows(sources) { return sources.map((s) => `<div class="source-row"><div class="source-header"><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${providerName[s.provider]} #${esc(s.external_id)} ↗</a><span class="source-actions"><button class="quiet" data-fetch="${s.id}">작품 정보 갱신</button><button class="quiet" data-comments="${s.id}">댓글 갱신</button></span></div><small>${s.metadata?.title ? `출처 제목: ${esc(s.display_title || s.metadata.title)} · ` : ""}${s.status === "fetched" ? `수집 ${new Date(s.fetched * 1000).toLocaleString("ko-KR")}` : "수동 등록 · 원격 정보 미확인"} · 태그 ${s.tags.length} · 댓글 ${s.comments.length}</small><div class="tags">${s.tags.filter(visibleTag).map((tag) => `<span class="tag">${esc(tag)}</span>`).join("")}</div>${s.comments.length ? `<details><summary>보관한 댓글 ${s.comments.length}개</summary>${s.comments.map((c) => `<div class="comment"><small>${esc(c.author)} · ${esc(c.posted_at)}</small>${esc(c.text)}</div>`).join("")}</details>` : ""}</div>`).join("") || `<p class="muted">같은 작품이 있는 사이트의 URL을 각각 연결하세요.</p>`; }
function renderDetail(work) {
    pauseVoicePlayers();
    $("#detail-content").innerHTML = `<div class="detail-layout">${cover(work)}<div><h2>${esc(work.display_title || work.title)}</h2><div class="card-artist">${esc(work.artist || "작가 미등록")}</div><div class="detail-meta"><span>번호 ${esc(work.short_id)}</span><span>${work.pages} 페이지</span><span>${(work.bytes / 1048576).toFixed(1)} MiB</span><span>${work.last_read ? `최근 열람 ${new Date(work.last_read * 1000).toLocaleDateString("ko-KR")}` : "열람 기록 없음"}</span></div><div class="rating" aria-label="별점">${[1, 2, 3, 4, 5].map((n) => `<button data-rating="${n}" aria-label="${n}점" aria-pressed="${n <= work.rating}" class="${n <= work.rating ? "on" : ""}"><svg class="icon" aria-hidden="true"><use href="#i-star"/></svg></button>`).join("")}<button data-rating="0" class="rating-clear" aria-label="별점 지우기">×</button></div><div class="detail-actions"><button class="primary" id="read-work" ${work.lrr_id || work.edition?.assets.some(a=>a.kind === "audio" || a.kind === "video") ? "" : "disabled"}>${work.edition?.kind === "voice_video" ? "▷ 보이스코믹 재생" : work.edition?.kind === "voice_pages" ? "▷ 만화+음성" : "▷ 읽기"}</button><button class="quiet" id="favorite-work">${work.favorite ? "즐겨찾기 해제" : "즐겨찾기"}</button>${work.lrr_id ? `<a class="quiet" href="/api/media/${work.lrr_id}/download" download>↓ PC로 받기</a>` : ""}<button class="quiet" id="edit-work">제목·작가 수정</button></div><p class="muted">${work.lrr_id ? "라이브러리에 저장된 만화 파일" : work.edition?.assets.some(asset => asset.kind !== "cover") ? "보이스코믹 미디어 연결됨" : "파일을 첨부하거나 만화 판본을 연결하세요."}</p></div></div>
    <section class="detail-section"><h3>내 태그 <button class="quiet" id="edit-user-tags">추가·삭제</button></h3><div class="tags">${work.user_tags.map((tag) => `<span class="tag"><button data-user-filter="${esc(tag)}">${esc(tag)}</button><button data-remove-user-tag="${esc(tag)}" aria-label="${esc(tag)} 제거">×</button></span>`).join("") || '<span class="muted">사용자 태그가 없습니다.</span>'}</div></section>
    <section class="detail-section"><h3>통합 태그</h3><div class="tags" id="combined-source-tags">${work.all_tags.map((tag) => `<button class="tag" data-tag="${esc(tag)}">${esc(tag)}</button>`).join("") || `<span class="muted">등록된 태그가 없습니다.</span>`}</div></section>
    <section class="detail-section"><h3>사이트 자동 연결</h3><p id="auto-source-state" role="status">자동 연결 상태 확인 중</p><div id="counterpart-results" role="status"></div><h3>연결된 출처 <span class="muted">번호를 누르면 원본 페이지로 이동합니다.</span></h3><div id="connected-source-list">${sourceRows(work.sources)}</div>
    <section class="detail-section"><h3>작품 URL로 자동 연결</h3><p class="muted">이헨·익헨·히토미의 작품 URL 하나를 저장하면 다른 사이트의 같은 작품을 자동으로 확인합니다. 로그인·접근 제한이 있으면 위의 자동 연결 상태에 표시됩니다.</p><form id="source-form" class="source-form"><label>작품 URL<input name="url" type="url" required placeholder="작품 상세 페이지의 전체 주소를 붙여 넣으세요"></label><button class="primary">URL 저장 · 자동 연결 시작</button><details><summary>태그·댓글 직접 입력 (선택)</summary><label>원본 태그<input name="tags" placeholder="쉼표로 구분"></label><label>댓글 JSON<textarea name="comments" placeholder='[{"id":"1","text":"댓글"}]'></textarea></label></details></form><details><summary>저장한 HTML 가져오기 (선택)</summary><form id="html-metadata-form"><h3>저장한 HTML에서 작품 정보 읽기</h3><label>원본 작품 URL<input name="url" type="url" required></label><label>저장한 HTML 파일<input id="metadata-file" type="file" accept=".html,.htm,.txt"></label><label>페이지 전체 HTML<textarea name="html" required placeholder="HTML을 데이터로만 읽습니다. 스크립트·광고·이미지는 실행하지 않습니다."></textarea></label><button id="metadata-preview" type="button" class="quiet">추출 미리보기</button><p id="metadata-preview-result" role="status"></p><button class="primary" type="submit" id="metadata-save" disabled>확인한 출처 정보 연결</button><p class="muted">기존 작품명·사용자 태그·파일은 유지합니다. 계정 정보가 포함된 HTML은 넣지 마세요.</p></form></details></section></section>`;
    renderEdition(work);
    refreshAutomaticSources().catch(() => {});
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
    if (state.detail?.edition?.kind !== "comic") {
        const player = $(state.detail?.edition?.kind === "voice_video" ? "#detail-content video" : "#detail-content audio");
        if (player) { player.scrollIntoView({block:"center"}); return player.play(); }
    }
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
    image.src = reader.pages[reader.page]; $("#reader-title").textContent = reader.work.display_title || reader.work.title; $("#reader-position").textContent = `${reader.page + 1} / ${reader.pages.length}`;
    $("#reader-prev").disabled = reader.page === 0; $("#reader-next").disabled = reader.page + 1 === reader.pages.length;
    $("#reader-page").max = String(reader.pages.length); $("#reader-page").value = String(displayedPage);
    document.title = `${displayedPage} / ${reader.pages.length} · ${reader.work.display_title || reader.work.title} · Library Studio`;
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
    if (button.id === "metadata-preview") {
        const form = $("#html-metadata-form"), snapshot = {url:form.elements.url.value,html:form.elements.html.value};
        const value = await api('/api/metadata/preview', snapshot);
        if (!form.isConnected || form.elements.url.value !== snapshot.url || form.elements.html.value !== snapshot.html) return;
        $("#metadata-preview-result").textContent = `${value.title} · ${value.artists.join(', ')} · ${value.languages.join(', ')} · 태그 ${value.tags.length} · 댓글 ${value.comments.length}`;
        $("#metadata-save").disabled = false;
    }
    if (button.dataset.counterpartSelect !== undefined) {
        const item = sourceMatchCandidates.get(state.detail.id)?.[Number(button.dataset.counterpartSelect)];
        if (!item) return;
        if (!item.comparison.language_match) throw new Error('언어가 같다고 확인된 후보만 이 판본에 연결할 수 있습니다.');
        await api(`/api/works/${state.detail.id}/sources`, {url:item.metadata.url,tags:item.metadata.tags,metadata:item.metadata,artist_if_empty:item.metadata.artists.join(', ').slice(0,500)});
        await showDetail(state.detail.id); await load(); toast('선택한 출처 정보를 연결했습니다.');
    }
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
        if (!/^[EXNL]?[0-9]{1,32}$/.test(short)) throw new Error("히토미 숫자, E번호, X번호, N번호 또는 L번호를 입력하세요.");
        await navigateRoute({ kind: "detail", short });
    }
    if (form.id === "reader-jump") {
        if (!state.reader) return;
        const page = Number($("#reader-page").value);
        if (!Number.isInteger(page) || page < 1 || page > state.reader.pages.length) throw new Error("이동할 쪽 번호를 확인하세요.");
        await navigateRoute({ kind: "reader", id: state.reader.work.id, page });
    }
    if (form.id === "editor-form") { const work = await api("/api/works", { title: data.title, artist: data.artist }); await api(`/api/works/${work.id}/edition`, {kind:data.kind || "comic",language:data.language || "",label:data.label || ""}); if (data.url) await api(`/api/works/${work.id}/sources`, { url: data.url }); form.closest("dialog").close(); form.reset(); await load(); await showDetail(work.id); }
    if (form.id === "source-form") { const value = { url: data.url }; if (data.tags) value.tags = data.tags; if (data.comments) value.comments = JSON.parse(data.comments); await api(`/api/works/${state.detail.id}/sources`, value); await showDetail(state.detail.id); await load(); }
    if (form.id === "html-metadata-form") {
        if ($("#metadata-save").disabled) return;
        $("#metadata-save").disabled = true;
        await api(`/api/works/${state.detail.id}/metadata`, {url:data.url,html:data.html});
        await showDetail(state.detail.id); await load(); toast('HTML의 작품 정보·태그·댓글을 출처에 연결했습니다.');
    }
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
$("#queue").onclick = $("#download-open").onclick = guard(async () => {
    $("#download-dialog").showModal();
    const status = await api('/api/downloads/status');
    const target = $('#download-form [name="target"]').value;
    $('#download-support').textContent = status.command_workers[target]
        ? '외부 작업자 연결됨 · 사이트별 실제 접근·다운로드 성공은 아직 미검증입니다.'
        : '외부 작업자가 연결되지 않았습니다. 서버 플러그인은 지원하는 URL만 처리하며, 로그인 세션은 외부 작업자에서 사용합니다.';
    if (status.command_workers[target]) $('#download-form [name="engine"]').value = 'command';
});
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
$('#automatic-source-links').onchange = guard(async event => {
    const value = await api('/api/source-linking',{enabled:event.target.checked});
    event.target.checked = value.enabled;
    toast(value.enabled ? '등록한 출처의 자동 연결을 켰습니다.' : '자동 출처 연결을 중지했습니다.');
});
api('/api/source-linking').then(value => { $('#automatic-source-links').checked = value.enabled; }).catch(() => {});
setInterval(() => { if ($('#detail').open && !document.hidden) refreshAutomaticSources().catch(() => {}); },4000);
$("#thumbnail-blur").onchange = (e) => { settings.thumbnailBlur = e.target.checked; saveSettings(); };
$("#privacy-route").onclick = () => { settings.thumbnailBlur = !settings.thumbnailBlur; saveSettings(); };
$("#card-size").onchange = (e) => { settings.size = e.target.value; saveSettings(); };
$("#page-size").onchange = guard(async (e) => { settings.limit = Number(e.target.value); state.page = 1; saveSettings(); await load(); });
$("#read-direction").onchange = (e) => { settings.direction = e.target.value; saveSettings(); };
$("#layout").onclick = () => { settings.layout = settings.layout === "list" ? "grid" : "list"; saveSettings(); };
$("#direction").onclick = guard(async () => { state.direction = state.direction === "desc" ? "asc" : "desc"; $("#direction").textContent = state.direction === "desc" ? "↓" : "↑"; await load(); });
$("#sort").onchange = guard(async (e) => { state.sort = e.target.value; state.page = 1; await load(); });
$("#search").oninput = () => { clearTimeout(state.searchTimer); state.searchTimer = setTimeout(guard(async () => {
    const query = $("#search").value;
    state.tag = ""; state.query = query; state.page = 1; await load();
    const tags = await api('/api/library/tags?q=' + encodeURIComponent(query));
    if ($("#search").value === query) $("#library-tag-suggestions").innerHTML = tags.slice(0,20).map(item => `<option value="${esc(item.tag)}" label="${item.count} 작품"></option>`).join('');
}), 250); };
document.addEventListener('input', event => {
    if (event.target.closest('#html-metadata-form')) {
        $("#metadata-save").disabled = true; $("#metadata-preview-result").textContent = '';
    }
});
document.addEventListener('change', guard(async event => {
    if (event.target.id !== 'metadata-file') return;
    const file = event.target.files[0]; if (!file) return;
    if (file.size > 2*1024*1024) throw new Error('HTML 파일은 최대 2MiB입니다.');
    const form = event.target.closest('form'), html = await file.text();
    if (!form.isConnected) return;
    form.elements.html.value = html; $("#metadata-save").disabled = true;
    $("#metadata-preview-result").textContent = '파일을 읽었습니다. 원본 URL을 입력하고 추출 미리보기를 누르세요.';
}));
$("#previous").onclick = guard(async () => { state.page -= 1; await load(); }); $("#next").onclick = guard(async () => { state.page += 1; await load(); });
$("#reader-prev").onclick = () => turnPage(-1); $("#reader-next").onclick = () => turnPage(1);
document.addEventListener("keydown", (e) => { if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) return; if (e.key === "/" && !$("#detail").open && !$("#reader").open) { e.preventDefault(); $("#search").focus(); } if ($("#reader").open && ["ArrowLeft", "ArrowRight"].includes(e.key)) { e.preventDefault(); turnPage((e.key === "ArrowRight" ? 1 : -1) * (settings.direction === "rtl" ? -1 : 1)); } });
// Phone navigation sheet; presentation only.
function setNav(open) { document.body.classList.toggle("nav-open", open); $("#nav-scrim").hidden = !open; $("#nav-toggle").setAttribute("aria-expanded", String(open)); }
$("#nav-toggle").onclick = () => setNav(!document.body.classList.contains("nav-open"));
$("#nav-scrim").onclick = () => setNav(false);
$("#sidebar").addEventListener("click", (e) => { if (e.target.closest("button,a")) setNav(false); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && document.body.classList.contains("nav-open")) { setNav(false); $("#nav-toggle").focus(); } });
applySettings();
applyRoute(); guard(showJobs)();
guard(async () => { const health = await api("/api/health"); $("#studio-version").textContent = Number.isInteger(health.studio_update) ? `Studio 업데이트 ${health.studio_update}` : "Studio 버전 표시 업데이트 대기"; $("#connection-dot").classList.add(health.lanraragi_connected ? "online" : "offline"); $("#connection-text").innerHTML = health.lanraragi_connected ? `서버 연결됨<small>LANraragi ${esc(health.version)} · 개인 라이브러리</small>` : "서버 연결 필요<small>작품 정보는 로컬에 보존됩니다.</small>"; })();
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

let organizePage = 1, organizeQuery = "", organizeBusy = false;
const organizeCandidates = new Map();
async function renderOrganization() {
    const result = await api(`/api/organization?page=${organizePage}&q=${encodeURIComponent(organizeQuery)}`);
    $("#organize-page").textContent = `${result.page} / ${Math.max(1, Math.ceil(result.total / result.limit))}`;
    $("#organize-prev").disabled = organizePage <= 1;
    $("#organize-next").disabled = organizePage * result.limit >= result.total;
    $("#organize-status").textContent = `${result.total}권 · 먼저 동기화하면 현재 파일명을 읽습니다. 대괄호의 값은 작가 추정이며 확인 후 저장하세요.`;
    $("#organize-items").innerHTML = result.items.map(work => {
        const hints = work.organization;
        return `<section class="detail-section" data-organize-work="${work.id}"><h3>${esc(work.display_title || work.title)}</h3><p class="muted">파일명: ${esc(work.archive_filename || "동기화 후 확인")}</p><p>${sources(work) || "연결된 출처 없음"}</p><form class="organize-artist"><label>작가<input name="artist" maxlength="500" value="${esc(work.artist || hints.artist)}"></label><button class="quiet">작가 저장</button></form><label>확인할 번호<input class="organize-number" inputmode="numeric" maxlength="12" value="${esc(hints.numbers.length === 1 ? hints.numbers[0].number : "")}" aria-label="확인할 작품 번호"></label><p class="muted">${hints.ambiguous ? "번호가 없거나 여러 개입니다. 확인할 번호를 직접 입력하세요." : "출처가 확정되지 않은 파일명 후보입니다."}</p><button class="quiet" data-match-work="${work.id}">세 사이트 함께 확인</button><div class="organize-results" aria-live="polite"></div><form class="organize-source"><label>원본 URL로 직접 연결<input name="url" type="url" required placeholder="https://…"></label><button class="quiet">URL 연결</button></form><p class="muted">통일 파일명 미리보기: ${esc(work.proposed_filename)}</p></section>`;
    }).join("") || '<p class="muted">표시할 작품이 없습니다. 라이브러리를 동기화하세요.</p>';
}
$("#organize-open").onclick = guard(async () => { $("#organize-dialog").showModal(); await renderOrganization(); });
$("#organize-artists").onclick = guard(async () => {
    const work_ids = [...$("#organize-items").querySelectorAll("[data-organize-work]")].map(section => section.dataset.organizeWork);
    if (!work_ids.length) return;
    const result = await api("/api/organization/artists", { work_ids });
    toast(`${result.updated}권의 빈 작가를 저장했습니다. 기존 작가는 유지됩니다.`);
    await renderOrganization(); await load();
});
$("#organize-artists-all").onclick = guard(async () => {
    const button = $("#organize-artists-all");
    button.disabled = true;
    try {
        const result = await api("/api/organization/artists/all", { scope: "library" });
        toast(`전체 라이브러리에서 ${result.updated}권의 빈 작가를 저장했습니다. 기존 작가는 유지됩니다.`);
        await renderOrganization(); await load();
    } finally { button.disabled = false; }
});
$("#organize-prev").onclick = guard(async () => { organizePage = Math.max(1, organizePage - 1); await renderOrganization(); });
$("#organize-next").onclick = guard(async () => { organizePage++; await renderOrganization(); });
$("#organize-search").onsubmit = guard(async event => { event.preventDefault(); organizeQuery = new FormData(event.target).get("query"); organizePage = 1; await renderOrganization(); });
$("#organize-items").addEventListener("submit", guard(async event => {
    if (event.target.matches(".organize-source")) {
        event.preventDefault();
        const id = event.target.closest("[data-organize-work]").dataset.organizeWork;
        await api(`/api/works/${id}/sources`, { url: new FormData(event.target).get("url") });
        toast("입력한 원본 URL을 연결했습니다. 원격 정보는 아직 미확인입니다.");
        await renderOrganization(); await load(); return;
    }
    if (!event.target.matches(".organize-artist")) return;
    event.preventDefault();
    const id = event.target.closest("[data-organize-work]").dataset.organizeWork;
    await api(`/api/works/${id}`, { artist: new FormData(event.target).get("artist") });
    toast("작가를 저장했습니다. 다음 동기화에서도 유지됩니다.");
    await renderOrganization(); await load();
}));
$("#organize-items").addEventListener("click", guard(async event => {
    const check = event.target.closest("[data-match-work]");
    const select = event.target.closest("[data-match-select]");
    if (check) {
        if (organizeBusy) return toast("진행 중인 사이트 확인을 기다려 주세요.");
        const section = check.closest("[data-organize-work]"), results = section.querySelector(".organize-results");
        const number = section.querySelector(".organize-number").value.trim();
        if (!/^[0-9]{1,12}$/.test(number)) return toast("확인할 번호를 입력하세요.");
        organizeBusy = true; check.disabled = true; results.textContent = "세 사이트 메타데이터 확인 중…";
        try {
            const value = await api(`/api/works/${check.dataset.matchWork}/matches`, { number });
            organizeCandidates.set(check.dataset.matchWork, value.items);
            results.innerHTML = value.items.map((item, index) => `<div class="source-row"><h4>${providerName[item.provider]} · ${esc(item.number)}</h4><p>${esc(item.title || ({ not_found: "해당 번호 없음", needs_url: "원본 URL 필요", access_required: "접근 제한·로그인 필요", invalid_response: "응답 검증 실패", unavailable: "연결 확인 필요" })[item.status] || "미확인")}</p><p>${esc(item.artists.join(", "))}</p><p class="muted">${esc(item.message)}</p>${item.status === "found" ? `<a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">원본 확인 ↗</a> <button class="quiet" data-match-select="${index}">이 출처 연결${item.artists.length ? "·빈 작가 채우기" : ""}</button>` : ""}</div>`).join("");
        } catch (error) { results.textContent = error.message; } finally { organizeBusy = false; check.disabled = false; }
    }
    if (select) {
        const id = select.closest("[data-organize-work]").dataset.organizeWork;
        const item = organizeCandidates.get(id)?.[Number(select.dataset.matchSelect)];
        if (!item || item.status !== "found") return;
        select.disabled = true;
        await api(`/api/works/${id}/sources`, { url: item.url, artist_if_empty: item.artists.join(", ") });
        toast("선택한 출처를 연결했습니다. 빈 작가는 후보에서 채우고 기존 작가는 유지합니다.");
        await renderOrganization(); await load();
    }
}));

const voicePositions = new Map(), voiceSaves = new Map();
let visualIndexCancelled = false;
function saveVoice(element, force = false) {
    if (!element.dataset.asset || !Number.isFinite(element.currentTime)) return;
    const id = element.dataset.asset, position = element.ended ? 0 : element.currentTime;
    voicePositions.set(id, position);
    if (!force && Date.now() - Number(element.dataset.savedAt || 0) < 5000) return;
    element.dataset.savedAt = String(Date.now());
    const previous = voiceSaves.get(id) || Promise.resolve();
    voiceSaves.set(id, previous.catch(() => {}).then(() => api(`/api/works/${element.dataset.work}/voice/${id}/progress`, { position })).catch(error => toast(error.message)));
}
function pauseVoicePlayers() {
    document.querySelectorAll('#detail-content audio, #detail-content video').forEach(element => { saveVoice(element, true); element.pause(); });
}
$('#detail').addEventListener('close', pauseVoicePlayers);
window.addEventListener('pagehide', pauseVoicePlayers);
function renderEdition(work) {
    const e = work.edition;
    if (!e) return;
    const kinds = {comic:'만화',voice_video:'보이스코믹 · 영상',voice_pages:'보이스코믹 · 만화+음성'};
    const section = document.createElement('section'); section.className = 'detail-section edition-section';
    section.innerHTML = `<h3>판본 · 보이스코믹</h3>${workCoverURL(work) ? '<div class="form-actions"><button class="quiet search-this-cover">이 표지로 비슷한 작품 찾기</button><button class="quiet save-this-cover">외부 검색용 표지 저장</button></div>' : ""}<p>${esc(kinds[e.kind])} · ${esc(e.language || '언어 미등록')} · ${esc(e.label || '판본 이름 미등록')}</p><div class="edition-siblings">${e.siblings.map(item => `<button class="quiet" data-edition-go="${item.id}" ${item.id === work.id ? 'disabled' : ''}>${esc(item.language || kinds[item.kind])} · ${esc(item.label || item.title)} · L${item.local_number}</button>`).join('') || '<p class="muted">이 판본은 아직 다른 판본과 묶지 않았습니다.</p>'}</div><details><summary>판본 정보 · 같은 작품 연결</summary><form class="edition-config"><label>형태<select name="kind">${Object.entries(kinds).map(([key,value]) => `<option value="${key}" ${e.kind === key ? 'selected' : ''}>${value}</option>`).join('')}</select></label><label>언어<input name="language" maxlength="200" value="${esc(e.language)}"></label><label>판본 이름<input name="label" maxlength="200" value="${esc(e.label)}" placeholder="원본 · 번역팀 · 보이스판"></label><label>번역자·번역팀<input name="translator" maxlength="200" value="${esc(e.translator)}"></label><label>함께 재생할 만화 번호<input name="comic_reference" placeholder="이 판본에 만화가 있으면 비워두세요. 다른 판본이면 L번호" value="${esc(e.comic_work_id ? (e.comic_work_id === work.id ? '' : 'L' + e.comic_local_number) : '')}"></label><p class="muted">음성형은 이 판본의 만화 또는 직접 지정한 만화 판본을 사용합니다. 페이지 연결 시간은 음성별로 저장합니다.</p><button class="quiet">판본 정보 저장</button></form><form class="edition-group"><label>같은 작품의 다른 판본 번호<input name="reference" required placeholder="L번호 · 연결된 출처 번호"></label><button class="quiet">같은 작품으로 묶기</button></form><button type="button" class="quiet edition-ungroup">이 판본을 묶음에서 분리</button><p class="muted">파일·출처·댓글·읽기 기록은 판본마다 보존됩니다. 번호만 같다고 자동으로 묶지 않습니다. 같은 출처 URL은 원래 연결한 판본에 유지하고 다른 판본은 위에서 이동하세요.</p></details><form class="voice-upload"><label>영상·음성·표지 첨부<input type="file" name="files" accept=".mp4,.webm,.mp3,.m4a,.wav,.flac,.ogg,.jpg,.jpeg,.png,.webp" multiple required></label><p class="muted">전용 Studio 저장소에 첨부합니다. 만화 파일은 기존 CBZ 등록을 사용하세요. 영상·음성 코덱은 브라우저 지원 범위에서 재생하며 자동 변환하지 않습니다.</p><button class="quiet">선택 파일 첨부</button><p class="voice-upload-status" role="status"></p></form><div class="voice-assets">${e.assets.map(asset => `<div class="voice-track" data-track="${asset.id}"><h4>${esc(asset.name)}</h4>${asset.kind === 'cover' ? '<span class="muted">표지 이미지</span>' : `<${asset.kind === 'video' ? 'video' : 'audio'} controls playsinline preload="metadata" data-asset="${asset.id}" data-work="${work.id}" src="/api/voice/assets/${asset.id}"></${asset.kind === 'video' ? 'video' : 'audio'}><label>재생 속도<select class="voice-speed">${[0.75,1,1.25,1.5,2].map(rate => `<option value="${rate}" ${rate===1?'selected':''}>${rate}배</option>`).join('')}</select></label><p class="voice-status muted" role="status">이어 듣기 ${Math.floor(asset.position)}초</p>`}<a class="quiet" href="/api/voice/assets/${asset.id}?download=1" download>파일 다운로드</a>${asset.kind === 'audio' && e.kind === 'voice_pages' ? `<div class="voice-comic"><p class="voice-page-label" role="status"></p><img class="voice-page" alt="보이스코믹 페이지" hidden><div class="form-actions"><button type="button" class="quiet voice-pages-retry">만화 페이지 다시 불러오기</button><button type="button" class="quiet voice-cue-prev">이전 페이지</button><button type="button" class="quiet voice-cue-next">다음 페이지</button></div><details><summary>페이지별 음성 시작 시간</summary><form class="voice-cues"><label>쪽=초 (한 줄에 하나)<textarea name="cues" placeholder="1=0&#10;2=12.5">${asset.cues.map(cue => `${cue.page}=${cue.second}`).join('\n')}</textarea></label><button class="quiet">페이지 연결 저장</button></form></details></div>` : ''}</div>`).join('')}</div>`;
    $('#detail-content').append(section);
    if (workCoverURL(work)) {
        section.querySelector('.search-this-cover').onclick = guard(async () => { const response = await fetch(workCoverURL(work)); if (!response.ok) throw new Error('표지를 읽을 수 없습니다.'); $('#visual-dialog').showModal(); await runVisualSearch(await response.blob()); });
        section.querySelector('.save-this-cover').onclick = guard(async () => {
            const response = await fetch(workCoverURL(work)); if (!response.ok) throw new Error('표지를 읽을 수 없습니다.');
            const blob = await response.blob(), url = URL.createObjectURL(blob), link = document.createElement('a');
            link.href = url; link.download = 'cover.' + ({'image/png':'png','image/webp':'webp','image/jpeg':'jpg'}[blob.type] || 'img'); link.click(); setTimeout(() => URL.revokeObjectURL(url),30000);
            $('#visual-dialog').showModal(); toast('저장한 표지를 외부 검색 사이트에서 직접 선택하세요.');
        });
    }
    section.querySelector('.edition-config').onsubmit = guard(async event => { event.preventDefault(); await api(`/api/works/${work.id}/edition`,Object.fromEntries(new FormData(event.target))); await showDetail(work.id); await load(); });
    section.querySelector('.edition-group').onsubmit = guard(async event => { event.preventDefault(); await api(`/api/works/${work.id}/edition/group`,Object.fromEntries(new FormData(event.target))); await showDetail(work.id); });
    section.querySelector('.edition-ungroup').onclick = guard(async () => { await api(`/api/works/${work.id}/edition/ungroup`,{}); await showDetail(work.id); });
    section.querySelectorAll('[data-edition-go]').forEach(button => { button.onclick = guard(() => showDetail(button.dataset.editionGo)); });
    section.querySelector('.voice-upload').onsubmit = guard(async event => {
        event.preventDefault(); const form = event.target, files = [...form.querySelector('input').files], button = form.querySelector('button'), status = form.querySelector('.voice-upload-status');
        if (files.length > 20) throw new Error('한 번에 최대 20개 파일을 첨부하세요.');
        button.disabled = true;
        try {
            for (const [index,file] of files.entries()) {
                status.textContent = `${index+1}/${files.length} 첨부 중…`;
                const response = await fetch(`/api/works/${work.id}/voice/upload?filename=${encodeURIComponent(file.name)}`,{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});
                const result = await response.json(); if (!response.ok) throw new Error(result.error || '첨부 실패');
            }
            await showDetail(work.id); await load(); toast('파일을 첨부했습니다.');
        } finally { button.disabled = false; }
    });
    for (const asset of e.assets) {
        const track = section.querySelector(`[data-track="${asset.id}"]`), player = track.querySelector('audio,video');
        if (!player) continue;
        player.addEventListener('loadedmetadata', () => { const position = voicePositions.get(asset.id) ?? asset.position; if (position > 0 && Number.isFinite(player.duration)) player.currentTime = Math.min(position, Math.max(0,player.duration-0.05)); });
        player.addEventListener('timeupdate', () => saveVoice(player));
        for (const event of ['pause','seeked','ended']) player.addEventListener(event, () => saveVoice(player,true));
        player.addEventListener('play', () => section.querySelectorAll('audio,video').forEach(other => { if (other !== player) other.pause(); }));
        player.addEventListener('error', () => { track.querySelector('.voice-status').textContent = '이 브라우저에서 재생하지 못했습니다. 코덱과 파일 상태를 확인하거나 다운로드하세요.'; });
        track.querySelector('.voice-speed').onchange = event => { player.playbackRate = Number(event.target.value); };
        if (asset.kind !== 'audio' || e.kind !== 'voice_pages') continue;
        let pages = [], lastPage = 0;
        const renderCue = () => {
            const cue = [...asset.cues].reverse().find(cue => cue.second <= player.currentTime);
            if (!pages.length) return;
            if (!cue) { lastPage=0; track.querySelector('.voice-page').hidden=true; track.querySelector('.voice-page-label').textContent='이 시간에 연결된 페이지가 없습니다.'; return; }
            if (cue.page>pages.length) { track.querySelector('.voice-page-label').textContent = '연결한 페이지가 만화 범위를 벗어납니다. 시간표를 수정하세요.'; return; }
            if (lastPage === cue.page) return;
            lastPage = cue.page; const image = track.querySelector('.voice-page');
            image.src = pageUrl(pages[cue.page-1],e.comic_lrr_id); image.hidden = false;
            track.querySelector('.voice-page-label').textContent = `${cue.page} / ${pages.length} 페이지`;
        };
        const refreshPages = async () => {
            if (!e.comic_lrr_id) { track.querySelector('.voice-page-label').textContent='먼저 만화 판본을 연결하세요.'; return; }
            track.querySelector('.voice-page-label').textContent='만화 페이지 준비 중…';
            try {
                const value = await api(`/api/media/${e.comic_lrr_id}/files`); pages = Array.isArray(value.pages) ? value.pages : [];
                track.querySelector('.voice-page-label').textContent = pages.length ? `${pages.length}페이지 준비됨 · 페이지별 시작 시간을 등록하세요.` : '페이지를 준비하고 있습니다. 잠시 후 다시 불러오세요.';
                lastPage=0; renderCue();
            } catch (error) { track.querySelector('.voice-page-label').textContent = error.message; }
        };
        track.querySelector('.voice-pages-retry').onclick = refreshPages;
        refreshPages();
        player.addEventListener('timeupdate', renderCue); player.addEventListener('seeked', renderCue);
        track.querySelector('.voice-cues').onsubmit = guard(async event => {
            event.preventDefault(); const text = new FormData(event.target).get('cues').trim();
            const cues = text ? text.split(/\r?\n/).map(line => { const match = /^\s*(\d+)\s*=\s*(\d+(?:\.\d+)?)\s*$/.exec(line); if (!match) throw new Error('쪽=초 형식으로 입력하세요.'); return {page:Number(match[1]),second:Number(match[2])}; }) : [];
            await api(`/api/works/${work.id}/voice/${asset.id}/cues`,{cues}); await showDetail(work.id);
        });
        for (const [selector,direction] of [['.voice-cue-prev',-1],['.voice-cue-next',1]]) track.querySelector(selector).onclick = () => {
            if (!asset.cues.length) return;
            let index = asset.cues.findLastIndex(cue => cue.second <= player.currentTime);
            index = Math.max(0,Math.min(asset.cues.length-1,index+direction)); player.currentTime = asset.cues[index].second; renderCue();
        };
    }
}

async function imageFingerprint(source) {
    const image = await createImageBitmap(source);
    try {
        if (image.width * image.height > 40000000) throw new Error('이미지 해상도가 너무 큽니다. 작은 사본을 사용하세요.');
        const canvas = document.createElement('canvas'); canvas.width = 9; canvas.height = 8;
        const context = canvas.getContext('2d',{willReadFrequently:true}); context.fillStyle = '#fff'; context.fillRect(0,0,9,8); context.drawImage(image,0,0,9,8);
        const pixels = context.getImageData(0,0,9,8).data;
        const luminance = index => pixels[index*4]*0.299 + pixels[index*4+1]*0.587 + pixels[index*4+2]*0.114;
        let hash = 0n;
        for (let y=0;y<8;y++) for (let x=0;x<8;x++) hash = (hash<<1n) | (luminance(y*9+x)>luminance(y*9+x+1) ? 1n : 0n);
        return hash.toString(16).padStart(16,'0');
    } finally { image.close(); }
}
$('#visual-open').onclick = () => $('#visual-dialog').showModal();
$('#visual-index-stop').onclick = () => { visualIndexCancelled = true; };
$('#visual-index').onclick = guard(async () => {
    const button = $('#visual-index'), status = $('#visual-index-status'); button.disabled = true;
    let indexed = 0, skipped = 0; visualIndexCancelled = false; $('#visual-index-stop').hidden = false;
    try {
        for (let page=1;page<=834;page++) {
            const result = await api(`/api/works?page=${page}&limit=120&sort=added&direction=asc`), items=[];
            if (result.total>100000) throw new Error('표지 색인 범위를 초과했습니다.');
            for (const work of result.items) {
                if (visualIndexCancelled) break;
                const url = workCoverURL(work);
                if (!url) continue;
                try { const response = await fetch(url,{cache:'reload'}); if (!response.ok) throw new Error('표지 확인 실패'); if (Number(response.headers.get('Content-Length'))>10*1024*1024) { await response.body.cancel(); throw new Error('표지 크기 초과'); } const blob = await response.blob(); if (blob.size>10*1024*1024) throw new Error('표지 크기 초과'); items.push({work_id:work.id,fingerprint:await imageFingerprint(blob)}); }
                catch { skipped++; }
                status.textContent = `표지 ${indexed+items.length}개 처리 · 실패 ${skipped}개`;
            }
            if (items.length) { await api('/api/visual/index',{items}); indexed += items.length; }
            if (visualIndexCancelled || page*120>=result.total) break;
        }
        status.textContent = `${indexed}개 표지 색인 ${visualIndexCancelled ? '중지됨' : '완료'} · 실패 ${skipped}개. 표지가 바뀌면 다시 갱신하세요.`;
    } finally { button.disabled = false; $('#visual-index-stop').hidden = true; }
});
async function runVisualSearch(blob) {
    if (blob.size>10*1024*1024) throw new Error('10MiB 이하 이미지를 사용하세요.');
    const result = await api('/api/visual/search',{fingerprint:await imageFingerprint(blob)});
    $('#visual-results').innerHTML = `<p class="muted">색인 ${result.indexed}개 · 비슷한 표지 후보 ${result.items.length}개. 지문 거리 0이 가장 비슷하며 같은 작품이라는 증거는 아닙니다.</p>` + result.items.map(item => `<button class="visual-result quiet" data-visual-work="${item.work.id}">${cover(item.work)}<span>${esc(item.work.display_title || item.work.title)} · 거리 ${item.distance}</span></button>`).join('');
    $('#visual-results').querySelectorAll('[data-visual-work]').forEach(button => { button.onclick = guard(async () => { $('#visual-dialog').close(); await showDetail(button.dataset.visualWork); }); });
}
$('#visual-file').onchange = guard(async event => {
    const file = event.target.files[0]; if (!file) return;
    if (!['image/jpeg','image/png','image/webp'].includes(file.type) || file.size>10*1024*1024) throw new Error('10MiB 이하 JPG·PNG·WebP 이미지를 선택하세요.');
    await runVisualSearch(file);
});

// Credentials travel only to the operator-configured NAS login service. Neither
// typed text nor session cookies are stored in the catalog/localStorage.
let loginSession = null, loginTimer = null, loginBusy = false;
const connectionStateName = { not_configured: '로그인 서비스 설치 필요', not_saved: '저장된 세션 없음', saved_unverified: '세션 저장됨 · 실제 접근 미검증', unavailable: '세션 만료 또는 파일 확인 필요' };
function clearLoginPreview() {
    clearTimeout(loginTimer); loginSession = null;
    $('#login-controls').hidden = true; $('#login-screen').removeAttribute('src'); $('#login-text').value = '';
}
function renderLoginFrame(frame) {
    if (!$('#connections-dialog').open) return;
    loginSession = frame.session;
    $('#login-controls').hidden = false;
    $('#login-screen').src = frame.image;
    $('#login-location').textContent = frame.location;
    $('#login-save').textContent = frame.browser_mode === 'desktop' ? '일반 브라우저 계정 세션 저장' : '로그인 완료 · 세션 저장';
    $('#login-restriction').hidden = !frame.restricted_request;
    $('#login-restriction').textContent = frame.blocked_navigation
        ? '허용 범위 밖으로 이동하려는 요청이 차단됐습니다. 로그인 진행이 안 되면 취소하고 이 상태를 알려주세요.'
        : '일부 외부 요소 요청이 차단됐습니다. 이 안내만으로 로그인 실패를 뜻하지 않습니다. 입력란이 보이면 로그인할 수 있습니다.';
    $('#connections-status').textContent = frame.response_status >= 400
        ? `로그인 사이트가 HTTP ${frame.response_status}을 반환했습니다. 사이트가 접근을 거부하거나 오류가 난 상태일 수 있습니다.`
        : frame.browser_mode === 'desktop' ? '일반 Chromium 원격 화면입니다. 사이트 인증과 로그인은 화면에서 직접 진행하세요.' : 'NAS 브라우저 화면이 열렸습니다. 아래 화면의 입력란을 선택해 로그인하세요.';
}
function sessionRequestNote(request) {
    if (!request) return ' · 최근 정보 조회 기록 없음';
    const mode = {no_matching_cookies:'요청 주소에 적용되는 쿠키 없음', not_sent:'요청하지 않음', saved_session:'저장 세션 사용', anonymous:'비로그인 요청', unusable_session:'저장 세션 사용 불가'}[request.mode] || '상태 확인 필요';
    const outcome = {ok:'응답 수신 · 로그인 유효성 미확인', session_required:'세션 재등록 필요', access_required:'사이트 추가 인증·접근 제한', unavailable:'네트워크·서버 연결 실패', not_found:'항목 없음', invalid_response:'응답 형식 오류', response_limit:'응답 크기 초과'}[request.status] || '확인 필요';
    const reason = {certificate_error:'인증서 검증 실패',tls_error:'TLS 연결 실패',dns_error:'DNS 조회 실패',timeout:'연결 시간 초과',connection_reset:'연결 초기화',connection_refused:'연결 거부',response_decode_error:'응답 문자 해석 실패',network_error:'네트워크 연결 실패'}[request.error_kind];
    return ` · 최근 조회: ${mode} / ${outcome}${typeof reason === 'string' ? ` · ${reason}` : ''}${request.http_status ? ` (HTTP ${request.http_status})` : ''}`;
}
$('#session-import-form').onsubmit = guard(async event => {
    event.preventDefault();
    if (loginBusy) return;
    const input = $('#session-import-file'), text = $('#session-import-text'), file = input.files[0];
    const pasted = text.value.trim();
    if (file && pasted) throw new Error('붙여넣기와 파일 중 하나만 선택하세요.');
    if (!file && !pasted) throw new Error('세션 내용을 붙여 넣거나 파일을 선택하세요.');
    if ((file && file.size > 131072) || new TextEncoder().encode(pasted).length > 131072) {
        input.value = ''; text.value = '';
        throw new Error('세션 내용은 128 KiB 이하여야 합니다.');
    }
    loginBusy = true; $('#session-import-submit').disabled = true;
    let content = '';
    try {
        content = file ? await file.text() : pasted; input.value = ''; text.value = '';
        await api('/api/site-connections', {op:'import-session', provider:$('#session-import-provider').value, content});
        content = '';
        toast('계정 세션을 NAS에 저장했습니다. 사이트 접근은 자동 연결 작업에서 확인합니다.');
        await connectionStatus();
    } finally { content = ''; input.value = ''; text.value = ''; loginBusy = false; $('#session-import-submit').disabled = false; }

});
async function connectionStatus() {
    const status = await api('/api/site-connections');
    const desktopMissing = status.browser_mode === 'desktop' && !status.desktop_available;
    if (status.browser_mode === 'desktop') $('#login-mode-note').textContent = '일반 Chromium 원격 화면입니다. 사람 인증과 로그인은 직접 진행합니다. 계정 세션 저장은 명시적으로 선택할 때만 수행하며 사람 인증 쿠키는 다운로드 작업자에 전달하지 않습니다. 실제 사이트 지원은 별도 확인이 필요합니다.';
    $('#connections-status').textContent = status.configured ? 'NAS 로그인 서비스 연결됨 · 실제 사이트 지원은 별도 검증합니다.' : 'NAS 로그인 서비스가 아직 설치되지 않았습니다. 다운로드 엔진과 전용 세션 저장 공간을 추가해야 합니다.';
    if (desktopMissing) $('#connections-status').textContent = '일반 브라우저 실행 패키지가 아직 설치되지 않았습니다. NAS 전용 브라우저 구성 연결이 필요합니다.';
    $('#session-import-submit').disabled = !status.configured || !status.session_import;
    $('#session-import-note').textContent = status.session_import ? '등록 후 자동 연결 작업이 다시 확인합니다. 저장 성공과 사이트 접근 성공은 별도로 표시합니다.' : '로그인 서비스의 세션 등록 기능 업데이트를 기다립니다.';
    $('#connections-sites').innerHTML = status.sites.map(s => `<div class="connection-site${s.last_request && s.last_request.status !== 'ok' ? ' failed' : ''}"><span><strong>${esc(s.name)}</strong> · ${esc(connectionStateName[s.state] || s.state)}${esc(sessionRequestNote(s.last_request))}</span><button class="quiet" data-site-start="${esc(s.provider)}" ${!status.configured || !s.login_available || desktopMissing ? 'disabled' : ''}>로그인 열기</button><button class="quiet" data-site-forget="${esc(s.provider)}" ${!status.configured || s.state === 'not_saved' ? 'disabled' : ''}>저장 세션 해제</button></div>`).join('');
    if (status.active) {
        loginSession = status.active.session;
        await loginOperation({ op: 'frame' });
    } else clearLoginPreview();
}
function scheduleLoginFrame() {
    clearTimeout(loginTimer);
    if (loginSession && $('#connections-dialog').open) loginTimer = setTimeout(() => {
        if (loginBusy) { scheduleLoginFrame(); return; }
        guard(() => loginOperation({ op: 'frame' }))();
    }, 2000);
}
async function loginOperation(operation) {
    if (loginBusy) return;
    loginBusy = true; clearTimeout(loginTimer);
    $('#login-controls').querySelectorAll('button,input').forEach(el => el.disabled = true);
    let savedNow = false;
    try {
        const result = await api('/api/site-connections', { ...operation, session: loginSession });
        if (result.image) renderLoginFrame(result);
        if (result.save_error) $('#connections-status').textContent = '브라우저의 세션 저장 응답이 없습니다. 로그인 상태를 확인하고 다시 저장하세요.';
        if (result.saving) $('#connections-status').textContent = '일반 브라우저의 계정 세션을 NAS에 저장하는 중입니다. 사람 인증 쿠키는 작업자로 전달하지 않습니다.';
        if (result.session_saved) {
            await api('/api/site-connections', { op: 'cancel', session: loginSession });
            clearLoginPreview();
            toast('계정 세션을 NAS에 저장했습니다. 실제 다운로드 지원은 별도 확인이 필요합니다.');
            savedNow = true;
        }
        if ((operation.op === 'save' && !result.saving) || operation.op === 'cancel') {
            clearLoginPreview();
            if (operation.op === 'save') toast('세션을 NAS에 저장했습니다. 실제 접근 성공은 아직 미검증입니다.');
        }
    } catch (error) {
        clearTimeout(loginTimer); throw error;
    } finally {
        loginBusy = false;
        $('#login-controls').querySelectorAll('button,input').forEach(el => el.disabled = false);
    }
    if (savedNow) await connectionStatus();
    scheduleLoginFrame();
}
$('#connections-open').onclick = guard(async () => { $('#connections-dialog').showModal(); await connectionStatus(); });
$('#connections-refresh').onclick = guard(connectionStatus);
$('#connections-dialog').addEventListener('close', () => {
    clearTimeout(loginTimer); $('#session-import-text').value = ''; $('#session-import-file').value = ''; $('#login-text').value = ''; $('#login-screen').removeAttribute('src');
});
$('#connections-sites').onclick = guard(async event => {
    const button = event.target.closest('button');
    if (!button || loginBusy) return;
    if (button.dataset.siteStart) {
        loginBusy = true; button.disabled = true;
        const began = Date.now(), originalLabel = button.textContent;
        const progress = () => { $('#connections-status').textContent = `NAS 브라우저에서 로그인 화면을 여는 중… ${Math.floor((Date.now() - began) / 1000)}초`; };
        progress(); button.textContent = '여는 중…';
        const timer = setInterval(progress, 1000);
        const controller = new AbortController();
        const deadline = setTimeout(() => controller.abort(), 50000);
        try {
            const frame = await api('/api/site-connections', { op: 'start', provider: button.dataset.siteStart }, { signal: controller.signal });
            clearInterval(timer);
            renderLoginFrame(frame);
            scheduleLoginFrame();
        } catch (error) {
            clearInterval(timer);
            const message = error.name === 'AbortError' ? '로그인 화면 열기가 시간 제한을 넘었습니다. 상태 새로고침으로 창이 열렸는지 확인하세요.' : error.message;
            $('#connections-status').textContent = message;
            throw new Error(message);
        } finally { clearInterval(timer); clearTimeout(deadline); loginBusy = false; button.disabled = false; button.textContent = originalLabel; }
    }
    if (button.dataset.siteForget) {
        if (!confirm('이 사이트의 NAS 저장 세션을 해제할까요? 원본 파일과 작품 정보는 유지됩니다.')) return;
        await api('/api/site-connections', { op: 'forget', provider: button.dataset.siteForget });
        await connectionStatus();
    }
});
$('#login-screen').onclick = guard(async event => {
    if (loginBusy || !loginSession) return;
    const box = event.currentTarget.getBoundingClientRect();
    await loginOperation({ op: 'click', x: Math.min(999, Math.max(0, (event.clientX - box.left) * 1000 / box.width)), y: Math.min(699, Math.max(0, (event.clientY - box.top) * 700 / box.height)) });
    $('#login-text').focus();
});
$('#login-text-form').onsubmit = guard(async event => {
    event.preventDefault(); if (loginBusy || !loginSession) return;
    const text = $('#login-text').value; $('#login-text').value = '';
    if (text) await loginOperation({ op: 'text', text });
});
$('#login-controls').addEventListener('click', guard(async event => {
    const button = event.target.closest('button');
    if (!button || loginBusy) return;
    if (button.dataset.loginKey) await loginOperation({ op: 'key', key: button.dataset.loginKey });
    if (button.dataset.loginScroll) await loginOperation({ op: 'scroll', delta: Number(button.dataset.loginScroll) });
}));
$('#login-visit').onclick = guard(() => loginOperation({ op: 'visit' }));
$('#login-save').onclick = guard(async () => { await loginOperation({ op: 'save' }); await connectionStatus(); });
$('#login-cancel').onclick = guard(async () => { await loginOperation({ op: 'cancel' }); await connectionStatus(); });
