'use strict';
const $ = id => document.getElementById(id);
const kinds = {comic:'만화',translation:'번역본',voice_comic:'보이스코믹',audio:'음성판'};
let works = [], activeEdition = null;
const translations = {none:'번역 없음',subtitles:'번역 자막',embedded:'자막 합성 영상'};
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
    card.append(el('span', work.codes.map(c => c.code).join(' · ') || `ORIGINAL · ${work.id.slice(0,8)}`, 'eyebrow'), el('h2', work.title), el('span', `${work.editions.length}개 판본`, 'badge'));
    if (!work.editions.length) card.append(el('p', '아직 연결된 판본이 없습니다.'));
    for (const edition of work.editions) {
      const button = el('button', undefined, 'edition');
      const translation = ['audio','voice_comic'].includes(edition.kind) ? ` · ${translations[edition.profile.translation]}` : '';
      button.append(el('span', edition.title), el('small', `${edition.profile.media_type === 'video' ? '영상' : kinds[edition.kind]}${translation} · ${edition.language || '언어 미지정'} · ${edition.tracks.length} 트랙`));
      button.addEventListener('click', () => safely(() => detail(edition.id, true)));
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
async function detail(id, scroll = false) {
  const edition = await api(`/api/editions/${id}`);
  activeEdition = id;
  const root = $('detail'); root.hidden = false; root.replaceChildren();
  root.append(el('span', `${kinds[edition.kind]} · ${edition.language || '언어 미지정'} · ${edition.id.slice(0,8)}`, 'eyebrow'), el('h2', edition.title));
  root.append(el('p', '제작진: ' + JSON.stringify(edition.credits)));
  const profileForm = el('form', undefined, 'profile-form');
  const mediaType = el('select'), translation = el('select'); mediaType.name = 'media_type'; translation.name = 'translation';
  for (const [value,title] of [['audio','음성'],['video','영상']]) { const option=el('option',title); option.value=value; mediaType.append(option); }
  for (const [value,title] of Object.entries(translations)) { const option=el('option',title); option.value=value; translation.append(option); }
  mediaType.value=edition.profile.media_type; translation.value=edition.profile.translation;
  profileForm.append(label('미디어 유형',mediaType),label('번역 상태',translation),el('button','판본 상태 저장'));
  profileForm.addEventListener('submit', event => { event.preventDefault(); safely(async () => {
    await api(`/api/editions/${id}/profile`, {media_type:mediaType.value,translation:translation.value}); await load(); await detail(id); status('판본 상태를 저장했습니다.');
  }); });
  root.append(profileForm);
  const work = works.find(w => w.id === edition.work_id), codeForm = el('form', undefined, 'code-form'), codeInput = input('code','RJ01234567');
  codeInput.pattern='RJ[0-9]{6,12}';
  codeForm.append(el('p', `원작 RJ 분류: ${(work?.codes || []).map(c => c.code).join(', ') || '미등록'}`), label('이 원작에 RJ 코드 연결',codeInput),el('button','RJ 코드 연결'));
  codeForm.addEventListener('submit', event => { event.preventDefault(); safely(async () => {
    await api(`/api/works/${edition.work_id}/codes`,{code:codeInput.value}); await load(); await detail(id); status('RJ 코드를 연결했습니다.');
  }); }); root.append(codeForm);
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
  const playAll = el('button','전체 트랙 재생'); playAll.disabled = !edition.tracks.length;
  playAll.addEventListener('click', () => { const pending=window.StudioPlayer.open(edition.tracks,edition.tracks[0]); safely(() => pending); });
  tracks.append(playAll,el('p','재생 순서는 플레이어 안에서 ↑ ↓로 변경할 수 있습니다.'));
  const list = el('ol', undefined, 'tracks');
  for (const track of edition.tracks) {
    const li = el('li'), button = el('button', `${track.title} · 이어듣기 ${Math.floor(track.resume)}초`);
    button.addEventListener('click', () => { const pending=window.StudioPlayer.open(edition.tracks,track); safely(() => pending); });
    li.append(button);
    li.append(el('small', `${track.subtitles.length}개 자막`));
    const subtitleForm = el('form'), path = input('relative_path', 'sample/01.ko.srt'), language=input('language','ko'), name=input('label','한국어');
    language.value='ko'; name.value='한국어';
    subtitleForm.append(label('자막 파일 상대 경로 (.srt / .vtt)',path),label('자막 언어',language),label('자막 이름',name),el('button','자막 연결'));
    subtitleForm.addEventListener('submit', event => { event.preventDefault(); safely(async () => {
      await api(`/api/tracks/${track.id}/subtitles`,{relative_path:path.value,language:language.value,label:name.value}); await load(); await detail(id); status('자막을 연결했습니다.');
    }); });
    const subtitleDetails = el('details'); subtitleDetails.append(el('summary','자막 추가'),subtitleForm); li.append(subtitleDetails); list.append(li);
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
  if (scroll) root.scrollIntoView({behavior:'smooth',block:'start'});
}
document.addEventListener('player-closed', () => safely(async () => { await load(); if (activeEdition) await detail(activeEdition); }));
$('search').addEventListener('input', render);
$('work-form').addEventListener('submit', event => {
  event.preventDefault(); safely(async () => {
    const work = await api('/api/works', {title:field(event.target,'title'),rj_code:field(event.target,'rj_code')});
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
safely(load);
