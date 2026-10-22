'use strict';
const $=id=>document.getElementById(id),core=window.LibraryCore;
let works=[],filter='all',activeWork=null,activeEdition=null,page=1,editingOrder=false,orderPending=false;
let fileList=[],filesLoaded=false,toastTimer,listLayout=false;
const viewNames={all:'전체 보관함',resume:'이어듣기',audio:'원본 음성',subtitles:'번역 자막',video:'영상'};
try{listLayout=localStorage.getItem('audio-library-layout')==='list';}catch(_){}
function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function button(text,cls,action){const n=el('button',text,cls);n.type='button';n.addEventListener('click',action);return n;}
function status(message,error=false){clearTimeout(toastTimer);const inside=$('manager').open,target=inside?$('manager-status'):$('status');target.textContent=message;target.hidden=false;target.className=inside?'dialog-status'+(error?' error':''):error?'error':'';toastTimer=setTimeout(()=>{target.hidden=true;},error?9000:4500);}
async function api(path,data){const r=await fetch(path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}),v=await r.json();if(!r.ok)throw new Error(v.error||'요청을 처리하지 못했습니다.');return v;}
async function safely(action){try{await action();}catch(error){status(error.message,true);}}
const field=(form,name)=>form.elements.namedItem(name).value;
function input(name,placeholder='',type='text',required=true){const n=el('input');Object.assign(n,{name,placeholder,type,required});return n;}
function label(text,control){const n=el('label',text);n.append(control);return n;}
function choice(name,options,selected=''){const n=el('select');n.name=name;for(const[value,text]of options){const o=el('option',text);o.value=value;n.append(o);}n.value=selected;return n;}
function fold(title,...nodes){const n=el('details',undefined,'management-section');n.append(el('summary',title),...nodes);return n;}
function savedEdition(id){try{return localStorage.getItem('audio-edition-'+id)||'';}catch(_){return '';}}
function rememberEdition(id,edition){try{localStorage.setItem('audio-edition-'+id,edition);}catch(_){}}
async function load(){works=(await api('/api/works')).works;fillManagerSelects();renderLibrary();}
function fillManagerSelects(){
  const old=$('work-select').value;
  $('work-select').replaceChildren(el('option','작품을 선택하세요'));$('work-select').firstChild.value='';
  $('manage-edition-select').replaceChildren(el('option','버전을 선택하세요'));$('manage-edition-select').firstChild.value='';
  for(const w of works){const name=[w.codes.map(c=>c.code).join(' · '),w.title].filter(Boolean).join(' / '),o=el('option',name);o.value=w.id;$('work-select').append(o);for(const e of w.editions){const n=el('option',`${name} / ${e.title}`);n.value=e.id;$('manage-edition-select').append(n);}}
  $('work-select').value=activeWork||old;$('edition-form').querySelector('button').disabled=!works.length;
}
function cover(work){
  const art=el('div',undefined,'cover'),placeholder=el('div',undefined,'placeholder');
  placeholder.append(el('span','♫','cover-symbol'),el('small',work.codes[0]?.code||'AUDIO COLLECTION'));art.append(placeholder,el('span',`${work.editions.length} 버전`,'pages'));
  const resumed=work.editions.map(core.resumeTrack).find(Boolean);if(resumed?.duration){const b=el('div',undefined,'read-progress');b.style.width=`${Math.min(100,resumed.resume/resumed.duration*100)}%`;art.append(b);}return art;
}
function renderLibrary(){
  const visible=core.filterWorks(works,$('search').value,filter,$('sort').value),pages=Math.max(1,Math.ceil(visible.length/24));page=Math.min(page,pages);
  $('page-title').textContent=viewNames[filter];$('count').textContent=`${visible.length} 작품`;$('page-description').textContent=filter==='resume'?'멈췄던 트랙부터 이어서 감상하세요.':'원본 음성부터 자막 영상까지, 작품별로 모아 감상하세요.';
  $('library').className=listLayout?'grid list':'grid';$('library').replaceChildren();
  for(const work of visible.slice((page-1)*24,page*24)){
    const card=el('article',undefined,'card'),open=button('','card-open',()=>showWork(work.id)),info=el('div',undefined,'card-info');
    info.append(el('h3',work.title),el('p',core.creator(work)||work.codes.map(c=>c.code).join(' · ')||'RJ 미등록','card-artist'));open.append(cover(work),info);card.append(open);
    const pills=el('div',undefined,'card-sources');for(const name of [...new Set(work.editions.map(core.editionLabel))])pills.append(el('span',name,'source-pill'));card.append(pills);
    const edition=core.preferred(work,'resume',savedEdition(work.id)),track=edition&&core.resumeTrack(edition);if(track)card.append(button(`▶ ${core.time(track.resume)}부터 이어듣기`,'resume-link',()=>start(edition,track)));
    $('library').append(card);
  }
  if(!visible.length){
    const empty=el('div',undefined,'empty');empty.append(el('span','▤'),el('h2',works.length?'조건에 맞는 작품이 없습니다':'아직 보관함이 비어 있습니다'),el('p',works.length?'검색어나 감상 버전 분류를 바꿔 보세요.':'작품을 추가하고 보유한 음성·영상 파일을 연결해 주세요.'));
    if(works.length)empty.append(button('전체 보관함 보기','quiet',()=>selectFilter('all')));
    else{if(location.hostname==='127.0.0.1'&&location.port==='43130'){const sample=el('a','샘플 서재 둘러보기','primary');sample.href='http://127.0.0.1:43132/';empty.append(sample,el('p','샘플은 별도 테스트 서재에 준비되어 있습니다.','form-hint'));}empty.append(button('＋ 작품 추가','primary',()=>safely(()=>openManager('new-work'))));}
    $('library').append(empty);
  }
  $('pagination').hidden=pages<=1;$('page-number').textContent=`${page} / ${pages}`;$('previous-page').disabled=page<=1;$('next-page').disabled=page>=pages;
  $('layout').textContent=listLayout?'▦':'☷';$('layout').setAttribute('aria-label',listLayout?'카드 보기로 전환':'목록 보기로 전환');
  for(const n of document.querySelectorAll('[data-filter]')){const on=n.dataset.filter===filter;n.classList.toggle('selected',on);n.classList.toggle('active',on);n.setAttribute('aria-pressed',String(on));}
}
function selectFilter(value){filter=value;page=1;showLibrary();}
function showLibrary(push=true){activeWork=null;activeEdition=null;editingOrder=false;$('library-view').hidden=false;$('work-view').hidden=true;renderLibrary();if(push){history.pushState(null,'',location.pathname+location.search);window.scrollTo({top:0});}}
function showWork(id,editionId='',push=true){
  const w=works.find(w=>w.id===id);if(!w){showLibrary(false);return;}const e=core.preferred(w,editionId?'all':filter,editionId||savedEdition(id));activeWork=id;activeEdition=e?.id||null;if(e)rememberEdition(id,e.id);
  $('library-view').hidden=true;$('work-view').hidden=false;renderWork(w,e);if(push){history.pushState(null,'',`#work/${id}${e?'/'+e.id:''}`);window.scrollTo({top:0});}
}
function start(edition,track,options={}){if(!track)return;if($('manager').open)$('manager').close();activeWork=edition.work_id;activeEdition=edition.id;rememberEdition(edition.work_id,edition.id);$('player-bar').hidden=false;const p=window.StudioPlayer.open(edition.tracks,track,options);safely(()=>p);}
function renderWork(work,edition){
  const root=$('detail');root.replaceChildren();const hero=el('div',undefined,'work-hero'),info=el('div',undefined,'work-info');
  info.append(el('div',work.codes.map(c=>c.code).join(' · ')||'MY COLLECTION','eyebrow'),el('h1',work.title));if(core.creator(work))info.append(el('p',core.creator(work),'muted'));info.append(el('p',`${work.editions.length}개 감상 버전`,'muted'));hero.append(cover(work),info);root.append(hero);
  const versions=el('div',undefined,'version-tabs');versions.setAttribute('role','group');versions.setAttribute('aria-label','감상 버전 선택');
  for(const e of work.editions){const tab=button('',e.id===edition?.id?'version-tab selected':'version-tab',()=>{editingOrder=false;showWork(work.id,e.id);});tab.setAttribute('aria-pressed',String(e.id===edition?.id));tab.append(el('strong',core.editionLabel(e)),el('small',`${e.tracks.length} 트랙 · ${core.language(e.language)}`));versions.append(tab);}root.append(versions);
  if(!edition){const empty=el('div',undefined,'empty');empty.append(el('h2','감상 버전을 추가해 주세요'),el('p','같은 작품의 원본·번역 자막·영상은 각각 별도 버전으로 연결합니다.'),button('＋ 버전 추가','primary',()=>safely(()=>openManager('new-edition'))));root.append(empty);return;}
  const panel=el('section',undefined,'listening-panel'),heading=el('div',undefined,'listening-heading'),description=el('div'),known=edition.tracks.length&&edition.tracks.every(t=>t.duration>0);
  description.append(el('div',core.editionLabel(edition),'eyebrow'),el('h2',edition.title),el('p',`${edition.tracks.length} 트랙${known?' · '+core.time(edition.tracks.reduce((s,t)=>s+t.duration,0)):''}${core.hasSubtitles(edition)?' · 자막 선택 가능':''}`,'muted'));heading.append(description);
  const actions=el('div',undefined,'listening-actions'),resume=core.resumeTrack(edition),play=button(resume?'▶ 처음부터 전체 재생':'▶ 전체 재생','primary',()=>{if(edition.tracks.length)start(edition,edition.tracks[0],{mode:'all',fromStart:true});});play.disabled=!core.playable(edition);actions.append(play);
  if(resume)actions.prepend(button(`▶ ${core.time(resume.resume)}부터 이어듣기`,'primary',()=>start(edition,resume)));
  if(edition.tracks.length>1)actions.append(button(editingOrder?'순서 편집 완료':'⇅ 순서 편집','quiet',()=>{editingOrder=!editingOrder;renderWork(work,edition);}));heading.append(actions);panel.append(heading);
  if(edition.profile.translation==='embedded')panel.append(el('p','영상 자체에 포함된 자막입니다. 별도 자막이 있는 경우 플레이어에서 조절할 수 있습니다.','listening-note'));
  else if(edition.profile.translation==='subtitles'&&!core.hasSubtitles(edition))panel.append(el('p','이 버전에는 아직 자막 파일이 연결되지 않았습니다. 작품 관리에서 연결할 수 있습니다.','listening-note'));
  const list=el('ol',undefined,'track-list');edition.tracks.forEach((track,index)=>{
    const row=el('li',undefined,'track-row'),playTrack=button('','track-play',()=>start(edition,track)),info=el('div',undefined,'track-info');info.append(el('strong',track.title),el('small',track.subtitles.length?track.subtitles.map(s=>s.label).join(' · '):edition.profile.translation==='embedded'?'영상 내 자막':'별도 자막 없음'));playTrack.append(el('span',String(index+1).padStart(2,'0'),'track-index'),info,el('span',track.duration?core.time(track.duration):'—','track-time'),el('span','▶','track-play-icon'));row.append(playTrack);
    if(editingOrder){const order=el('div',undefined,'order-buttons');for(const[delta,mark,name]of[[-1,'↑','위로'],[1,'↓','아래로']]){const move=button(mark,'icon-button',()=>safely(async()=>{if(orderPending)return;orderPending=true;const ids=window.StudioPlayer.move(edition.tracks,track.id,delta).map(t=>t.id);try{await api(`/api/editions/${edition.id}/order`,{track_ids:ids});await load();showWork(work.id,edition.id,false);status('재생 순서를 저장했습니다.');}finally{orderPending=false;}}));move.disabled=orderPending||(delta<0?index===0:index===edition.tracks.length-1);move.setAttribute('aria-label',`${track.title} ${name}`);order.append(move);}row.append(order);}list.append(row);
  });panel.append(list);
  if(!edition.tracks.length)panel.append(el('p','아직 재생할 파일이 연결되지 않았습니다.','muted'),button('파일 연결하기','quiet',()=>safely(()=>openManager('edition-settings'))));root.append(panel);
}
async function openManager(panel='new-work'){fillManagerSelects();if(activeWork)$('work-select').value=activeWork;$('manager').showModal();setManagerPanel(panel);if(panel==='edition-settings'&&activeEdition){$('manage-edition-select').value=activeEdition;await renderManagement(activeEdition);}}
function setManagerPanel(panel){$('manager-status').hidden=true;for(const n of document.querySelectorAll('.manager-panel'))n.hidden=n.id!==panel;for(const n of document.querySelectorAll('[data-panel]'))n.classList.toggle('selected',n.dataset.panel===panel);$('manager-title').textContent=panel==='new-work'?'작품 추가':panel==='new-edition'?'감상 버전 추가':'파일·출처 관리';}
async function loadFiles(){const result=await api('/api/local-files');fileList=result.items;filesLoaded=true;if(result.truncated)status('파일이 많아 일부만 표시합니다. 원하는 파일이 없으면 직접 경로를 입력할 수 있습니다.');}
function filePicker(kind){const files=fileList.filter(f=>kind==='subtitle'?f.kind==='subtitle':f.kind!=='subtitle'),s=choice('relative_path',[['','파일을 선택하세요'],...files.map(f=>[f.relative_path,f.relative_path])]);s.required=true;return s;}
async function refreshManagement(id,message){await load();if(activeWork)showWork(activeWork,activeEdition,false);$('manage-edition-select').value=id;await renderManagement(id);status(message);}
async function renderManagement(id){
  const root=$('manage-content');root.replaceChildren();if(!id)return;const e=await api(`/api/editions/${id}`);if(!filesLoaded)await loadFiles();root.append(el('h3',e.title),button('↻ 연결된 파일 새로고침','quiet',()=>safely(async()=>{await loadFiles();await renderManagement(id);})));
  if(!fileList.length)root.append(el('p','이 서버에 연결된 미디어 파일이 없습니다. 파일을 준비한 뒤 목록을 새로고침해 주세요.','form-hint'));
  const trackForm=el('form',undefined,'management-form'),selected=filePicker('media'),title=input('title','파일을 고르면 이름이 채워집니다.'),duration=input('duration','모르면 0','number'),manual=input('manual_path','폴더/파일.mp3','text',false);Object.assign(duration,{value:'0',min:'0',step:'any'});
  selected.addEventListener('change',()=>{title.value=selected.value.split('/').pop().replace(/\.[^.]+$/,'');});manual.addEventListener('input',()=>{selected.required=!manual.value;});
  trackForm.append(label('연결할 음성·영상 파일',selected),label('트랙 이름',title),fold('직접 경로 입력 · 재생 길이',label('파일 경로 (목록에 없을 때)',manual),label('길이 (초)',duration)),el('button','트랙 연결','primary'));
  trackForm.addEventListener('submit',event=>{event.preventDefault();safely(async()=>{await api(`/api/editions/${id}/tracks`,{title:title.value,relative_path:manual.value||selected.value,duration:Number(duration.value)});await refreshManagement(id,'트랙을 연결했습니다.');});});root.append(fold('＋ 트랙 연결',trackForm));
  for(const track of e.tracks){const form=el('form',undefined,'management-form'),file=filePicker('subtitle'),name=input('label','한국어'),language=choice('language',[['ko','한국어'],['ja','일본어'],['en','영어']],'ko');name.value='한국어';form.append(el('p',track.subtitles.length?`연결된 자막: ${track.subtitles.map(s=>s.label).join(', ')}`:'연결된 자막이 없습니다.','form-hint'),label('자막 파일',file),label('표시 이름',name),label('자막 언어',language),el('button','자막 연결','primary'));form.addEventListener('submit',event=>{event.preventDefault();safely(async()=>{await api(`/api/tracks/${track.id}/subtitles`,{relative_path:file.value,label:name.value,language:language.value});await refreshManagement(id,'자막을 연결했습니다.');});});root.append(fold(`${track.title} · 자막 관리`,form));}
  const profile=el('form',undefined,'management-form'),media=choice('media_type',[['audio','음성'],['video','영상']],e.profile.media_type),translation=choice('translation',[['none','번역 없음'],['subtitles','별도 번역 자막'],['embedded','자막 합성 영상']],e.profile.translation);profile.append(label('미디어 유형',media),label('번역 상태',translation),el('button','상태 저장','primary'));profile.addEventListener('submit',event=>{event.preventDefault();safely(async()=>{await api(`/api/editions/${id}/profile`,{media_type:media.value,translation:translation.value});await refreshManagement(id,'버전 상태를 저장했습니다.');});});
  const codeForm=el('form',undefined,'management-form'),code=input('code','RJ01234567');code.pattern='RJ[0-9]{6,12}';codeForm.append(label('이 작품에 RJ 코드 연결',code),el('button','RJ 연결','primary'));codeForm.addEventListener('submit',event=>{event.preventDefault();safely(async()=>{await api(`/api/works/${e.work_id}/codes`,{code:code.value});await refreshManagement(id,'RJ 코드를 연결했습니다.');});});root.append(fold('버전 상태 · RJ 분류',profile,codeForm));
  const sources=el('div');for(const source of e.sources){const records=el('div',undefined,'source');records.append(el('strong',`${source.provider} / ${source.external_id}`));for(const snapshot of source.snapshots){const link=el('a',snapshot.submitted_url);Object.assign(link,{href:snapshot.submitted_url,target:'_blank',rel:'noopener noreferrer'});records.append(fold(new Date(snapshot.recorded*1000).toLocaleString(),link,el('pre',JSON.stringify(snapshot.raw_metadata,null,2))));}sources.append(records);}
  const form=el('form',undefined,'management-form'),metadata=el('textarea');Object.assign(metadata,{name:'raw_metadata',value:'{}',rows:4});form.append(label('출처',input('provider','dlsite')),label('출처별 원본 ID',input('external_id','RJ01234567')),label('원본 URL',input('url','https://…','url')),fold('원본 메타데이터 JSON',label('JSON 원본',metadata)),el('button','출처 기록 추가','primary'));form.addEventListener('submit',event=>{event.preventDefault();safely(async()=>{await api(`/api/editions/${id}/sources`,{provider:field(form,'provider'),external_id:field(form,'external_id'),url:field(form,'url'),raw_metadata:JSON.parse(metadata.value)});await refreshManagement(id,'원본 기록을 추가했습니다. 이전 기록도 보존됩니다.');});});sources.append(form);root.append(fold('출처와 원본 기록 (선택)',sources));
}
function route(){const m=/^#work\/([0-9a-f]{32})(?:\/([0-9a-f]{32}))?$/.exec(location.hash);if(m)showWork(m[1],m[2]||'',false);else showLibrary(false);}
document.addEventListener('player-closed',()=>safely(async()=>{await load();if(activeWork)showWork(activeWork,activeEdition,false);}));
for(const n of document.querySelectorAll('[data-filter]'))n.addEventListener('click',()=>selectFilter(n.dataset.filter));
for(const n of document.querySelectorAll('[data-panel]'))n.addEventListener('click',()=>{setManagerPanel(n.dataset.panel);if(n.dataset.panel==='edition-settings'&&activeEdition){$('manage-edition-select').value=activeEdition;safely(()=>renderManagement(activeEdition));}});
$('search').addEventListener('input',()=>{page=1;showLibrary();});$('sort').addEventListener('change',()=>{page=1;renderLibrary();});
$('layout').addEventListener('click',()=>{listLayout=!listLayout;try{localStorage.setItem('audio-library-layout',listLayout?'list':'grid');}catch(_){}renderLibrary();});
$('previous-page').addEventListener('click',()=>{page--;renderLibrary();});$('next-page').addEventListener('click',()=>{page++;renderLibrary();});$('back-library').addEventListener('click',()=>showLibrary());
$('manage-work').addEventListener('click',()=>safely(()=>openManager(activeEdition?'edition-settings':'new-edition')));$('add-work').addEventListener('click',()=>safely(()=>openManager('new-work')));$('close-manager').addEventListener('click',()=>$('manager').close());$('manage-edition-select').addEventListener('change',()=>safely(()=>renderManagement($('manage-edition-select').value)));
$('work-form').addEventListener('submit',event=>{event.preventDefault();safely(async()=>{const f=event.target,w=await api('/api/works',{title:field(f,'title'),rj_code:field(f,'rj_code')});f.reset();await load();activeWork=w.id;activeEdition=null;$('work-select').value=w.id;setManagerPanel('new-edition');status('작품을 등록했습니다. 감상 버전을 추가해 주세요.');});});
$('edition-form').addEventListener('submit',event=>{event.preventDefault();safely(async()=>{const f=event.target,media=field(f,'media_type'),translation=field(f,'translation');if(translation==='embedded'&&media!=='video')throw new Error('자막이 합성된 버전은 미디어를 영상으로 선택하세요.');const e=await api('/api/editions',{work_id:field(f,'work_id'),title:field(f,'title'),kind:'audio',language:field(f,'language'),credits:field(f,'circle')?{circle:field(f,'circle')}:{} });await api(`/api/editions/${e.id}/profile`,{media_type:media,translation});f.reset();activeWork=e.work_id;activeEdition=e.id;await load();showWork(activeWork,activeEdition);setManagerPanel('edition-settings');$('manage-edition-select').value=e.id;await renderManagement(e.id);status('이 버전에 연결할 파일을 선택해 주세요.');});});
window.addEventListener('popstate',route);window.addEventListener('hashchange',route);
document.addEventListener('keydown',event=>{if(event.key==='/'&&!$('manager').open&&$('cinema').hidden&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName)){event.preventDefault();$('search').focus();}});
safely(async()=>{await load();route();const h=await api('/api/health');$('connection-dot').classList.add(h.status==='ok'?'online':'offline');$('connection-text').replaceChildren(el('span','서버 연결됨'),el('small','개인 음성 라이브러리'));});
