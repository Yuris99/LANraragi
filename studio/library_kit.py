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
  --lib-faint:#a29b92;
  /* One accent, plus status */
  --lib-accent:#e8b04a;
  --lib-accent-ink:#1a1408;
  --lib-accent-soft:rgba(232,176,74,.14);
  --lib-danger:#f08a7a;
  --lib-danger-bg:#2c1a17;
  --lib-success:#8fc79a;
  --lib-success-bg:#16241a;
  /* Shape */
  --lib-radius:8px;
  --lib-radius-sm:4px;
  --lib-radius-lg:12px;
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
  /* Shared bar */
  --lib-bar-h:0px;
}
html.has-library-bar{--lib-bar-h:48px}
@media (max-width:560px){html.has-library-bar{--lib-bar-h:52px}}
html.has-library-bar body{padding-top:var(--lib-bar-h)}
@media (prefers-reduced-motion:reduce){:root{--lib-fast:0ms;--lib-med:0ms}}
'''

ASSETS['bar.css'] = r'''/* Shared Library bar, loaded into the bar's shadow root by shell.js. */
:host{all:initial;font-family:var(--lib-font,system-ui,sans-serif)}
*{box-sizing:border-box}
.bar{height:var(--lib-bar-h,48px);display:flex;align-items:center;gap:16px;padding:0 16px;
  background:color-mix(in srgb,var(--lib-bg,#0e0d0c) 92%,transparent);backdrop-filter:blur(10px);
  border-bottom:1px solid var(--lib-line,#2b2927);color:var(--lib-text,#f1f0ee);font-size:14px;line-height:1.4}
a,button{font:inherit;color:inherit;text-decoration:none;background:none;border:0;cursor:pointer;-webkit-tap-highlight-color:transparent}
:focus-visible{outline:2px solid var(--lib-text,#f1f0ee);outline-offset:2px;border-radius:6px}
.brand{display:flex;align-items:center;gap:10px;font-weight:650;letter-spacing:-.01em;flex:none}
.mark{display:flex;align-items:flex-end;gap:2px;width:26px;height:26px;padding:5px 5px 4px;border-radius:6px;background:var(--lib-raised,#211f1d)}
.mark i{display:block;width:4px;border-radius:1px;background:var(--lib-text,#f1f0ee)}
.mark i:nth-child(1){height:14px}.mark i:nth-child(2){height:11px;background:var(--lib-accent,#e8b04a)}.mark i:nth-child(3){height:16px}
nav{display:flex;gap:2px;min-width:0;overflow-x:auto;scrollbar-width:none;flex:1}
nav::-webkit-scrollbar{display:none}
.tab{display:flex;align-items:center;gap:7px;height:34px;padding:0 12px;border-radius:var(--lib-radius,8px);
  color:var(--lib-muted,#c2bcb4);white-space:nowrap;transition:background var(--lib-fast,120ms),color var(--lib-fast,120ms)}
.tab svg,.out svg{width:17px;height:17px;flex:none}
.tab:hover{background:var(--lib-surface,#171615);color:var(--lib-text,#f1f0ee)}
.tab[aria-current="page"]{background:var(--lib-raised,#211f1d);color:var(--lib-text,#f1f0ee);font-weight:600}
.tab[aria-current="page"] svg{color:var(--lib-accent,#e8b04a)}
.out{display:flex;align-items:center;gap:6px;height:34px;padding:0 10px;border-radius:var(--lib-radius,8px);color:var(--lib-faint,#a29b92);flex:none}
.out:hover{background:var(--lib-surface,#171615);color:var(--lib-text,#f1f0ee)}
@media (max-width:560px){
  .bar{gap:4px;padding:0 6px}
  .brand span:last-child,.out span{display:none}
  nav{justify-content:space-between}
  .tab{flex-direction:column;justify-content:center;gap:2px;height:46px;padding:0 6px;min-width:52px;font-size:11px}
}
'''

ASSETS['shell.js'] = r'''// Library shared top bar. One script for every section:
//   <link rel="stylesheet" href="/_library/tokens.css">
//   <script src="/_library/shell.js" defer></script>
// Renders in a shadow root so section CSS (Stash, roulette…) cannot restyle it,
// and the bar cannot leak styles into the section.
(() => {
    if (window.__libraryShell || !document.body) return;
    window.__libraryShell = true;

    const SECTIONS = [
        { id: 'manga', label: '만화', href: '/', match: p => !/^\/(audio|roulette|cyoa|real|diet)(\/|$)/.test(p),
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
    const path = location.pathname;
    const current = SECTIONS.find(s => s.match(path)) || SECTIONS[0];
    const svg = body => `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;

    const host = document.createElement('library-bar');
    host.setAttribute('role', 'banner');
    host.style.cssText = 'position:fixed;inset:0 0 auto 0;z-index:2147483000;display:block;height:var(--lib-bar-h,48px);visibility:hidden';
    const root = host.attachShadow({ mode: 'open' });
    root.innerHTML = `
<link rel="stylesheet" href="/_library/bar.css">
<div class="bar">
  <a class="brand" href="/" aria-label="Library 홈"><span class="mark" aria-hidden="true"><i></i><i></i><i></i></span><span>Library</span></a>
  <nav aria-label="Library 섹션">${SECTIONS.map(s =>
      `<a class="tab" href="${s.href}"${s === current ? ' aria-current="page"' : ''}>${svg(s.icon)}<span>${s.label}</span></a>`).join('')}</nav>
  <button class="out" type="button" title="로그아웃">${svg('<path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 16l-4-4 4-4M6 12h10"/>')}<span>로그아웃</span></button>
</div>`;
    // Reveal only once the bar's stylesheet is in, so it never flashes unstyled.
    root.querySelector('link').addEventListener('load', () => { host.style.visibility = ''; });
    root.querySelector('.out').addEventListener('click', async () => {
        try { await fetch('/api/session/logout', { method: 'POST', credentials: 'same-origin' }); } catch (_) { /* go to login anyway */ }
        location.assign('/login');
    });
    document.documentElement.classList.add('has-library-bar', 'library-' + current.id);
    document.body.prepend(host);
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
.sections{display:flex;flex-wrap:wrap;justify-content:center;gap:6px;margin:0;padding:0;list-style:none}
.sections li{font-size:var(--lib-text-xs);color:var(--lib-faint);padding:3px 10px;border:1px solid var(--lib-line);border-radius:999px}
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
  <ul class="sections" aria-label="Library 섹션">
    <li>만화</li><li>음성</li><li>룰렛</li><li>CYOA</li><li>실사</li>
  </ul>
</main>
</body>
</html>
'''
