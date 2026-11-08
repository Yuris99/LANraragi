'use strict';
(() => {
  const $ = id => document.getElementById(id), core = window.PlayerCore;
  const basePath = typeof location !== 'undefined' && location.pathname.startsWith('/audio/') ? '/audio' : '';
  const stage = $('cinema'), media = $('media'), caption = $('caption');
  let tracks = [], current = null, cues = [], wake = null, wakePending = false;
  let generation = 0, progressPending = false, lastSaved = 0, loading = false, switching = false;
  let resume = 0, returnFocus = null, orderPending = false, saveOrder = null;
  let controlsTimer = null, controlsVisible = true, seeking = false, keyboardMode = false;
  const chrome = [$('player-header'), $('player-transport'), $('player-controls')];
  const preferences = {size:28, vertical:72, horizontal:50, delay:0, enabled:true, keepAwake:true, speed:1, mode:'all'};
  try { Object.assign(preferences, JSON.parse(localStorage.getItem('audio-player-preferences') || '{}')); } catch (_) { /* Private mode or invalid stored data. */ }
  for (const [key,min,max] of [['size',14,72],['vertical',8,88],['horizontal',10,90],['delay',-120,120],['speed',0.5,2]]) {
    preferences[key] = Math.max(min, Math.min(max, Number(preferences[key]) || (key === 'delay' ? 0 : min)));
  }
  preferences.mode = preferences.mode === 'single' ? 'single' : 'all';

  const note = message => { $('player-status').textContent = message; if (message) showControls(); };
  function renderPlayButton(playing) {
    $('toggle-play').innerHTML = `<svg width="28" height="28" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${playing ? '<path d="M8 5v14M16 5v14"/>' : '<path d="m8 4 12 8-12 8Z"/>'}</svg>`;
    $('toggle-play').setAttribute('aria-label', playing ? '일시정지' : '재생');
  }
  function canHideControls() {
    const focused = document.activeElement;
    return !stage.hidden && !media.paused && !media.ended && !media.error && !loading && !switching && !seeking && !keyboardMode
      && !$('player-settings').open && !$('player-queue').open
      && !(stage.contains(focused) && ['INPUT','SELECT','TEXTAREA'].includes(focused?.tagName));
  }
  function setControlsVisible(visible) {
    controlsVisible = visible;
    if (!visible && chrome.some(node => node.contains(document.activeElement))) $('screen-controls').focus();
    stage.classList.toggle('controls-hidden', !visible);
    for (const node of chrome) { node.inert = !visible; node.setAttribute('aria-hidden', String(!visible)); }
    $('screen-controls').setAttribute('aria-expanded', String(visible));
    $('screen-controls').setAttribute('aria-label', visible ? '재생 조작 버튼 숨기기' : '재생 조작 버튼 표시');
  }
  function scheduleHide() {
    clearTimeout(controlsTimer); controlsTimer = null;
    if (controlsVisible && canHideControls()) controlsTimer = setTimeout(() => { if (canHideControls()) setControlsVisible(false); }, 3000);
  }
  function showControls() { setControlsVisible(true); scheduleHide(); }
  function panelState() {
    $('player-panels').hidden = !$('player-settings').open && !$('player-queue').open;
    $('player-settings-button').setAttribute('aria-expanded', String(!!$('player-settings').open));
    $('player-queue-button').setAttribute('aria-expanded', String(!!$('player-queue').open));
    showControls();
  }
  async function request(path, data) {
    const response = await fetch(basePath + path, data === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    const value = await response.json();
    if (!response.ok) throw new Error(value.error || '요청을 처리할 수 없습니다.');
    return value;
  }
  const safe = action => Promise.resolve().then(action).catch(error => note(error.message));
  function backgroundInert(value) {
    for (const node of document.querySelectorAll('body > aside,body > header,body > main,body > footer')) node.inert = value;
  }
  function persist() { try { localStorage.setItem('audio-player-preferences', JSON.stringify(preferences)); } catch (_) { /* Optional preferences. */ } }
  function settings() {
    caption.style.fontSize = `${preferences.size}px`;
    caption.style.top = `${preferences.vertical}%`;
    caption.style.left = `${preferences.horizontal}%`;
    caption.style.maxWidth = `${Math.min(92, preferences.horizontal * 2, (100 - preferences.horizontal) * 2)}%`;
    caption.hidden = !preferences.enabled;
    $('caption-size-value').textContent = `${preferences.size}px`;
    $('caption-delay-value').textContent = `${Number(preferences.delay).toFixed(1)}초 (＋는 늦게)`;
    media.playbackRate = Number(preferences.speed);
    renderCaptions(); persist();
  }
  function renderCaptions() { caption.textContent = core.activeCues(cues, media.currentTime || 0, preferences.delay); }

  async function releaseWake() {
    if (wake) { const old = wake; wake = null; await old.release().catch(() => {}); }
    $('wake-status').textContent = '화면 유지 꺼짐';
  }
  async function acquireWake() {
    if (wake || wakePending || media.paused || stage.hidden || !preferences.keepAwake || document.visibilityState !== 'visible') return;
    if (!navigator.wakeLock || !window.isSecureContext) {
      $('wake-status').textContent = '화면 유지 불가 · HTTPS/브라우저 확인'; return;
    }
    wakePending = true;
    try {
      const lock = await navigator.wakeLock.request('screen');
      if (stage.hidden || media.paused || !preferences.keepAwake) { await lock.release(); return; }
      wake = lock;
      $('wake-status').textContent = '화면 꺼짐 방지 중';
      lock.addEventListener('release', () => {
        if (wake === lock) { wake = null; $('wake-status').textContent = '화면 유지 해제됨 · 화면 유지 버튼으로 재시도'; }
      });
    } catch (_) { $('wake-status').textContent = '화면 유지 거부됨 · 절전/권한 확인'; }
    finally { wakePending = false; }
  }
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') safe(acquireWake);
    else safe(releaseWake);
  });

  async function saveProgress() {
    const track = current;
    if (!track || loading || media.readyState < 1 || !Number.isFinite(media.currentTime)) return;
    const seconds = Math.min(media.currentTime, track.duration || Infinity);
    const saved = await request(`/api/tracks/${track.id}/progress`, {seconds});
    track.resume = saved.resume;
  }
  function navigation() {
    const index = tracks.findIndex(t => t.id === current?.id);
    $('player-previous').disabled = index <= 0 || switching;
    $('player-next').disabled = index < 0 || index >= tracks.length - 1 || switching;
  }
  function updateQueue() {
    $('queue').replaceChildren();
    for (const track of tracks) {
      const li = document.createElement('li'); li.className = track.id === current?.id ? 'current' : '';
      const play = document.createElement('button'); play.textContent = window.AudioTrackTitle?.(track) || track.title; play.className = 'queue-title';
      play.addEventListener('click', () => safe(() => select(track, true))); li.append(play);
      for (const [delta, symbol, name] of [[-1,'↑','위로'],[1,'↓','아래로']]) {
        const button = document.createElement('button'); button.textContent = symbol;
        button.setAttribute('aria-label', `${track.title} ${name}`);
        const index = tracks.indexOf(track);
        button.disabled = orderPending || (delta < 0 ? index === 0 : index === tracks.length - 1);
        button.addEventListener('click', () => safe(async () => {
          if (orderPending) return;
          orderPending = true; updateQueue();
          const updated = core.move(tracks, track.id, delta);
          try {
            if(saveOrder)await saveOrder(updated.map(t => t.id));
            else await request(`/api/editions/${track.edition_id}/order`, {track_ids:updated.map(t => t.id)});
            tracks = updated; note('트랙 순서를 저장했습니다.');
          } finally { orderPending = false; updateQueue(); navigation(); }
        }));
        li.append(button);
      }
      $('queue').append(li);
    }
  }
  async function loadCaptions(track, token) {
    const select = $('subtitle-select'); select.replaceChildren();
    const off = document.createElement('option'); off.value = ''; off.textContent = '자막 없음'; select.append(off);
    for (const subtitle of track.subtitles || []) {
      const option = document.createElement('option'); option.value = subtitle.id; option.textContent = `${subtitle.label} · ${window.LibraryCore?.subtitleLanguageLabel?.(subtitle)||subtitle.language}`; select.append(option);
    }
    const first = track.subtitles?.[0];
    select.value = first?.id || '';
    if (first) {
      try {
        const value = await request(`/api/subtitles/${first.id}`);
        if (token === generation) { cues = value.cues; renderCaptions(); }
      } catch (error) { if (token === generation) note(`자막 오류: ${error.message}`); }
    }
  }
  async function select(track, restore = false) {
    if (switching) return;
    switching = true; navigation();
    try {
      // Pause before replacing the media; delayed pause events never write a new track's position.
      media.pause(); await saveProgress();
      loading = true; current = track; cues = []; caption.textContent = ''; lastSaved = 0;
      const token = ++generation;
      resume = restore ? track.resume || 0 : 0;
      $('player-title').textContent = window.AudioTrackTitle?.(track) || track.title;
      $('playing').textContent = window.AudioTrackTitle?.(track) || track.title;
      media.src = `${basePath}/api/tracks/${track.id}/media`; media.load();
      $('seek').value = '0'; $('seek').disabled = true;
      $('elapsed').textContent = '0:00'; $('total').textContent = '0:00';
      updateQueue(); note('불러오는 중…');
      void loadCaptions(track, token);
    } finally { switching = false; navigation(); }
  }
  async function enterFullscreen() {
    if (document.fullscreenElement) return;
    if (!stage.requestFullscreen) { note('화면 채우기 모드입니다. 이 브라우저는 전체 화면 API를 지원하지 않습니다.'); return; }
    try { await stage.requestFullscreen(); }
    catch (_) { note('화면 채우기 모드입니다. 전체 화면 버튼으로 다시 시도할 수 있습니다.'); }
  }
  function open(list, track, options = {}) {
    if (!list.length) return;
    returnFocus = document.activeElement;
    stage.hidden = false; document.body.classList.add('cinema-open');
    keyboardMode = false; seeking = false;
    $('player-settings').open = false; $('player-queue').open = false; panelState();
    backgroundInert(true);
    if (options.mode === 'all' || options.mode === 'single') {
      preferences.mode = options.mode;
      $('play-mode').value = options.mode;
      persist();
    }
    $('close-player').focus();
    // Fill the page without changing the user's browser/window mode.
    // Native fullscreen is requested only by the dedicated fullscreen button.
    saveOrder = typeof options.order === 'function' ? options.order : null;
    tracks = [...list];
    return select(track, !options.fromStart);
  }
  async function close() {
    media.pause();
    try { await saveProgress(); } catch (error) { note(error.message); }
    await releaseWake();
    if (document.fullscreenElement) await document.exitFullscreen().catch(() => {});
    stage.hidden = true; document.body.classList.remove('cinema-open');
    clearTimeout(controlsTimer); controlsTimer = null;
    backgroundInert(false);
    returnFocus?.focus();
    document.dispatchEvent(new Event('player-closed'));
  }
  function seek(delta) {
    if (media.readyState < 1) return;
    media.currentTime = Math.max(0, Math.min(Number.isFinite(media.duration) ? media.duration : Infinity, media.currentTime + delta));
    renderCaptions();
  }
  async function skip(delta) {
    const index = tracks.findIndex(t => t.id === current?.id), track = tracks[index + delta];
    if (track) await select(track);
  }
  media.addEventListener('loadedmetadata', () => {
    if (!current) return;
    loading = false;
    media.currentTime = Number.isFinite(media.duration) && resume >= media.duration - 0.5 ? 0 : resume;
    media.playbackRate = Number(preferences.speed);
    $('seek').disabled = !Number.isFinite(media.duration);
    $('seek').max = Number.isFinite(media.duration) ? String(media.duration) : '0';
    $('total').textContent = core.formatTime(media.duration);
    note('');
    if (stage.hidden) { media.pause(); return; }
    media.play().catch(() => note('재생 버튼을 눌러 시작하세요.'));
  });
  media.addEventListener('timeupdate', () => {
    $('seek').value = String(media.currentTime); $('elapsed').textContent = core.formatTime(media.currentTime); renderCaptions();
    if (!loading && !progressPending && !media.paused && Date.now() - lastSaved > 5000) {
      lastSaved = Date.now(); progressPending = true;
      safe(saveProgress).finally(() => { progressPending = false; });
    }
  });
  media.addEventListener('play', () => { if (stage.hidden) { media.pause(); return; } renderPlayButton(true); showControls(); safe(acquireWake); });
  media.addEventListener('pause', () => { renderPlayButton(false); showControls(); safe(releaseWake); if (!switching && !stage.hidden) safe(saveProgress); });
  media.addEventListener('seeked', () => { renderCaptions(); if (!loading && !stage.hidden) safe(saveProgress); });
  media.addEventListener('ended', () => safe(async () => {
    if (stage.hidden) return;
    await releaseWake();
    try { await saveProgress(); } catch (error) { note(error.message); }
    const next = core.nextTrack(tracks, current?.id, preferences.mode);
    if (next) await select(next);
    else note('재생 완료 · 자동 반복 없이 종료했습니다.');
  }));
  media.addEventListener('error', () => { loading = false; note('파일을 재생할 수 없습니다. 파일 위치와 브라우저 코덱 지원을 확인하세요.'); safe(releaseWake); });
  $('toggle-play').addEventListener('click', () => safe(async () => {
    if (!current) return;
    if (media.paused) await media.play(); else media.pause();
  }));
  $('seek').addEventListener('input', () => { if (media.readyState >= 1) media.currentTime = Number($('seek').value); renderCaptions(); });
  $('back-ten').addEventListener('click', () => seek(-10));
  $('forward-ten').addEventListener('click', () => seek(10));
  $('player-previous').addEventListener('click', () => safe(() => skip(-1)));
  $('player-next').addEventListener('click', () => safe(() => skip(1)));
  $('close-player').addEventListener('click', () => safe(close));
  $('fullscreen').addEventListener('click', () => safe(enterFullscreen));
  $('screen-controls').addEventListener('click', () => {
    if (controlsVisible && canHideControls()) { clearTimeout(controlsTimer); setControlsVisible(false); }
    else showControls();
  });
  $('player-settings-button').addEventListener('click', () => { $('player-settings').open = !$('player-settings').open; $('player-queue').open = false; panelState(); });
  $('player-queue-button').addEventListener('click', () => { $('player-queue').open = !$('player-queue').open; $('player-settings').open = false; panelState(); });
  $('player-settings').addEventListener('toggle', panelState);
  $('player-queue').addEventListener('toggle', panelState);
  stage.addEventListener('pointerdown', () => { keyboardMode = false; if (controlsVisible) scheduleHide(); });
  stage.addEventListener('pointermove', event => { if (event.pointerType === 'mouse') showControls(); });
  stage.addEventListener('focusin', event => { if (event.target !== $('screen-controls')) showControls(); });
  stage.addEventListener('focusout', () => queueMicrotask(scheduleHide));
  $('seek').addEventListener('pointerdown', () => { seeking = true; showControls(); });
  for (const event of ['pointerup','pointercancel','blur']) $('seek').addEventListener(event, () => { seeking = false; scheduleHide(); });
  $('reopen-player').addEventListener('click', () => { if (current) { returnFocus = document.activeElement; stage.hidden = false; keyboardMode = false; document.body.classList.add('cinema-open'); backgroundInert(true); showControls(); $('close-player').focus(); } });
  $('subtitle-select').addEventListener('change', () => safe(async () => {
    const token = ++generation; cues = []; renderCaptions();
    const id = $('subtitle-select').value;
    if (id) { const value = await request(`/api/subtitles/${id}`); if (token === generation) { cues = value.cues; renderCaptions(); } }
  }));
  for (const [id,key] of [['caption-size','size'],['caption-vertical','vertical'],['caption-horizontal','horizontal'],['caption-delay','delay'],['player-speed','speed'],['play-mode','mode'],['caption-enabled','enabled'],['keep-awake','keepAwake']]) {
    const control = $(id); control.type === 'checkbox' ? control.checked = preferences[key] : control.value = preferences[key];
    control.addEventListener(control.type === 'range' || control.type === 'number' ? 'input' : 'change', () => {
      preferences[key] = control.type === 'checkbox' ? control.checked : key === 'mode' ? control.value : Number(control.value);
      settings();
      if (key === 'keepAwake') safe(() => preferences.keepAwake ? acquireWake() : releaseWake());
    });
  }
  $('retry-wake').addEventListener('click', () => safe(acquireWake));
  document.addEventListener('keydown', event => {
    if (stage.hidden) return;
    keyboardMode = true; showControls();
    if (event.key === 'Escape') { safe(close); return; }
    if (event.key === 'Tab') {
      const focusable = [...stage.querySelectorAll('button:not(:disabled),input:not(:disabled),select,summary')].filter(n => n.getClientRects().length);
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
  });
  settings();
  function updateTitleMetadata(updated) {
    const byId=new Map(updated.map(track=>[track.id,track]));
    for(const track of tracks){const fresh=byId.get(track.id);if(fresh){track.title_ko=fresh.title_ko;track.title_translation_kind=fresh.title_translation_kind;track.title_translation=fresh.title_translation;}}
    if(current){$('player-title').textContent=window.AudioTrackTitle?.(current)||current.title;$('playing').textContent=window.AudioTrackTitle?.(current)||current.title;updateQueue();}
  }
  window.StudioPlayer = {open, move:core.move, updateTitleMetadata};
})();
