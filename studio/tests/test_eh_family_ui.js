// Exercise the shipped renderers with two real-origin aliases of one family.
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const source=fs.readFileSync('studio/web/app.js','utf8');
const context=vm.createContext({URL,settings:{tagLanguage:'en'}});
const helpers=source.slice(source.indexOf('const providerName ='),source.indexOf('const visibleTag ='));
const esc=source.slice(source.indexOf('const esc ='),source.indexOf('\n',source.indexOf('const esc =')));
const badges=source.slice(source.indexOf('function sources(work)'),source.indexOf('function workCoverURL'));
const rows=source.slice(source.indexOf('function sourceRows('),source.indexOf('function renderDetail('));
const tagHelpers=source.slice(source.indexOf('const tagKinds ='),source.indexOf('function drawTagExplanation('));
vm.runInContext(helpers+'\n'+esc+'\nconst visibleTag=()=>true;\n'+tagHelpers+'\n'+badges+'\n'+rows+'\nglobalThis.render={sources,sourceRows,sourceShortcut};',context);
const comment={id:'generated-1',author:'Generated author',posted_at:'generated',text:'Keep comment'};
const a={id:'a'.repeat(32),provider:'ehentai',external_id:'123',url:'https://e-hentai.org/g/123/abc/',tags:['artist:generated','language:korean'],comments:[comment],status:'manual',metadata:{}};
const b={...a,id:'b'.repeat(32),provider:'exhentai',url:'https://exhentai.org/g/123/abc/',tags:['artist:generated','tag:extra']};
const badge=context.render.sources({sources:[a,b]});
assert.equal((badge.match(/source-pill/g)||[]).length,1);
const html=context.render.sourceRows([a,b]);
assert.equal((html.match(/class="source-row"/g)||[]).length,1);
assert.ok(html.includes(a.url)&&html.includes(b.url));
assert.ok(html.includes('data-fetch="'+a.id+'"')&&html.includes('data-fetch="'+b.id+'"'));
assert.equal((html.match(/Keep comment/g)||[]).length,1);
assert.equal((html.match(/data-tag-label="artist:generated"/g)||[]).length,1);
assert.ok(html.includes('tag:extra'));
assert.equal(JSON.stringify(a.comments),JSON.stringify([comment]));
assert.ok(badge.includes('href="'+a.url+'"')&&badge.includes('href="'+b.url+'"'));
assert.ok(badge.includes('#i-ehentai')&&badge.includes('#i-exhentai'));
for(const url of ['javascript:alert(1)','https://example.com/g/123/','https://e-hentai.org@example.com/','https://e-hentai.org:444/']) {
    assert.ok(!context.render.sourceShortcut({...a,url}).includes('href='));
}
console.log('EH family UI: one badge and source group, original URLs/actions preserved, tags/comments deduplicated for display');
