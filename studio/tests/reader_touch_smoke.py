"""Isolated Chromium touch/click harness using the real reader markup and handlers.

No NAS, credentials, personal images or external requests. --baseline may name a
read-only checkout to verify its shipped HTML/CSS with the candidate handlers.
Requires installed Playwright/Chromium; physical mobile browsers remain separate.
"""
import argparse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading

from playwright.sync_api import sync_playwright


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--baseline',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    baseline=args.baseline or root
    source=(root/'web/app.js').read_text(encoding='utf-8')
    turn=source[source.index('function turnPage('):source.index('function guard(')]
    original=(baseline/'web/app.js').read_text(encoding='utf-8')
    assert turn==original[original.index('function turnPage('):original.index('function guard(')]
    handlers=source[source.index('$("#reader-prev").onclick'):source.index('document.addEventListener("keydown"')]
    markup=(baseline/'web/index.html').read_text(encoding='utf-8')
    reader=re.search(r'<dialog\b[^>]*\bid="reader"[^>]*>.*?</dialog>',markup,re.S).group()
    css=(baseline/'web/style.css').read_text(encoding='utf-8')
    script='''
const $=selector=>document.querySelector(selector);
const state={reader:{work:{id:'generated'},pages:['1','2','3'],page:1}};
const settings={direction:'ltr'};
let turns=0,maxTouches=0;
document.addEventListener('touchstart',event=>{maxTouches=Math.max(maxTouches,event.touches.length);},{passive:true});
function update(){
    const n=state.reader.page+1;
    $('#reader-position').textContent=n+' / 3';
    $('#reader-title').textContent='Generated touch test';
    $('#reader-prev').disabled=n===1; $('#reader-next').disabled=n===3;
    const svg='<svg xmlns="http://www.w3.org/2000/svg" width="240" height="620"><rect width="240" height="620" fill="#e6e8ed"/><text x="120" y="300" text-anchor="middle" font-size="44">Page '+n+'</text></svg>';
    $('#reader-image').src='data:image/svg+xml,'+encodeURIComponent(svg);
}
function navigateRoute(route){turns++;state.reader.page=route.page-1;location.hash='#/L1/'+route.page;update();}
window.testReader={
    reset:(direction='ltr')=>{settings.direction=direction;state.reader.page=1;turns=0;maxTouches=0;$('#reader').scrollTop=0;update();},
    info:()=>({page:state.reader.page,turns,maxTouches,scale:visualViewport.scale,scroll:$('#reader').scrollTop})
};
''' +turn+handlers+"\n$('#reader').showModal();update();"
    fixture=('<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1">'
             '<meta charset="utf-8"><style>'+css+'</style>'+reader+'<script>'+script+'</script>').encode()
    baseline_fixture=fixture.replace(handlers.encode(),handlers[:handlers.index('const readerSurface =')].encode())
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            data=baseline_fixture if self.path=='/baseline' else fixture
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    args.output.mkdir(parents=True,exist_ok=True)
    try:
        with sync_playwright() as pw:
            installed=Path(pw.chromium.executable_path)
            chrome=Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
            browser=pw.chromium.launch(headless=True,executable_path=str(installed if installed.is_file() else chrome))
            context=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True,device_scale_factor=1)
            context.route('**/*',lambda route:route.continue_() if route.request.url.startswith('http://127.0.0.1:') else route.abort())
            page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto('http://127.0.0.1:'+str(server.server_port))
            page.locator('#reader-image').wait_for()
            cdp=context.new_cdp_session(page)
            cdp.send('Emulation.setTouchEmulationEnabled',{'enabled':True,'maxTouchPoints':5})
            def drag(start,end):
                cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':start[0],'y':start[1],'id':1}]})
                for step in range(1,9):
                    point={'x':start[0]+(end[0]-start[0])*step/8,'y':start[1]+(end[1]-start[1])*step/8,'id':1}
                    cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[point]})
                    page.wait_for_timeout(16)
                cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]});page.wait_for_timeout(100)
            def info():return page.evaluate('testReader.info()')
            def pinch(session):
                def points(spread):return [{'x':195-spread,'y':350,'id':1},{'x':195+spread,'y':350,'id':2}]
                session.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':points(40)})
                for step in range(1,9):
                    session.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':points(40+step*5)})
                    page.wait_for_timeout(16)
                session.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
                page.wait_for_timeout(150)
            results={}
            drag((270,300),(110,300));assert info()['page']==2,info();results['ltr_left_next']=True
            page.mouse.click(60,300)
            assert info()['page']==2 and info()['turns']==1,info();results['swipe_click_single_turn']=True
            drag((110,300),(270,300));assert info()['page']==1,info();results['ltr_right_previous']=True
            page.evaluate("testReader.reset('rtl')")
            drag((270,300),(110,300));assert info()['page']==0,info();results['rtl_left_previous']=True
            drag((110,300),(270,300));assert info()['page']==1,info();results['rtl_right_next']=True
            page.evaluate('testReader.reset()')
            box=page.locator('#reader-next').bounding_box()
            page.touchscreen.tap(box['x']+box['width']/2,box['y']+box['height']/2)
            assert info()['turns']==1 and info()['page']==2,info();results['control_tap_once']=True
            page.evaluate('testReader.reset()')
            page.touchscreen.tap(340,300)
            assert info()['page']==2 and info()['turns']==1,info()
            page.touchscreen.tap(60,300)
            assert info()['page']==1 and info()['turns']==2,info();results['ltr_surface_taps']=True
            page.touchscreen.tap(380,300);assert info()['page']==2,info()
            page.touchscreen.tap(10,300);assert info()['page']==1 and info()['turns']==4,info();results['edge_surface_taps']=True
            page.touchscreen.tap(195,80)
            assert info()['page']==1 and info()['turns']==4,info();results['center_tap_no_turn']=True
            page.touchscreen.tap(195,300)
            assert info()['page']==2 and info()['turns']==5,info();results['image_tap_next']=True
            page.evaluate("testReader.reset('rtl')")
            page.touchscreen.tap(340,300);assert info()['page']==0,info()
            page.touchscreen.tap(60,300);assert info()['page']==1,info();results['rtl_surface_taps']=True
            page.evaluate('testReader.reset()')
            page.mouse.click(340,300);assert info()['page']==2,info()
            page.mouse.click(60,300);assert info()['page']==1,info();results['mouse_surface_clicks']=True
            page.mouse.move(340,300);page.mouse.down();page.mouse.move(300,300,steps=6);page.mouse.up()
            assert info()['page']==1 and info()['turns']==2,info();results['mouse_drag_no_turn']=True
            page.evaluate('testReader.reset()')
            drag((220,600),(200,200));assert info()['page']==1 and info()['scroll']==0,info();results['normal_vertical_drag_no_scroll']=True
            page.mouse.click(340,300)
            assert info()['page']==1 and info()['turns']==0,info();results['scroll_click_no_turn']=True
            page.evaluate('testReader.reset()')
            pinch(cdp)
            current=info();assert current['page']==1 and current['maxTouches']==2,current
            baseline_page=context.new_page();baseline_page.goto('http://127.0.0.1:'+str(server.server_port)+'/baseline')
            baseline_cdp=context.new_cdp_session(baseline_page)
            baseline_cdp.send('Emulation.setTouchEmulationEnabled',{'enabled':True,'maxTouchPoints':5})
            pinch(baseline_cdp)
            baseline_scale=baseline_page.evaluate('testReader.info().scale');baseline_page.close()
            assert current['scale']>=baseline_scale-.05,(current,baseline_scale)
            results.update({'native_two_finger_no_turn':True,'candidate_pinch_scale':current['scale'],
                            'baseline_pinch_scale':baseline_scale,'native_zoom_observed':current['scale']>1.1})
            cdp.send('Emulation.setPageScaleFactor',{'pageScaleFactor':1.6})
            drag((250,350),(100,350));assert info()['page']==1 and info()['scale']>1.1,info()
            results['emulated_zoom_pan_no_turn']=True
            assert not errors,errors
            cdp.send('Emulation.setPageScaleFactor',{'pageScaleFactor':1})
            page.evaluate('testReader.reset()')
            page.screenshot(path=str(args.output/'reader-touch-chromium.png'))
            results.update({'engine':'Chromium','input':'CDP trusted touch input and Playwright mouse','baseline':str(baseline),'physical_device_verified':False,'site_requests':0})
            (args.output/'reader-touch-results.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8')
            print(json.dumps(results));browser.close()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)


if __name__=='__main__':main()
