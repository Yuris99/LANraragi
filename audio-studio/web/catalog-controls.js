'use strict';
(() => {
  let vocabulary=null,voiceActor='';const drafts=new Map();
  const voiceLabel=el('label','성우'),voiceSelect=el('select');voiceSelect.id='voice-filter';voiceSelect.setAttribute('aria-label','성우 필터');voiceLabel.append(voiceSelect);document.querySelector('.media-filters').append(voiceLabel);
  function sync(){const actors=new Map();for(const w of works)for(const e of w.editions)for(const a of e.voice_actors||[])if(!actors.has(a.id))actors.set(a.id,a.name);voiceSelect.replaceChildren(new Option('전체 성우',''),...[...actors].sort((a,b)=>a[1].localeCompare(b[1],'ja')).map(([id,name])=>new Option(name,id)));if(!actors.has(voiceActor))voiceActor='';voiceSelect.value=voiceActor;}
  voiceSelect.onchange=()=>{voiceActor=voiceSelect.value;page=1;showLibrary(false);};
  function tags(work){
    const details=el('details',undefined,'classification-editor'),summary=el('summary','DLsite 기준 분류 태그 지정');details.append(summary,el('p','분류 태그는 DLsite 기준으로 통합합니다. 알플레이 원본 태그는 참고용으로만 보관하며, 추천은 선택 후 저장해야 적용됩니다.','form-hint'));
    const raw=core.sourceTags(work,{},'rplay');
    if(raw.length){const reference=el('details',undefined,'rplay-tag-reference');reference.append(el('summary',`알플레이 원본 태그 참고 · ${raw.length}개`),el('p',raw.join(' · '),'tag-originals'));details.append(reference);}
    const body=el('div');details.append(body);let initialized=false;
    details.addEventListener('toggle',()=>{if(!details.open||initialized)return;initialized=true;void setup().catch(error=>{body.replaceChildren(el('p',error.message,'error'));initialized=false;});});
    async function setup(){
      body.textContent='DLsite 분류 목록을 불러오는 중…';vocabulary=vocabulary||(await api('/api/tag-vocabulary')).tags;
      let draft=drafts.get(work.id);if(!draft){const stored=hiddenTags.work_tags?.[work.id],source=stored===undefined?core.sourceTags(work,{},'dlsite'):stored;draft={selected:new Set(source),revision:tagVisibilityRevision};drafts.set(work.id,draft);}
      const selected=draft.selected,search=input('classification-search','DLsite 태그 찾기','search',false),choices=el('div',undefined,'classification-options'),suggestions=el('div',undefined,'classification-suggestions'),message=el('p',undefined,'classification-status'),form=el('form'),save=el('button','선택한 분류 태그 저장','primary');search.setAttribute('aria-label','DLsite 분류 태그 검색');message.setAttribute('role','status');
      const canonical=new Map();for(const row of vocabulary)for(const alias of[row.tag,...row.aliases||[]])canonical.set(core.tagKey(alias),row.tag);
      // Normalize only this explicit editing draft; originals and stored selections are untouched until save.
      const normalized=new Set([...selected].map(tag=>canonical.get(core.tagKey(tag))||tag));draft.selected=normalized;
      const draw=()=>{choices.replaceChildren();const term=search.value.normalize('NFC').toLocaleLowerCase();for(const row of vocabulary){if(term&&![row.tag,row.ko,...row.aliases||[]].join(' ').toLocaleLowerCase().includes(term))continue;const labelNode=el('label',undefined,'classification-choice'),check=el('input');check.type='checkbox';check.value=row.tag;check.checked=normalized.has(row.tag);check.onchange=()=>{check.checked?normalized.add(row.tag):normalized.delete(row.tag);message.textContent=`${normalized.size}개 선택 · 저장 전`;};labelNode.append(check,el('span',row.ko?`${row.ko} (${row.tag})`:row.tag));choices.append(labelNode);}if(!choices.children.length)choices.append(el('p','일치하는 DLsite 태그가 없습니다.','muted'));};
      for(const row of core.suggestTags(work,vocabulary)){const candidate=button(`${row.ko||row.tag} · ${row.reason}`,'quiet',()=>{normalized.add(row.tag);draw();message.textContent='추천 후보를 선택했습니다. 저장 전에는 적용되지 않습니다.';});candidate.dataset.recommendedTag=row.tag;suggestions.append(candidate);}
      if(!suggestions.children.length)suggestions.append(el('p','이름이 명확히 대응하는 추천 후보가 없습니다. 아래 목록에서 직접 선택하세요.','muted'));
      form.append(el('h3','추천 후보 · 자동 적용 안 함'),suggestions,label('분류 태그 찾기',search),choices,message,save);search.oninput=draw;
      const clear=button('선택 비우기','quiet',()=>{normalized.clear();draw();message.textContent='선택을 비웠습니다. 저장하면 분류 태그만 비워집니다. 원본은 남습니다.';});form.append(clear);
      form.onsubmit=event=>{event.preventDefault();void safely(async()=>{save.disabled=true;try{const result=await api(`/api/works/${work.id}/classification-tags`,{revision:draft.revision,tags:[...normalized]});setTagVisibility(result);drafts.delete(work.id);refreshTagViews();status('DLsite 기준 분류 태그를 저장했습니다. 원본 태그는 보존했습니다.');renderWork(work,work.editions.find(e=>e.id===activeEdition));}catch(error){message.textContent=error.message;if(error.status===409)message.textContent+=' 초안은 보존했습니다. 서버본을 새로 연 뒤 다시 선택해 주세요.';}finally{save.disabled=false;}});};
      form.append(button('초안 취소 · 서버본 다시 열기','quiet',()=>{void safely(async()=>{setTagVisibility(await api('/api/tag-visibility'));drafts.delete(work.id);initialized=false;body.replaceChildren();await setup();initialized=true;});}));body.replaceChildren(form);draw();
    }
    return details;
  }
  function facts(edition){
    const section=el('section',undefined,'catalog-facts');section.append(el('h3','성우 · 실제 언어 확인'));
    const actors=edition.voice_actors||[],cast=el('p');cast.append(el('strong',edition.voice_actors_checked?'공식 상품 성우: ':'성우: '),el('span',actors.length?actors.map(a=>a.name).join(' · '):edition.voice_actors_checked?'공식 상품에 성우 정보 없음':'미확인'));
    const source=edition.voice_actors_source;if(/^https:\/\/www\.dlsite\.com\/maniax\/work\/=\/product_id\/RJ[0-9]{6,12}\.html$/.test(source)){const link=el('a','공식 근거 확인');Object.assign(link,{href:source,target:'_blank',rel:'noopener noreferrer'});cast.append(' ',link);}section.append(cast);
    if(edition.voice_actors_checked)section.append(el('p','상품에 기재된 성우 크레딧입니다. 실제 파일의 화자나 더빙 성우를 음성으로 식별한 결과는 아닙니다.','form-hint'));
    const observation=edition.audio_language_observation;
    if(observation?.method){const label=observation.language?core.language(observation.language):'판단 보류';section.append(el('p',`음성 샘플: ${label} · 자동 감지, 직접 확인 아님`));const details=el('details');details.append(el('summary','음성 검사 범위·근거'),el('p',`전체 ${observation.total_tracks}트랙 중 대표 ${observation.sampled_tracks}트랙의 두 구간을 확인했습니다. 전체 트랙·구간이나 더빙 여부를 검증한 결과가 아닙니다.`, 'form-hint'));for(const sample of observation.samples||[])details.append(el('p',`${Number(sample.at_seconds||0).toFixed(1)}초부터 ${Number(sample.sample_seconds||0).toFixed(1)}초 · ${sample.language||'미확인'} · 모델점수 ${Number(sample.score||0).toFixed(3)}`));section.append(details);}else section.append(el('p','음성 내용 언어: 아직 미확인','muted'));
    const subtitles=edition.tracks.flatMap(t=>t.subtitles||[]),observed=subtitles.filter(s=>s.language_observation),counts=new Map();for(const s of observed){const language=s.language_observation.language||'unknown';counts.set(language,(counts.get(language)||0)+1);}if(subtitles.length)section.append(el('p',`자막 내용 검사: ${observed.length}/${subtitles.length}파일 · ${[...counts].map(([k,n])=>`${k==='mixed'?'혼합 가능':k==='unknown'?'판단 보류':core.language(k)} ${n}개`).join(' · ')}. 문자 기반 자동 감지이며 번역 품질·싱크 검사가 아닙니다.`));
    return section;
  }
  window.CatalogControls={tags,facts,sync,voice:()=>voiceActor,reset:()=>{voiceActor='';voiceSelect.value='';}};sync();
})();
