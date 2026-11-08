// Run the real player module against a small simulated DOM, with no browser/window actions.
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const core = require('../web/player-core.js');
class Element {
  constructor(id='') { Object.assign(this,{id,hidden:false,value:'',type:'',tagName:'BUTTON',textContent:'',style:{},children:[],listeners:{},className:'',disabled:false,open:false}); const classes=new Set();this.classList={add:name=>classes.add(name),remove:name=>classes.delete(name),contains:name=>classes.has(name),toggle:(name,on)=>{const show=on===undefined?!classes.has(name):on;show?classes.add(name):classes.delete(name);return show;}}; }
  addEventListener(name,fn) { (this.listeners[name] ||= []).push(fn); }
  emit(name,extra={}) { for(const fn of this.listeners[name] || []) fn({target:this,key:'',preventDefault(){},...extra}); }
  append(node) { this.children.push(node); }
  replaceChildren() { this.children=[]; }
  setAttribute(name,value) { this[name]=value; }
  focus() { document.activeElement=this; }
  contains(node) { return this===node || this.children.some(child=>child.contains(node)); }
  querySelectorAll() { return []; }
}
const nodes = new Map();
const get = id => { if(!nodes.has(id)) nodes.set(id,new Element(id));return nodes.get(id); };
const stage=get('cinema');stage.hidden=true;
for(const id of ['player-header','player-transport','player-controls','screen-controls'])stage.append(get(id));
get('player-header').append(get('close-player'));
get('player-controls').append(get('seek'));get('seek').tagName='INPUT';
let fullscreens=0,wakeRequests=0,wakeReleases=0;
stage.requestFullscreen=async()=>{fullscreens++;};
const media=get('media');
Object.assign(media,{paused:true,readyState:1,currentTime:0,duration:10,playbackRate:1});
media.load=()=>{media.ended=false;queueMicrotask(()=>media.emit('loadedmetadata'));};
media.pause=()=>{media.paused=true;media.emit('pause');};
media.play=async()=>{media.paused=false;media.emit('play');};
const documentListeners={};
const document={getElementById:get,createElement:()=>new Element(),querySelectorAll:()=>[],visibilityState:'visible',activeElement:null,body:new Element(),addEventListener:(name,fn)=>{(documentListeners[name]||=[]).push(fn);},dispatchEvent(){},exitFullscreen:async()=>{}};
let now=0,timerId=0;const timers=new Map();
const setTimer=(fn,delay)=>{timers.set(++timerId,{fn,at:now+delay});return timerId;};
const tick=async(ms)=>{now+=ms;for(const[id,timer]of [...timers])if(timer.at<=now){timers.delete(id);timer.fn();}await flush();};
const updates=[],basePath=process.env.AUDIO_TEST_BASE||'';
const context={location:{pathname:basePath+'/'},window:{PlayerCore:core,isSecureContext:true},document,localStorage:{getItem:()=>null,setItem(){}},navigator:{wakeLock:{request:async()=>{wakeRequests++;return{addEventListener(){},release:async()=>{wakeReleases++;}};}}},
  fetch:async(url,options)=>{assert.ok(url.startsWith(basePath+'/api/'),'Player requests stay inside the Audio path');const body=options?.body?JSON.parse(options.body):{};updates.push([url,body]);return{ok:true,json:async()=>({resume:body.seconds||0})};},Event:class{},console,setTimeout:setTimer,clearTimeout:id=>timers.delete(id),queueMicrotask};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../web/player.js'),'utf8'),context);
const flush=async()=>{await new Promise(setImmediate);};
(async()=>{
  const a={id:'a',edition_id:'e',title:'first',duration:10,resume:0,subtitles:[]};
  const b={id:'b',edition_id:'e',title:'last',duration:10,resume:0,subtitles:[]};
  await context.window.StudioPlayer.open([a,b],a);await flush();
  assert.equal(stage.hidden,false);assert.equal(media.src,`${basePath}/api/tracks/a/media`);
  assert.equal(fullscreens,0,'Opening a track must not change the user browser/window to fullscreen');
  assert.equal(media.paused,false);
  media.currentTime=2;const priorUpdates=updates.length;
  context.window.AudioTrackTitle=track=>track.title_ko?track.title_ko+'\n'+track.title:track.title;
  context.window.StudioPlayer.updateTitleMetadata([{...a,title_ko:'수정한 제목',title_translation_kind:'manual'}]);
  assert.equal(get('player-title').textContent,'수정한 제목\nfirst');assert.equal(media.currentTime,2);
  assert.equal(media.paused,false);assert.equal(updates.length,priorUpdates,'Editing a displayed title never reloads media or saves playback progress');
  context.window.StudioPlayer.updateTitleMetadata([a]);context.window.AudioTrackTitle=track=>track.title;
  assert.equal(wakeRequests,1);
  get('caption').textContent='caption stays visible';const captionTop=get('caption').style.top;
  await tick(3000);assert.equal(stage.classList.contains('controls-hidden'),true);
  assert.equal(get('player-header').inert,true);assert.equal(get('caption').hidden,false);
  assert.equal(get('caption').textContent,'caption stays visible');assert.equal(get('caption').style.top,captionTop);
  get('screen-controls').emit('click');assert.equal(stage.classList.contains('controls-hidden'),false);
  get('toggle-play').emit('click');await flush();
  assert.equal(media.paused,true);
  assert.equal(wakeReleases,1);
  await tick(5000);assert.equal(stage.classList.contains('controls-hidden'),false,'Pause keeps controls visible');
  get('fullscreen').emit('click');await flush();
  assert.equal(fullscreens,1,'Only the explicit fullscreen button requests native fullscreen');
  media.currentTime=10;media.paused=true;media.emit('ended');await flush();
  assert.equal(get('player-title').textContent,'last');
  assert.equal(media.currentTime,0,'Next track starts at the beginning');
  media.currentTime=10;media.paused=true;media.emit('ended');await flush();
  assert.equal(get('player-title').textContent,'last');
  assert.match(get('player-status').textContent,/재생 완료/);
  get('close-player').emit('click');await flush();
  assert.equal(stage.hidden,true);
  get('play-mode').value='single';get('play-mode').emit('change');a.resume=7;
  await context.window.StudioPlayer.open([a,b],a,{mode:'all',fromStart:true});await flush();
  assert.equal(get('play-mode').value,'all','Full-play action overrides a saved single-track mode');
  assert.equal(media.currentTime,0,'Full-play action starts the first track at zero');
  assert.equal(fullscreens,1,'Full-play action must not request fullscreen');
  get('player-settings-button').emit('click');await tick(5000);
  assert.equal(stage.classList.contains('controls-hidden'),false,'Settings stay visible');
  get('player-settings-button').emit('click');await tick(3000);assert.equal(stage.classList.contains('controls-hidden'),true);
  get('screen-controls').emit('click');get('seek').focus();get('seek').emit('pointerdown');await tick(5000);
  assert.equal(stage.classList.contains('controls-hidden'),false,'Seeking stays visible');
  document.activeElement=null;get('seek').emit('pointerup');await tick(3000);assert.equal(stage.classList.contains('controls-hidden'),true);
  get('screen-controls').emit('click');for(const fn of documentListeners.keydown)fn({key:'Tab',preventDefault(){}});await tick(5000);
  assert.equal(stage.classList.contains('controls-hidden'),false,'Keyboard controls stay visible');
  get('close-player').emit('click');await flush();
  media.load=()=>{media.ended=false;};
  await context.window.StudioPlayer.open([a,b],a);await flush();get('close-player').emit('click');await flush();
  media.emit('loadedmetadata');await flush();assert.equal(media.paused,true,'Late loading after close must not start playback');
  console.log('Player runtime: auto-hide, tap reveal, stable captions, pause/settings/seek/keyboard visibility, explicit fullscreen and playback lifecycle passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
