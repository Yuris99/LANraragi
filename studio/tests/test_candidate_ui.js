// Generated metadata only. Run from the repository root, or pipe this file to node.
const fs = require('fs'), vm = require('vm'), assert = require('assert/strict');
const source = fs.readFileSync('studio/web/app.js', 'utf8');
const escapeLine = source.split('\n').find(line => line.startsWith('const esc ='));
const render = source.slice(source.indexOf('function counterpartRows('), source.indexOf('// Modal dialogs'));
const context = { URL, providerName: { hitomi: 'Hitomi' } };
vm.createContext(context);
vm.runInContext(escapeLine + '\n' + render + '\nthis.renderCandidates=counterpartRows;', context);
const work = { sources: [{ metadata: { languages: ['korean'], pages: 32 } }] };
const candidate = (languages, languageMatch, url='https://hitomi.la/galleries/123456.html') => ({
    display_title: 'Title',
    metadata: { provider: 'hitomi', external_id: '123456', title: '[Author] Title (123456)', languages, pages: 34, url },
    comparison: { language_match: languageMatch, title_similarity: .54, artist_match: true, page_match: false, tag_similarity: .4 }
});
const html = context.renderCandidates([candidate(['japanese'],false), candidate(['korean'],true)],work);
assert(html.includes('기준 언어: 한국어'));
assert(html.includes('href="https://hitomi.la/galleries/123456.html" target="_blank" rel="noopener noreferrer"'));
assert(html.includes('언어 다름 · 별도 판본'));
assert(html.includes('페이지 다름 (32 / 34)'));
assert(html.includes('data-counterpart-select="0" disabled'));
assert(html.includes('data-counterpart-select="1" >'));
assert(html.indexOf('data-counterpart-select="1"') < html.indexOf('<details>'));
assert(!html.includes('[Author]') && !html.includes('Hitomi #123456'));
const unknown = context.renderCandidates([candidate([],false)],work);
assert(unknown.includes('언어 미확인') && unknown.includes('같은 언어의 후보를 아직 확인하지 못했습니다.'));
for (const url of ['javascript:alert(1)','https://attacker.example/','https://user:secret@hitomi.la/galleries/1.html']) {
    const bad = context.renderCandidates([candidate(['korean'],true,url)],work);
    assert(!bad.includes('href='));
    assert(bad.includes('data-counterpart-select="0" disabled'));
}
const escaped = candidate(['korean'],true); escaped.display_title='<img onerror=alert(1)>';
assert(!context.renderCandidates([escaped],work).includes('<img'));
console.log('Candidate UI: links, language groups, safe titles, selection indexes and unsafe URLs passed');
