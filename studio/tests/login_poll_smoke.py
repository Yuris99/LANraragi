"""Generated preview: direct keyboard, IME, touch, wheel and slow polling."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re
import threading

from playwright.sync_api import sync_playwright


def main():
    root = Path(__file__).resolve().parents[1]
    source = (root / 'web/app.js').read_text(encoding='utf-8')
    markup = (root / 'web/index.html').read_text(encoding='utf-8')
    dialog = re.search(r'<dialog\b[^>]*\bid="connections-dialog"[^>]*>.*?</dialog>', markup, re.S).group()
    script = '''
const $ = selector => document.querySelector(selector);
const state = {};
const esc = value => String(value);
const guard = fn => (...args) => Promise.resolve(fn(...args)).catch(error => { throw error; });
const toast = () => {};
let releaseFrame = null;
const fixture = {calls: [], hold: false, frameDelay:0, frameTimes:[], release: () => releaseFrame({})};
const frame = {session:'generated-window', image:'data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="700"><rect width="1000" height="700" fill="white"/></svg>'),location:'Generated page',browser_mode:'desktop'};
async function api(url, data) {
    fixture.calls.push(data);
    if (data.op === 'frame') {
        fixture.frameTimes.push(performance.now());
        if (fixture.hold) await new Promise(resolve => { releaseFrame = resolve; });
        if (fixture.frameDelay) await new Promise(resolve => setTimeout(resolve,fixture.frameDelay));
        return frame;
    }
    return {accepted:true};
}
''' + source[source.index('const providerName ='):source.index('const visibleTag =')] + source[source.index('// Credentials travel only'):]
    script += "\n$('#connections-dialog').showModal();renderLoginFrame(frame);"
    document = ('<!doctype html><meta charset="utf-8"><style>' +
                (root / 'web/style.css').read_text(encoding='utf-8') + '</style>' +
                '<button id="connections-open">Generated open</button>' + dialog +
                '<script>' + script + '</script>').encode()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(document)))
            self.end_headers()
            self.wfile.write(document)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.environ.get('STUDIO_TEST_CHROMIUM', '/usr/bin/chromium'), headless=True, args=['--no-sandbox'])
            page = browser.new_page(viewport={'width':1200, 'height':1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto('http://127.0.0.1:' + str(server.server_port))
            page.locator('#login-text-tools summary').click()
            text = page.locator('#login-text')
            text.fill('generated-')
            text.focus()
            page.evaluate("fixture.hold=true;void loginOperation({op:'frame'});")
            assert text.is_enabled(), 'Automatic polling must leave the input enabled'
            assert text.evaluate('el => el === document.activeElement'), 'Polling must preserve focus'
            page.keyboard.type('value')
            assert text.input_value() == 'generated-value'
            page.evaluate('fixture.hold=false;fixture.release()')
            page.wait_for_function('() => !loginBusy')
            assert text.evaluate('el => el === document.activeElement')
            assert text.input_value() == 'generated-value'
            # Submit while another slow frame is in flight: send exactly once afterwards.
            page.evaluate("fixture.hold=true;void loginOperation({op:'frame'});")
            page.locator('#login-text-form button').click()
            assert page.evaluate("fixture.calls.filter(call => call.op === 'text').length") == 0
            page.evaluate('fixture.hold=false;fixture.release()')
            page.wait_for_function("() => fixture.calls.some(call => call.op === 'text')")
            sent = page.evaluate("fixture.calls.filter(call => call.op === 'text')")
            assert len(sent) == 1 and sent[0]['text'] == 'generated-value'
            assert text.input_value() == ''
            page.locator('#login-text-tools summary').click()
            screen = page.locator('#login-screen')
            screen.click(position={'x':80,'y':80})
            page.wait_for_function('() => !loginInputDraining')
            direct = page.locator('#login-direct-input')
            assert direct.evaluate('el => el === document.activeElement')
            # Poll remains deliberately slow while the user types a burst.
            page.evaluate("fixture.calls=[];fixture.hold=true;void loginOperation({op:'frame'});")
            page.keyboard.type('ab')
            page.keyboard.press('Backspace')
            page.keyboard.type('c')
            assert direct.evaluate('el => el === document.activeElement')
            page.evaluate('fixture.hold=false;fixture.release()')
            page.wait_for_function('() => !loginInputDraining')
            calls = page.evaluate("fixture.calls.filter(call => call.op !== 'frame')")
            assert ''.join(c.get('text','') for c in calls[:2]) == 'ab', calls
            assert [c['key'] for c in calls if c['op']=='key'] == ['Backspace'], calls
            assert calls[-1]['text'] == 'c', calls
            assert direct.input_value() == ''
            page.evaluate('fixture.calls=[]')
            page.keyboard.press('Control+a')
            page.keyboard.press('Shift+Tab')
            page.keyboard.insert_text('generated-paste')
            page.keyboard.press('Enter')
            page.wait_for_function('() => !loginInputDraining')
            calls = page.evaluate("fixture.calls.filter(call => call.op !== 'frame')")
            assert [c.get('key') or c.get('text') for c in calls] == ['Control+A','Shift+Tab','generated-paste','Enter'], calls
            assert direct.input_value() == ''
            page.evaluate('fixture.calls=[]')
            direct.evaluate('''el => {
                el.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}));
                el.value='ㅎ';el.dispatchEvent(new InputEvent('input',{bubbles:true,isComposing:true}));
            }''')
            assert not page.evaluate("fixture.calls.some(call => call.op === 'text')")
            direct.evaluate('''el => {
                el.value='한글';el.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true,data:'한글'}));
                el.dispatchEvent(new InputEvent('input',{bubbles:true,isComposing:false}));
            }''')
            page.wait_for_function('() => !loginInputDraining')
            assert page.evaluate("fixture.calls.filter(call => call.op === 'text').map(call => call.text)") == ['한글']
            direct.evaluate("el => el.dispatchEvent(new InputEvent('beforeinput',{bubbles:true,cancelable:true,inputType:'deleteContentBackward'}))")
            page.wait_for_function('() => !loginInputDraining')
            assert page.evaluate("fixture.calls.filter(call => call.op === 'key').at(-1).key") == 'Backspace'
            page.keyboard.press('Escape')
            assert page.locator('#login-keyboard').evaluate('el => el === document.activeElement'), 'Esc must leave remote keyboard capture'
            page.wait_for_function('() => !loginInputDraining')
            page.evaluate('fixture.calls=[]')
            screen.hover()
            page.mouse.wheel(0,400)
            page.wait_for_function("() => fixture.calls.some(call => call.op === 'scroll')")
            assert page.evaluate("fixture.calls.find(call => call.op === 'scroll').delta") == 400
            output = root.parent/'work/login-direct-input'
            output.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(output/'desktop.png'))
            page.set_viewport_size({'width':390,'height':844})
            screen.scroll_into_view_if_needed()
            page.wait_for_function('() => !loginInputDraining')
            page.evaluate('fixture.calls=[]')
            box=screen.bounding_box();x=box['x']+box['width']/2;y=box['y']+box['height']/2
            cdp=page.context.new_cdp_session(page)
            cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y}]})
            cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':x,'y':y-65}]})
            cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
            page.wait_for_function("() => fixture.calls.some(call => call.op === 'scroll')")
            page.wait_for_function('() => !loginInputDraining')
            calls=page.evaluate("fixture.calls.filter(call => call.op !== 'frame')")
            assert len(calls)==1 and calls[0]['op']=='scroll' and calls[0]['delta']>0, calls
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert page.locator('#connections-dialog').evaluate('el=>el.scrollWidth<=el.clientWidth+1')
            page.screenshot(path=str(output/'mobile.png'))
            # The measured NAS preview takes ~140ms: active interaction must not
            # add another 1.5 seconds between every returned frame.
            page.evaluate("fixture.frameDelay=140;fixture.frameTimes=[];sendLoginInput({op:'key',key:'Tab'});")
            page.wait_for_function('() => fixture.frameTimes.length >= 4', timeout=2000)
            intervals=page.evaluate('fixture.frameTimes.slice(1).map((t,i)=>t-fixture.frameTimes[i])')
            assert max(intervals)<550, intervals
            print('ACTIVE_PREVIEW_INTERVAL_MS='+str(round(max(intervals))))
            page.evaluate("frame.save_error=true;frame.save_error_kind='no_account_cookies';")
            page.evaluate("() => loginOperation({op:'frame'})")
            error=page.locator('#connections-status').inner_text()
            assert '\uc800\uc7a5\ud558\uc9c0 \ubabb' in error,error
            page.evaluate("frame.save_error=false;frame.save_error_kind=null;")
            page.evaluate("() => loginOperation({op:'frame'})")
            assert page.locator('#connections-status').inner_text()==error,'A later preview must not erase the save failure'
            assert not errors, errors
            browser.close()
        print('LOGIN_DIRECT=PASS slow_poll_focus=true ordered_typing=true paste=true ime_once=true keys=true wheel=true trusted_touch_scroll=true escape_releases=true desktop_mobile=true')
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


if __name__ == '__main__':
    main()
