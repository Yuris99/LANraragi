// Generated reader input only. Exercise the shipped navigation and input handlers.
const fs = require('fs'), vm = require('vm'), assert = require('assert/strict');
const source = fs.readFileSync('studio/web/app.js', 'utf8');
const turn = source.slice(source.indexOf('function turnPage('), source.indexOf('function guard('));
const handlers = source.slice(source.indexOf('const readerSurface ='), source.indexOf('document.addEventListener("keydown"'));

function fixture() {
    const listeners = {}, options = {}, routes = [];
    let now = 1000;
    const surface = { clientWidth: 390, scrollWidth: 390, contains: target => target === 'page', getBoundingClientRect: () => ({ left: 0, width: 390 }) };
    const reader = { open: true, scrollTop: 0 };
    const state = { reader: { work: { id: 'generated' }, pages: ['1', '2', '3'], page: 1 } };
    const settings = { direction: 'ltr' }, window = { innerWidth: 390, visualViewport: { scale: 1 } };
    const context = { $: selector => selector === '#reader' ? reader : surface, state, settings, window, Date: { now: () => now },
        document: { addEventListener: (name, handler, value) => { listeners[name] = handler; options[name] = value; } },
        navigateRoute: route => { routes.push(route); state.reader.page = route.page - 1; } };
    vm.runInNewContext(turn + '\n' + handlers, context);
    const point = (x = 240, y = 300, id = 1) => ({ identifier: id, clientX: x, clientY: y });
    const start = (x = 240, y = 300, target = 'page', touches) => listeners.touchstart({ target, touches: touches || [point(x, y)] });
    const end = (x = 120, y = 300, touches = [], id = 1) => listeners.touchend({ target: 'page', touches, changedTouches: [point(x, y, id)] });
    const mouseEvent = (x, extra = {}) => ({ target: 'page', button: 0, clientX: x, clientY: 300, detail: 1, ...extra });
    const click = (x, extra = {}) => { listeners.mousedown(mouseEvent(x, extra)); listeners.click(mouseEvent(x, extra)); };
    return { listeners, options, routes, surface, reader, state, settings, window, point, start, end, click, mouseEvent, advance: () => { now += 600; } };
}

let f = fixture(); f.start(); f.end(); assert.equal(f.state.reader.page, 2);
assert.deepEqual(JSON.parse(JSON.stringify(f.routes[0])), { kind: 'reader', id: 'generated', page: 3 });
f.start(120); f.end(240); assert.equal(f.state.reader.page, 1);
f.settings.direction = 'rtl'; f.start(); f.end(); assert.equal(f.state.reader.page, 0);
f.start(120); f.end(240); assert.equal(f.state.reader.page, 1);
for (const name of ['touchstart', 'touchend', 'touchcancel']) assert.equal(f.options[name].passive, true);

for (const [dx, dy] of [[-20, -200], [-80, -100], [-47, 0], [10, 0]]) {
    f = fixture(); f.start(); f.end(240 + dx, 300 + dy); assert.equal(f.routes.length, 0);
}
for (const target of ['button', 'page-number', 'toolbar', 'outside']) {
    f = fixture(); f.start(240, 300, target); f.end(); assert.equal(f.routes.length, 0);
    f.click(340, { target }); assert.equal(f.routes.length, 0);
}
for (const x of [0, 23, 367, 389]) { f = fixture(); f.start(x); f.end(180); assert.equal(f.routes.length, 0); }
f = fixture(); f.start(); f.start(240, 300, 'outside', [f.point(), f.point(100, 300, 2)]); f.end(); f.click(340); assert.equal(f.routes.length, 0);
f = fixture(); f.start(); f.end(120, 300, [f.point(100, 300, 2)]); f.end(); assert.equal(f.routes.length, 0);
f = fixture(); f.start(); f.listeners.touchcancel(); f.end(); f.click(340); assert.equal(f.routes.length, 0);
f = fixture(); f.start(); f.end(120, 300, [], 2); assert.equal(f.routes.length, 0);
f = fixture(); f.window.visualViewport.scale = 2; f.start(); f.end(); f.click(340); assert.equal(f.routes.length, 0);
f = fixture(); f.start(); f.window.visualViewport.scale = 2; f.end(); assert.equal(f.routes.length, 0);
f = fixture(); f.surface.scrollWidth = 600; f.start(); f.end(); f.click(340); assert.equal(f.routes.length, 0);
f = fixture(); f.reader.open = false; f.start(); f.end(); f.click(340); assert.equal(f.routes.length, 0);
f = fixture(); f.start(); f.reader.open = false; f.end(); assert.equal(f.routes.length, 0);
f = fixture(); f.start(); f.state.reader = { ...f.state.reader }; f.end(); assert.equal(f.routes.length, 0);
f = fixture(); f.start(); f.state.reader.page = 0; f.end(); assert.equal(f.routes.length, 0);
f = fixture(); f.state.reader.page = 0; f.start(120); f.end(240); assert.equal(f.routes.length, 0);
f = fixture(); f.state.reader.page = 2; f.start(); f.end(); assert.equal(f.routes.length, 0);
f = fixture(); f.start(); f.end(); f.end(); f.click(340); assert.equal(f.routes.length, 1, 'One swipe must not also produce a click turn');

f = fixture(); f.click(340); assert.equal(f.state.reader.page, 2); f.click(40); assert.equal(f.state.reader.page, 1);
f.settings.direction = 'rtl'; f.click(340); assert.equal(f.state.reader.page, 0); f.click(40); assert.equal(f.state.reader.page, 1);
f = fixture(); f.click(195); assert.equal(f.routes.length, 0, 'Center stays available for native zoom');
for (const extra of [{ button: 1 }, { button: 2 }, { detail: 2 }, { defaultPrevented: true }]) {
    f = fixture(); f.click(340, extra); assert.equal(f.routes.length, 0);
}
f = fixture(); f.listeners.mousedown(f.mouseEvent(340)); f.listeners.click(f.mouseEvent(300)); assert.equal(f.routes.length, 0);
f = fixture(); f.listeners.mousedown(f.mouseEvent(340)); f.listeners.dragstart(); f.listeners.click(f.mouseEvent(340)); assert.equal(f.routes.length, 0);
f = fixture(); f.listeners.mousedown(f.mouseEvent(340)); f.reader.scrollTop = 100; f.listeners.click(f.mouseEvent(340)); assert.equal(f.routes.length, 0);
f = fixture(); f.listeners.mousedown(f.mouseEvent(340)); f.state.reader = { ...f.state.reader }; f.listeners.click(f.mouseEvent(340)); assert.equal(f.routes.length, 0);
f = fixture(); f.start(); f.end(230, 100); f.click(340); assert.equal(f.routes.length, 0, 'A vertical scroll must not become a click'); f.advance(); f.click(340); assert.equal(f.routes.length, 1);
f = fixture(); f.start(340); f.end(340); f.click(340); assert.equal(f.routes.length, 1, 'Native touch compatibility click turns exactly once');
f = fixture(); f.start(380); f.end(380); f.click(380); assert.equal(f.state.reader.page, 2, 'An edge tap is allowed while edge swipes remain native');
f.start(10); f.end(10); f.click(10); assert.equal(f.state.reader.page, 1);
f = fixture(); f.state.reader.page = 0; f.click(40); f.state.reader.page = 2; f.click(340); assert.equal(f.routes.length, 0);
console.log('Reader input: LTR/RTL swipe/tap/click, bounds, scrolling, zoom, drag, cancellation, stale gestures and duplicate-click guards passed');
