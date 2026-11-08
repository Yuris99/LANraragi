"""Shared Library kit served by the Studio hub at /_library/* and /login.

Kept as one Python module so it ships through the existing Studio update
channel (which only deploys root *.py and three web files). Every section
(만화 · 음성 · 룰렛 · CYOA · 실사) loads tokens.css and shell.js from here.
"""

TYPES = {'css': 'text/css; charset=utf-8', 'js': 'text/javascript; charset=utf-8', 'html': 'text/html; charset=utf-8'}

ASSETS = {}

ASSETS['tokens.css'] = r'''/* Library design tokens — the single visual base for every section
   (만화 · 음성 · 룰렛 · CYOA · 실사). Grown from the manga Studio:
   warm near-black ground, elevation by lightness, one amber hue for reading
   data and the active state. Sections map their own variables onto these.
   Served at /_library/tokens.css. Change values here, not per app. */
:root{
  color-scheme:dark;
  /* Ground and elevation */
  --lib-bg:#0e0d0c;
  --lib-surface:#171615;
  --lib-raised:#211f1d;
  --lib-hover:#2a2826;
  --lib-overlay:rgba(8,7,6,.72);
  /* Lines */
  --lib-line:#2b2927;
  --lib-control:#4a4642;
  /* Text (floor 12px, running text 14–15px) */
  --lib-text:#f1f0ee;
  --lib-muted:#c2bcb4;
  --lib-text-bright:#ffffff;
  --lib-on-text:#141210;
  --lib-faint:#a29b92;
  /* One accent, plus status */
  --lib-accent:#e8b04a;
  --lib-accent-ink:#1a1408;
  --lib-accent-soft:rgba(232,176,74,.14);
  --lib-danger:#f08a7a;
  --lib-danger-bg:#2c1a17;
  --lib-success:#8fc79a;
  --lib-success-bg:#16241a;
  --lib-warning:#ecd77a;
  --lib-warning-bg:#262212;
  /* Shape */
  --lib-radius:8px;
  --lib-radius-sm:4px;
  --lib-radius-lg:12px;
  --lib-radius-pill:999px;
  --lib-shadow-pop:0 10px 40px rgb(0 0 0 / .5);
  --lib-shadow-dialog:0 24px 80px rgb(0 0 0 / .6);
  /* Spacing scale (4px base) */
  --lib-space-1:4px;--lib-space-2:8px;--lib-space-3:12px;--lib-space-4:16px;
  --lib-space-5:24px;--lib-space-6:32px;--lib-space-7:48px;
  /* Type */
  --lib-font:Pretendard,"Pretendard Variable","Apple SD Gothic Neo","Malgun Gothic","Noto Sans KR","Segoe UI",system-ui,sans-serif;
  --lib-font-mono:ui-monospace,"Cascadia Mono",Consolas,monospace;
  --lib-text-xs:12px;--lib-text-sm:13px;--lib-text-md:14px;--lib-text-lg:17px;--lib-text-xl:22px;
  /* Motion */
  --lib-ease:cubic-bezier(.2,.7,.2,1);
  --lib-fast:120ms;--lib-med:200ms;
  /* Sections switch from their own title menu, so nothing is reserved at the top.
     Kept at 0 for section CSS that offsets fixed parts by it. */
  --lib-bar-h:0px;
}
/* Section accents: everything else is shared; only the one accent hue changes.
   Same lightness band so every accent reads equally on the shared dark ground
   (all >= 7:1 against --lib-bg). Kept apart from --lib-danger and --lib-success.
   A section sets <html data-library-section="..."> (shell.js also sets it). */
:root{
  --lib-accent-manga:#e8b04a;     /* 호박 */
  --lib-accent-audio:#5ec8b6;     /* 청록 */
  --lib-accent-roulette:#ee8fc4;  /* 장미 */
  --lib-accent-cyoa:#ab9ff2;      /* 보라 */
  --lib-accent-real:#72b6ec;      /* 하늘 */
}
html[data-library-section="audio"]{--lib-accent:var(--lib-accent-audio);--lib-accent-ink:#06201c;--lib-accent-soft:rgba(94,200,182,.14)}
html[data-library-section="roulette"]{--lib-accent:var(--lib-accent-roulette);--lib-accent-ink:#2a0d1d;--lib-accent-soft:rgba(238,143,196,.14)}
html[data-library-section="cyoa"]{--lib-accent:var(--lib-accent-cyoa);--lib-accent-ink:#17122e;--lib-accent-soft:rgba(171,159,242,.14)}
html[data-library-section="real"]{--lib-accent:var(--lib-accent-real);--lib-accent-ink:#0a1a28;--lib-accent-soft:rgba(114,182,236,.14)}
@media (prefers-reduced-motion:reduce){:root{--lib-fast:0ms;--lib-med:0ms}}
'''

ASSETS['bar.css'] = r'''/* Section switch menu, loaded into the menu's shadow root by shell.js. */
:host{all:initial;font-family:var(--lib-font,system-ui,sans-serif)}
*{box-sizing:border-box}
.menu{position:fixed;min-width:208px;max-width:calc(100vw - 16px);padding:6px;display:flex;flex-direction:column;gap:2px;
  background:var(--lib-raised,#211f1d);border:1px solid var(--lib-line,#2b2927);border-radius:var(--lib-radius-lg,12px);
  box-shadow:var(--lib-shadow-pop,0 10px 40px rgb(0 0 0 / .5));color:var(--lib-text,#f1f0ee);font-size:14px;line-height:1.4;
  transform-origin:top left;animation:in var(--lib-fast,120ms) var(--lib-ease,ease-out)}
@keyframes in{from{opacity:0;transform:translateY(-4px) scale(.98)}}
.head.item{color:var(--lib-text,#f1f0ee);font-weight:650;letter-spacing:-.01em;padding-left:6px}
.mark{display:flex;align-items:flex-end;gap:2px;width:24px;height:24px;padding:5px 5px 4px;border-radius:6px;background:var(--lib-surface,#171615)}
.mark i{display:block;width:3px;border-radius:1px;background:var(--lib-text,#f1f0ee)}
.mark i:nth-child(1){height:12px}.mark i:nth-child(2){height:9px;background:var(--lib-accent,#e8b04a)}.mark i:nth-child(3){height:14px}
a,button{font:inherit;color:inherit;text-decoration:none;background:none;border:0;cursor:pointer;text-align:left;-webkit-tap-highlight-color:transparent}
.item{display:flex;align-items:center;gap:10px;height:36px;padding:0 10px;border-radius:var(--lib-radius,8px);color:var(--lib-muted,#c2bcb4);width:100%}
.item svg{width:17px;height:17px;flex:none}
.item:hover,.item:focus-visible{background:var(--lib-surface,#171615);color:var(--lib-text,#f1f0ee);outline:none}
.item:focus-visible{box-shadow:inset 0 0 0 2px var(--lib-text,#f1f0ee)}
.item[aria-current="page"]{color:var(--lib-text,#f1f0ee);font-weight:600}
.item[aria-current="page"] svg{color:var(--lib-accent,#e8b04a)}
.item[aria-current="page"]::after{content:"";margin-left:auto;width:6px;height:6px;border-radius:50%;background:var(--lib-accent,#e8b04a)}
.item:not([aria-current]):hover svg{color:var(--tab-accent)}
.tab-manga{--tab-accent:var(--lib-accent-manga,#e8b04a)}.tab-audio{--tab-accent:var(--lib-accent-audio,#5ec8b6)}
.tab-roulette{--tab-accent:var(--lib-accent-roulette,#ee8fc4)}.tab-cyoa{--tab-accent:var(--lib-accent-cyoa,#ab9ff2)}
.tab-real{--tab-accent:var(--lib-accent-real,#72b6ec)}
hr{border:0;border-top:1px solid var(--lib-line,#2b2927);margin:4px 2px}
.out{color:var(--lib-faint,#a29b92)}
@media (pointer:coarse){.item{height:44px}}
@media (prefers-reduced-motion:reduce){.menu{animation:none}}
'''

ASSETS['shell.js'] = r'''// Library section switch. One script for every section:
//   <link rel="stylesheet" href="/_library/tokens.css">
//   <script src="/_library/shell.js" defer></script>
// Nothing is reserved at the top of the page. The section's own title
// (.lib-section-title, or any element marked data-library-switcher) becomes a
// button that opens a small menu of sections plus logout. The menu renders in a
// shadow root so section CSS (Stash, roulette…) cannot restyle it.
(() => {
    if (window.__libraryShell || !document.body) return;
    window.__libraryShell = true;

    const SECTIONS = [
        { id: 'manga', label: '만화', href: '/manga', match: p => !/^\/(audio|roulette|cyoa|real|diet)(\/|$)/.test(p),
          icon: '<path d="M4 5.5c2.6-1 5-1 8 1 3-2 5.4-2 8-1v13c-2.6-1-5-1-8 1-3-2-5.4-2-8-1z"/><path d="M12 6.5v13"/>' },
        { id: 'audio', label: '음성', href: '/audio/', match: p => /^\/audio(\/|$)/.test(p),
          icon: '<path d="M4 15v-3a8 8 0 0 1 16 0v3"/><rect x="3.5" y="14" width="4" height="6" rx="1.5"/><rect x="16.5" y="14" width="4" height="6" rx="1.5"/>' },
        { id: 'roulette', label: '룰렛', href: '/roulette/', match: p => /^\/roulette(\/|$)/.test(p),
          icon: '<circle cx="12" cy="12" r="8.5"/><path d="M12 3.5V12l6 6M12 12l-6 6"/><circle cx="12" cy="12" r="1.6"/>' },
        { id: 'cyoa', label: 'CYOA', href: '/cyoa/', match: p => /^\/cyoa(\/|$)/.test(p),
          icon: '<circle cx="6" cy="5.5" r="2"/><circle cx="6" cy="18.5" r="2"/><circle cx="18" cy="12" r="2"/><path d="M6 7.5v9M6 10c0 2 2 2 4 2h6"/>' },
        { id: 'real', label: '실사', href: '/real/', match: p => /^\/real(\/|$)/.test(p),
          icon: '<rect x="3.5" y="6.5" width="17" height="12.5" rx="2"/><path d="M8.5 6.5 10 4h4l1.5 2.5"/><circle cx="12" cy="12.7" r="3.3"/>' },
    ];
    const current = SECTIONS.find(s => s.match(location.pathname)) || SECTIONS[0];
    const html = document.documentElement;
    html.classList.add('library-' + current.id);
    // Sections should also put data-library-section in their HTML so the accent is right before this runs.
    if (!html.dataset.librarySection) html.dataset.librarySection = current.id;

    const svg = body => `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
    const TRIGGERS = '[data-library-switcher], .lib-section-title, html[data-library-section="real"] .navbar-brand';

    const host = document.createElement('library-menu');
    host.style.cssText = 'position:fixed;inset:0 auto auto 0;z-index:2147483000;display:block';
    host.hidden = true;
    const root = host.attachShadow({ mode: 'open' });
    root.innerHTML = `
<link rel="stylesheet" href="/_library/bar.css">
<div class="menu" role="menu" aria-label="Library 섹션">
  <a class="item head" role="menuitem" href="/" title="Library 허브"><span class="mark" aria-hidden="true"><i></i><i></i><i></i></span><span>Library</span></a>
  <hr>
  ${SECTIONS.map(s => `<a class="item tab-${s.id}" role="menuitem" href="${s.href}"${s === current ? ' aria-current="page"' : ''}>${svg(s.icon)}<span>${s.label}</span></a>`).join('')}
  <hr>
  <button class="item out" type="button" role="menuitem">${svg('<path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 16l-4-4 4-4M6 12h10"/>')}<span>로그아웃</span></button>
</div>`;
    const menu = root.querySelector('.menu');
    const items = () => [...root.querySelectorAll('.item')];
    let opener = null;

    root.querySelector('.out').addEventListener('click', async () => {
        try { await fetch('/api/session/logout', { method: 'POST', credentials: 'same-origin' }); } catch (_) { /* go to login anyway */ }
        location.assign('/login');
    });

    function close(focusBack) {
        if (host.hidden) return;
        host.hidden = true;
        if (opener) { opener.setAttribute('aria-expanded', 'false'); if (focusBack) opener.focus(); }
        opener = null;
    }
    function open(trigger) {
        opener = trigger;
        trigger.setAttribute('aria-expanded', 'true');
        host.hidden = false;
        const r = trigger.getBoundingClientRect();
        const w = menu.offsetWidth, h = menu.offsetHeight;
        const left = Math.max(8, Math.min(r.left, innerWidth - w - 8));
        const below = r.bottom + 6;
        menu.style.left = left + 'px';
        menu.style.top = (below + h > innerHeight - 8 ? Math.max(8, r.top - h - 6) : below) + 'px';
        (root.querySelector('[aria-current]') || items()[0]).focus();
    }

    function enhance(el) {
        if (el.dataset.libraryTrigger) return;
        el.dataset.libraryTrigger = '1';
        if (!/^(A|BUTTON)$/.test(el.tagName)) { el.setAttribute('role', 'button'); el.tabIndex = 0; }
        el.setAttribute('aria-haspopup', 'menu');
        el.setAttribute('aria-expanded', 'false');
        el.title = el.title || '섹션 이동';
        el.style.cursor = 'pointer';
        // Caret right after the section name, before any <small> subtitle.
        const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, { acceptNode: n => n.textContent.trim() ? 1 : 3 });
        const name = walker.nextNode();
        const caret = document.createElement('span');
        caret.setAttribute('aria-hidden', 'true');
        caret.style.cssText = 'display:inline-block;width:14px;height:14px;margin-left:6px;vertical-align:-1px;opacity:.55';
        caret.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>';
        // Sit beside the highest wrapper of the name that holds no subtitle, so a
        // translation script rewriting the name's own <span> keeps the caret.
        let spot = name;
        while (spot && spot.parentNode !== el && !spot.parentNode.querySelector('small')) spot = spot.parentNode;
        if (spot) spot.after(caret); else el.append(caret);
        const toggle = event => {
            event.preventDefault(); event.stopPropagation();
            if (opener === el) close(false); else { close(false); open(el); }
        };
        el.addEventListener('click', toggle);
        el.addEventListener('keydown', event => {
            if (event.key === 'Enter' || event.key === ' ' || event.key === 'ArrowDown') toggle(event);
        });
    }
    const scan = () => document.querySelectorAll(TRIGGERS).forEach(enhance);

    root.addEventListener('keydown', event => {
        const list = items(), i = list.indexOf(root.activeElement);
        // Close only the menu, not the section's own sheet or dialog behind it.
        if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(true); }
        else if (event.key === 'ArrowDown') { event.preventDefault(); list[(i + 1) % list.length].focus(); }
        else if (event.key === 'ArrowUp') { event.preventDefault(); list[(i - 1 + list.length) % list.length].focus(); }
        else if (event.key === 'Home') { event.preventDefault(); list[0].focus(); }
        else if (event.key === 'End') { event.preventDefault(); list[list.length - 1].focus(); }
        else if (event.key === 'Tab') close(false);
    });
    document.addEventListener('pointerdown', event => { if (!event.composedPath().includes(host)) close(false); }, true);
    addEventListener('resize', () => close(false));
    addEventListener('scroll', () => close(false), true);

    document.body.append(host);
    scan();
    // Single-page sections (Stash, roulette) render their titles later.
    let pending = 0;
    new MutationObserver(() => { pending ||= requestAnimationFrame(() => { pending = 0; scan(); }); }).observe(document.body, { childList: true, subtree: true });
})();
'''

ASSETS['login.css'] = r'''*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--lib-bg);color:var(--lib-text);font-family:var(--lib-font);font-size:var(--lib-text-md);line-height:1.55;-webkit-font-smoothing:antialiased;word-break:keep-all}
.login{min-height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:var(--lib-space-5);padding:var(--lib-space-6) var(--lib-space-4)}
.brand{display:flex;gap:12px;align-items:center;font-size:var(--lib-text-lg);font-weight:600;letter-spacing:-.01em}
.brand small{display:block;font-size:var(--lib-text-xs);font-weight:400;color:var(--lib-faint);letter-spacing:0;margin-top:1px}
.mark{display:flex;align-items:flex-end;gap:2px;width:32px;height:32px;padding:6px 6px 5px;border-radius:7px;background:var(--lib-raised)}
.mark i{display:block;width:5px;border-radius:1px;background:var(--lib-text)}
.mark i:nth-child(1){height:18px}.mark i:nth-child(2){height:14px;background:var(--lib-accent)}.mark i:nth-child(3){height:20px}
.card{width:100%;max-width:360px;display:flex;flex-direction:column;gap:var(--lib-space-2);background:var(--lib-surface);border:1px solid var(--lib-line);border-radius:var(--lib-radius-lg);padding:var(--lib-space-5)}
h1{margin:0;font-size:var(--lib-text-xl);font-weight:650;letter-spacing:-.02em}
.lead{margin:0 0 var(--lib-space-3);color:var(--lib-muted)}
label{font-size:var(--lib-text-sm);color:var(--lib-muted)}
input{font:inherit;background:var(--lib-bg);border:1px solid var(--lib-control);border-radius:var(--lib-radius);color:var(--lib-text);padding:10px 12px;min-height:44px;width:100%}
input:focus-visible,button:focus-visible{outline:2px solid var(--lib-text);outline-offset:2px}
button{font:inherit;font-weight:600;margin-top:var(--lib-space-3);min-height:44px;border:0;border-radius:var(--lib-radius);background:var(--lib-text);color:var(--lib-bg);cursor:pointer;transition:opacity var(--lib-fast)}
button:hover{opacity:.9}
button:disabled{opacity:.5;cursor:default}
.error{margin:var(--lib-space-1) 0 0;padding:8px 10px;border-radius:var(--lib-radius);background:var(--lib-danger-bg);color:var(--lib-danger);font-size:var(--lib-text-sm)}
[hidden]{display:none!important}
'''

ASSETS['login.js'] = r'''// Hub login. Only same-site relative paths are accepted as the return address.
(() => {
    const raw = new URLSearchParams(location.search).get('next') || '/';
    const next = /^\/(?![\/\\])/.test(raw) && !raw.startsWith('/login') ? raw : '/';
    const form = document.getElementById('login-form');
    const input = document.getElementById('password');
    const error = document.getElementById('login-error');
    const submit = document.getElementById('login-submit');

    fetch('/api/session', { credentials: 'same-origin' })
        .then(r => r.ok ? r.json() : null)
        .then(v => { if (v && v.authenticated) location.replace(next); })
        .catch(() => {});

    form.addEventListener('submit', async event => {
        event.preventDefault();
        error.hidden = true;
        if (!input.value) { error.textContent = '비밀번호를 입력하세요.'; error.hidden = false; input.focus(); return; }
        submit.disabled = true; submit.textContent = '확인 중…';
        try {
            const response = await fetch('/api/session/login', {
                method: 'POST', credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password: input.value }),
            });
            if (response.ok) { location.replace(next); return; }
            const value = await response.json().catch(() => ({}));
            error.textContent = value.error || `로그인하지 못했습니다 (HTTP ${response.status}).`;
        } catch (_) {
            error.textContent = '서버에 연결할 수 없습니다. 잠시 후 다시 시도하세요.';
        }
        error.hidden = false; input.select();
        submit.disabled = false; submit.textContent = '로그인';
    });
})();
'''

ASSETS['login.html'] = r'''<!doctype html>
<html lang="ko">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>Library 로그인</title>
<link rel="stylesheet" href="/_library/tokens.css"><link rel="stylesheet" href="/_library/login.css">
<script src="/_library/login.js" defer></script></head>
<body>
<main class="login">
  <div class="brand"><span class="mark" aria-hidden="true"><i></i><i></i><i></i></span><span>Library<small>개인 서재</small></span></div>
  <form id="login-form" class="card" novalidate>
    <h1>로그인</h1>
    <p class="lead">한 번 로그인하면 모든 섹션을 이어서 씁니다.</p>
    <label for="password">비밀번호</label>
    <input id="password" name="password" type="password" autocomplete="current-password" required autofocus>
    <p id="login-error" class="error" role="alert" hidden></p>
    <button id="login-submit" type="submit">로그인</button>
  </form>
</main>
</body>
</html>
'''

ASSETS['hub.css'] = r'''*{box-sizing:border-box}
html,body{min-height:100%}
body{margin:0;background:var(--lib-bg);color:var(--lib-text);font-family:var(--lib-font);font-size:var(--lib-text-md);line-height:1.55;-webkit-font-smoothing:antialiased;word-break:keep-all}
.hub{max-width:960px;margin:0 auto;padding:var(--lib-space-6) var(--lib-space-4) var(--lib-space-7)}
.top{display:flex;align-items:center;justify-content:space-between;gap:var(--lib-space-4);margin-bottom:var(--lib-space-7)}
.brand{display:flex;gap:12px;align-items:center;font-size:var(--lib-text-lg);font-weight:600;letter-spacing:-.01em}
.brand small{display:block;font-size:var(--lib-text-xs);font-weight:400;color:var(--lib-faint);letter-spacing:0;margin-top:1px}
.mark{display:flex;align-items:flex-end;gap:2px;width:32px;height:32px;padding:6px 6px 5px;border-radius:7px;background:var(--lib-raised)}
.mark i{display:block;width:5px;border-radius:1px;background:var(--lib-text)}
.mark i:nth-child(1){height:18px}.mark i:nth-child(2){height:14px;background:var(--lib-accent)}.mark i:nth-child(3){height:20px}
.out{font:inherit;font-size:var(--lib-text-sm);display:inline-flex;align-items:center;gap:6px;min-height:36px;padding:0 12px;border:1px solid var(--lib-line);border-radius:var(--lib-radius);background:none;color:var(--lib-muted);cursor:pointer;transition:background var(--lib-fast),color var(--lib-fast)}
.out:hover{background:var(--lib-surface);color:var(--lib-text)}
h1{margin:0 0 var(--lib-space-4);font-size:var(--lib-text-xl);font-weight:650;letter-spacing:-.02em}
.grid{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));gap:var(--lib-space-3)}
.tile{--a:var(--lib-accent);position:relative;display:flex;flex-direction:column;gap:var(--lib-space-5);min-height:148px;height:100%;padding:var(--lib-space-4) var(--lib-space-4) var(--lib-space-4);
  background:linear-gradient(150deg,color-mix(in srgb,var(--a) 20%,var(--lib-surface)) 0%,color-mix(in srgb,var(--a) 6%,var(--lib-surface)) 55%,var(--lib-surface) 100%);
  border:1px solid color-mix(in srgb,var(--a) 22%,var(--lib-line));border-radius:var(--lib-radius-lg);color:inherit;text-decoration:none;isolation:isolate;overflow:hidden;
  transition:border-color var(--lib-fast) var(--lib-ease),transform var(--lib-med) var(--lib-ease)}
/* Hover deepens the section's own wash; a layer so it can fade. */
.tile::before{content:"";position:absolute;inset:0;z-index:-1;background:radial-gradient(120% 90% at 0% 0%,color-mix(in srgb,var(--a) 22%,transparent),transparent 70%);opacity:0;transition:opacity var(--lib-med) var(--lib-ease)}
.tile:hover::before,.tile:focus-visible::before{opacity:1}
.tile:hover{border-color:color-mix(in srgb,var(--a) 50%,var(--lib-line))}
.tile:active{transform:scale(.985)}
.tile:focus-visible{outline:2px solid var(--lib-text);outline-offset:2px}
.icon{display:grid;place-items:center;width:40px;height:40px;border-radius:10px;background:color-mix(in srgb,var(--a) 20%,transparent);color:var(--a)}
.icon svg{width:22px;height:22px}
.tile>span:last-child{margin-top:auto}
.name,.desc{display:block}
.out svg{width:16px;height:16px}
.go svg{width:18px;height:18px;display:block}
.name{font-size:var(--lib-text-lg);font-weight:600;letter-spacing:-.01em}
.desc{margin-top:2px;font-size:var(--lib-text-sm);color:var(--lib-faint)}
.go{position:absolute;top:var(--lib-space-4);right:var(--lib-space-4);color:var(--lib-faint);opacity:0;transform:translateX(-4px);transition:opacity var(--lib-fast),transform var(--lib-med) var(--lib-ease)}
.tile:hover .go,.tile:focus-visible .go{opacity:1;transform:none;color:var(--a)}
.manga{--a:var(--lib-accent-manga)}.audio{--a:var(--lib-accent-audio)}.roulette{--a:var(--lib-accent-roulette)}.cyoa{--a:var(--lib-accent-cyoa)}.real{--a:var(--lib-accent-real)}
@media (max-width:520px){.hub{padding-top:var(--lib-space-5)}.top{margin-bottom:var(--lib-space-6)}.grid{grid-template-columns:1fr 1fr}.tile{min-height:128px}}
@media (hover:none){.go{display:none}}
'''

ASSETS['hub.js'] = r'''// Library hub at /. Old manga bookmarks (/#/E123, /?q=…) still open the manga section.
(() => {
    const legacy = () => {
        if (!location.hash.startsWith('#/') && !location.search) return false;
        location.replace('/manga' + location.search + location.hash);
        return true;
    };
    addEventListener('hashchange', legacy);
    if (legacy()) return;
    document.querySelector('.out').addEventListener('click', async () => {
        try { await fetch('/api/session/logout', { method: 'POST', credentials: 'same-origin' }); } catch (_) { /* go to login anyway */ }
        location.assign('/login');
    });
})();
'''

_HUB_SECTIONS = [
    ('manga', '/manga', '만화', '만화·동인지 서재',
     '<path d="M4 5.5c2.6-1 5-1 8 1 3-2 5.4-2 8-1v13c-2.6-1-5-1-8 1-3-2-5.4-2-8-1z"/><path d="M12 6.5v13"/>'),
    ('audio', '/audio/', '음성', '동인 음성',
     '<path d="M4 15v-3a8 8 0 0 1 16 0v3"/><rect x="3.5" y="14" width="4" height="6" rx="1.5"/><rect x="16.5" y="14" width="4" height="6" rx="1.5"/>'),
    ('roulette', '/roulette/', '룰렛', '무작위 뽑기',
     '<circle cx="12" cy="12" r="8.5"/><path d="M12 3.5V12l6 6M12 12l-6 6"/><circle cx="12" cy="12" r="1.6"/>'),
    ('cyoa', '/cyoa/', 'CYOA', '선택형 이야기',
     '<circle cx="6" cy="5.5" r="2"/><circle cx="6" cy="18.5" r="2"/><circle cx="18" cy="12" r="2"/><path d="M6 7.5v9M6 10c0 2 2 2 4 2h6"/>'),
    ('real', '/real/', '실사', '사진·영상',
     '<rect x="3.5" y="6.5" width="17" height="12.5" rx="2"/><path d="M8.5 6.5 10 4h4l1.5 2.5"/><circle cx="12" cy="12.7" r="3.3"/>'),
]
_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">%s</svg>'

ASSETS['hub.html'] = r'''<!doctype html>
<html lang="ko">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>Library</title>
<link rel="stylesheet" href="/_library/tokens.css"><link rel="stylesheet" href="/_library/hub.css">
<script src="/_library/hub.js" defer></script></head>
<body>
<main class="hub">
  <header class="top">
    <div class="brand"><span class="mark" aria-hidden="true"><i></i><i></i><i></i></span><span>Library<small>개인 서재</small></span></div>
    <button class="out" type="button">''' + _SVG % '<path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 16l-4-4 4-4M6 12h10"/>' + r'''로그아웃</button>
  </header>
  <h1>섹션</h1>
  <ul class="grid">
''' + ''.join(
    '    <li><a class="tile %s" href="%s"><span class="icon">%s</span><span class="go">%s</span>'
    '<span><span class="name">%s</span><span class="desc">%s</span></span></a></li>\n'
    % (sid, href, _SVG % icon, _SVG % '<path d="M7 17 17 7M9 7h8v8"/>', name, desc)
    for sid, href, name, desc, icon in _HUB_SECTIONS) + r'''  </ul>
</main>
</body>
</html>
'''

ASSETS['components.css'] = r'''/* Library shared components. Values are the manga Studio's, expressed in tokens.
   Opt-in by class (lib-*) so nothing changes until a section uses it.
   Load after tokens.css:  <link rel="stylesheet" href="/_library/components.css">
   Only --lib-accent* differs between sections; never write raw colours here. */

/* Base: put class="lib-base" on <body> for the shared page defaults. */
.lib-base{margin:0;background:var(--lib-bg);color:var(--lib-text);font-family:var(--lib-font);font-size:var(--lib-text-md);line-height:1.55;-webkit-font-smoothing:antialiased;word-break:keep-all;overflow-wrap:break-word}
.lib-base *,.lib-base *::before,.lib-base *::after{box-sizing:border-box}
.lib-base :focus-visible{outline:2px solid var(--lib-text);outline-offset:2px}
.lib-base a{color:inherit;text-decoration:none}
.lib-base progress{accent-color:var(--lib-accent)}

/* Layout: fixed sidebar under the shared bar + main column. */
.lib-sidebar{position:fixed;inset:var(--lib-bar-h,0px) auto 0 0;z-index:20;width:232px;background:var(--lib-bg);border-right:1px solid var(--lib-line);padding:22px 12px 16px;display:flex;flex-direction:column;overflow-y:auto;overflow-x:hidden}
.lib-sidebar>*{flex-shrink:0}
.lib-main{margin-left:232px;min-height:calc(100vh - var(--lib-bar-h,0px));padding:0 32px 48px}
.lib-section-title{margin:0 8px 24px;font-size:var(--lib-text-lg);font-weight:600;letter-spacing:-.01em}
.lib-section-title small{display:block;font-size:var(--lib-text-xs);font-weight:400;color:var(--lib-faint);letter-spacing:0;margin-top:1px}
.lib-nav-label{font-size:var(--lib-text-xs);color:var(--lib-faint);margin:18px 12px 6px}
.lib-nav{display:flex;flex-direction:column;gap:2px}
.lib-nav-item{width:100%;display:flex;gap:10px;align-items:center;text-align:left;min-height:38px;padding:8px 12px;border:0;border-radius:var(--lib-radius);background:none;font:inherit;font-size:var(--lib-text-md);color:var(--lib-muted);cursor:pointer}
.lib-nav-item svg{width:18px;height:18px;flex:none;color:var(--lib-faint)}
.lib-nav-item:hover{background:var(--lib-surface);color:var(--lib-text)}
.lib-nav-item.is-active,.lib-nav-item[aria-current="page"]{background:var(--lib-raised);color:var(--lib-text);font-weight:600}
.lib-nav-item.is-active svg,.lib-nav-item[aria-current="page"] svg{color:var(--lib-accent)}
.lib-nav-item .lib-count{margin-left:auto;font-size:var(--lib-text-xs);color:var(--lib-muted);font-variant-numeric:tabular-nums}
@media (max-width:900px){
  .lib-sidebar{transform:translateX(-100%);visibility:hidden;transition:transform var(--lib-med) ease,visibility var(--lib-med);width:280px;max-width:86vw}
  .lib-nav-open .lib-sidebar{transform:none;visibility:visible;box-shadow:0 0 60px rgb(0 0 0 / .6)}
  .lib-main{margin-left:0;padding:0 20px 40px}
}

/* Page heading and toolbar */
.lib-page-head{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;padding:28px 0 6px}
.lib-h1{font-weight:600;font-size:26px;letter-spacing:-.02em;line-height:1.25;margin:0}
.lib-h2{font-weight:600;font-size:18px;letter-spacing:-.01em;line-height:1.35;margin:0}
.lib-page-count{color:var(--lib-faint);font-size:var(--lib-text-md);font-variant-numeric:tabular-nums}
.lib-lead{margin:0 0 16px;color:var(--lib-muted);font-size:var(--lib-text-sm)}
.lib-muted{font-size:var(--lib-text-sm);line-height:1.65;color:var(--lib-faint)}
.lib-toolbar{display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap;padding-bottom:14px;margin-bottom:8px;border-bottom:1px solid var(--lib-line)}
.lib-actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}

/* Buttons: one inverted primary, outlined secondary, text tertiary, danger. */
.lib-btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;min-height:36px;padding:7px 14px;border:1px solid var(--lib-control);border-radius:var(--lib-radius);background:none;color:var(--lib-text);font:inherit;font-size:var(--lib-text-md);line-height:1.4;white-space:nowrap;cursor:pointer;transition:background var(--lib-fast)}
.lib-btn:not(:disabled):hover{background:var(--lib-raised)}
.lib-btn:disabled{opacity:.45;cursor:default}
.lib-btn svg{width:17px;height:17px;flex:none}
.lib-btn-primary{background:var(--lib-text);border-color:var(--lib-text);color:var(--lib-on-text);font-weight:600}
.lib-btn-primary:not(:disabled):hover{background:var(--lib-text-bright);border-color:var(--lib-text-bright)}
.lib-btn-text{border-color:transparent;color:var(--lib-muted)}
.lib-btn-text:not(:disabled):hover{color:var(--lib-text);background:var(--lib-surface)}
.lib-btn-danger{color:var(--lib-danger);border-color:var(--lib-danger)}
.lib-btn-danger:not(:disabled):hover{background:var(--lib-danger-bg)}
.lib-icon-btn{display:inline-grid;place-items:center;width:36px;height:36px;padding:0;border:1px solid var(--lib-control);border-radius:var(--lib-radius);background:none;color:var(--lib-text);cursor:pointer}
.lib-icon-btn:hover{background:var(--lib-raised)}
.lib-icon-btn svg{width:18px;height:18px}

/* Form fields */
.lib-field{display:flex;flex-direction:column;gap:6px;margin:16px 0;color:var(--lib-muted);font-size:var(--lib-text-md);font-weight:500}
.lib-input{font:inherit;font-weight:400;line-height:1.4;background:var(--lib-bg);border:1px solid var(--lib-control);border-radius:var(--lib-radius);color:var(--lib-text);padding:10px 12px;min-height:40px;max-width:100%}
.lib-input::placeholder{color:var(--lib-faint)}
select.lib-input{cursor:pointer}
.lib-hint{font-size:var(--lib-text-xs);font-weight:400;color:var(--lib-faint)}
.lib-search{display:flex;align-items:center;gap:8px;min-height:40px;padding:0 12px;border:1px solid var(--lib-control);border-radius:var(--lib-radius);background:var(--lib-bg);color:var(--lib-faint)}
.lib-search input{flex:1;min-width:0;border:0;background:none;color:var(--lib-text);font:inherit;outline:0}

/* Chips (filters) and tags */
.lib-chips{display:flex;gap:6px;flex-wrap:wrap}
.lib-chip{min-height:34px;padding:6px 13px;border:1px solid var(--lib-line);border-radius:var(--lib-radius-pill);background:none;color:var(--lib-muted);font:inherit;font-size:var(--lib-text-sm);cursor:pointer}
.lib-chip:hover{color:var(--lib-text);border-color:var(--lib-control)}
.lib-chip.is-selected,.lib-chip[aria-pressed="true"]{color:var(--lib-on-text);background:var(--lib-text);border-color:var(--lib-text);font-weight:600}
.lib-tag{display:inline-flex;align-items:center;gap:4px;min-height:30px;padding:4px 10px;background:var(--lib-raised);border-radius:var(--lib-radius-pill);color:var(--lib-text);font-size:var(--lib-text-sm);line-height:1.3}
.lib-badge{display:inline-flex;align-items:center;gap:4px;min-height:22px;padding:1px 8px;border-radius:var(--lib-radius-pill);background:var(--lib-raised);color:var(--lib-muted);font-size:var(--lib-text-xs);font-variant-numeric:tabular-nums}
.lib-badge-accent{background:var(--lib-accent-soft);color:var(--lib-accent)}
.lib-badge-danger{background:var(--lib-danger-bg);color:var(--lib-danger)}
.lib-badge-success{background:var(--lib-success-bg);color:var(--lib-success)}
.lib-badge-warning{background:var(--lib-warning-bg);color:var(--lib-warning)}

/* Media grid and cover card (works, voice editions, galleries, stories) */
.lib-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(var(--lib-card-width,185px),1fr));gap:28px 20px}
.lib-cover-card{position:relative;min-width:0;border-radius:6px;color:inherit;cursor:pointer}
.lib-cover-card:focus-visible{outline-offset:4px}
.lib-cover{background:var(--lib-surface);aspect-ratio:3/4;border-radius:var(--lib-radius-sm);position:relative;overflow:hidden}
.lib-cover-wide{aspect-ratio:16/9}
.lib-cover-square{aspect-ratio:1}
.lib-cover img,.lib-cover video{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;display:block}
.lib-cover-fill img,.lib-cover-fill video{object-fit:cover}
.lib-cover-card:hover .lib-cover{background:var(--lib-raised)}
.lib-cover-title{font-size:var(--lib-text-md);font-weight:500;line-height:1.45;margin:10px 0 2px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}
.lib-cover-meta{color:var(--lib-muted);font-size:var(--lib-text-sm);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.lib-cover-progress{position:absolute;left:0;right:0;bottom:0;height:3px;background:rgb(0 0 0 / .45)}
.lib-cover-progress>i{display:block;height:100%;background:var(--lib-accent)}

/* Panels and list rows */
.lib-panel{background:var(--lib-surface);border:1px solid var(--lib-line);border-radius:var(--lib-radius-lg);padding:20px}
.lib-list{display:flex;flex-direction:column}
.lib-row{display:flex;align-items:center;gap:14px;min-height:52px;padding:10px 4px;border-bottom:1px solid var(--lib-line)}
.lib-row:hover{background:var(--lib-surface)}
.lib-row-main{flex:1;min-width:0}
.lib-row-title{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.lib-row-meta{font-size:var(--lib-text-xs);color:var(--lib-faint)}

/* Dialog */
.lib-dialog{color:var(--lib-text);background:var(--lib-surface);border:1px solid var(--lib-line);border-radius:var(--lib-radius-lg);padding:28px;width:480px;max-width:calc(100vw - 24px);max-height:calc(100dvh - 32px);overflow:auto;box-shadow:var(--lib-shadow-dialog)}
.lib-dialog::backdrop{background:var(--lib-overlay)}
.lib-dialog h2{font-size:20px;margin:0 0 12px}
.lib-dialog-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:24px}

/* Notices and toast */
.lib-notice{padding:10px 12px;border-radius:var(--lib-radius);background:var(--lib-raised);color:var(--lib-muted);font-size:var(--lib-text-sm)}
.lib-notice-danger{background:var(--lib-danger-bg);color:var(--lib-danger)}
.lib-notice-success{background:var(--lib-success-bg);color:var(--lib-success)}
.lib-notice-warning{background:var(--lib-warning-bg);color:var(--lib-warning)}
.lib-toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);z-index:99;width:max-content;max-width:min(560px,calc(100vw - 32px));padding:12px 20px;border:0;border-radius:var(--lib-radius);background:var(--lib-text);color:var(--lib-on-text);box-shadow:var(--lib-shadow-pop);font-size:var(--lib-text-md);line-height:1.5;overflow-wrap:anywhere}

/* Empty state */
.lib-empty{text-align:center;padding:64px 20px;color:var(--lib-muted)}
.lib-empty svg{width:40px;height:40px;color:var(--lib-faint)}
.lib-empty h2{color:var(--lib-text);margin:12px 0 8px;font-size:18px}
.lib-empty p{line-height:1.7;font-size:var(--lib-text-md);margin:0 0 20px}

/* Progress / rating */
.lib-progress{height:4px;border-radius:2px;background:var(--lib-raised);overflow:hidden}
.lib-progress>i{display:block;height:100%;background:var(--lib-accent)}
.lib-rating{color:var(--lib-accent);letter-spacing:1px}
'''

ASSETS['guide.html'] = r'''<!doctype html>
<html lang="ko" data-library-section="manga">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>디자인 기준 · Library</title>
<link rel="stylesheet" href="/_library/tokens.css"><link rel="stylesheet" href="/_library/components.css"><link rel="stylesheet" href="/_library/guide.css">
<script src="/_library/shell.js" defer></script><script src="/_library/guide.js" defer></script></head>
<body class="lib-base">
<aside class="lib-sidebar" aria-label="섹션 메뉴">
  <div class="lib-section-title" id="guide-section-title">만화<small>개인 서재</small></div>
  <div class="lib-nav-label">라이브러리</div>
  <nav class="lib-nav">
    <a class="lib-nav-item is-active" href="#"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><rect x="4" y="4" width="6" height="7" rx="1"/><rect x="14" y="4" width="6" height="7" rx="1"/><rect x="4" y="14" width="6" height="6" rx="1"/><rect x="14" y="14" width="6" height="6" rx="1"/></svg>전체 보관함<span class="lib-count">128</span></a>
    <a class="lib-nav-item" href="#"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="m12 4 2.4 5 5.4.7-4 3.8 1 5.4L12 16.3 7.2 19l1-5.4-4-3.8 5.4-.7z"/></svg>즐겨찾기<span class="lib-count">12</span></a>
    <a class="lib-nav-item" href="#"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/></svg>최근 본 항목</a>
  </nav>
  <div class="lib-nav-label">도구</div>
  <nav class="lib-nav"><a class="lib-nav-item" href="#"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>추가</a></nav>
</aside>
<main class="lib-main">
  <div class="lib-page-head"><h1 class="lib-h1">디자인 기준</h1><span class="lib-page-count">모든 섹션 공통</span></div>
  <p class="lead lib-lead">섹션을 바꾸면 포인트 색만 바뀝니다. 나머지는 모두 같아야 합니다.</p>
  <div class="lib-chips" role="group" aria-label="섹션 색 미리보기" id="guide-sections">
    <button class="lib-chip is-selected" data-section="manga" aria-pressed="true">만화</button>
    <button class="lib-chip" data-section="audio" aria-pressed="false">음성</button>
    <button class="lib-chip" data-section="roulette" aria-pressed="false">룰렛</button>
    <button class="lib-chip" data-section="cyoa" aria-pressed="false">CYOA</button>
    <button class="lib-chip" data-section="real" aria-pressed="false">실사</button>
  </div>

  <h2 class="lib-h2 guide-h">툴바 · 버튼</h2>
  <div class="lib-toolbar">
    <div class="lib-chips"><button class="lib-chip is-selected">전체</button><button class="lib-chip">읽는 중</button><button class="lib-chip">완료</button></div>
    <div class="lib-actions"><button class="lib-btn-text lib-btn">텍스트</button><button class="lib-btn">보조</button><button class="lib-btn lib-btn-danger">삭제</button><button class="lib-btn lib-btn-primary">+ 주 버튼</button><button class="lib-icon-btn" aria-label="보기 전환"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M4 6h16M4 12h16M4 18h16"/></svg></button></div>
  </div>

  <h2 class="lib-h2 guide-h">카드 그리드</h2>
  <div class="lib-grid" id="guide-grid"></div>

  <h2 class="lib-h2 guide-h">목록</h2>
  <div class="lib-list">
    <div class="lib-row"><span class="lib-badge lib-badge-accent">재생 중</span><div class="lib-row-main"><div class="lib-row-title">목록 행 제목</div><div class="lib-row-meta">보조 정보 · 12:40</div></div><span class="lib-rating" aria-label="평점 4">★★★★☆</span></div>
    <div class="lib-row"><span class="lib-badge">대기</span><div class="lib-row-main"><div class="lib-row-title">두 번째 행</div><div class="lib-row-meta">보조 정보</div></div><span class="lib-badge lib-badge-success">완료</span></div>
    <div class="lib-row"><span class="lib-badge">대기</span><div class="lib-row-main"><div class="lib-row-title">오류가 난 행</div><div class="lib-row-meta">보조 정보</div></div><span class="lib-badge lib-badge-danger">실패</span></div>
    <div class="lib-row"><span class="lib-badge">대기</span><div class="lib-row-main"><div class="lib-row-title">확인이 필요한 행</div><div class="lib-row-meta">보조 정보</div></div><span class="lib-badge lib-badge-warning">검토 필요</span></div>
  </div>

  <h2 class="lib-h2 guide-h">패널 · 입력</h2>
  <div class="guide-two">
    <div class="lib-panel">
      <label class="lib-field">이름<input class="lib-input" placeholder="입력 예시"></label>
      <label class="lib-field">분류<select class="lib-input"><option>선택</option></select><span class="lib-hint">도움말 문구</span></label>
      <div class="lib-search"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="11" cy="11" r="6"/><path d="m20 20-4.5-4.5"/></svg><input placeholder="검색"></div>
    </div>
    <div class="lib-panel guide-stack">
      <div class="lib-progress" aria-label="진행률 60%"><i class="guide-60"></i></div>
      <div class="lib-notice">일반 안내</div>
      <div class="lib-notice lib-notice-success">저장했습니다.</div>
      <div class="lib-notice lib-notice-warning">번역을 검토해야 합니다.</div>
      <div class="lib-notice lib-notice-danger">연결할 수 없습니다.</div>
      <div><span class="lib-tag">태그</span> <span class="lib-tag">female:example</span> <span class="lib-badge">42</span></div>
      <div class="lib-actions"><button class="lib-btn" id="guide-dialog-open">대화상자 열기</button><button class="lib-btn" id="guide-toast-open">알림 띄우기</button></div>
    </div>
  </div>

  <h2 class="lib-h2 guide-h">빈 화면</h2>
  <div class="lib-empty"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="4" y="5" width="16" height="14" rx="2"/><path d="M8 10h8M8 14h5"/></svg><h2>아직 항목이 없습니다</h2><p>항목을 추가하면 여기에 표시됩니다.</p><button class="lib-btn lib-btn-primary">+ 추가</button></div>
</main>
<dialog class="lib-dialog" id="guide-dialog"><h2>대화상자</h2><p class="lib-muted">확인이 필요한 작업을 설명합니다.</p><label class="lib-field">메모<input class="lib-input"></label><div class="lib-dialog-actions"><button class="lib-btn" id="guide-dialog-close">취소</button><button class="lib-btn lib-btn-primary" id="guide-dialog-ok">확인</button></div></dialog>
<div class="lib-toast" id="guide-toast" role="status" hidden>처리했습니다.</div>
</body>
</html>
'''

ASSETS['guide.css'] = r'''/* Only the reference page's own arrangement; components come from components.css. */
.guide-h{margin:40px 0 14px}
.guide-two{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:20px}
.guide-stack{display:flex;flex-direction:column;gap:12px}
.guide-placeholder{height:100%;display:grid;place-items:center;color:var(--lib-faint);font-size:var(--lib-text-sm)}
.guide-60{width:60%}
.guide-p0{width:35%}.guide-p2{width:80%}.guide-p4{width:55%}
#guide-sections{margin-top:4px}
[hidden]{display:none!important}
'''

ASSETS['guide.js'] = r'''// Design reference page: switches the section accent and demonstrates dialog/toast.
(() => {
    const titles = { manga: ['만화', '개인 서재'], audio: ['음성', '동인 음성'], roulette: ['룰렛', '랜덤 뽑기'], cyoa: ['CYOA', '선택형 이야기'], real: ['실사', '사진 · 영상'] };
    const grid = document.getElementById('guide-grid');
    const shapes = ['', '', 'lib-cover-square', '', 'lib-cover-wide', ''];
    grid.innerHTML = shapes.map((shape, i) => `
      <a class="lib-cover-card" href="#"><div class="lib-cover ${shape}"><div class="guide-placeholder">표지 ${i + 1}</div>${i % 2 ? '' : `<div class="lib-cover-progress"><i class="guide-p${i}"></i></div>`}</div>
      <div class="lib-cover-title">카드 제목 ${i + 1} — 두 줄까지 표시되는 긴 제목 예시</div><div class="lib-cover-meta">작가 · 보조 정보</div></a>`).join('');

    const html = document.documentElement;
    const title = document.getElementById('guide-section-title');
    document.getElementById('guide-sections').addEventListener('click', event => {
        const button = event.target.closest('[data-section]');
        if (!button) return;
        html.dataset.librarySection = button.dataset.section;
        for (const b of document.querySelectorAll('#guide-sections [data-section]')) {
            const on = b === button;
            b.classList.toggle('is-selected', on); b.setAttribute('aria-pressed', String(on));
        }
        const [name, sub] = titles[button.dataset.section];
        title.firstChild.textContent = name; title.querySelector('small').textContent = sub;
    });

    const dialog = document.getElementById('guide-dialog');
    document.getElementById('guide-dialog-open').onclick = () => dialog.showModal();
    document.getElementById('guide-dialog-close').onclick = () => dialog.close();
    document.getElementById('guide-dialog-ok').onclick = () => dialog.close();
    const toast = document.getElementById('guide-toast');
    let timer;
    document.getElementById('guide-toast-open').onclick = () => {
        toast.hidden = false; clearTimeout(timer); timer = setTimeout(() => { toast.hidden = true; }, 2500);
    };
})();
'''
