(function(root) {
  'use strict';
  const tagLabels=typeof module!=='undefined'&&module.exports?require('./tag-labels.js'):(root.AudioTagLabels||{});
  const koreanTag=tag=>Object.prototype.hasOwnProperty.call(tagLabels,tag)&&typeof tagLabels[tag]==='string'?tagLabels[tag]:'';
  const tagLabel=(tag,language='ko')=>language==='ja'?tag:koreanTag(tag)||tag;
  const tagKey=tag=>(koreanTag(tag)||tag).trim().normalize('NFC').toLocaleLowerCase();
  const own=(object,key)=>Object.prototype.hasOwnProperty.call(object||{},key);
  const resolveTagKey=(tag,settings={})=>{const base=tagKey(tag),aliases=settings.tag_aliases||{},seen=new Set();let key=base;while(own(aliases,key)){if(seen.has(key)||typeof aliases[key]!=='string')return base;seen.add(key);key=tagKey(aliases[key]);}return key;};
  const tagAliases=new Map();for(const [original,korean] of Object.entries(tagLabels)){const key=tagKey(original);tagAliases.set(key,[...(tagAliases.get(key)||[]),original,korean]);}
  const tagSearchText=(tag,settings={})=>{const key=resolveTagKey(tag,settings),members=[key,tagKey(tag),...Object.keys(settings.tag_aliases||{}).filter(k=>resolveTagKey(k,settings)===key)],names=settings.tag_names||{};return[tag,koreanTag(tag),...members.flatMap(k=>[k,...(tagAliases.get(k)||[]),...(own(names,k)?Object.values(names[k]):[])])].join(' ');};
  const tagGroups=(tags,settings={})=>{const groups=new Map();for(const tag of tags){if(typeof tag!=='string'||!tag.trim())continue;const value=tag.trim().normalize('NFC'),key=resolveTagKey(value,settings);if(!groups.has(key))groups.set(key,{key,aliases:[],members:[]});const group=groups.get(key);if(!group.aliases.includes(value))group.aliases.push(value);if(!group.members.includes(tagKey(value)))group.members.push(tagKey(value));}return [...groups.values()];};
  const tagGroupLabel=(group,language='ko',settings={})=>{const labels=own(settings.tag_names,group.key)?settings.tag_names[group.key]:{},custom=labels[language==='ja'?'original':'ko'],preferred=group.aliases.filter(tag=>tagKey(tag)===group.key),aliases=preferred.length?preferred:[...(tagAliases.get(group.key)||[]),group.key];return custom||(language==='ja'?(aliases.find(tag=>koreanTag(tag)&&tag!==koreanTag(tag))||aliases[0]):aliases.map(koreanTag).find(Boolean)||aliases[0]);};
  const tagState=(tag,include=[],exclude=[],settings={})=>exclude.some(t=>resolveTagKey(t,settings)===resolveTagKey(tag,settings))?'exclude':include.some(t=>resolveTagKey(t,settings)===resolveTagKey(tag,settings))?'include':'none';
  const cycleTag=(tag,include=[],exclude=[],settings={})=>{const key=resolveTagKey(tag,settings),state=tagState(key,include,exclude,settings),without=list=>list.filter(t=>resolveTagKey(t,settings)!==key);return{include:state==='none'?[...without(include),key]:without(include),exclude:state==='include'?[...without(exclude),key]:without(exclude)};};
  const tagFavorite=(tag,settings={})=>(settings.favorite_tags||[]).some(t=>resolveTagKey(t,settings)===resolveTagKey(tag,settings));
  const tagHidden=(tag,provider,settings={})=>{const hidden=Array.isArray(settings)?{rplay:settings}:settings;return(hidden.hidden_tags||[]).includes(resolveTagKey(tag,hidden))||(hidden[provider]||hidden['hidden_'+provider+'_tags']||[]).includes(tag);};
  const randomRank=(value,seed=0)=>{let h=(2166136261^Number(seed))>>>0;for(const c of String(value)){h=Math.imul(h^c.charCodeAt(0),16777619)>>>0;}h=Math.imul(h^(h>>>16),2246822507);h=Math.imul(h^(h>>>13),3266489909);return(h^(h>>>16))>>>0;};
  const sortTagGroups=(groups,counts,{include=[],exclude=[],settings={},sort='count-desc',seed=0,language='ko'}={})=>[...groups].sort((a,b)=>{const priority=g=>tagState(g.key,include,exclude,settings)!=='none'?0:tagFavorite(g.key,settings)?1:2;const pinned=priority(a)-priority(b);if(pinned)return pinned;const name=()=>tagGroupLabel(a,language,settings).localeCompare(tagGroupLabel(b,language,settings),'ko',{numeric:true});let n=sort==='count-desc'?(counts.get(b.key)||0)-(counts.get(a.key)||0):sort==='count-asc'?(counts.get(a.key)||0)-(counts.get(b.key)||0):sort==='random'?randomRank(a.key,seed)-randomRank(b.key,seed):name();return n||name()||a.key.localeCompare(b.key);});
  const playable=e=>['audio','voice_comic'].includes(e.kind)&&e.tracks.length>0;
  const resumeTrack=e=>e.tracks.find(t=>t.resume>0&&(!t.duration||t.resume<t.duration-0.5))||null;
  const hasSubtitles=e=>e.tracks.some(t=>(t.subtitles||[]).length);
  const manualAudioLanguage=e=>own(e.media_details,'audio_language')?e.media_details.audio_language:e.credits?.nas_import?.audio_language_unverified?'':e.language||'';
  const audioLanguage=e=>manualAudioLanguage(e)||e.audio_language_observation?.language||'';
  const mediaFacts=e=>{const d=e.media_details||{},files=hasSubtitles(e)?'present':d.subtitle_files||'unknown',video=e.profile.media_type==='video'?d.video_subtitles||'unknown':'none';return{subtitle_files:files,video_subtitles:video,subtitles:files==='present'||['soft','burned','both'].includes(video)?'present':files==='none'&&video==='none'?'none':'unknown',script:d.script||'unknown',dubbing:d.dubbing||'unknown'};};
  const mediaMatches=(e,filters={})=>{const f=mediaFacts(e),sub=filters.subtitles||'all';return(sub==='all'||sub==='file'&&f.subtitle_files==='present'||sub==='video'&&['soft','burned','both'].includes(f.video_subtitles)||sub==='soft'&&['soft','both'].includes(f.video_subtitles)||sub==='burned'&&['burned','both'].includes(f.video_subtitles)||sub===f.subtitles)&&(!filters.script||filters.script==='all'||filters.script===f.script)&&(!filters.dubbing||filters.dubbing==='all'||filters.dubbing===f.dubbing);};
  const matches=(e,f)=>f==='video'?e.profile.media_type==='video':f==='subtitles'?mediaFacts(e).subtitles==='present':f==='audio'?e.profile.media_type==='audio':f==='resume'?!!resumeTrack(e):f==='ko-audio'?audioLanguage(e)==='ko':f==='ja-audio'?audioLanguage(e)==='ja':f==='unknown-audio'?!audioLanguage(e):true;
  const providers=work=>['dlsite','rplay','twitter'].filter(provider=>(work.codes||[]).some(c=>c.provider?.toLowerCase()===provider)||(work.editions||[]).some(e=>e.credits?.nas_import?.provider?.toLowerCase()===provider||(e.sources||[]).some(s=>s.provider?.toLowerCase()===provider)));
  const displayTitle=(work,language='ko')=>{
    const ids=new Set((work.codes||[]).map(c=>c.code.toUpperCase()));
    for(const e of work.editions||[]){
      const info=e.credits?.nas_import;if(info?.source_id)ids.add((info.provider?.toLowerCase()==='rplay'?'RP':'')+String(info.source_id).toUpperCase());
      for(const s of e.sources||[])ids.add((s.provider?.toLowerCase()==='rplay'?'RP':'')+String(s.external_id).toUpperCase());
    }
    const clean=value=>{const title=typeof value==='string'?value.trim():'',prefix=/^[\[［]([^\]］]+)[\]］]\s*/.exec(title);return prefix&&ids.has(prefix[1].normalize('NFKC').toUpperCase())?title.slice(prefix[0].length):title;};
    const titles=work.source_info_titles||{},stored=clean(work.title),original=clean(titles.ja)||stored,korean=clean(work.title_ko_manual)||clean(titles.ko)||clean(work.title_ko_auto);
    if(language==='both')return [...new Set([korean,original].filter(Boolean))].join('\n')||stored||'제목 없음';
    return (language==='ja'?original||korean:korean||original)||stored||'제목 없음';
  };
  const rplaySource=work=>{
    for(const e of work.editions||[])for(const s of e.sources||[]){
      if(s.provider?.toLowerCase()!=='rplay'||!/^[a-f0-9]{24}$/i.test(s.external_id))continue;
      const url=`https://rplay.live/play/${s.external_id}`;
      if((s.snapshots||[]).some(snapshot=>snapshot.submitted_url===url))return{editionId:e.id,url,provider:'rplay'};
    }
    return null;
  };
  const dlsiteSource=work=>{
    for(const e of work.editions||[]){
      for(const s of e.sources||[])if(s.provider==='dlsite'&&/^RJ[0-9]{6,12}$/.test(s.external_id))return{editionId:e.id,url:`https://www.dlsite.com/maniax/work/=/product_id/${s.external_id}.html`,provider:'dlsite'};
      const info=e.credits?.nas_import;
      if(info?.provider?.toLowerCase()==='dlsite'&&/^RJ[0-9]{6,12}$/.test(info.source_id))return{editionId:e.id,url:`https://www.dlsite.com/maniax/work/=/product_id/${info.source_id}.html`,provider:'dlsite'};
    }
    return null;
  };
  const sourceTags=(work,hiddenTags={},providerOnly='')=>{
    const values=[];
    function add(tags,provider){if(providerOnly&&provider!==providerOnly)return;if(Array.isArray(tags))for(const value of tags){const text=typeof value==='string'?value:value?.label||value?.name;if(typeof text==='string'&&text.trim()){const tag=text.trim().normalize('NFC');if(!tagHidden(tag,provider,hiddenTags))values.push(tag);}}}
    function read(value,provider,depth=0){
      if(!value||typeof value!=='object'||depth>6)return;
      if(Array.isArray(value)){for(const item of value)read(item,provider,depth+1);return;}
      add(value.tags,provider);add(value.genres_replaced?.length?value.genres_replaced:value.genres,provider);
      for(const [key,item] of Object.entries(value))if(!['tags','genres','genres_replaced','custom_genres'].includes(key)&&item&&typeof item==='object')read(item,provider,depth+1);
    }
    add(work.source_info_tags,'dlsite');
    for(const e of work.editions||[]){add(e.credits?.tags,(e.credits?.nas_import?.provider||'').toLowerCase());for(const s of e.sources||[])for(const snapshot of s.snapshots||[])read(snapshot.raw_metadata,(s.provider||'').toLowerCase());}
    return [...new Set(values)];
  };
  // RPLAY source tags remain readable references; only DLsite vocabulary/manual choices classify works.
  const activeSourceTags=(work,settings={})=>sourceTags(work,{...settings,rplay:sourceTags(work,{},'rplay')});
  const workTags=(work,preferences={},hiddenTags={})=>[...new Set([...(own(hiddenTags.work_tags,work.id)?hiddenTags.work_tags[work.id].filter(tag=>!tagHidden(tag,'',hiddenTags)):activeSourceTags(work,hiddenTags)),...(preferences[work.id]?.tags||[]).filter(tag=>!tagHidden(tag,'',hiddenTags))])];
  const suggestTags=(work,vocabulary)=>{const normalize=s=>s.normalize('NFKC').replace(/^#+/,'').trim().toLocaleLowerCase(),raw=new Set(sourceTags(work,{},'rplay').map(normalize)),title=normalize(displayTitle(work,'both'));return vocabulary.flatMap(row=>{const names=[row.tag,row.ko,...(row.aliases||[])].filter(Boolean),exact=names.some(t=>raw.has(normalize(t))),inTitle=names.some(t=>normalize(t).length>=3&&title.includes(normalize(t)));return exact||inTitle?[{...row,reason:exact?'알플레이 원본 태그 이름 일치':'제목에 태그명 등장 · 내용 확인 필요'}]:[];});};
  const sourceCodes=work=>[...new Set([...(work.codes||[]).filter(c=>c.provider==='dlsite').map(c=>c.code),...(work.editions||[]).flatMap(e=>[e.credits?.nas_import?.provider?.toLowerCase()==='dlsite'?e.credits.nas_import.source_id:'',...(e.sources||[]).filter(s=>s.provider?.toLowerCase()==='dlsite').map(s=>s.external_id)])].filter(id=>typeof id==='string'&&/^RJ[0-9]{6,12}$/.test(id)))];
  const familyKey=work=>{const original=work.source_info_title_sources?.ja;if(providers(work).includes('dlsite')&&typeof original==='string'&&/^RJ[0-9]{6,12}$/.test(original))return 'dlsite:'+original;const code=sourceCodes(work)[0];return code?'dlsite:'+code:rplaySource(work)?'rplay:'+rplaySource(work).url:'work:'+work.id;};
  const groupWorks=(works,enabled=true)=>{const groups=new Map();for(const work of works){const key=enabled?familyKey(work):'work:'+work.id;if(!groups.has(key))groups.set(key,{key,work,members:[]});groups.get(key).members.push(work);}return [...groups.values()];};
  const audioLabel=e=>audioLanguage(e)?`${core.language(audioLanguage(e))} 음성${manualAudioLanguage(e)?'':' · 샘플 자동감지'}`:'음성 언어 미확인';
  const subtitleLanguageLabel=s=>{const observed=s.language_observation?.language;return observed==='mixed'?'혼합 가능 자막파일 · 내용 자동감지':observed?`${core.language(observed)} 자막파일 · 내용 자동감지`:s.language&&s.language!=='und'?`${core.language(s.language)} 자막파일 · 기존 표기`:'자막파일 · 언어 미확인';};
  const subtitleLabel=e=>{const f=mediaFacts(e),labels=[];if(hasSubtitles(e))labels.push([...new Set(e.tracks.flatMap(t=>t.subtitles||[]).map(subtitleLanguageLabel))].join(' · '));else if(f.subtitle_files==='present')labels.push('자막파일 있음 · 미연결');if(['soft','both'].includes(f.video_subtitles))labels.push('선택형 자막영상');if(['burned','both'].includes(f.video_subtitles))labels.push('붙박이 자막영상');return labels.join(' · ')||(f.subtitles==='none'?'자막 없음 · 확인':'자막 미확인');};
  const scriptLabel=e=>mediaFacts(e).script==='present'?'대본 있음':mediaFacts(e).script==='none'?'대본 없음 · 확인':'대본 미확인';
  const dubbingLabel=e=>mediaFacts(e).dubbing==='present'?`더빙 있음${audioLanguage(e)?' · '+core.language(audioLanguage(e)):''}`:mediaFacts(e).dubbing==='none'?'더빙 없음 · 확인':'더빙 미확인';
  const mediaLabels=e=>{const facts=mediaFacts(e),labels=[audioLabel(e)],unknown=[];for(const [key,label,read]of [['subtitles','자막',subtitleLabel],['script','대본',scriptLabel],['dubbing','더빙',dubbingLabel]]){if(facts[key]==='unknown')unknown.push(label);else labels.push(read(e));}if(unknown.length)labels.push(unknown.join('·')+' 미확인');return labels;};
  const trackTitle=(track,mode='both')=>{const original=track.title||'',ko=typeof track.title_ko==='string'?track.title_ko.trim():'';return mode==='original'?original:mode==='ko'?ko||original:[...new Set([ko,original].filter(Boolean))].join('\n');};
  const core={playable,resumeTrack,hasSubtitles,matches,mediaFacts,mediaMatches,mediaLabels,scriptLabel,dubbingLabel,providers,displayTitle,rplaySource,dlsiteSource,sourceTags,activeSourceTags,tags:workTags,tagLabel,tagSearchText,tagKey,resolveTagKey,tagGroups,tagGroupLabel,tagState,cycleTag,tagFavorite,tagHidden,randomRank,sortTagGroups,sourceCodes,familyKey,groupWorks,audioLanguage,audioLabel,subtitleLabel,trackTitle,suggestTags,subtitleLanguageLabel,
    mergePreferenceBackup(backup,works,preferences){
      if(backup?.type!=='audio-studio-preferences'||backup.version!==1||!backup.items||typeof backup.items!=='object'||Array.isArray(backup.items)||Object.keys(backup.items).length>10000)throw new Error('즐겨찾기·내 태그 백업 파일이 아닙니다.');
      const known=new Set(works.map(w=>w.id)),updates={};let skipped=0;
      for(const [id,item] of Object.entries(backup.items)){
        if(!/^[a-f0-9]{32}$/.test(id)||!item||typeof item.favorite!=='boolean'||!Array.isArray(item.tags)||!item.tags.every(t=>typeof t==='string')||item.tags.some(t=>t.includes(',')||t.includes('，')||t.includes('\n')))throw new Error('백업 파일의 작품 또는 태그 형식이 올바르지 않습니다.');
        const tags=core.parseTags(item.tags.join(','));
        if(!known.has(id)){skipped++;continue;}
        const current=preferences[id]||{favorite:false,tags:[]};
        updates[id]={favorite:current.favorite===true||item.favorite,tags:core.parseTags([...current.tags,...tags].join(','))};
      }
      return{updates,skipped};
    },
    coverSource(work){return dlsiteSource(work)||rplaySource(work);},
    identity(work){return[...providers(work).map(p=>p==='dlsite'?'DLsite':p==='rplay'?'RPLAY':'Twitter 폴더'),...new Set([...(work.codes||[]).map(c=>c.code),...sourceCodes(work)])].join(' · ')||'출처 미지정';},
    folderTree(tracks){
      const root={name:'',folders:[],tracks:[],count:tracks.length};
      for(const track of tracks){
        const parts=(track.relative_path||'').split('/');parts.pop();let node=root;
        for(const name of parts.filter(Boolean)){
          let folder=node.folders.find(f=>f.name===name);
          if(!folder){folder={name,folders:[],tracks:[],count:0};node.folders.push(folder);}
          folder.count++;node=folder;
        }
        node.tracks.push(track);
      }
      return root;
    },
    editionLabel(e){
      if(e.profile.media_type==='video')return ['영상',...mediaLabels(e)].filter(Boolean).join(' · ');
      if(!['audio','voice_comic'].includes(e.kind))return e.kind==='translation'?'번역본':'만화';
      return mediaLabels(e).join(' · ');
    },
    preferred(work,filter='all',saved='',mediaFilters={}){
      const selected=work.editions.find(e=>e.id===saved&&matches(e,filter)&&mediaMatches(e,mediaFilters));if(selected)return selected;
      const eligible=work.editions.filter(e=>matches(e,filter)&&mediaMatches(e,mediaFilters));
      return eligible.find(e=>playable(e)&&hasSubtitles(e))||eligible.find(playable)||eligible[0]||work.editions[0]||null;
    },
    parseTags(value){
      if(typeof value!=='string')throw new Error('태그는 쉼표로 구분해 입력하세요.');
      const tags=[...new Set(value.split(/[,，\n]/).map(tag=>tag.trim().normalize('NFC')).filter(Boolean))];
      if(tags.length>20||tags.some(tag=>tag.length>40))throw new Error('태그는 최대 20개, 각 40자까지 입력할 수 있습니다.');
      return tags;
    },
    filterWorks(works,query='',filter='all',sort='added',{favoritesOnly=false,tags=[],excludeTags=[],preferences={},provider='all',titleLanguage='ko',hiddenRplayTags=[],hiddenTags={rplay:hiddenRplayTags},randomSeed=0,randomGroup=true,mediaFilters={},voiceActor=''}={}){
      const term=query.trim().normalize('NFC').toLocaleLowerCase();
      const searchText=w=>JSON.stringify(w,(key,value)=>['raw_metadata','tags','source_info_tags'].includes(key)?undefined:value)+' '+workTags(w,preferences,hiddenTags).map(tag=>tagSearchText(tag,hiddenTags)).join(' ');
      return works.filter(w=>{const keys=new Set(workTags(w,preferences,hiddenTags).map(tag=>resolveTagKey(tag,hiddenTags)));return(!term||searchText(w).toLocaleLowerCase().includes(term))&&(filter==='translation-issues'?!!w.title_translation?.issues?.length||w.editions.some(e=>e.tracks.some(t=>t.title_translation?.issues?.length)):filter==='untagged'?!keys.size:filter==='all'||w.editions.some(e=>matches(e,filter)))
        &&(!Object.values(mediaFilters).some(v=>v&&v!=='all')||w.editions.some(e=>matches(e,filter)&&mediaMatches(e,mediaFilters)))&&(provider==='all'||providers(w).includes(provider))&&(!voiceActor||w.editions.some(e=>(e.voice_actors||[]).some(a=>a.id===voiceActor)))&&(!favoritesOnly||preferences[w.id]?.favorite===true)&&tags.every(tag=>keys.has(resolveTagKey(tag,hiddenTags)))&&!excludeTags.some(tag=>keys.has(resolveTagKey(tag,hiddenTags)));})
        .sort((a,b)=>{
          const title=()=>displayTitle(a,titleLanguage).localeCompare(displayTitle(b,titleLanguage),'ko',{numeric:true});
          const tracks=w=>w.editions.reduce((sum,e)=>sum+e.tracks.length,0);
          const duration=w=>{const e=core.preferred(w,filter,'',mediaFilters);return e?.tracks.length&&e.tracks.every(t=>Number.isFinite(t.duration)&&t.duration>0)?e.tracks.reduce((sum,t)=>sum+t.duration,0):null;};
          let result;
          if(sort==='title'||sort==='title-desc')result=title()*(sort==='title-desc'?-1:1);
          else if(sort==='rj')result=(a.codes[0]?.code||'\uffff').localeCompare(b.codes[0]?.code||'\uffff',undefined,{numeric:true});
          else if(sort==='oldest')result=a.created-b.created;
          else if(sort==='provider')result=providers(a).join().localeCompare(providers(b).join());
          else if(sort==='random')result=randomRank(randomGroup?familyKey(a):a.id,randomSeed)-randomRank(randomGroup?familyKey(b):b.id,randomSeed);
          else if(sort==='tracks'||sort==='tracks-asc')result=(tracks(b)-tracks(a))*(sort==='tracks-asc'?-1:1);
          else if(sort==='duration'||sort==='duration-asc'){const x=duration(a),y=duration(b);result=x===null?(y===null?0:1):y===null?-1:(y-x)*(sort==='duration-asc'?-1:1);}
          else return b.created-a.created;
          return result||title()||String(a.id).localeCompare(String(b.id));
        });
    },
    time(seconds){return !Number.isFinite(seconds)||seconds<0?'—':`${Math.floor(seconds/60)}:${String(Math.floor(seconds%60)).padStart(2,'0')}`;},
    language(value){return {ko:'한국어',ja:'일본어',en:'영어',other:'기타 언어'}[value]||value||'언어 미지정';},
    creator(work){for(const e of work.editions){const c=e.credits||{},v=c.circle||c.artist||c.voice;if(v)return Array.isArray(v)?v.join(', '):String(v);}return '';}
  };
  if(typeof module!=='undefined'&&module.exports)module.exports=core;else root.LibraryCore=core;
})(typeof window!=='undefined'?window:globalThis);
