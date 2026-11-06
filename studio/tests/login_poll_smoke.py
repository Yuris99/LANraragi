"""Generated login preview: slow polling preserves typing and queues input."""
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
const esc = value => String(value);
const guard = fn => (...args) => Promise.resolve(fn(...args)).catch(error => { throw error; });
const toast = () => {};
let releaseFrame = null;
const fixture = {calls: [], hold: false, release: () => releaseFrame({})};
const frame = {session:'generated-window', image:'data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="700"><rect width="1000" height="700" fill="white"/></svg>'),location:'Generated page',browser_mode:'desktop'};
async function api(url, data) {
    fixture.calls.push(data);
    if (data.op === 'frame') {
        if (fixture.hold) await new Promise(resolve => { releaseFrame = resolve; });
        return frame;
    }
    return {accepted:true};
}
''' + source[source.index('// Credentials travel only'):]
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
            text = page.locator('#login-text')
            text.fill('generated-')
            text.focus()
            page.evaluate("fixture.hold=true;void loginOperation({op:'frame'});")
            assert text.is_enabled(), 'Automatic polling must leave the input enabled'
            assert text.evaluate('el => el === document.activeElement'), 'Polling must preserve focus'
            page.keyboard.type('value')
            assert text.input_value() == 'generated-value'
            page.evaluate('fixture.release()')
            page.wait_for_function('() => !loginBusy')
            assert text.evaluate('el => el === document.activeElement')
            assert text.input_value() == 'generated-value'
            # Submit while another slow frame is in flight: send exactly once afterwards.
            page.evaluate("void loginOperation({op:'frame'});")
            page.locator('#login-text-form button').click()
            assert page.evaluate("fixture.calls.filter(call => call.op === 'text').length") == 0
            page.evaluate('fixture.release()')
            page.wait_for_function("() => fixture.calls.some(call => call.op === 'text')")
            sent = page.evaluate("fixture.calls.filter(call => call.op === 'text')")
            assert len(sent) == 1 and sent[0]['text'] == 'generated-value'
            assert text.input_value() == ''
            assert not errors, errors
            browser.close()
        print('LOGIN_POLL=PASS focus_and_draft_preserved=true input_during_poll_sent_once=true')
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


if __name__ == '__main__':
    main()
