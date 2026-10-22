'use strict';
const $ = id => document.getElementById(id);
const kinds = {comic:'만화',translation:'번역본',voice_comic:'보이스코믹',audio:'음성판'};
let works = [], playlist = [], current = null, lastSaved = 0;
const audio = $('audio');
function el(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
}
function status(message, error = false) {
  $('status').textContent = message;
  $('status').className = error ? 'error' : '';
}
async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || '요청에 실패했습니다.');
  return result;
}
async function safely(action) {
  try { await action(); } catch (error) { status(error.message, true); }
}
function field(form, name) { return form.elements.namedItem(name).value; }
async function load() {
  works = (await api('/api/works')).works;
  const old = $('work-select').value;
  $('work-select').replaceChildren(el('option', '원작을 선택하세요'));
  $('work-select').firstChild.value = '';
  for (const work of works) {
    const option = el('option', `${work.title} · ${work.id.slice(0,8)}`);
    option.value = work.id;
    $('work-select').append(option);
  }
  if (works.some(w => w.id === old)) $('work-select').value = old;
  $('edition-form').querySelector('button').disabled = !works.length;
  render();
}
function render() {
  const query = $('search').value.trim().toLocaleLowerCase();
  const visible = works.filter(w => JSON.stringify(w).toLocaleLowerCase().includes(query));
  $('count').textContent = `${visible.length}개 원작`;
  $('library').replaceChildren();
  if (!visible.length) {
    const empty = el('div', undefined, 'empty');
    empty.append(el('h2', works.length ? '검색 결과가 없습니다' : '첫 번째 원작을 등록해 보세요'),
      el('p', '원작 아래 만화·번역본·보이스코믹·음성판을 별도로 연결할 수 있습니다.'));
    $('library').append(empty);
  }
  for (const work of visible) {
    const card = el('article', undefined, 'work');
    card.append(el('span', `ORIGINAL · ${work.id.slice(0,8)}`, 'eyebrow'), el('h2', work.title), el('span', `${work.editions.length}개 판본`, 'badge'));
    if (!work.editions.length) card.append(el('p', '아직 연결된 판본이 없습니다.'));
    for (const edition of work.editions) {
      const button = el('button', undefined, 'edition');
      button.append(el('span', edition.title), el('small', `${kinds[edition.kind]} · ${edition.language || '언어 미지정'} · ${edition.tracks.length} 트랙`));
      button.addEventListener('click', () => safely(() => detail(edition.id)));
      card.append(button);
    }
    $('library').append(card);
  }
}
function label(caption, input) {
  const node = el('label', caption); node.append(input); return node;
}
function input(name, placeholder = '', type = 'text') {
  const node = el('input'); node.name = name; node.placeholder = placeholder; node.type = type; node.required = true; return node;
}
function jsonInput(name) {
  const node = el('textarea'); node.name = name; node.value = '{}'; node.rows = 4; node.required = true; return node;
}
async function detail(id) {
  const edition = await api(`/api/editions/${id}`);
  const root = $('detail'); root.hidden = false; root.replaceChildren();
  root.append(el('span', `${kinds[edition.kind]} · ${edition.language || '언어 미지정'} · ${edition.id.slice(0,8)}`, 'eyebrow'), el('h2', edition.title));
  root.append(el('p', '제작진: ' + JSON.stringify(edition.credits)));
  const grid = el('div', undefined, 'detail-grid'), sources = el('section'), tracks = el('section');
  sources.append(el('h3', '출처와 원본 기록'));
  for (const source of edition.sources) {
    const item = el('div', undefined, 'source');
    item.append(el('strong', `${source.provider} / ${source.external_id}`));
    const snapshots = el('details'); snapshots.append(el('summary', `원본 기록 ${source.snapshots.length}개 보기`));
    for (const snapshot of source.snapshots) {
      const link = el('a', snapshot.submitted_url); link.href = snapshot.submitted_url; link.target = '_blank'; link.rel = 'noreferrer noopener';
      snapshots.append(el('p', new Date(snapshot.recorded * 1000).toLocaleString()), link, el('pre', JSON.stringify(snapshot.raw_metadata, null, 2)));
    }
    item.append(snapshots); sources.append(item);
  }
  const sourceForm = el('form');
  sourceForm.append(label('출처 이름', input('provider', 'dlsite / dmm / hitomi')), label('출처별 원본 ID', input('external_id', '예: RJ01234567')),
    label('원본 URL', input('url', 'https://…', 'url')), label('원본 메타데이터 JSON', jsonInput('raw_metadata')), el('button', '원본 기록 추가'));
  sourceForm.addEventListener('submit', event => { event.preventDefault(); safely(async () => {
    await api(`/api/editions/${id}/sources`, {provider:field(sourceForm,'provider'), external_id:field(sourceForm,'external_id'), url:field(sourceForm,'url'), raw_metadata:JSON.parse(field(sourceForm,'raw_metadata'))});
    await load(); await detail(id); status('원본 기록을 추가했습니다. 이전 기록도 보존됩니다.');
  }); });
  sources.append(sourceForm);
  tracks.append(el('h3', '트랙 목록'));
  const list = el('ol', undefined, 'tracks');
  for (const track of edition.tracks) {
    const li = el('li'), button = el('button', `${track.title} · 이어듣기 ${Math.floor(track.resume)}초`);
    button.addEventListener('click', () => safely(() => play(edition.tracks, track)));
    li.append(button); list.append(li);
  }
  tracks.append(list);
  if (['audio','voice_comic'].includes(edition.kind)) {
    tracks.append(el('p', '이 서비스의 media 폴더에 직접 준비한 파일을 등록하세요. 파일은 읽기 전용으로 재생합니다.'));
    const trackForm = el('form'), duration = input('duration', '길이를 모르면 0', 'number');
    duration.value = '0'; duration.min = '0'; duration.step = 'any';
    trackForm.append(label('트랙 제목', input('title')), label('media 폴더 안의 상대 경로', input('relative_path', 'sample/01.wav')),
      label('길이 (초)', duration), el('button', '트랙 등록'));
    trackForm.addEventListener('submit', event => { event.preventDefault(); safely(async () => {
      await api(`/api/editions/${id}/tracks`, {title:field(trackForm,'title'), relative_path:field(trackForm,'relative_path'), duration:Number(field(trackForm,'duration'))});
      await load(); await detail(id); status('트랙을 등록했습니다.');
    }); });
    tracks.append(trackForm);
  } else tracks.append(el('p', '이 판본은 원작 연결·출처 관리용입니다. 음성 재생은 음성판·보이스코믹에서 사용할 수 있습니다.'));
  grid.append(sources, tracks); root.append(grid);
}
async function saveProgress() {
  const track = current;
  if (!track || audio.readyState < 1 || !audio.currentSrc.endsWith(`/api/tracks/${track.id}/media`) || !Number.isFinite(audio.currentTime)) return;
  const seconds = Math.min(audio.currentTime, track.duration || Infinity);
  const saved = await api(`/api/tracks/${track.id}/progress`, {seconds});
  track.resume = saved.resume;
}
async function play(tracks, track) {
  await saveProgress();
  playlist = tracks; current = track; lastSaved = 0;
  $('playing').textContent = track.title;
  audio.src = `/api/tracks/${track.id}/media`;
  audio.load();
  updateNavigation();
}
function updateNavigation() {
  const index = playlist.findIndex(t => t.id === current?.id);
  $('previous').disabled = index <= 0;
  $('next').disabled = index < 0 || index >= playlist.length - 1;
}
function skip(delta) {
  const index = playlist.findIndex(t => t.id === current?.id);
  const track = playlist[index + delta];
  if (track) safely(() => play(playlist, track));
}
audio.addEventListener('loadedmetadata', () => {
  audio.playbackRate = Number($('speed').value);
  const resume = current?.resume || 0;
  audio.currentTime = Number.isFinite(audio.duration) && resume >= audio.duration - 0.5 ? 0 : resume;
  audio.play().catch(() => status('재생 버튼을 눌러 이어듣기를 시작하세요.'));
});
audio.addEventListener('error', () => status('음성을 열 수 없습니다. 파일 위치와 브라우저의 형식 지원을 확인하세요.', true));
audio.addEventListener('timeupdate', () => {
  if (Date.now() - lastSaved >= 5000 && !audio.paused) { lastSaved = Date.now(); safely(saveProgress); }
});
audio.addEventListener('pause', () => safely(saveProgress));
audio.addEventListener('ended', () => safely(async () => { await saveProgress(); skip(1); }));
$('speed').addEventListener('change', () => { audio.playbackRate = Number($('speed').value); });
$('previous').addEventListener('click', () => skip(-1));
$('next').addEventListener('click', () => skip(1));
$('search').addEventListener('input', render);
$('work-form').addEventListener('submit', event => {
  event.preventDefault(); safely(async () => {
    const work = await api('/api/works', {title:field(event.target,'title')});
    event.target.reset(); await load(); $('work-select').value = work.id; status('새 원작을 등록했습니다.');
  });
});
$('edition-form').addEventListener('submit', event => {
  event.preventDefault(); safely(async () => {
    const form = event.target;
    const edition = await api('/api/editions', {work_id:field(form,'work_id'),title:field(form,'title'),kind:field(form,'kind'),language:field(form,'language'),credits:JSON.parse(field(form,'credits'))});
    form.reset(); await load(); await detail(edition.id); status('선택한 원작에 별도 판본을 연결했습니다.');
  });
});
updateNavigation(); safely(load);
