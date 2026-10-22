// Run the real player module against a small simulated DOM, with no browser/window actions.
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const core = require('../web/player-core.js');
class Element {
  constructor(id='') { Object.assign(this,{id,hidden:false,value:'',type:'',textContent:'',style:{},children:[],listeners:{},className:'',disabled:false}); this.classList={add(){},remove(){},toggle(){return true;}}; }
  addEventListener(name,fn) { (this.listeners[name] ||= []).push(fn); }
  emit(name) { for(const fn of this.listeners[name] || []) fn({key:'',preventDefault(){}}); }
  append(node) { this.children.push(node); }
  replaceChildren() { this.children=[]; }
  setAttribute(name,value) { this[name]=value; }
  focus() {}
  querySelectorAll() { return []; }
}
const nodes = new Map();
const get = id => { if(!nodes.has(id)) nodes.set(id,new Element(id));return nodes.get(id); };
const stage=get('cinema');stage.hidden=true;
let fullscreens=0,wakeRequests=0,wakeReleases=0;
stage.requestFullscreen=async()=>{fullscreens++;};
const media=get('media');
Object.assign(media,{paused:true,readyState:1,currentTime:0,duration:10,playbackRate:1});
media.load=()=>queueMicrotask(()=>media.emit('loadedmetadata'));
media.pause=()=>{media.paused=true;media.emit('pause');};
media.play=async()=>{media.paused=false;media.emit('play');};
const document={getElementById:get,createElement:()=>new Element(),querySelectorAll:()=>[],visibilityState:'visible',body:new Element(),addEventListener(){},dispatchEvent(){},exitFullscreen:async()=>{}};
const updates=[];
const context={window:{PlayerCore:core,isSecureContext:true},document,localStorage:{getItem:()=>null,setItem(){}},navigator:{wakeLock:{request:async()=>{wakeRequests++;return{addEventListener(){},release:async()=>{wakeReleases++;}};}}},
  fetch:async(url,options)=>{const body=options?.body?JSON.parse(options.body):{};updates.push([url,body]);return{ok:true,json:async()=>({resume:body.seconds||0})};},Event:class{},console};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../web/player.js'),'utf8'),context);
const flush=async()=>{await new Promise(setImmediate);};
(async()=>{
  const a={id:'a',edition_id:'e',title:'first',duration:10,resume:0,subtitles:[]};
  const b={id:'b',edition_id:'e',title:'last',duration:10,resume:0,subtitles:[]};
  await context.window.StudioPlayer.open([a,b],a);await flush();
  assert.equal(stage.hidden,false);
  assert.equal(fullscreens,0,'Opening a track must not change the user browser/window to fullscreen');
  assert.equal(media.paused,false);
  assert.equal(wakeRequests,1);
  get('toggle-play').emit('click');await flush();
  assert.equal(media.paused,true);
  assert.equal(wakeReleases,1);
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
  get('close-player').emit('click');await flush();
  console.log('Player runtime: explicit-only fullscreen, pause/wake release, next-track reset, final stop and full-play options passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
