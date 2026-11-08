'use strict';
const $=id=>document.getElementById(id),core=window.LibraryCore;
const basePath=location.pathname.startsWith('/audio/')?'/audio':'';
let works=[],catalogWorks=[],filter='all',activeWork=null,activeEdition=null,page=1,editingOrder=false,orderPending=false;
let fileList=[],filesLoaded=false,toastTimer,listLayout=false;
let preferences={},favoritesOnly=false,selectedTags=[],excludedTags=[],provider='all';
const mediaFilters={subtitles:'all',script:'all',dubbing:'all'},mediaDrafts=new Map();
let hiddenTags={hidden_rplay_tags:[],hidden_dlsite_tags:[],hidden_tags:[],favorite_tags:[],tag_aliases:{},tag_names:{},revision:0},tagVisibilityRevision=0,tagDraft=null,tagSaving=false;
let tagMergeSelection=new Set(),tagEditKey='',tagLikeSaving=false,tagRandomSeed=Date.now(),workRandomSeed=Date.now();
let folderView=false;
let loadGeneration=0;
const displayKey='audio-display-settings-v1',display={tagLanguage:'ko',titleLanguage:'ko',trackLanguage:'both',groupSameWork:true,pageSize:'24',sort:'added',tagSort:'count-desc'};
const openHoldings=new Set();
const translationDrafts=new Map(),translationOpen=new Set();
const sortValues=['added','oldest','title','title-desc','provider','rj','tracks','tracks-asc','duration','duration-asc','random'];
const tagSortValues=['count-desc','count-asc','name','random'];
try{const saved=JSON.parse(localStorage.getItem(displayKey)||'null');if(saved){if(['ko','ja'].includes(saved.tagLanguage))display.tagLanguage=saved.tagLanguage;if(['ko','ja','both'].includes(saved.titleLanguage))display.titleLanguage=saved.titleLanguage;if(['ko','original','both'].includes(saved.trackLanguage))display.trackLanguage=saved.trackLanguage;if(typeof saved.groupSameWork==='boolean')display.groupSameWork=saved.groupSameWork;if(['12','24','48','96','all'].includes(saved.pageSize))display.pageSize=saved.pageSize;if(sortValues.includes(saved.sort))display.sort=saved.sort;if(tagSortValues.includes(saved.tagSort))display.tagSort=saved.tagSort;}}catch(_){}
const tagLabel=tag=>core.tagLabel(tag,display.tagLanguage),displayTitle=work=>core.displayTitle(work,display.titleLanguage);
window.AudioTrackTitle=track=>core.trackTitle(track,display.trackLanguage);
function saveDisplay(){try{localStorage.setItem(displayKey,JSON.stringify(display));}catch(_){status('표시 설정을 저장하지 못했습니다. 이번 화면에만 적용합니다.',true);}}
const preferenceKey=id=>'audio-work-preferences-v1:'+id;
const viewNames={all:'전체 보관함',resume:'이어듣기',audio:'음성',subtitles:'자막 있는 버전',video:'영상','ko-audio':'한국어 음성','ja-audio':'일본어 음성','unknown-audio':'음성 언어 미확인',untagged:'태그 미등록','translation-issues':'번역 검토 필요'};
try{listLayout=localStorage.getItem('audio-library-layout')==='list';}catch(_){}
function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function icon(name){
  const paths={fullscreen:'<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/>',previous:'<path d="m18 5-11 7 11 7ZM5 5v14"/>',next:'<path d="m6 5 11 7-11 7ZM19 5v14"/>',settings:'<path d="M4 7h9m4 0h3M4 17h3m4 0h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',music:'<path d="M9 18V5l12-2v13M9 8l12-2"/><ellipse cx="6" cy="18" rx="3" ry="3"/><ellipse cx="18" cy="16" rx="3" ry="3"/>',library:'<rect x="3" y="4" width="5" height="16" rx="1"/><path d="M12 4v16m4-15 4 14"/>',clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',star:'<path d="m12 3 2.8 5.7 6.3.9-4.6 4.5 1.1 6.3-5.6-3-5.6 3 1.1-6.3L3 9.6l6.2-.9Z"/>',export:'<path d="M14 3h7v7m0-7L10 14M9 4H4v16h16v-5"/>',search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',plus:'<path d="M12 5v14M5 12h14"/>',back:'<path d="m10 5-7 7 7 7M3 12h18"/>',grid:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',list:'<path d="M9 5h12M9 12h12M9 19h12M3 5h1M3 12h1M3 19h1"/>',play:'<path d="m8 4 12 8-12 8Z"/>',folder:'<path d="M3 7V5a2 2 0 0 1 2-2h5l3 4h6a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z"/>'};
  const n=el('span',undefined,'ui-icon');n.setAttribute('aria-hidden','true');
  n.innerHTML=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${paths[name]||paths.music}</svg>`;return n;
}
function button(text,cls,action,iconName){const n=el('button',text,cls);n.type='button';n.addEventListener('click',action);if(iconName)n.prepend(icon(iconName));return n;}
function status(message,error=false){clearTimeout(toastTimer);const inside=$('manager').open,target=inside?$('manager-status'):$('status');target.textContent=message;target.hidden=false;target.className=inside?'dialog-status'+(error?' error':''):error?'error':'';toastTimer=setTimeout(()=>{target.hidden=true;},error?9000:4500);}
async function api(path,data){const r=await fetch(basePath+path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}),v=await r.json();if(!r.ok){const error=new Error(v.error||'요청을 처리하지 못했습니다.');error.status=r.status;throw error;}return v;}
async function safely(action){try{await action();}catch(error){status(error.message,true);}}
const field=(form,name)=>form.elements.namedItem(name).value;
function input(name,placeholder='',type='text',required=true){const n=el('input');Object.assign(n,{name,placeholder,type,required});return n;}
function label(text,control){const n=el('label',text);n.append(control);return n;}
function choice(name,options,selected=''){const n=el('select');n.name=name;for(const[value,text]of options){const o=el('option',text);o.value=value;n.append(o);}n.value=selected;return n;}
function fold(title,...nodes){const n=el('details',undefined,'management-section');n.append(el('summary',title),...nodes);return n;}
function savedEdition(id){try{return localStorage.getItem('audio-edition-'+id)||'';}catch(_){return '';}}
function rememberEdition(id,edition){try{localStorage.setItem('audio-edition-'+id,edition);}catch(_){}}
function readPreferences(id){
  try{
    const value=JSON.parse(localStorage.getItem(preferenceKey(id))||'null');
    if(value?.version===1&&typeof value.favorite==='boolean'&&Array.isArray(value.tags)&&value.tags.every(tag=>typeof tag==='string'))return{favorite:value.favorite,tags:core.parseTags(value.tags.join(','))};
  }catch(_){}
  return{favorite:false,tags:[]};
}
function savePreferences(id,changes){
  const value={version:1,...readPreferences(id),...changes};
  try{localStorage.setItem(preferenceKey(id),JSON.stringify(value));}catch(_){throw new Error('브라우저에 저장하지 못했습니다. 사이트 저장 공간 설정을 확인한 뒤 다시 시도하세요.');}
  preferences[id]=value;
}
function exportPreferences(){
  const items={};for(const work of catalogWorks){const value=readPreferences(work.id);if(value.favorite||value.tags.length)items[work.id]=value;}
  const blob=new Blob([JSON.stringify({type:'audio-studio-preferences',version:1,items},null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),link=document.createElement('a');
  link.href=url;link.download='audio-favorites-tags.json';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  status(`즐겨찾기·내 태그 ${Object.keys(items).length}개 작품의 백업을 저장했습니다.`);
}
async function importPreferences(file){
  if(!file)return;if(file.size>2*1024*1024)throw new Error('백업 파일은 2 MiB 이하만 가져올 수 있습니다.');
  const existing=Object.fromEntries(catalogWorks.map(w=>[w.id,readPreferences(w.id)])),result=core.mergePreferenceBackup(JSON.parse(await file.text()),catalogWorks,existing);
  const before=new Map(Object.keys(result.updates).map(id=>[id,localStorage.getItem(preferenceKey(id))]));
  try{for(const [id,value] of Object.entries(result.updates))localStorage.setItem(preferenceKey(id),JSON.stringify({version:1,...value}));}
  catch(error){let rollbackFailed=false;for(const [id,value] of before){try{if(value===null)localStorage.removeItem(preferenceKey(id));else localStorage.setItem(preferenceKey(id),value);}catch(_){rollbackFailed=true;}}throw new Error(rollbackFailed?'일부 항목의 저장·복원이 끝나지 않았습니다. 기존 백업을 보관하고 저장 공간을 확인해 주세요.':'저장하지 못해 이전 내용으로 복원했습니다. 브라우저 저장 공간을 확인해 주세요.');}
  Object.assign(preferences,result.updates);renderLibrary();if(activeWork){const work=works.find(w=>w.id===activeWork);renderWork(work,work.editions.find(e=>e.id===activeEdition));}
  status(`${Object.keys(result.updates).length}개 작품의 즐겨찾기·내 태그를 합쳤습니다.${result.skipped?` 현재 보관함에 없는 ${result.skipped}개는 건너뛰었습니다.`:''}`);
}
function updateFavoriteButton(n,work,compact){
  const on=preferences[work.id]?.favorite===true;
  n.setAttribute('aria-pressed',String(on));n.setAttribute('aria-label',`${displayTitle(work)} 즐겨찾기 ${on?'해제':'추가'}`);n.title=`즐겨찾기 ${on?'해제':'추가'}`;
  if(!compact)n.querySelector('.favorite-label').textContent=on?'즐겨찾기 해제':'즐겨찾기 추가';
}
function favoriteButton(work,compact=false){
  const n=button('',compact?'favorite-button':'quiet favorite-detail',()=>safely(()=>{
    savePreferences(work.id,{favorite:!preferences[work.id]?.favorite});renderLibrary();
    if(activeWork)updateFavoriteButton(n,work,compact);
    const buttons=[...document.querySelectorAll('[data-favorite-work]')];
    (buttons.find(b=>b.dataset.favoriteWork===work.id&&(activeWork?b.className.includes('favorite-detail'):b.className==='favorite-button'))||$('favorites-filter')).focus();
    status(preferences[work.id].favorite?'즐겨찾기에 추가했습니다.':'즐겨찾기에서 해제했습니다.');
  }));
  n.dataset.favoriteWork=work.id;
  n.append(icon('star'));if(!compact)n.append(el('span',undefined,'favorite-label'));updateFavoriteButton(n,work,compact);
  return n;
}
function renderTagFilters(){
  const focused=document.activeElement?.dataset?.tag||document.activeElement?.dataset?.favoriteTag,likedFocus=!!document.activeElement?.dataset?.favoriteTag;
  const rawGroups=core.tagGroups([...works.flatMap(w=>core.tags(w,preferences,hiddenTags)),...selectedTags,...excludedTags],hiddenTags);
  const counts=new Map();
  for(const group of core.groupWorks(core.filterWorks(works,$('search').value,filter,'added',{favoritesOnly,tags:selectedTags,excludeTags:excludedTags,preferences,provider,hiddenTags,mediaFilters,voiceActor:window.CatalogControls?.voice()||''}),display.groupSameWork))for(const key of new Set(group.members.flatMap(work=>core.tags(work,preferences,hiddenTags)).map(tag=>core.resolveTagKey(tag,hiddenTags))))counts.set(key,(counts.get(key)||0)+1);
  const groups=core.sortTagGroups(rawGroups,counts,{include:selectedTags,exclude:excludedTags,settings:hiddenTags,sort:display.tagSort,seed:tagRandomSeed,language:display.tagLanguage});
  const term=$('tag-search').value.trim().normalize('NFC').toLocaleLowerCase();
  $('tag-options').replaceChildren();
  for(const group of groups){
    const key=group.key,state=core.tagState(key,selectedTags,excludedTags,hiddenTags),name=core.tagGroupLabel(group,display.tagLanguage,hiddenTags);
    if(term&&!group.aliases.some(tag=>core.tagSearchText(tag,hiddenTags).toLocaleLowerCase().includes(term))&&state==='none')continue;
    const count=counts.get(key)||0,n=button(name,'chip'+(state==='include'?' selected':state==='exclude'?' tag-excluded':''),()=>{
      cycleTagFilter(key);page=1;renderLibrary();
      $('tag-options').scrollTop=0;[...$('tag-options').querySelectorAll('[data-tag]')].find(b=>b.dataset.tag===key)?.focus();
    });
    n.append(el('span',String(count),'tag-count'));if(state!=='none')n.append(el('span',state==='include'?'포함':'제외','tag-state'));
    n.dataset.tag=key;n.dataset.tagState=state;n.title=`기존 이름: ${group.aliases.join(' · ')}`;n.setAttribute('aria-label',`${name} · ${state==='include'?'포함':state==='exclude'?'제외':'선택 안 함'} · ${count}개 작품`);n.setAttribute('aria-pressed',state==='exclude'?'mixed':String(state==='include'));
    const wrapper=el('div',undefined,'tag-choice');wrapper.append(n,tagLikeButton(group,hiddenTags,false));$('tag-options').append(wrapper);
  }
  const names=keys=>keys.map(key=>core.tagGroupLabel(groups.find(g=>g.key===key)||{key,aliases:[key]},display.tagLanguage,hiddenTags)).join(' · ');
  $('selected-tag-count').textContent=[selectedTags.length?`포함 ${names(selectedTags)}`:'',excludedTags.length?`제외 ${names(excludedTags)}`:''].filter(Boolean).join(' / ')||'전체';
  $('tag-filter-hint').textContent=groups.length?`통합 태그 ${groups.length}개 · 선택한 태그, 좋아요한 태그 순서로 먼저 표시합니다. 누르면 선택 안 함 → 포함 → 제외로 바뀝니다.`:'태그가 없는 작품은 상세에서 내 태그를 추가할 수 있습니다.';
  $('tag-search').hidden=!groups.length;
  $('reshuffle-tags').hidden=display.tagSort!=='random';
  if(focused)[...$('tag-options').querySelectorAll(likedFocus?'[data-favorite-tag]':'[data-tag]')].find(n=>(likedFocus?n.dataset.favoriteTag:n.dataset.tag)===focused)?.focus();
  $('clear-tags').hidden=!selectedTags.length&&!excludedTags.length;
}
function cycleTagFilter(tag){const next=core.cycleTag(tag,selectedTags,excludedTags,hiddenTags);selectedTags=next.include;excludedTags=next.exclude;}
function updateTagRow(row,work,compact=false,members=[work]){
  const groups=core.tagGroups(members.flatMap(w=>core.tags(w,preferences,hiddenTags)),hiddenTags);row.replaceChildren();row.hidden=false;
  if(!groups.length){row.append(el('span','태그 미등록','metadata-note'));return;}
  for(const group of groups.slice(0,compact?3:groups.length)){const state=core.tagState(group.key,selectedTags,excludedTags,hiddenTags),name=core.tagGroupLabel(group,display.tagLanguage,hiddenTags),n=button(name,(compact?'tag-label':'chip')+(state==='include'?' selected':state==='exclude'?' tag-excluded':''),()=>{cycleTagFilter(group.key);page=1;showLibrary();if(compact)$('tag-filter').querySelector('summary').focus();});n.dataset.tag=group.key;n.dataset.tagState=state;n.title=`기존 이름: ${group.aliases.join(' · ')}`;n.setAttribute('aria-label',`${name} · ${state==='include'?'포함':state==='exclude'?'제외':'선택 안 함'}`);n.setAttribute('aria-pressed',state==='exclude'?'mixed':String(state==='include'));if(state!=='none')n.append(el('span',state==='include'?'포함':'제외','tag-state'));row.append(n);}
  if(compact&&groups.length>3)row.append(el('span',`+${groups.length-3}`,'tag-label'));
}
function renderWorkTags(work,draft=null){
  const section=el('section',undefined,'work-tags'),personal=preferences[work.id]?.tags||[],row=el('div',undefined,'work-tag-list');
  row.setAttribute('aria-label','작품 태그');
  updateTagRow(row,work);
  const editor=el('details',undefined,'tag-editor'),form=el('form',undefined,'tag-form'),control=input('tags','예: 수면, 자연음','text',false),hint=el('p','DLsite 원본 분류와 직접 지정한 분류가 표시됩니다. 알플레이 원본은 참고용입니다. 개인 태그는 쉼표로 구분 · 최대 20개, 각 40자이며 이 브라우저에 저장됩니다.','form-hint');
  control.id='work-tags-input';control.maxLength=1000;control.value=draft?draft.value:personal.join(', ');editor.open=draft?.open||false;hint.id='work-tags-hint';control.setAttribute('aria-describedby',hint.id);
  const caption=label('직접 추가할 태그',control);caption.htmlFor=control.id;
  editor.append(el('summary',personal.length?'내 태그 편집':'내 태그 추가'));form.append(caption,hint,el('button','태그 저장','primary'));
  form.addEventListener('submit',event=>{event.preventDefault();safely(()=>{
    const next=core.parseTags(control.value);savePreferences(work.id,{tags:next});control.value=next.join(', ');editor.open=false;renderLibrary();renderWork(work,work.editions.find(e=>e.id===activeEdition));
    $('detail').querySelector('.tag-editor').querySelector('summary').focus();status('태그를 저장했습니다.');
  });});
  editor.append(form);section.append(row,editor,button('태그 관리','filter-reset',()=>safely(openTagManager)));if(window.CatalogControls)section.append(window.CatalogControls.tags(work));return section;
}
function setTagVisibility(value){hiddenTags={schema:1,revision:value.revision,hidden_rplay_tags:value.hidden_rplay_tags||[],hidden_dlsite_tags:value.hidden_dlsite_tags||[],hidden_tags:value.hidden_tags||[],favorite_tags:value.favorite_tags||[],tag_aliases:value.tag_aliases||{},tag_names:value.tag_names||{},work_tags:value.work_tags||{}};tagVisibilityRevision=value.revision;}
// Twitter는 자료 정리 전까지 화면에서 보류한다. 원본 API·DB·개인 설정은 보존한다.
async function load(){const result=await api('/api/works');catalogWorks=result.works;works=catalogWorks.filter(work=>!core.providers(work).includes('twitter'));if(result.tag_visibility)setTagVisibility(result.tag_visibility);preferences=Object.fromEntries(catalogWorks.map(w=>[w.id,readPreferences(w.id)]));window.StudioPlayer.updateTitleMetadata?.(works.flatMap(w=>w.editions.flatMap(e=>e.tracks)));window.CatalogControls?.sync();fillManagerSelects();renderLibrary();if(result.translation_warning||result.tag_visibility_error||result.media_details_error)status(result.translation_warning||result.tag_visibility_error||result.media_details_error,true);void enrichSourceTags(++loadGeneration);}
function tagLikeButton(group,settings,draft){
  const name=core.tagGroupLabel(group,display.tagLanguage,settings),on=core.tagFavorite(group.key,settings),n=button('','tag-like',()=>draft?toggleDraftTagLike(group.key):safely(()=>toggleTagLike(group.key)), 'star');
  n.dataset.favoriteTag=group.key;n.setAttribute('aria-label',`${name} 태그 좋아요 ${on?'해제':'추가'}`);n.setAttribute('aria-pressed',String(on));n.disabled=!draft&&tagLikeSaving;return n;
}
function favoriteList(key,settings,on){const next=(settings.favorite_tags||[]).filter(tag=>core.resolveTagKey(tag,settings)!==key);return on?[...next,key]:next;}
async function toggleTagLike(key){
  if(tagLikeSaving)return;tagLikeSaving=true;const on=!core.tagFavorite(key,hiddenTags);
  try{const result=await api('/api/tag-visibility',{revision:tagVisibilityRevision,favorite_tags:favoriteList(key,hiddenTags,on)});setTagVisibility(result);refreshTagViews();$('tag-options').scrollTop=0;}
  catch(error){if(error.status===409){setTagVisibility(await api('/api/tag-visibility'));refreshTagViews();}throw error;}
  finally{tagLikeSaving=false;renderTagFilters();}
}
function tagRecords(settings){
  const records=new Map();
  function add(tag,p,id){const key=core.resolveTagKey(tag,settings);if(!records.has(key))records.set(key,{key,aliases:[],members:[],works:new Set(),pairs:new Map()});const group=records.get(key);if(!group.aliases.includes(tag))group.aliases.push(tag);if(!group.members.includes(core.tagKey(tag)))group.members.push(core.tagKey(tag));if(id){group.works.add(id);group.pairs.set(p+'\n'+tag,{tag,provider:p});}}
  for(const w of works){const dl=new Set(core.sourceTags(w,{},'dlsite'));for(const tag of core.activeSourceTags(w))add(tag,dl.has(tag)?'dlsite':'',w.id);for(const tag of settings.work_tags?.[w.id]||[])add(tag,'',w.id);for(const tag of preferences[w.id]?.tags||[])add(tag,'',w.id);}
  const extra=[...Object.keys(settings.tag_aliases||{}),...Object.values(settings.tag_aliases||{}),...Object.keys(settings.tag_names||{}),...(settings.hidden_tags||[]),...(settings.favorite_tags||[]),...(settings.hidden_dlsite_tags||[])];for(const tag of extra)if(records.has(core.resolveTagKey(tag,settings)))add(tag,'');
  return [...records.values()];
}
function groupHidden(group,settings){const pairs=[...group.pairs.values()];return pairs.length?pairs.every(p=>core.tagHidden(p.tag,p.provider,settings)):(settings.hidden_tags||[]).includes(group.key);}
function toggleDraftTagLike(key){tagDraft.favorite_tags=favoriteList(key,tagDraft,!core.tagFavorite(key,tagDraft));renderTagManager();}
function toggleDraftTagHidden(group){
  const restore=groupHidden(group,tagDraft);tagDraft.hidden_tags=(tagDraft.hidden_tags||[]).filter(tag=>core.resolveTagKey(tag,tagDraft)!==group.key);
  if(restore){for(const field of ['hidden_rplay_tags','hidden_dlsite_tags'])tagDraft[field]=tagDraft[field].filter(tag=>core.resolveTagKey(tag,tagDraft)!==group.key);}
  else tagDraft.hidden_tags.push(group.key);renderTagManager();
}
function renderMergeControls(){
  const groups=tagRecords(tagDraft).filter(g=>tagMergeSelection.has(g.key)),old=$('tag-merge-target').value;$('tag-merge-target').replaceChildren();
  for(const group of groups){const option=el('option',core.tagGroupLabel(group,display.tagLanguage,tagDraft));option.value=group.key;$('tag-merge-target').append(option);}
  if(groups.some(g=>g.key===old))$('tag-merge-target').value=old;
  $('tag-merge-tools').hidden=groups.length<2;$('tag-merge-count').textContent=`병합 선택 ${groups.length}개`;
}
function mergeSelectedTags(){
  const target=$('tag-merge-target').value,selected=new Set(tagMergeSelection);if(selected.size<2||!selected.has(target))return;
  const groups=tagRecords(tagDraft).filter(g=>selected.has(g.key)),hide=groups.every(g=>groupHidden(g,tagDraft));
  const aliases=new Map(Object.entries(tagDraft.tag_aliases)),keys=new Set([...aliases.keys(),...aliases.values(),...selected]);
  for(const key of keys)if(selected.has(core.resolveTagKey(key,tagDraft))){if(key===target)aliases.delete(key);else aliases.set(key,target);}
  tagDraft.tag_aliases=Object.fromEntries(aliases);tagDraft.hidden_tags=tagDraft.hidden_tags.filter(k=>k!==target);if(hide)tagDraft.hidden_tags.push(target);
  tagMergeSelection=new Set([target]);tagEditKey=target;renderTagManager();
}
function unmergeTag(key){const aliases=Object.fromEntries(Object.entries(tagDraft.tag_aliases).filter(([tag])=>core.resolveTagKey(tag,tagDraft)!==key));tagDraft.tag_aliases=aliases;tagMergeSelection.clear();tagEditKey='';renderTagManager();}
function tagNameEditor(group){
  const section=el('section',undefined,'tag-name-editor'),labels=Object.prototype.hasOwnProperty.call(tagDraft.tag_names,group.key)?tagDraft.tag_names[group.key]:{};
  section.append(el('h3','이름·번역 편집'),el('p',`기존 태그: ${group.aliases.join(' · ')}`,'tag-originals'));
  const pair=el('div',undefined,'pair'),ko=input('tag-name-ko',core.tagGroupLabel(group,'ko'),'text',false),original=input('tag-name-original',core.tagGroupLabel(group,'ja'),'text',false);
  ko.id='tag-name-ko';original.id='tag-name-original';ko.maxLength=original.maxLength=300;ko.value=labels.ko||'';original.value=labels.original||'';pair.append(label('한국어 표시 이름',ko),label('원문 표시 이름',original));section.append(pair,el('p','비우면 기본 이름을 사용합니다. 이름 수정만으로 다른 태그와 병합되지는 않습니다.','form-hint'));
  const update=()=>{tagDraft.tag_names={...tagDraft.tag_names,[group.key]:{ko:ko.value,original:original.value}};const target=[...$('source-tag-options').querySelectorAll('[data-tag-edit]')].find(n=>n.dataset.tagEdit===group.key);if(target)target.querySelector('strong').textContent=core.tagGroupLabel(group,display.tagLanguage,tagDraft);renderMergeControls();};
  for(const control of [ko,original]){control.addEventListener('input',update);control.addEventListener('keydown',e=>{if(e.key==='Enter')e.preventDefault();});}
  section.append(button('이름 원래대로','quiet',()=>{const names={...tagDraft.tag_names};delete names[group.key];tagDraft.tag_names=names;renderTagManager();}));
  if(Object.keys(tagDraft.tag_aliases).some(k=>core.resolveTagKey(k,tagDraft)===group.key))section.append(button('병합 해제','quiet',()=>unmergeTag(group.key)));
  return section;
}
function renderTagManager(){
  const records=tagRecords(tagDraft),counts=new Map(records.map(g=>[g.key,g.works.size]));
  const groups=core.sortTagGroups(records,counts,{include:[...tagMergeSelection],settings:tagDraft,sort:display.tagSort,seed:tagRandomSeed,language:display.tagLanguage}),term=$('source-tag-search').value.trim().normalize('NFC').toLocaleLowerCase();
  $('source-tag-options').replaceChildren();
  for(const group of groups){
    if(term&&!group.aliases.some(tag=>core.tagSearchText(tag,tagDraft).toLocaleLowerCase().includes(term)))continue;
    const name=core.tagGroupLabel(group,display.tagLanguage,tagDraft),row=el('div',undefined,'tag-management-row'),check=el('input'),caption=button('','tag-name-button',()=>{tagEditKey=tagEditKey===group.key?'':group.key;renderTagManager();if(tagEditKey)$('tag-name-ko')?.focus();});
    check.type='checkbox';check.checked=tagMergeSelection.has(group.key);check.dataset.mergeTag=group.key;check.setAttribute('aria-label',`${name} 병합 선택`);check.addEventListener('change',()=>{if(check.checked)tagMergeSelection.add(group.key);else tagMergeSelection.delete(group.key);renderTagManager();[...$('source-tag-options').querySelectorAll('[data-merge-tag]')].find(n=>n.dataset.mergeTag===group.key)?.focus();});
    caption.dataset.tagEdit=group.key;caption.append(el('strong',name),el('small',`${group.works.size}개 보유본 · ${group.aliases.join(' · ')}`));row.append(check,caption,tagLikeButton(group,tagDraft,true),button(groupHidden(group,tagDraft)?'복원':'숨기기','quiet',()=>toggleDraftTagHidden(group)));$('source-tag-options').append(row);if(tagEditKey===group.key)$('source-tag-options').append(tagNameEditor(group));
  }
  if(!$('source-tag-options').children.length)$('source-tag-options').append(el('p',groups.length?'일치하는 태그가 없습니다.':'등록된 태그가 없습니다.','muted'));
  $('source-tag-count').textContent=`통합 태그 ${groups.length}개 · 변경 후 아래에서 저장하세요.`;$('shuffle-managed-tags').hidden=display.tagSort!=='random';renderMergeControls();
}
function refreshTagViews(){
  const available=new Set(works.flatMap(w=>core.tags(w,preferences,hiddenTags)).map(tag=>core.resolveTagKey(tag,hiddenTags)));excludedTags=[...new Set(excludedTags.map(tag=>core.resolveTagKey(tag,hiddenTags)))].filter(key=>available.has(key));selectedTags=[...new Set(selectedTags.map(tag=>core.resolveTagKey(tag,hiddenTags)))].filter(key=>available.has(key)&&!excludedTags.includes(key));page=1;renderLibrary();
  if(activeWork){const row=$('detail').querySelector('.work-tag-list');if(row)updateTagRow(row,works.find(w=>w.id===activeWork));}
}
async function openTagManager(){
  if($('source-tag-manager').open)return;
  const value=await api('/api/tag-visibility');setTagVisibility(value);refreshTagViews();tagDraft=structuredClone(hiddenTags);tagMergeSelection.clear();tagEditKey='';$('source-tag-search').value='';$('tag-manager-sort').value=display.tagSort;$('source-tag-status').hidden=true;renderTagManager();$('source-tag-manager').showModal();$('source-tag-search').focus();
}
async function saveTagVisibility(event){
  event.preventDefault();if(tagSaving)return;tagSaving=true;const controls=[...$('source-tag-form').querySelectorAll('input,select,button')].map(n=>[n,n.disabled]);for(const [n]of controls)n.disabled=true;
  try{
    const value=await api('/api/tag-visibility',{...tagDraft,revision:tagVisibilityRevision});setTagVisibility(value);refreshTagViews();
    $('source-tag-manager').close();status('태그 이름·병합·좋아요·숨김 설정을 저장했습니다. 원본은 유지됩니다.');
  }catch(error){$('source-tag-status').textContent=error.message;$('source-tag-status').hidden=false;}
  finally{tagSaving=false;for(const [n,disabled]of controls)n.disabled=disabled;}
}
function renderMediaDetails(edition){
  const draft=mediaDrafts.get(edition.id),saved=edition.media_details||{},section=el('details',undefined,'media-details'),form=el('form',undefined,'media-details-form');
  section.dataset.mediaEdition=edition.id;section.open=draft?.open||false;section.append(el('summary','자막·대본·더빙 확인 / 수정'));
  const defaults={subtitle_files:core.hasSubtitles(edition)?'present':'unknown',video_subtitles:edition.profile.media_type==='video'?'unknown':'none',script:'unknown',dubbing:'unknown',audio_language:core.audioLanguage(edition),note:''},value=draft?.value||{...defaults,...saved},controls={};
  const fields=[['subtitle_files','별도 자막파일',[['unknown','미확인'],['none','없음 · 직접 확인'],['present','있음 · 직접 확인']]],['video_subtitles','영상 자체 자막',[['unknown','미확인'],['none','없음 · 직접 확인'],['soft','선택형 자막 · 영상 스트림'],['burned','붙박이 자막 · 화면에 합성'],['both','선택형 + 붙박이 모두']]],['script','대본',[['unknown','미확인'],['none','없음 · 직접 확인'],['present','있음 · 직접 확인']]],['dubbing','더빙',[['unknown','미확인'],['none','없음 · 직접 확인'],['present','있음 · 직접 확인']]],['audio_language','실제 음성 언어',[['','미확인'],['ja','일본어'],['ko','한국어'],['en','영어'],['other','기타 언어']]]];
  const grid=el('div',undefined,'media-details-grid');
  for(const [key,name,options]of fields){const control=choice(key,options,value[key]);control.dataset.mediaField=key;controls[key]=control;if(key==='subtitle_files'&&core.hasSubtitles(edition)){control.value='present';control.disabled=true;for(const option of control.children)if(option.value==='present')option.textContent='있음 · 등록된 파일 연결';}if(key==='video_subtitles'&&edition.profile.media_type!=='video'){control.value='none';control.disabled=true;for(const option of control.children)if(option.value==='none')option.textContent='해당 없음 · 음성 버전';}grid.append(label(name,control));}
  const note=el('textarea');note.rows=2;note.maxLength=1000;note.value=value.note;note.dataset.mediaField='note';note.placeholder='예: 확인한 대본 파일명, 재생해 확인한 언어·자막 종류';controls.note=note;
  const message=el('p',undefined,'dialog-status error');message.setAttribute('role','alert');message.hidden=true;
  const remember=()=>mediaDrafts.set(edition.id,{value:Object.fromEntries(Object.entries(controls).map(([key,n])=>[key,n.value])),revision:draft?.revision??edition.media_details_revision,open:section.open});
  for(const control of Object.values(controls))control.addEventListener('input',remember);section.addEventListener('toggle',()=>{if(mediaDrafts.has(edition.id))remember();});
  const count=edition.tracks.reduce((n,t)=>n+t.subtitles.length,0),linked=edition.tracks.filter(t=>t.subtitles.length).length;
  form.append(el('p',count?`등록된 자막파일 ${count}개 · ${linked}/${edition.tracks.length}개 트랙에 연결됨. 언어·싱크가 검증됐다는 뜻은 아닙니다.`:'연결된 자막파일이 없습니다. 파일 미연결과 자막 없음은 다릅니다.','form-hint'),grid,label('확인 근거 / 메모',note),el('p','파일명·한국어 제목만으로 대본이나 더빙을 확정하지 않습니다. 확인한 항목만 바꾸세요. 선택형 영상 자막의 재생 지원은 미디어·브라우저에 따라 다릅니다.','form-hint'),message);
  const actions=el('div',undefined,'media-details-actions'),save=el('button','확인 기록 저장','primary'),discard=button('초안 취소','quiet',()=>{mediaDrafts.delete(edition.id);renderWork(works.find(w=>w.id===activeWork),edition);});save.type='submit';save.disabled=!Number.isInteger(edition.media_details_revision);actions.append(discard,save);form.append(actions);
  form.addEventListener('submit',event=>{event.preventDefault();safely(async()=>{
    remember();const pending=mediaDrafts.get(edition.id),disabled=new Map(Object.values(controls).map(n=>[n,n.disabled]));save.disabled=discard.disabled=true;for(const n of disabled.keys())n.disabled=true;message.hidden=true;
    try{await api(`/api/editions/${edition.id}/media-details`,{revision:pending.revision,details:pending.value});mediaDrafts.delete(edition.id);await load();if(activeWork)renderWork(works.find(w=>w.id===activeWork),works.flatMap(w=>w.editions).find(e=>e.id===activeEdition));status('자막·대본·더빙 확인 기록을 저장했습니다. 원본은 보존됩니다.');}
    catch(error){message.textContent=error.message;message.hidden=false;}
    finally{for(const [n,old]of disabled)n.disabled=old;save.disabled=discard.disabled=false;}
  });});
  section.append(form);return section;
}
function translationBadge(meta){
  const problem=!!meta?.issues?.length,name={official:'공식 한국어',manual:'직접 입력',machine:'자동번역',original:'원문',missing:'번역 미등록'}[meta?.kind]||'번역 미등록';
  const suspected=meta?.issues?.some(issue=>['refused','term_omission','redacted','user_flagged'].includes(issue.code));
  const n=el('span',problem?`${name} · ${suspected?'검열·완화 의심':'검토 필요'}`:`${name}${['machine','manual'].includes(meta?.kind)?meta.reviewed?' · 검수 완료':' · 미검수':''}`,'translation-badge'+(problem?' translation-problem':''));
  if(problem)n.title=meta.issues.map(issue=>issue.message).join(' · ');return n;
}
function translationEditor(kind,id,meta){
  const key=kind+':'+id,draft=translationDrafts.get(key),details=el('details',undefined,'translation-editor'),form=el('form',undefined,'translation-form');
  details.dataset.translationKey=key;details.open=draft?.open??translationOpen.has(key);details.append(el('summary',kind==='work'?'한국어 제목 편집':'한국어 트랙명 편집'));
  const control=el('textarea');control.rows=2;control.required=true;control.maxLength=4096;control.value=draft?.text??meta.text??'';control.placeholder='한국어 번역을 입력하세요.';
  const reviewed=el('input'),flagged=el('input');reviewed.type=flagged.type='checkbox';reviewed.checked=draft?.reviewed??(meta.kind==='manual'&&!!meta.reviewed);flagged.checked=draft?.flagged??!!meta.flagged;
  const remember=()=>translationDrafts.set(key,{text:control.value,reviewed:reviewed.checked,flagged:flagged.checked,revision:draft?.revision??meta.revision??0,original:draft?.original??meta.original,open:details.open});
  for(const n of [control,reviewed,flagged])n.addEventListener(n===control?'input':'change',remember);
  details.addEventListener('toggle',()=>{if(details.open)translationOpen.add(key);else translationOpen.delete(key);remember();});
  const original=el('p',`원문 · ${meta.original}`,'translation-original'),hint=el('p','원문은 유지하고 번역문만 이 서버에 저장합니다. 직접 저장한 번역은 자동번역보다 우선합니다.','form-hint');
  const reviewedLabel=el('label'),flaggedLabel=el('label');reviewedLabel.append(reviewed,el('span','검수 완료'));flaggedLabel.append(flagged,el('span','검열·의미 완화 의심'));
  form.append(original,label('한국어 번역',control),reviewedLabel,flaggedLabel,hint);
  if(meta.issues?.length){const reasons=el('ul',undefined,'translation-reasons');for(const issue of meta.issues)reasons.append(el('li',issue.message));form.append(reasons,el('p','자동 표시는 검열 여부를 확정하지 않습니다. 원문과 대조해 주세요.','form-hint'));}
  if(meta.candidate){const candidate=el('details',undefined,'translation-candidate');candidate.append(el('summary',meta.response_scope==='batch'?'자동번역 묶음 응답 보기':'자동번역 응답 보기'),el('pre',meta.candidate));form.append(candidate);}
  const save=el('button','번역 저장','primary');form.append(save);form.addEventListener('submit',event=>{event.preventDefault();safely(async()=>{
    save.disabled=true;remember();const pending=translationDrafts.get(key);
    try{await api(`/api/${kind==='work'?'works':'tracks'}/${id}/title-translation`,pending);translationDrafts.delete(key);translationOpen.add(key);await load();if(activeWork){const w=works.find(w=>w.id===activeWork);renderWork(w,w.editions.find(e=>e.id===activeEdition));}status('번역을 저장했습니다. 원문은 유지됩니다.');}finally{save.disabled=false;}
  });});details.append(form);return details;
}
async function enrichSourceTags(generation){
  const pending=works.filter(w=>(!w.source_info_titles||!core.sourceTags(w).length)&&core.dlsiteSource(w));
  async function next(){
    while(pending.length&&generation===loadGeneration){
      const work=pending.shift(),source=core.dlsiteSource(work);
      try{
        const info=await api(`/api/editions/${source.editionId}/source-info`);
        if(generation!==loadGeneration)return;
        work.source_info_tags=Array.isArray(info.tags)?info.tags:[];
        if(info.titles&&typeof info.titles==='object')work.source_info_titles=info.titles;
        const oldFamily=core.familyKey(work);if(info.title_sources)work.source_info_title_sources=info.title_sources;
        if(!activeWork){
          if(selectedTags.length||excludedTags.length||$('search').value||oldFamily!==core.familyKey(work)||(display.groupSameWork&&works.some(w=>w.id!==work.id&&core.familyKey(w)===core.familyKey(work)))||['title','title-desc'].includes($('sort').value))renderLibrary();
          else{renderTagFilters();const card=[...document.querySelectorAll('.card')].find(n=>n.dataset.workId===work.id);if(card){updateTagRow(card.querySelector('.card-tags'),work,true);card.querySelector('h3').textContent=displayTitle(work);updateFavoriteButton(card.querySelector('.favorite-button'),work,true);}}
        }else if(activeWork===work.id){const row=$('detail').querySelector('.work-tag-list');if(row)updateTagRow(row,work);$('detail').querySelector('h1').textContent=displayTitle(work);}
      }catch(_){} // Missing/deleted public products retain their stored tags and remain usable.
    }
  }
  await Promise.all([next(),next()]);
}
function fillManagerSelects(){
  const old=$('work-select').value;
  $('work-select').replaceChildren(el('option','작품을 선택하세요'));$('work-select').firstChild.value='';
  $('manage-edition-select').replaceChildren(el('option','버전을 선택하세요'));$('manage-edition-select').firstChild.value='';
  for(const w of works){const name=[core.identity(w),displayTitle(w)].join(' / '),o=el('option',name);o.value=w.id;$('work-select').append(o);for(const e of w.editions){const n=el('option',`${name} / ${e.title}`);n.value=e.id;$('manage-edition-select').append(n);}}
  $('work-select').value=activeWork||old;$('edition-form').querySelector('button').disabled=!works.length;
}
function cover(work,members=[work]){
  const art=el('div',undefined,'cover'),placeholder=el('div',undefined,'placeholder');
  placeholder.append(icon('music'),el('small','표지 없음'));art.append(placeholder,el('span',`${members.reduce((n,w)=>n+w.editions.length,0)} 버전`,'pages'));
  const source=core.coverSource(work);
  if(source){const image=el('img'),caption=placeholder.querySelector('small');caption.textContent='표지 불러오는 중';Object.assign(image,{alt:'',loading:'lazy',decoding:'async',referrerPolicy:'no-referrer',src:`${basePath}/api/editions/${source.editionId}/cover${work.cover_revision?'?v='+work.cover_revision:''}`});image.addEventListener('load',()=>{placeholder.hidden=true;});image.addEventListener('error',()=>{image.hidden=true;placeholder.hidden=false;caption.textContent='표지 없음';});art.prepend(image);}
  const resumed=work.editions.map(core.resumeTrack).find(Boolean);if(resumed?.duration){const b=el('div',undefined,'read-progress');b.style.width=`${Math.min(100,resumed.resume/resumed.duration*100)}%`;art.append(b);}return art;
}
function holdings(members,current=''){
  const details=el('details',undefined,'holdings'),key=core.familyKey(members[0]),favoriteCount=members.filter(w=>preferences[w.id]?.favorite).length;
  details.open=openHoldings.has(key);details.addEventListener('toggle',()=>{if(details.open)openHoldings.add(key);else openHoldings.delete(key);});
  details.append(el('summary',`보유본 ${members.length}개 · ${members.reduce((n,w)=>n+w.editions.length,0)} 버전${favoriteCount?' · 즐겨찾기 '+favoriteCount+'개':''}`));
  members.forEach((work,i)=>{const row=el('div',undefined,'holding-row'),formats=[...new Set(work.editions.map(e=>e.credits?.nas_import?.file_format).filter(Boolean))].join('/'),copy=work.editions.some(e=>e.credits?.nas_import?.separate_physical_copy),name=`${copy?'별도 보유본':'보유본'} ${i+1} · ${core.sourceCodes(work).join('/')||core.identity(work)}${formats?' · '+formats:''}`;
    const open=button(name,'holding-open',()=>showWork(work.id));open.append(el('small',[...new Set(work.editions.flatMap(e=>core.mediaLabels(e)).filter(Boolean))].join(' · ')));if(work.id===current)open.setAttribute('aria-current','true');row.append(open,favoriteButton(work,true));details.append(row);});
  return details;
}
function renderLibrary(){
  const matched=core.filterWorks(works,$('search').value,filter,$('sort').value,{favoritesOnly,tags:selectedTags,excludeTags:excludedTags,preferences,provider,titleLanguage:display.titleLanguage,hiddenTags,randomSeed:workRandomSeed,randomGroup:display.groupSameWork,mediaFilters,voiceActor:window.CatalogControls?.voice()||''}),visible=core.groupWorks(matched,display.groupSameWork),size=display.pageSize==='all'?Math.max(1,visible.length):Number(display.pageSize),pages=Math.max(1,Math.ceil(visible.length/size));page=Math.min(page,pages);$('reshuffle-works').hidden=$('sort').value!=='random';
  $('page-title').textContent=favoritesOnly?(filter==='all'?'즐겨찾기':`즐겨찾기 · ${viewNames[filter]}`):viewNames[filter];$('count').textContent=`${visible.length} 작품${visible.length!==matched.length?' · '+matched.length+' 보유본':''}`;$('page-description').textContent=favoritesOnly?'다시 듣고 싶은 작품을 모았습니다.':filter==='resume'?'멈췄던 트랙부터 이어서 감상하세요.':'같은 출처와 공식 언어판으로 확인된 보유본을 함께 볼 수 있습니다.';
  $('metadata-filter').value=['ko-audio','ja-audio','unknown-audio','untagged','translation-issues'].includes(filter)?filter:'all';
  if(filter==='ko-audio'||filter==='ja-audio')$('page-description').textContent='확인된 음성 언어만 표시합니다. 언어 미확인 버전은 포함하지 않습니다.';
  else if(filter==='unknown-audio')$('page-description').textContent='실제 음성 언어 확인이 필요한 버전입니다. 제목·자막 언어로 더빙을 추정하지 않습니다.';
  else if(filter==='untagged')$('page-description').textContent='태그가 아직 없는 보유본입니다. 상세에서 내 태그를 추가할 수 있습니다.';
  else if(filter==='translation-issues')$('page-description').textContent='번역 거절·누락·의미 완화가 의심되거나 직접 표시한 항목입니다. 자동 판정은 원문 대조가 필요합니다.';
  $('favorites-filter').classList.toggle('selected',favoritesOnly);$('favorites-filter').setAttribute('aria-pressed',String(favoritesOnly));
  $('favorites-nav').classList.toggle('active',favoritesOnly);$('favorites-nav').setAttribute('aria-pressed',String(favoritesOnly));
  $('clear-filters').hidden=filter==='all'&&provider==='all'&&!favoritesOnly&&!selectedTags.length&&!excludedTags.length&&!$('search').value&&Object.values(mediaFilters).every(v=>v==='all')&&!window.CatalogControls?.voice();renderTagFilters();
  for(const n of document.querySelectorAll('[data-provider]')){const on=n.dataset.provider===provider;n.classList.toggle('selected',on);n.setAttribute('aria-pressed',String(on));}
  $('library').className=listLayout?'grid list':'grid';$('library').replaceChildren();
  for(const group of visible.slice((page-1)*size,page*size)){
    const work=group.work;
    const card=el('article',undefined,'card'),open=button('','card-open',()=>showWork(work.id)),info=el('div',undefined,'card-info');card.dataset.workId=work.id;
    info.append(el('p',core.identity(work),'card-code'),el('h3',displayTitle(work),display.titleLanguage==='both'?'title-both':''),el('p',core.creator(work)||`${work.editions.reduce((sum,e)=>sum+e.tracks.length,0)} 트랙`,'card-artist'));open.append(cover(work,group.members),info);card.append(open);if(group.members.length===1)card.append(favoriteButton(work,true));
    const editions=group.members.flatMap(w=>w.editions),pills=el('div',undefined,'card-sources');for(const name of new Set([...editions.map(e=>e.profile.media_type==='video'?'영상':'음성'),...editions.flatMap(core.mediaLabels)].filter(Boolean)))pills.append(el('span',name,'source-pill'));card.append(pills);
    if(work.title_translation)card.append(translationBadge(work.title_translation));
    else if(display.titleLanguage!=='ja'&&core.providers(work).includes('dlsite')&&!work.source_info_titles?.ko)card.append(el('p',work.title_ko_auto?'제목 자동번역 · 원문 보존':'한국어 제목 미확인 · 원문 표시','metadata-note'));
    const problemTracks=editions.flatMap(e=>e.tracks).filter(track=>track.title_translation?.issues?.length).length;if(problemTracks)card.append(el('span',`트랙 번역 검토 ${problemTracks}개`,'translation-badge translation-problem'));
    const row=el('div',undefined,'card-tags');updateTagRow(row,work,true,group.members);card.append(row);
    if(group.members.length>1)card.append(holdings(group.members));
    const edition=group.members.map(w=>core.preferred(w,'resume',savedEdition(w.id),mediaFilters)).find(e=>e&&core.resumeTrack(e)),track=edition&&core.resumeTrack(edition);if(track)card.append(button(`${core.time(track.resume)}부터 이어듣기`,'resume-link',()=>start(edition,track),'play'));
    $('library').append(card);
  }
  if(!visible.length){
    const noFavorites=favoritesOnly&&!works.some(w=>preferences[w.id]?.favorite);
    const empty=el('div',undefined,'empty');empty.append(icon(noFavorites?'star':'library'),el('h2',works.length?(noFavorites?'즐겨찾기한 작품이 없습니다':'조건에 맞는 작품이 없습니다'):'아직 보관함이 비어 있습니다'),el('p',works.length?(noFavorites?'작품 카드의 별 버튼으로 다시 듣고 싶은 작품을 담으세요.':'검색어, 감상 버전, 즐겨찾기 또는 태그 조건을 바꿔 보세요.'):'작품을 추가하고 보유한 음성·영상 파일을 연결해 주세요.'));
    if(works.length)empty.append(button('전체 보관함 보기','quiet',resetFilters));
    else{if(location.hostname==='127.0.0.1'&&location.port==='43130'){const sample=el('a','샘플 서재 둘러보기','primary');sample.href='http://127.0.0.1:43132/';empty.append(sample,el('p','샘플은 별도 테스트 서재에 준비되어 있습니다.','form-hint'));}empty.append(button('＋ 작품 추가','primary',()=>safely(()=>openManager('new-work'))));}
    $('library').append(empty);
  }
  $('pagination').hidden=pages<=1;$('page-number').textContent=`${page} / ${pages} · ${visible.length}개`;$('previous-page').disabled=page<=1;$('next-page').disabled=page>=pages;
  $('layout').replaceChildren(icon(listLayout?'grid':'list'));$('layout').setAttribute('aria-label',listLayout?'카드 보기로 전환':'목록 보기로 전환');
  for(const n of document.querySelectorAll('[data-filter]')){const on=n.dataset.filter===filter&&!(favoritesOnly&&n.className.includes('nav-item'));n.classList.toggle('selected',on);n.classList.toggle('active',on);n.setAttribute('aria-pressed',String(on));}
}
function selectFilter(value){filter=value;page=1;showLibrary();}
function resetFilters(){window.CatalogControls?.reset();for(const key of Object.keys(mediaFilters)){mediaFilters[key]='all';$(key+'-filter').value='all';}filter='all';provider='all';favoritesOnly=false;selectedTags=[];excludedTags=[];$('search').value='';$('tag-search').value='';page=1;showLibrary();}
async function refreshMissingCovers(){
  const control=$('refresh-covers'),pending=works.filter(w=>core.coverSource(w));let completed=0,available=0,missing=0,errors=0;control.disabled=true;
  async function next(){while(pending.length){const work=pending.shift();try{const result=await api(`/api/editions/${core.coverSource(work).editionId}/cover/refresh`,{});if(result.available){available++;work.cover_revision=Date.now();}else missing++;}catch(_){errors++;}completed++;$('cover-refresh-status').textContent=`표지 ${completed} / ${works.filter(w=>core.coverSource(w)).length} · 확인 ${available} · 없음 ${missing} · 오류 ${errors}`;}}
  try{await Promise.all([next(),next()]);await load();if(activeWork){const w=works.find(w=>w.id===activeWork);renderWork(w,w.editions.find(e=>e.id===activeEdition));}}finally{control.disabled=false;}
}
function showLibrary(push=true){window.AudioFiles?.hide();activeWork=null;activeEdition=null;editingOrder=false;$('library-view').hidden=false;$('work-view').hidden=true;renderLibrary();if(push){history.pushState(null,'',location.pathname+location.search);window.scrollTo({top:0});}}
function showWork(id,editionId='',push=true){
  window.AudioFiles?.hide();
  const w=works.find(w=>w.id===id);if(!w){showLibrary(false);return;}const e=core.preferred(w,editionId?'all':filter,editionId||savedEdition(id),editionId?{}:mediaFilters);activeWork=id;activeEdition=e?.id||null;if(e)rememberEdition(id,e.id);
  $('library-view').hidden=true;$('work-view').hidden=false;renderWork(w,e);if(push){history.pushState(null,'',`#work/${id}${e?'/'+e.id:''}`);window.scrollTo({top:0});}
}
function start(edition,track,options={}){if(!track)return;if($('manager').open)$('manager').close();activeWork=edition.work_id;activeEdition=edition.id;rememberEdition(edition.work_id,edition.id);$('player-bar').hidden=false;const p=window.StudioPlayer.open(edition.tracks,track,options);safely(()=>p);}
function renderWork(work,edition){
  const root=$('detail'),editor=root.dataset.workId===work.id?root.querySelector('.tag-editor'):null,draft=editor?{value:editor.querySelector('input').value,open:editor.open}:null;root.dataset.workId=work.id;root.replaceChildren();const hero=el('div',undefined,'work-hero'),info=el('div',undefined,'work-info');
  info.append(el('p',core.identity(work),'work-code'),el('h1',displayTitle(work)));if(core.creator(work))info.append(el('p',core.creator(work),'work-creator'));const source=core.coverSource(work);if(source){const link=el('a',`${source.provider==='dlsite'?'DLsite':'RPLAY'} 원본 보기`,'original-source');Object.assign(link,{href:source.url,target:'_blank',rel:'noopener noreferrer'});info.append(link);}info.append(el('p',`${work.editions.length}개 감상 버전`,'muted'),favoriteButton(work));hero.append(cover(work),info);root.append(hero);
  const related=works.filter(w=>core.familyKey(w)===core.familyKey(work));if(related.length>1)root.append(holdings(related,work.id));
  const titleMeta=work.title_translation||{original:work.source_info_titles?.ja||work.title,text:work.title_ko_manual||work.source_info_titles?.ko||work.title_ko_auto||'',kind:'missing',revision:0};
  info.append(translationBadge(titleMeta));root.append(translationEditor('work',work.id,titleMeta),renderWorkTags(work,draft));
  const versions=el('div',undefined,'version-tabs');versions.setAttribute('role','group');versions.setAttribute('aria-label','감상 버전 선택');
  for(const e of work.editions){const tab=button('',e.id===edition?.id?'version-tab selected':'version-tab',()=>{editingOrder=false;showWork(work.id,e.id);});tab.setAttribute('aria-pressed',String(e.id===edition?.id));tab.append(el('strong',e.title),el('small',`${core.editionLabel(e)} · ${e.tracks.length} 트랙`));versions.append(tab);}root.append(versions);
  if(!edition){const empty=el('div',undefined,'empty');empty.append(el('h2','감상 버전을 추가해 주세요'),el('p','같은 작품의 원본·번역 자막·영상은 각각 별도 버전으로 연결합니다.'),button('＋ 버전 추가','primary',()=>safely(()=>openManager('new-edition'))));root.append(empty);return;}
  const panel=el('section',undefined,'listening-panel'),heading=el('div',undefined,'listening-heading'),description=el('div'),known=edition.tracks.length&&edition.tracks.every(t=>t.duration>0);
  panel.append(el('p',core.mediaLabels(edition).join(' · '),'listening-note'));
  description.append(el('h2',edition.title),el('p',`${edition.tracks.length} 트랙${known?' · '+core.time(edition.tracks.reduce((s,t)=>s+t.duration,0)):''}${core.hasSubtitles(edition)?' · 자막 선택 가능':''}`,'muted'));heading.append(description);
  const actions=el('div',undefined,'listening-actions'),resume=core.resumeTrack(edition),play=button(resume?'처음부터 전체 재생':'전체 재생','primary',()=>{if(edition.tracks.length)start(edition,edition.tracks[0],{mode:'all',fromStart:true});},'play');play.disabled=!core.playable(edition);actions.append(play);
  if(resume)actions.prepend(button(`${core.time(resume.resume)}부터 이어듣기`,'quiet',()=>start(edition,resume),'clock'));
  if(edition.tracks.length>1)actions.append(button(editingOrder?'순서 편집 완료':'순서 편집','quiet',()=>{editingOrder=!editingOrder;if(editingOrder)folderView=false;renderWork(work,edition);},'list'));heading.append(actions);panel.append(heading);
  if(edition.profile.translation!=='none'&&core.mediaFacts(edition).subtitles==='unknown')panel.append(el('p','기존 자막판 표기는 있지만 실제 연결·영상 자막 확인 기록이 없습니다. 자막 있음으로 확정하지 않습니다.','listening-note'));
  if(core.hasSubtitles(edition))panel.append(el('p','연결된 자막파일이 있습니다. 파일 연결·파싱과 별개로 음성 싱크·번역 품질은 직접 확인해야 합니다.','listening-note'));
  panel.append(renderMediaDetails(edition));if(window.CatalogControls)panel.append(window.CatalogControls.facts(edition));
  const fileActions=el('div',undefined,'work-file-actions');fileActions.append(button('설명·번역 파일 보기','quiet',()=>safely(()=>window.AudioFiles.open('files',edition)),'folder'),button('이 버전을 재생목록에 복사','quiet',()=>safely(()=>window.AudioFiles.addTracks(edition.tracks.map(t=>t.id),displayTitle(work))),'list'));panel.append(fileActions);
  const views=el('div',undefined,'track-views');views.setAttribute('role','group');views.setAttribute('aria-label','트랙 보기 방식');
  for(const [folders,text,name]of[[false,'재생목록','list'],[true,'폴더 보기','folder']]){const n=button(text,folderView===folders?'view-tab selected':'view-tab',()=>{folderView=folders;editingOrder=false;renderWork(work,edition);$('detail').querySelector('.view-tab.selected').focus();},name);n.setAttribute('aria-pressed',String(folderView===folders));views.append(n);}panel.append(views);
  if(folderView&&!editingOrder){panel.append(renderFolders(core.folderTree(edition.tracks),edition),el('p','현재 버전에 등록된 트랙의 경로입니다. 전체 재생은 저장된 재생 순서를 따릅니다.','folder-note'));}
  else{const list=el('ol',undefined,'track-list');edition.tracks.forEach((track,index)=>list.append(renderTrack(edition,track,index)));panel.append(list);}
  if(!edition.tracks.length)panel.append(el('p','아직 재생할 파일이 연결되지 않았습니다.','muted'),button('파일 연결하기','quiet',()=>safely(()=>openManager('edition-settings'))));root.append(panel);
}
function renderTrack(edition,track,index){
    const row=el('li',undefined,'track-row'),playTrack=button('','track-play',()=>start(edition,track)),info=el('div',undefined,'track-info'),format=(track.relative_path.split('.').pop()||'').toUpperCase();info.append(el('strong',window.AudioTrackTitle(track)),el('small',[format,track.title_translation_kind==='machine'?'제목 자동번역':'',track.subtitles.length?track.subtitles.map(s=>s.label).join(' · '):core.mediaFacts(edition).video_subtitles==='burned'?'붙박이 자막영상':'이 트랙에 연결된 자막파일 없음'].filter(Boolean).join(' · ')));playTrack.append(el('span',String(index+1),'track-index'),info,el('span',track.duration?core.time(track.duration):'—','track-time'),icon('play'));row.append(playTrack);
    if(editingOrder){const order=el('div',undefined,'order-buttons');for(const[delta,mark,name]of[[-1,'↑','위로'],[1,'↓','아래로']]){const move=button(mark,'icon-button',()=>safely(async()=>{if(orderPending)return;orderPending=true;const ids=window.StudioPlayer.move(edition.tracks,track.id,delta).map(t=>t.id);try{await api(`/api/editions/${edition.id}/order`,{track_ids:ids});await load();showWork(edition.work_id,edition.id,false);status('재생 순서를 저장했습니다.');}finally{orderPending=false;}}));move.disabled=orderPending||(delta<0?index===0:index===edition.tracks.length-1);move.setAttribute('aria-label',`${track.title} ${name}`);order.append(move);}row.append(order);}
    const main=el('div',undefined,'track-main');main.append(...row.children);row.replaceChildren(main);
    const meta=track.title_translation||{original:track.title,text:track.title_ko||'',kind:track.title_translation_kind||'missing',revision:0};
    info.append(translationBadge(meta));main.append(button('목록에 추가','quiet track-save-list',()=>safely(()=>window.AudioFiles.addTracks([track.id]))));row.append(translationEditor('track',track.id,meta));return row;
}
function renderFolders(node,edition,depth=0){
  const list=el('ul',undefined,'folder-tree');
  for(const folder of node.folders){const item=el('li'),details=el('details',undefined,'folder-group'),summary=el('summary');details.open=depth<2;summary.append(icon('folder'),el('strong',folder.name),el('span',`${folder.count} 트랙`,'folder-count'));details.append(summary,renderFolders(folder,edition,depth+1));item.append(details);list.append(item);}
  for(const track of node.tracks){const row=renderTrack(edition,track,edition.tracks.findIndex(t=>t.id===track.id));row.querySelector('.track-info').append(el('small',track.relative_path.split('/').pop(),'file-name'));list.append(row);}return list;
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
function route(){if(window.AudioFiles?.route())return;const m=/^#work\/([0-9a-f]{32})(?:\/([0-9a-f]{32}))?$/.exec(location.hash);if(m)showWork(m[1],m[2]||'',false);else showLibrary(false);}
document.addEventListener('player-closed',()=>safely(async()=>{await load();if(activeWork)showWork(activeWork,activeEdition,false);}));
for(const n of document.querySelectorAll('[data-filter]'))n.addEventListener('click',()=>{if(n.className.includes('nav-item')&&n.dataset.filter==='all')resetFilters();else selectFilter(n.dataset.filter);});
for(const n of document.querySelectorAll('[data-provider]'))n.addEventListener('click',()=>{provider=n.dataset.provider;page=1;showLibrary();});
for(const n of document.querySelectorAll('[data-panel]'))n.addEventListener('click',()=>{setManagerPanel(n.dataset.panel);if(n.dataset.panel==='edition-settings'&&activeEdition){$('manage-edition-select').value=activeEdition;safely(()=>renderManagement(activeEdition));}});
$('search').addEventListener('input',()=>{page=1;showLibrary();});$('sort').value=display.sort;$('sort').addEventListener('change',()=>{display.sort=$('sort').value;saveDisplay();page=1;renderLibrary();});
for(const [id,key] of [['tag-language','tagLanguage'],['title-language','titleLanguage'],['track-language','trackLanguage'],['page-size','pageSize']]){$(id).value=display[key];$(id).addEventListener('change',()=>{display[key]=$(id).value;saveDisplay();page=1;renderLibrary();if(activeWork){const w=works.find(w=>w.id===activeWork);renderWork(w,w.editions.find(e=>e.id===activeEdition));}fillManagerSelects();});}
$('group-same-work').checked=display.groupSameWork;$('group-same-work').addEventListener('change',()=>{display.groupSameWork=$('group-same-work').checked;saveDisplay();page=1;renderLibrary();});
$('metadata-filter').addEventListener('change',()=>selectFilter($('metadata-filter').value));
for(const key of Object.keys(mediaFilters))$(key+'-filter').addEventListener('change',()=>{mediaFilters[key]=$(key+'-filter').value;page=1;showLibrary();});
$('refresh-covers').addEventListener('click',()=>safely(refreshMissingCovers));
$('preferences-export').addEventListener('click',()=>safely(exportPreferences));
$('preferences-import').addEventListener('click',()=>$('preferences-file').click());
$('preferences-file').addEventListener('change',()=>safely(async()=>{try{await importPreferences($('preferences-file').files[0]);}finally{$('preferences-file').value='';}}));
$('favorites-filter').addEventListener('click',()=>{favoritesOnly=!favoritesOnly;page=1;renderLibrary();});
$('favorites-nav').addEventListener('click',()=>{favoritesOnly=true;filter='all';provider='all';selectedTags=[];excludedTags=[];$('search').value='';page=1;showLibrary();});
$('clear-filters').addEventListener('click',()=>{resetFilters();$('favorites-filter').focus();});
$('clear-tags').addEventListener('click',()=>{selectedTags=[];excludedTags=[];page=1;renderLibrary();$('tag-filter').querySelector('summary').focus();});
$('tag-search').addEventListener('input',renderTagFilters);
$('manage-source-tags').addEventListener('click',()=>safely(openTagManager));
$('source-tag-search').addEventListener('input',renderTagManager);
for(const id of ['tag-sort','tag-manager-sort']){$(id).value=display.tagSort;$(id).addEventListener('change',()=>{display.tagSort=$(id).value;saveDisplay();$('tag-sort').value=$('tag-manager-sort').value=display.tagSort;renderTagFilters();if($('source-tag-manager').open)renderTagManager();});}
$('reshuffle-tags').addEventListener('click',()=>{tagRandomSeed++;renderTagFilters();});
$('shuffle-managed-tags').addEventListener('click',()=>{tagRandomSeed++;renderTagManager();});
$('tag-merge').addEventListener('click',mergeSelectedTags);
$('reshuffle-works').addEventListener('click',()=>{workRandomSeed++;page=1;renderLibrary();});
$('source-tag-search').addEventListener('keydown',event=>{if(event.key==='Enter')event.preventDefault();});
$('source-tag-form').addEventListener('submit',saveTagVisibility);
$('source-tag-cancel').addEventListener('click',()=>$('source-tag-manager').close());
$('source-tag-manager').addEventListener('cancel',event=>{if(tagSaving)event.preventDefault();});
$('layout').addEventListener('click',()=>{listLayout=!listLayout;try{localStorage.setItem('audio-library-layout',listLayout?'list':'grid');}catch(_){}renderLibrary();});
$('previous-page').addEventListener('click',()=>{page--;renderLibrary();});$('next-page').addEventListener('click',()=>{page++;renderLibrary();});$('back-library').addEventListener('click',()=>showLibrary());
$('manage-work').addEventListener('click',()=>safely(()=>openManager(activeEdition?'edition-settings':'new-edition')));$('add-work').addEventListener('click',()=>safely(()=>openManager('new-work')));$('close-manager').addEventListener('click',()=>$('manager').close());$('manage-edition-select').addEventListener('change',()=>safely(()=>renderManagement($('manage-edition-select').value)));
$('work-form').addEventListener('submit',event=>{event.preventDefault();safely(async()=>{const f=event.target,w=await api('/api/works',{title:field(f,'title'),rj_code:field(f,'rj_code')});f.reset();await load();activeWork=w.id;activeEdition=null;$('work-select').value=w.id;setManagerPanel('new-edition');status('작품을 등록했습니다. 감상 버전을 추가해 주세요.');});});
$('edition-form').addEventListener('submit',event=>{event.preventDefault();safely(async()=>{const f=event.target,media=field(f,'media_type'),translation=field(f,'translation');if(translation==='embedded'&&media!=='video')throw new Error('자막이 합성된 버전은 미디어를 영상으로 선택하세요.');const e=await api('/api/editions',{work_id:field(f,'work_id'),title:field(f,'title'),kind:'audio',language:field(f,'language'),credits:field(f,'circle')?{circle:field(f,'circle')}:{} });await api(`/api/editions/${e.id}/profile`,{media_type:media,translation});f.reset();activeWork=e.work_id;activeEdition=e.id;await load();showWork(activeWork,activeEdition);setManagerPanel('edition-settings');$('manage-edition-select').value=e.id;await renderManagement(e.id);status('이 버전에 연결할 파일을 선택해 주세요.');});});
window.addEventListener('popstate',route);window.addEventListener('hashchange',route);
document.addEventListener('keydown',event=>{if(event.key==='/'&&!$('manager').open&&$('cinema').hidden&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName)){event.preventDefault();$('search').focus();}});
for(const n of document.querySelectorAll('[data-icon]'))n.append(icon(n.dataset.icon));
safely(async()=>{await load();route();const h=await api('/api/health');$('connection-dot').classList.add(h.status==='ok'?'online':'offline');$('connection-text').replaceChildren(el('span','서버 연결됨'),el('small','개인 음성 라이브러리'));});
