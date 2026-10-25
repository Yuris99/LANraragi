// Synthetic responses only; no site, session or browser requests.
const fs = require('fs'), vm = require('vm'), assert = require('assert/strict');
const source = fs.readFileSync('studio/web/app.js', 'utf8');
const apiSource = source.slice(source.indexOf('async function api('),source.indexOf('const workShortIds'));
const noteSource = source.slice(source.indexOf('function sessionRequestNote('),source.indexOf("$('#session-import-form').onsubmit"));
let response, requests = 0;
const context = {fetch:async () => {requests++;return response;}};
vm.createContext(context);
vm.runInContext(apiSource+'\n'+noteSource+'\nthis.callApi=api;this.note=sessionRequestNote;',context);

(async () => {
    const expected={items:[{id:'generated'}]};
    response={ok:true,status:200,json:async()=>expected};
    assert.equal(await context.callApi('/generated'),expected);
    response={ok:false,status:502,json:async()=>({error:'외부 서버 연결 오류 (HTTP 503)'})};
    await assert.rejects(context.callApi('/generated'),/외부 서버 연결 오류 \(HTTP 503\)/);
    for (const status of [200,403,502]) {
        response={ok:status===200,status,json:async()=>{throw new SyntaxError('private HTML cookie');}};
        const before=requests;
        await assert.rejects(context.callApi('/generated'),error=>{
            assert(error.message.includes(`HTTP ${status}`));
            assert(error.message.includes('Studio 서버'));
            assert(!error.message.includes('private'));
            return true;
        });
        assert.equal(requests,before+1,'Do not retry an ambiguous response');
    }
    const aborted=Object.assign(new Error('cancelled'),{name:'AbortError'});
    response={ok:true,status:200,json:async()=>{throw aborted;}};
    await assert.rejects(context.callApi('/generated'),error=>error===aborted);
    const old={mode:'saved_session',status:'unavailable',http_status:null};
    assert(context.note(old).includes('네트워크·서버 연결 실패'));
    assert(context.note({...old,error_kind:'connection_reset'}).includes('연결 초기화'));
    assert(!context.note({...old,error_kind:'private exception and cookie'}).includes('private'));
    assert(!context.note({...old,error_kind:'__proto__'}).includes('[object Object]'));
    assert(context.note({...old,status:'ok',http_status:200}).includes('로그인 유효성 미확인'));
    assert(context.note({...old,http_status:503}).includes('HTTP 503'));
    console.log('API errors: JSON success/error, non-JSON HTTP status, no retry/leaks, abort and safe request notes passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
