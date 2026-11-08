// Exercise the real library module without opening a browser or changing the user screen.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
class Element{
  constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.style={};this.listeners={};this.attributes={};this.className='';this.hidden=false;this.open=false;this._text='';this._value='';
    this.classList={toggle:(name,on)=>{const classes=new Set(this.className.split(' ').filter(Boolean));const use=on===undefined?!classes.has(name):on;use?classes.add(name):classes.delete(name);this.className=[...classes].join(' ');return use;},add:name=>this.classList.toggle(name,true)};}
  append(...nodes){for(const n of nodes){n.parent=this;this.children.push(n);}}
  prepend(...nodes){for(const n of nodes)n.parent=this;this.children.unshift(...nodes);}
  replaceChildren(...nodes){this.children=[];this._text='';this.append(...nodes);}
  get firstChild(){return this.children[0];}
  get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
  set textContent(value){this._text=String(value);this.children=[];}
  get value(){return this._value||(this.tagName==='SELECT'?this.children[0]?.value||'':'');}
  set value(value){this._value=String(value);}
  setAttribute(name,value){this.attributes[name]=String(value);if(name==='class')this.className=value;else if(name.startsWith('data-'))this.dataset[name.slice(5)]=value;else this[name]=value;}
  addEventListener(name,fn){(this.listeners[name]||=[]).push(fn);}
  emit(name){for(const fn of this.listeners[name]||[])fn({target:this,preventDefault(){}});}
  querySelectorAll(selector){return descendants(this).filter(n=>match(n,selector));}
  querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
  get elements(){return{namedItem:name=>descendants(this).find(n=>n.name===name)};}
  showModal(){this.open=true;}
  close(){this.open=false;}
  focus(){document.activeElement=this;}
  reset(){for(const n of descendants(this))if(n.tagName==='INPUT')n.value='';}
}
function descendants(n){return n.children.flatMap(c=>[c,...descendants(c)]);}
function match(n,s){return s.startsWith('.')?s.slice(1).split('.').every(c=>n.className.split(' ').includes(c)):s.startsWith('[data-')?s.slice(6,-1).replace(/-([a-z])/g,(_,c)=>c.toUpperCase()) in n.dataset:n.tagName===s.toUpperCase();}
const root=new Element('html'),stack=[root];
const html=fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8');
const voids=new Set(['META','LINK','INPUT','BR','HR','IMG']);
for(const token of html.match(/<[^>]+>|[^<]+/g)){
  if(token.startsWith('</')){stack.pop();continue;}
  if(token.startsWith('<!'))continue;
  if(token.startsWith('<')){const [,tag,attrs]=/^<(\w+)([^>]*)>/.exec(token);const n=new Element(tag);for(const m of attrs.matchAll(/([\w-]+)(?:="([^"]*)")?/g)){if(m[1]==='hidden')n.hidden=true;else n.setAttribute(m[1],m[2]??true);}stack.at(-1).append(n);if(!voids.has(n.tagName))stack.push(n);}
  else stack.at(-1)._text+=token;
}
const listeners={};
const document={getElementById:id=>descendants(root).find(n=>n.id===id),createElement:tag=>new Element(tag),querySelectorAll:s=>root.querySelectorAll(s),addEventListener:(name,fn)=>{(listeners[name]||=[]).push(fn);},activeElement:null};
const $=document.getElementById;
const workId='a'.repeat(32),originalId='b'.repeat(32),subtitleId='c'.repeat(32),videoId='d'.repeat(32);
const makeEdition=(id,title,media,translation,subs,resume=0)=>({id,work_id:workId,title,kind:'audio',language:'ko',credits:{circle:'테스트 서클'},profile:{media_type:media,translation},sources:[],tracks:[{id:id[0].repeat(31)+'1',edition_id:id,title:title+' 트랙',relative_path:'sample.wav',duration:60,resume,subtitles:subs}]});
const editions=[makeEdition(originalId,'원본 음성','audio','none',[]),makeEdition(subtitleId,'한국어 자막판','audio','subtitles',[{id:'s',label:'한국어'}],10),makeEdition(videoId,'자막 영상판','video','embedded',[])];
const works=[{id:workId,title:'테스트 작품',created:1,codes:[{provider:'dlsite',code:'RJ00000000'}],editions}];
const opened=[],requests=[];
const basePath=process.env.AUDIO_TEST_BASE||'';
const location={hostname:'127.0.0.1',port:'43132',pathname:basePath+'/',search:'',hash:''};
const window={LibraryCore:require('../web/library-core.js'),StudioPlayer:{open:(...args)=>{opened.push(args);return Promise.resolve();},move:require('../web/player-core.js').move},addEventListener(){},scrollTo(){}};
const storage=new Map();let storageFails=false;
const context={window,document,location,history:{pushState:(_a,_b,url)=>{location.hash=url.includes('#')?url.slice(url.indexOf('#')):'';}},localStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>{if(storageFails)throw new Error('Quota exceeded');storage.set(key,value);}},setTimeout:(fn,ms)=>{const timer=setTimeout(fn,ms);timer.unref();return timer;},clearTimeout,console,
 fetch:async(url,options)=>{assert.ok(url.startsWith(basePath+'/api/'),'API calls stay inside the selected Audio path');requests.push([url,options]);url=url.slice(basePath.length);let value;if(url==='/api/works')value={works:structuredClone(works)};else if(url==='/api/health')value={status:'ok'};else if(url==='/api/local-files')value={items:[{relative_path:'sample.wav',kind:'audio'},{relative_path:'sample.ko.srt',kind:'subtitle'}]};else if(url.endsWith('/source-info'))value={tags:['公式補充'],available:true};else if(url.endsWith('/cover/refresh'))value={available:!url.includes('7'.repeat(32))};else if(url.startsWith('/api/editions/'))value=structuredClone(editions.find(e=>e.id===url.split('/')[3]));else throw new Error('Unexpected request '+url);return{ok:true,json:async()=>value};}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8'),context);
const flush=()=>new Promise(setImmediate);
const find=(node,cls)=>descendants(node).find(n=>n.className.split(' ').includes(cls));
const findButton=(node,text)=>descendants(node).find(n=>n.tagName==='BUTTON'&&n.textContent===text);
(async()=>{
  await flush();assert.equal($('manager').open,false);assert.equal($('library-view').hidden,false);assert.equal($('library').children.length,1);
  find($('library'),'card-open').emit('click');
  assert.equal($('work-view').hidden,false);assert.equal($('library-view').hidden,true);
  assert.equal(find($('detail'),'version-tabs').children.length,3);
  assert.ok($('detail').textContent.includes('한국어 자막판'));
  assert.ok(!$('detail').textContent.includes('JSON'),'Listening screen does not contain metadata forms');
  findButton($('detail'),'처음부터 전체 재생').emit('click');await flush();
  assert.equal(opened[0][1].edition_id,subtitleId);assert.equal(opened[0][2].mode,'all');assert.equal(opened[0][2].fromStart,true);
  find($('detail'),'version-tabs').children[2].emit('click');
  findButton($('detail'),'전체 재생').emit('click');await flush();assert.equal(opened[1][1].edition_id,videoId);
  findButton($('detail'),'폴더 보기').emit('click');
  assert.ok(find($('detail'),'folder-tree'));
  find($('detail'),'track-play').emit('click');await flush();
  assert.equal(opened[2][1].edition_id,videoId,'Folder browsing plays the same edition and track');
  findButton($('detail'),'재생목록').emit('click');
  assert.ok(find($('detail'),'track-list'));
  $('manage-work').emit('click');await flush();assert.equal($('manager').open,true);assert.equal($('edition-settings').hidden,false);
  const picker=descendants($('manage-content')).find(n=>n.tagName==='SELECT'&&n.name==='relative_path');assert.ok(picker.children.some(n=>n.value==='sample.wav'));
  picker.value='sample.wav';picker.emit('change');const title=descendants($('manage-content')).find(n=>n.name==='title');assert.equal(title.value,'sample');
  $('close-manager').emit('click');assert.equal($('manager').open,false);
  $('back-library').emit('click');assert.equal($('library-view').hidden,false);
  const key='audio-work-preferences-v1:'+workId;
  find($('library'),'favorite-button').emit('click');await flush();
  assert.equal(JSON.parse(storage.get(key)).favorite,true);
  assert.equal(find($('library'),'favorite-button').attributes['aria-pressed'],'true');
  assert.equal(document.activeElement,find($('library'),'favorite-button'),'Favorite toggle retains keyboard focus');
  find($('library'),'card-open').emit('click');
  $('work-tags-input').value=' 수면, 자연음,수면 ';
  find($('detail'),'tag-form').emit('submit');await flush();
  assert.deepEqual(JSON.parse(storage.get(key)).tags,['수면','자연음']);
  assert.equal(JSON.parse(storage.get(key)).favorite,true,'Saving tags preserves the favorite');
  $('work-tags-input').value='가'.repeat(41);find($('detail'),'tag-form').emit('submit');await flush();
  assert.deepEqual(JSON.parse(storage.get(key)).tags,['수면','자연음'],'Invalid input does not overwrite saved tags');
  assert.ok($('status').textContent.includes('40자'));
  const draft=$('work-tags-input');draft.value='아직 저장하지 않은 태그';
  find($('detail'),'favorite-detail').emit('click');await flush();
  assert.equal($('work-tags-input'),draft);assert.equal(draft.value,'아직 저장하지 않은 태그','Favorite toggle preserves the unsaved tag draft');
  find($('detail'),'favorite-detail').emit('click');await flush();
  find($('detail'),'tag-editor').open=true;findButton($('detail'),'폴더 보기').emit('click');
  assert.equal($('work-tags-input').value,'아직 저장하지 않은 태그');assert.equal(find($('detail'),'tag-editor').open,true,'Changing track view preserves the tag draft and disclosure');
  $('back-library').emit('click');
  works.push({...works[0],id:'e'.repeat(32),codes:[{provider:'dlsite',code:'RJ00000001'}],title:'다른 작품'});
  await vm.runInNewContext('load()',context);
  assert.equal($('library').children.length,2);
  assert.equal(find($('library'),'favorite-button').attributes['aria-pressed'],'true','Reload restores the saved favorite');
  $('favorites-filter').emit('click');assert.equal($('library').children.length,1);
  $('tag-options').querySelectorAll('[data-tag]')[0].emit('click');$('tag-options').querySelectorAll('[data-tag]')[1].emit('click');
  assert.equal($('library').children.length,1);assert.ok($('selected-tag-count').textContent.includes('수면'));
  find($('library'),'favorite-button').emit('click');await flush();
  assert.ok($('library').textContent.includes('즐겨찾기한 작품이 없습니다'));
  assert.equal(document.activeElement,$('favorites-filter'),'Removing the last favorite moves focus to its filter');
  $('clear-filters').emit('click');assert.equal($('library').children.length,2);assert.equal($('selected-tag-count').textContent,'전체');
  $('favorites-nav').emit('click');assert.ok($('library').textContent.includes('즐겨찾기한 작품이 없습니다'));
  document.querySelectorAll('[data-filter]').find(n=>n.dataset.filter==='all'&&n.className.includes('nav-item')).emit('click');assert.equal($('library').children.length,2);
  $('search').value='자연음';$('search').emit('input');assert.equal($('library').children.length,1,'Search includes personal tags');
  storageFails=true;find($('library'),'favorite-button').emit('click');await flush();
  assert.equal(JSON.parse(storage.get(key)).favorite,false,'Failed storage never claims a saved favorite');
  assert.ok($('status').textContent.includes('저장하지 못했습니다'));storageFails=false;
  storage.set(key,'{broken json');await vm.runInNewContext('load()',context);
  $('clear-filters').emit('click');assert.equal($('library').children.length,2,'Malformed local storage does not break browsing');
  $('search').value='not-present';$('search').emit('input');assert.ok($('library').textContent.includes('조건에 맞는 작품이 없습니다'));
  findButton($('library'),'전체 보관함 보기').emit('click');assert.equal($('search').value,'');assert.equal($('library').children.length,2);
  const sourceId='612bbf2c16d4881b2056bb44',rplayWork={id:'f'.repeat(32),title:`[RP${sourceId}] 밤의 라디오`,created:3,codes:[],editions:[{...editions[0],id:'7'.repeat(32),credits:{nas_import:{provider:'rplay',source_id:sourceId}},sources:[{provider:'rplay',external_id:sourceId,snapshots:[{submitted_url:`https://rplay.live/play/${sourceId}`}]}]}]};
  works.push(rplayWork);await vm.runInNewContext('load()',context);
  const providerButtons=document.querySelectorAll('[data-provider]'),rplayFilter=providerButtons.find(n=>n.dataset.provider==='rplay');
  rplayFilter.emit('click');assert.equal($('library').children.length,1);assert.equal(rplayFilter.attributes['aria-pressed'],'true');
  assert.equal(find($('library'),'card-info').querySelector('h3').textContent,'밤의 라디오');
  assert.equal(find($('library'),'card-code').textContent,'RPLAY');assert.ok(!$('library').textContent.includes('RJ 미등록'));
  const image=$('library').querySelector('img'),placeholder=find($('library'),'placeholder');
  assert.equal(image.src,`${basePath}/api/editions/${'7'.repeat(32)}/cover`);image.emit('load');assert.equal(placeholder.hidden,true);
  image.emit('error');assert.equal(image.hidden,true);assert.equal(placeholder.hidden,false,'Unavailable thumbnails retain a usable placeholder');
  find($('library'),'card-open').emit('click');assert.equal($('detail').querySelector('h1').textContent,'밤의 라디오');
  assert.equal(find($('detail'),'original-source').href,`https://rplay.live/play/${sourceId}`);
  $('back-library').emit('click');$('clear-filters').emit('click');assert.equal($('library').children.length,3);
  providerButtons.find(n=>n.dataset.provider==='dlsite').emit('click');assert.equal($('library').children.length,2);
  $('clear-filters').emit('click');assert.equal($('library').children.length,3);
  works[0].editions=editions.map(e=>({...e,credits:{...e.credits,tags:['原本','睡眠']}}));
  storage.set(key,JSON.stringify({version:1,favorite:true,tags:['내 태그']}));await vm.runInNewContext('load()',context);
  const originalCard=$('library').children.find(n=>n.dataset.workId===workId);find(originalCard,'card-open').emit('click');
  assert.equal($('work-tags-input').value,'내 태그','Editor contains only personal tags');
  assert.ok(find($('detail'),'work-tag-list').textContent.includes('原本'));
  $('work-tags-input').value='';find($('detail'),'tag-form').emit('submit');await flush();
  assert.deepEqual(JSON.parse(storage.get(key)).tags,[]);assert.equal(JSON.parse(storage.get(key)).favorite,true);
  assert.ok(find($('detail'),'work-tag-list').textContent.includes('原本'),'Clearing personal tags preserves original tags');
  $('back-library').emit('click');$('tag-search').value='原本';$('tag-search').emit('input');assert.equal($('tag-options').querySelectorAll('[data-tag]').length,1);
  $('tag-options').querySelectorAll('[data-tag]')[0].emit('click');assert.equal($('library').children.length,1,'Imported tags participate in filtering');
  $('clear-filters').emit('click');assert.equal($('tag-search').value,'');
  const missing={...works[0],id:'8'.repeat(32),codes:[],editions:[{...editions[0],id:'9'.repeat(32),credits:{nas_import:{provider:'dlsite',source_id:'RJ987654'}},sources:[]}]};
  works.push(missing);await vm.runInNewContext('load()',context);await flush();
  const enriched=$('library').children.find(n=>n.dataset.workId===missing.id);
  assert.ok(find(enriched,'card-tags').textContent.includes('公式補充'),'Missing original tags load from the public source-info endpoint');
  assert.equal(storage.has('audio-work-preferences-v1:'+missing.id),false,'Source enrichment does not rewrite personal preferences');
  works[0].editions=works[0].editions.map(e=>({...e,credits:{...e.credits,tags:['耳かき','癒し']}}));
  await vm.runInNewContext('load()',context);await flush();
  $('tag-search').value='귀청소';$('tag-search').emit('input');
  assert.equal($('tag-options').querySelectorAll('[data-tag]').length,1);assert.equal($('tag-options').querySelectorAll('[data-tag]')[0].textContent,'귀청소1');
  assert.equal($('tag-options').querySelectorAll('[data-tag]')[0].dataset.tag,'귀청소');
  $('tag-options').querySelectorAll('[data-tag]')[0].emit('click');assert.equal($('library').children.length,1);
  assert.equal(document.activeElement.dataset.tag,'귀청소','Merged tag filter retains keyboard focus');
  assert.ok($('selected-tag-count').textContent.includes('귀청소'));
  $('clear-filters').emit('click');$('search').value='힐링';$('search').emit('input');assert.equal($('library').children.length,1);
  $('clear-filters').emit('click');
  find($('library').children.find(n=>n.dataset.workId===workId),'card-open').emit('click');
  assert.ok(find($('detail'),'work-tag-list').textContent.includes('귀청소'));
  assert.equal($('work-tags-input').value,'','Source translations never overwrite personal tag input');
  assert.equal(requests.filter(([,o])=>o?.method==='POST').length,0,'Browsing and choosing versions never mutates the catalog');
  $('work-tags-input').value='저장 전 초안';
  $('tag-language').value='ja';$('tag-language').emit('change');
  assert.ok(find($('detail'),'work-tag-list').textContent.includes('耳かき'));
  assert.ok(!find($('detail'),'work-tag-list').textContent.includes('귀청소'));
  assert.equal($('work-tags-input').value,'저장 전 초안','Changing display settings preserves the unsaved tag draft');
  works[0].source_info_titles={ko:'공식 한국어 제목',ja:'日本語タイトル'};await vm.runInNewContext('load()',context);
  $('title-language').value='both';$('title-language').emit('change');
  assert.equal($('detail').querySelector('h1').textContent,'공식 한국어 제목\n日本語タイトル');
  $('title-language').value='ja';$('title-language').emit('change');assert.equal($('detail').querySelector('h1').textContent,'日本語タイトル');
  $('back-library').emit('click');$('tag-search').value='귀청소';$('tag-search').emit('input');
  assert.equal($('tag-options').querySelectorAll('[data-tag]')[0].querySelector('span').textContent,'1','Tag counts count works, not duplicate editions');
  assert.ok($('tag-options').querySelectorAll('[data-tag]')[0].attributes['aria-label'].includes('1개 작품'));
  $('clear-filters').emit('click');
  for(let i=0;i<27;i++)works.push({...works[0],id:'page-'+i,title:'작품 '+i,codes:[],source_info_titles:undefined,editions:[{...editions[0],credits:{}}]});
  await vm.runInNewContext('load()',context);
  $('page-size').value='12';$('page-size').emit('change');assert.equal($('library').children.length,12);assert.equal($('pagination').hidden,false);
  $('next-page').emit('click');assert.ok($('page-number').textContent.startsWith('2 /'));
  $('page-size').value='all';$('page-size').emit('change');assert.equal($('library').children.length,works.length);assert.equal($('pagination').hidden,true);
  $('sort').value='title-desc';$('sort').emit('change');
  assert.deepEqual(JSON.parse(storage.get('audio-display-settings-v1')),{tagLanguage:'ja',titleLanguage:'ja',trackLanguage:'both',groupSameWork:true,pageSize:'all',sort:'title-desc',tagSort:'count-desc'});
  assert.equal(opened.length,3,'Display controls never start playback or request fullscreen');
  await vm.runInNewContext('refreshMissingCovers()',context);
  assert.equal($('refresh-covers').disabled,false);
  assert.ok($('cover-refresh-status').textContent.includes('없음 1'));
  assert.equal(requests.filter(([,o])=>o?.method==='POST').length,2);
  assert.ok(requests.filter(([,o])=>o?.method==='POST').every(([url])=>url.endsWith('/cover/refresh')),'Recovery writes only app caches, never catalog titles or playback progress');
  const beforeGroup=works.length;
  works.push({...works[0],id:'separate-copy',codes:[],source_info_titles:undefined,editions:[{...editions[0],credits:{nas_import:{provider:'dlsite',source_id:'RJ00000000',separate_physical_copy:true}}}]});
  await vm.runInNewContext('load()',context);assert.equal($('library').children.length,beforeGroup,'A second holding stays accessible inside one card');
  const grouped=$('library').children.find(n=>find(n,'holdings')),holding=find(grouped,'holdings');assert.ok(holding.textContent.includes('보유본 2개'));
  assert.equal(holding.querySelectorAll('.favorite-button').length,2,'Each holding retains its own favorite');
  $('group-same-work').checked=false;$('group-same-work').emit('change');assert.equal($('library').children.length,works.length);
  $('metadata-filter').value='ko-audio';$('metadata-filter').emit('change');assert.equal($('page-title').textContent,'한국어 음성');
  $('clear-filters').emit('click');assert.equal($('metadata-filter').value,'all');
  works[0].editions[0].tracks[0].title_ko='한국어 트랙';works[0].editions[0].tracks[0].title_translation_kind='machine';await vm.runInNewContext('load()',context);
  find($('library').children.find(n=>n.dataset.workId===workId),'card-open').emit('click');
  find($('detail'),'version-tabs').children[0].emit('click');
  assert.ok(find($('detail'),'track-info').querySelector('strong').textContent.includes('한국어 트랙\n'));
  $('track-language').value='original';$('track-language').emit('change');assert.equal(find($('detail'),'track-info').querySelector('strong').textContent,editions[0].tracks[0].title);
  console.log('Library runtime: playback navigation, tag editing/filtering, favorites, persistence, storage failure, focus and non-mutating browsing passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
