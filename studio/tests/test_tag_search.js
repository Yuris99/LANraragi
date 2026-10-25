// Synthetic tags only. Exercise the actual search handlers without a browser or network.
const fs = require('fs'), vm = require('vm'), assert = require('assert/strict');
const source = fs.readFileSync('studio/web/app.js', 'utf8');
const nodes = new Map();
function node(selector) {
    if (!nodes.has(selector)) nodes.set(selector, {
        value: '', hidden: false, innerHTML: '', attrs: {}, handlers: {},
        setAttribute(key, value) { this.attrs[key] = value; },
        removeAttribute(key) { delete this.attrs[key]; },
        addEventListener(key, handler) { this.handlers[key] = handler; }
    });
    return nodes.get(selector);
}
let options = [], pendingTags, navigations = 0;
const context = {
    $: node, state: {}, esc: value => String(value),
    api: async () => pendingTags ? await pendingTags : [
        { tag: 'female:sample', count: 3 }, { tag: 'male:sample', count: 2 }, { tag: 'saved', count: 1 }
    ],
    guard: handler => handler, navigateLibrary: async () => { navigations++; },
    load: async () => {}, setTimeout: () => 1, clearTimeout: () => {},
    document: { activeElement: node('#search'), querySelectorAll: () => options }
};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('const tagKinds ='), source.indexOf('async function refreshLibraryStatus()')), context);
vm.runInContext(source.slice(source.indexOf('let suggestionRequest ='), source.indexOf("document.addEventListener('input'")), context);
const event = key => ({ key, preventDefault() {} });
const option = { dataset: { suggestTag: 'male:sample' }, getAttribute: () => 'true' };
(async () => {
    assert.deepEqual(Array.from(await context.matchingTags({ kind: 'male', term: 'sample' }), t => t.tag), ['male:sample']);
    node('#search').value = 'male:sample';
    await context.refreshSuggestions('male:sample');
    options = [option];
    // A changed query must never select a candidate left from the previous query.
    node('#search').value = 'female:other';
    node('#search').oninput();
    await node('#search').handlers.keydown(event('Enter'));
    assert.equal(navigations, 0, 'changed query selected an old suggestion');
    // Escape/blur must also prevent a hidden candidate from being applied.
    node('#search-suggestions').hidden = true;
    await node('#search').handlers.keydown(event('Enter'));
    assert.equal(navigations, 0, 'hidden suggestion was selected');
    // A delayed response must not reopen a dismissed suggestion list.
    let resolveTags;
    pendingTags = new Promise(resolve => { resolveTags = resolve; });
    const request = context.refreshSuggestions('female:other');
    context.hideSuggestions();
    resolveTags([{ tag: 'female:other', count: 1 }]);
    await request;
    assert.equal(node('#search-suggestions').hidden, true);
    // A current, visible candidate remains selectable.
    pendingTags = null;
    node('#search').value = 'male:sample';
    await context.refreshSuggestions('male:sample');
    await node('#search').handlers.keydown(event('Enter'));
    assert.equal(navigations, 1);
    assert.equal(context.state.allTag, 'male:sample');
    console.log('Tag search: exact namespace, stale/hidden suggestions, delayed dismissal and current selection passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
