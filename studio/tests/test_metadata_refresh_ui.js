const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');
const helpers=source.slice(source.indexOf('const providerName ='),source.indexOf('const visibleTag ='));
const code=source.slice(source.indexOf('let metadataRefreshRunning'),source.indexOf('const workShortIds'));
const ref=(provider,id)=>({provider,id,url:`https://${provider}.generated/g/${id}/`});
const work=(id,sources=[],lrr_id=null)=>({id,short_id:'L'+id,sources,lrr_id});
function setup(request) {
    const elements=new Map(),calls=[];
    const context=vm.createContext({api:async(path,data)=>{calls.push({path,data});return request(path,data,context);},
        load:async()=>{},setTimeout:callback=>callback(),$:selector=>{
            if (!elements.has(selector)) elements.set(selector,{textContent:'',disabled:false,hidden:true});
            return elements.get(selector);
        }});
    vm.runInContext(helpers+'\n'+code+'\nglobalThis.run=refreshLinkedMetadata;',context);
    return {context,calls,elements,note:()=>elements.get('#metadata-refresh-status').textContent};
}
async function main() {
    const a=work('a',[ref('ehentai','1'),ref('ehentai','1'),ref('exhentai','2')]);
    const b=work('b',[ref('hitomi','3')]),c=work('c',[],'generated-archive');
    const data=[a,b,c,...Array.from({length:119},(_,i)=>work('missing'+i))];
    const first=setup(async(path,body)=>{
        if (!body) return {total:data.length,items:path.endsWith('page=1')?data.slice(0,120):data.slice(120)};
        if (path.endsWith('/restore-source')) return {restored:true,record:{evidence:[]},work:{...c,sources:[ref('ehentai','4')]}};
        assert.equal(body.defer_automatic,true);return {};
    });
    await first.context.run();
    assert.equal(first.calls.filter(c=>c.path.endsWith('/fetch')).length,4);
    assert.match(first.note(),/원본 복원 1개/);assert.match(first.note(),/갱신 4건/);
    assert.equal(first.elements.get('#refresh-metadata').disabled,false);
    const denial=setup(async(path,body)=>{
        if (!body) return {total:2,items:[a,b]};
        if (path.includes('/sources/1/')) throw new Error('Access required');return {};
    });
    await denial.context.run();
    assert.equal(denial.calls.filter(c=>c.path.endsWith('/fetch')).length,2);
    assert.match(denial.note(),/실패 1건/);assert.match(denial.note(),/보류 1건/);
    const stop=setup(async(path,body,ctx)=>{
        if (!body) return {total:2,items:[a,b]};
        vm.runInContext('metadataRefreshStop=true',ctx);return {};
    });
    await stop.context.run();assert.match(stop.note(),/^중지/);
    assert.equal(stop.calls.filter(c=>c.path.endsWith('/fetch')).length,1);
    const preflight=setup(async(path,body,ctx)=>{
        if (!body) return {total:1,items:[c]};
        vm.runInContext('metadataRefreshStop=true',ctx);
        return {restored:true,record:{evidence:[]},work:{...c,sources:[ref('ehentai','4')]}};
    });
    await preflight.context.run();assert.match(preflight.note(),/원본 출처 1개 복원/);
    assert.equal(preflight.calls.filter(c=>c.path.endsWith('/fetch')).length,0);
    let release;
    const gate=new Promise(resolve=>{release=resolve;});
    const concurrent=setup(async(path,body)=>body?{}:await gate);
    const pending=concurrent.context.run();await concurrent.context.run();
    assert.equal(concurrent.calls.length,1);release({total:1,items:[b]});await pending;
    console.log('METADATA_REFRESH_UI=PASS pagination=true original_record_restore=true deduplication=true site_error_stop=true cancel=true one_active_run=true');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
