(function(root) {
  'use strict';
  const playable=e=>['audio','voice_comic'].includes(e.kind)&&e.tracks.length>0;
  const resumeTrack=e=>e.tracks.find(t=>t.resume>0&&(!t.duration||t.resume<t.duration-0.5))||null;
  const hasSubtitles=e=>e.tracks.some(t=>(t.subtitles||[]).length);
  const matches=(e,f)=>f==='video'?e.profile.media_type==='video':f==='subtitles'?e.profile.translation!=='none':f==='audio'?e.profile.media_type==='audio'&&e.profile.translation==='none':f==='resume'?!!resumeTrack(e):true;
  const core={playable,resumeTrack,hasSubtitles,matches,
    editionLabel(e){
      if(e.profile.media_type==='video')return e.profile.translation==='embedded'?'자막 영상':hasSubtitles(e)||e.profile.translation==='subtitles'?'영상 + 자막':'영상';
      if(!['audio','voice_comic'].includes(e.kind))return e.kind==='translation'?'번역본':'만화';
      return e.profile.translation==='subtitles'?'번역 자막':'원본 음성';
    },
    preferred(work,filter='all',saved=''){
      const selected=work.editions.find(e=>e.id===saved&&matches(e,filter));if(selected)return selected;
      const eligible=work.editions.filter(e=>matches(e,filter));
      return eligible.find(e=>playable(e)&&hasSubtitles(e))||eligible.find(playable)||eligible[0]||work.editions[0]||null;
    },
    filterWorks(works,query='',filter='all',sort='added'){
      const term=query.trim().toLocaleLowerCase();
      return works.filter(w=>(!term||JSON.stringify(w).toLocaleLowerCase().includes(term))&&(filter==='all'||w.editions.some(e=>matches(e,filter))))
        .sort(sort==='title'?(a,b)=>a.title.localeCompare(b.title,'ko'):sort==='rj'?(a,b)=>(a.codes[0]?.code||'\uffff').localeCompare(b.codes[0]?.code||'\uffff'):(a,b)=>b.created-a.created);
    },
    time(seconds){return !Number.isFinite(seconds)||seconds<0?'—':`${Math.floor(seconds/60)}:${String(Math.floor(seconds%60)).padStart(2,'0')}`;},
    language(value){return {ko:'한국어',ja:'일본어',en:'영어'}[value]||value||'언어 미지정';},
    creator(work){for(const e of work.editions){const c=e.credits||{},v=c.circle||c.artist||c.voice;if(v)return Array.isArray(v)?v.join(', '):String(v);}return '';}
  };
  if(typeof module!=='undefined'&&module.exports)module.exports=core;else root.LibraryCore=core;
})(typeof window!=='undefined'?window:globalThis);
