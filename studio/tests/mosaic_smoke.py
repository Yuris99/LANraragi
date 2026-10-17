"""Synthetic-only browser checks for blur, reveal and uncropped cover ratios."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import Studio,make_server
from store import Store
from playwright.sync_api import sync_playwright


def main():
    fixtures={}
    for letter,dimensions in zip('abc',[(320,480),(640,240),(180,720)]):
        picture=Image.new('RGB',dimensions,(90,120,180));draw=ImageDraw.Draw(picture);w,h=dimensions
        draw.rectangle((0,0,w,int(h*.12)),fill=(230,40,40))
        draw.rectangle((0,int(h*.88),w,h),fill=(40,210,70))
        draw.rectangle((0,0,int(w*.12),h),fill=(40,80,230))
        draw.rectangle((int(w*.88),0,w,h),fill=(230,210,40))
        stream=io.BytesIO();picture.save(stream,format='PNG');fixtures[letter*40]=stream.getvalue()
    class FixtureLRR:
        def json(self,path,*args):
            if path=='/api/info':return {'version':'synthetic'}
            if path=='/api/archives':return [{'arcid':key} for key in fixtures]
            key=path.split('/')[3]
            if path.endswith('/metadata'):return {'arcid':key,'title':'Synthetic cover '+key[0],'pagecount':1}
            if path.endswith('/files'):return {'pages':['/api/archives/'+key+'/page?p=1']}
            raise ValueError('Unknown fixture endpoint')
        def open(self,path,*args,**kwargs):
            png=fixtures[path.split('/')[3]];response=io.BytesIO(png);response.status=200
            response.headers={'Content-Type':'image/png','Content-Length':str(len(png))};return response
    with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'STUDIO_PASSWORD':'synthetic-blur-password'}):
        app=Studio(Store(Path(directory)/'fixture.db'),FixtureLRR());app.sync()
        server=make_server('127.0.0.1',0,app);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
                context=browser.new_context(http_credentials={'username':'admin','password':'synthetic-blur-password'},viewport={'width':1440,'height':1000})
                page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.add_init_script('HTMLCanvasElement.prototype.getContext = () => {throw new Error("Canvas is unnecessary for blur")}')
                base='http://127.0.0.1:'+str(server.server_port)
                def loaded():
                    page.wait_for_function('()=>document.querySelectorAll(".card img").length===3 && [...document.querySelectorAll(".card img")].every(i=>i.complete&&i.naturalWidth)')
                def blurred(expected):
                    for image in page.locator('.card img').all():
                        style=image.evaluate('(el)=>({filter:getComputedStyle(el).filter,fit:getComputedStyle(el).objectFit,transform:getComputedStyle(el).transform})')
                        assert style=={'filter':'blur(10px)' if expected else 'none','fit':'contain','transform':'none'},style
                    assert page.locator('.card canvas').count()==0
                page.goto(base);loaded();blurred(True)
                page.screenshot(path=str(Path(__file__).resolve().parents[2]/'work/thumbnail-blur-preview.png'))
                page.locator('.card').first.click()
                assert page.locator('#detail img').evaluate('(el)=>getComputedStyle(el).filter')=='none'
                assert page.locator('#detail img').evaluate('(el)=>getComputedStyle(el).objectFit')=='contain'
                page.locator('#read-work').click()
                page.wait_for_function('()=>document.querySelector("#reader-image").complete&&document.querySelector("#reader-image").naturalWidth')
                assert page.locator('#reader-image').evaluate('(el)=>getComputedStyle(el).filter')=='none'
                page.locator('#close-reader').click();page.locator('#close-detail').click()
                page.locator('#settings-button').click();page.locator('#thumbnail-blur').uncheck()
                page.locator('#settings [data-close]').click();page.reload();loaded();blurred(False)
                assert page.evaluate('JSON.parse(localStorage.getItem("studio-view")).thumbnailBlur') is False
                # Check actual screenshot pixels at all four original edges.
                # This catches crop/zoom/distortion with portrait, wide and tall inputs.
                def check_edges():
                    for image in page.locator('.card img').all():
                        nw,nh=image.evaluate('(el)=>[el.naturalWidth,el.naturalHeight]')
                        shot=Image.open(io.BytesIO(image.screenshot())).convert('RGB');w,h=shot.size
                        scale=min(w/nw,h/nh);rw,rh=nw*scale,nh*scale;ox,oy=(w-rw)/2,(h-rh)/2
                        for x,y,color in [(.5,.06,(230,40,40)),(.5,.94,(40,210,70)),(.06,.5,(40,80,230)),(.94,.5,(230,210,40))]:
                            pixel=shot.getpixel((int(ox+rw*x),int(oy+rh*y)))
                            assert max(abs(a-b) for a,b in zip(pixel,color))<12,(nw,nh,w,h,x,y,pixel,color)
                page.eval_on_selector_all(".card-select,.cover .pages,.favorite-star", "els=>els.forEach(el=>el.style.visibility='hidden')")
                for width,height in [(1440,1000),(390,844)]:
                    page.set_viewport_size({'width':width,'height':height})
                    for layout in ['grid','list']:
                        if page.locator('#grid').evaluate('(el)=>el.classList.contains("list")')!=(layout=='list'):page.locator('#layout').click()
                        check_edges()
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.set_viewport_size({'width':1440,'height':1000});page.locator('#layout').click()
                for size in ['small','large']:
                    page.locator('#settings-button').click();page.locator('#card-size').select_option(size);page.locator('#settings [data-close]').click();check_edges()
                page.eval_on_selector_all(".card-select,.cover .pages,.favorite-star", "els=>els.forEach(el=>el.style.visibility='')")
                page.screenshot(path=str(Path(__file__).resolve().parents[2]/'work/thumbnail-contain-preview.png'))
                page.locator('#privacy-route').click();blurred(True);page.reload();loaded();blurred(True)
                page.goto(base+'/unsen');loaded();blurred(False);page.goto(base);loaded();blurred(True)
                old=context.new_page();old.add_init_script('localStorage.setItem("studio-view",JSON.stringify({thumbnailMosaic:false}))');old.goto(base)
                old.wait_for_function('()=>document.querySelectorAll(".card img").length===3')
                assert old.locator('#thumbnail-blur').is_checked() is False
                assert old.locator('.card img').first.evaluate('(el)=>getComputedStyle(el).filter')=='none'
                assert not errors,errors
                browser.close()
            print(json.dumps({'thumbnail_blur_default':True,'no_pixel_canvas_or_zoom':True,'four_edges_preserved_for_three_ratios':True,
                              'grid_list_desktop_mobile':True,'three_card_sizes':True,'detail_reader_original':True,
                              'saved_toggle_and_legacy_preference':True,'unsen_compatible':True,'page_errors':errors}))
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':main()
