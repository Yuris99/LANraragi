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
function match(n,s){return s.startsWith('.')?n.className.split(' ').includes(s.slice(1)):s.startsWith('[data-')?s.slice(6,-1) in n.dataset:n.tagName===s.toUpperCase();}
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
const location={hostname:'127.0.0.1',port:'43132',pathname:'/',search:'',hash:''};
const window={LibraryCore:require('../web/library-core.js'),StudioPlayer:{open:(...args)=>{opened.push(args);return Promise.resolve();},move:require('../web/player-core.js').move},addEventListener(){},scrollTo(){}};
const context={window,document,location,history:{pushState:(_a,_b,url)=>{location.hash=url.includes('#')?url.slice(url.indexOf('#')):'';}},localStorage:{getItem:()=>null,setItem(){}},setTimeout,clearTimeout,console,
 fetch:async(url,options)=>{requests.push([url,options]);let value;if(url==='/api/works')value={works:structuredClone(works)};else if(url==='/api/health')value={status:'ok'};else if(url==='/api/local-files')value={items:[{relative_path:'sample.wav',kind:'audio'},{relative_path:'sample.ko.srt',kind:'subtitle'}]};else if(url.startsWith('/api/editions/'))value=structuredClone(editions.find(e=>e.id===url.split('/')[3]));else throw new Error('Unexpected request '+url);return{ok:true,json:async()=>value};}};
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
  findButton($('detail'),'▶ 처음부터 전체 재생').emit('click');await flush();
  assert.equal(opened[0][1].edition_id,subtitleId);assert.equal(opened[0][2].mode,'all');assert.equal(opened[0][2].fromStart,true);
  find($('detail'),'version-tabs').children[2].emit('click');
  findButton($('detail'),'▶ 전체 재생').emit('click');await flush();assert.equal(opened[1][1].edition_id,videoId);
  $('manage-work').emit('click');await flush();assert.equal($('manager').open,true);assert.equal($('edition-settings').hidden,false);
  const picker=descendants($('manage-content')).find(n=>n.tagName==='SELECT'&&n.name==='relative_path');assert.ok(picker.children.some(n=>n.value==='sample.wav'));
  picker.value='sample.wav';picker.emit('change');const title=descendants($('manage-content')).find(n=>n.name==='title');assert.equal(title.value,'sample');
  $('close-manager').emit('click');assert.equal($('manager').open,false);
  $('back-library').emit('click');assert.equal($('library-view').hidden,false);
  $('search').value='not-present';$('search').emit('input');assert.ok($('library').textContent.includes('조건에 맞는 작품이 없습니다'));
  assert.equal(requests.filter(([,o])=>o?.method==='POST').length,0,'Browsing and choosing versions never mutates the catalog');
  console.log('Library runtime: card -> version -> play, hidden management, file picker and non-mutating browsing passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
