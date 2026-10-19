"""Real local Studio + Chromium, generated WAV/H264/PNG only, no external site."""
import io
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import threading
from unittest.mock import patch
from PIL import Image
from playwright.sync_api import sync_playwright
from navigation_smoke import FixtureLRR
from test_editions import audio_bytes
from server import Studio,make_server
from store import Store


def cover_bytes(reverse=False):
    image=Image.new('RGB',(180,240))
    for y in range(240):
        for x in range(180):image.putpixel((x,y),(int(255*x/179) if reverse else int(255*(179-x)/179),y%180,70))
    stream=io.BytesIO();image.save(stream,'PNG');return stream.getvalue()


def main():
    with tempfile.TemporaryDirectory() as temporary,patch.dict(os.environ,{'STUDIO_PASSWORD':'synthetic-voice-editions'}):
        root=Path(temporary);store=Store(root/'studio.db');(root/'uploads').mkdir()
        original=store.create_work('Generated original','Generated artist',lrr_id='a'*40,pages=7)
        translated=store.create_work('Generated translation','Generated artist',lrr_id='b'*40,pages=7)
        voice=store.create_work('Generated video-only comic')
        lrr=FixtureLRR();lrr.fail_files_once=True
        app=Studio(store,lrr,root/'uploads')
        wav=audio_bytes();audio=app.voice.receive(original['id'],io.BytesIO(wav),len(wav),'Generated voice.wav')
        for work,reverse in [(original,False),(translated,False),(voice,True)]:
            raw=cover_bytes(reverse);app.voice.receive(work['id'],io.BytesIO(raw),len(raw),'Generated cover.png')
        store.configure_edition(original['id'],{'kind':'voice_pages','label':'Voiced original','language':'日本語'})
        store.configure_edition(translated['id'],{'kind':'comic','language':'한국어','label':'Team A','translator':'Generated team'})
        store.group_edition(translated['id'],'L'+str(original['local_number']))
        store.save_voice_cues(original['id'],audio['id'],[{'page':1,'second':0},{'page':2,'second':2},{'page':3,'second':4}])
        video=root/'generated.mp4'
        subprocess.run(['ffmpeg','-loglevel','error','-f','lavfi','-i','color=c=blue:s=160x120:r=10','-f','lavfi','-i','sine=frequency=440:sample_rate=44100','-t','3','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(video)],check=True,timeout=30)
        raw=video.read_bytes();app.voice.receive(voice['id'],io.BytesIO(raw),len(raw),'Generated video.mp4')
        store.configure_edition(voice['id'],{'kind':'voice_video','label':'Standalone voice'})
        server=make_server('127.0.0.1',0,app);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:'+str(server.server_port)
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--autoplay-policy=no-user-gesture-required'])
                context=browser.new_context(http_credentials={'username':'admin','password':'synthetic-voice-editions'},viewport={'width':1440,'height':1000})
                page=context.new_page();errors=[];external=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.on('request',lambda request:external.append(request.url) if not request.url.startswith(base) and not request.url.startswith('blob:') else None)
                page.goto(base+'/#/L'+str(original['local_number']))
                page.locator('audio').wait_for();page.wait_for_function('()=>document.querySelector("audio").readyState>=1')
                assert page.locator('.edition-siblings button').count()==2
                assert '한국어' in page.locator('.edition-siblings').inner_text()
                page.wait_for_function('()=>document.querySelector(".voice-page-label").textContent.includes("preparing")')
                page.locator('audio').evaluate('(audio)=>{audio.currentTime=2.5}')
                page.locator('.voice-pages-retry').click()
                page.wait_for_function('()=>document.querySelector(".voice-page-label").textContent.includes("2 / 7")')
                page.wait_for_function('()=>document.querySelector(".voice-page").naturalWidth>0')
                page.wait_for_function('async ()=>{const w=await (await fetch("/api/works/'+original['id']+'")).json();return w.edition.assets.some(a=>a.kind==="audio"&&a.position>=2.4)}')
                page.locator('audio').evaluate('(audio)=>audio.play()');page.wait_for_function('()=>document.querySelector("audio").currentTime>2.7');page.locator('audio').evaluate('(audio)=>audio.pause()')
                page.reload();page.locator('audio').wait_for();page.wait_for_function('()=>document.querySelector("audio").currentTime>=2.4')
                page.locator('.voice-cue-next').click();page.wait_for_function('()=>document.querySelector(".voice-page-label").textContent.includes("3 / 7")')
                page.locator('.voice-speed').select_option('1.5');assert page.locator('audio').evaluate('(a)=>a.playbackRate')==1.5
                page.locator('.edition-siblings [data-edition-go="'+translated['id']+'"]').click()
                page.wait_for_function('()=>!document.querySelector("audio")')
                assert page.locator('.edition-section').inner_text().find('Team A')>=0
                page.locator('.edition-section > details').evaluate('(el)=>el.open=true')
                page.locator('.edition-ungroup').click();page.wait_for_function('()=>document.querySelectorAll(".edition-siblings button").length===0')
                page.locator('.edition-section > details').evaluate('(el)=>el.open=true')
                page.locator('.edition-group input').fill('L'+str(original['local_number']));page.locator('.edition-group button').click()
                page.wait_for_function('()=>document.querySelectorAll(".edition-siblings button").length===2')
                page.goto(base+'/#/L'+str(voice['local_number']))
                page.locator('video').wait_for();page.wait_for_function('()=>document.querySelector("video").readyState>=2')
                assert page.locator('video').evaluate('(video)=>video.videoWidth')==160
                page.locator('#read-work').click()
                page.wait_for_function('()=>document.querySelector("video").currentTime>0.2')
                page.locator('video').evaluate('(video)=>video.pause()')
                assert not store.get_work(voice['id'])['lrr_id']
                page.locator('#close-detail').click()
                page.locator('#visual-open').click();page.locator('#visual-index').click()
                page.wait_for_function('()=>document.querySelector("#visual-index-status").textContent.includes("색인 완료")')
                page.locator('#visual-file').set_input_files({'name':'Generated query.png','mimeType':'image/png','buffer':cover_bytes()})
                page.wait_for_function('()=>document.querySelectorAll("[data-visual-work]").length===2')
                assert page.locator('#visual-dialog a[target="_blank"]').count()==3
                assert all(page.locator('#visual-dialog a').nth(i).get_attribute('rel')=='noopener noreferrer' for i in range(3))
                assert not external,external
                page.locator('[data-visual-work="'+original['id']+'"]').click();page.locator('audio').wait_for()
                # Exercise real streamed upload through the UI, without duplicate track records.
                page.locator('.voice-upload input').set_input_files({'name':'Additional voice.wav','mimeType':'audio/wav','buffer':wav})
                page.locator('.voice-upload button').click();page.wait_for_function('()=>document.querySelector("#toast").textContent.includes("파일을 첨부")')
                for width,height in [(1440,1000),(390,844)]:
                    page.set_viewport_size({'width':width,'height':height})
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    assert page.evaluate('document.querySelector("#detail").scrollWidth<=document.querySelector("#detail").clientWidth+1')
                # Check actual painting above nested and scrolling modal dialogs.
                for width,height in [(1440,1000),(390,844)]:
                    page.set_viewport_size({'width':width,'height':height})
                    page.locator('.edition-section > details').evaluate('(el)=>el.open=true')
                    page.locator('.edition-group input').fill('L999999999')
                    page.locator('.edition-group button').click()
                    page.wait_for_function('()=>!document.querySelector("#toast").hidden')
                    page.evaluate('document.querySelector("#settings").showModal()')
                    page.wait_for_function('()=>document.querySelector("#toast").parentElement.id==="settings"')
                    page.evaluate('document.querySelector("#settings").scrollTop=10000')
                    assert page.evaluate("""()=>{const el=document.querySelector('#toast'),r=el.getBoundingClientRect();el.style.pointerEvents='auto';const top=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);el.style.pointerEvents='';return top===el&&r.top>=0&&r.bottom<=innerHeight&&r.left>=0&&r.right<=innerWidth}""")
                    page.evaluate('document.querySelector("#settings").close()')
                    page.wait_for_function('()=>document.querySelector("#toast").parentElement.id==="detail"')
                    page.locator('.edition-section > details').evaluate('(el)=>el.open=true')
                    page.locator('.edition-group button').click()
                    page.wait_for_function('()=>!document.querySelector("#toast").hidden')
                    assert page.locator('.edition-group button').evaluate('(el)=>document.activeElement===el')
                page.wait_for_function('()=>document.querySelector("#toast").hidden',timeout=8000)
                assert not page.locator('#toast').evaluate('(el)=>el.matches(":popover-open")')
                assert not errors,errors
                browser.close()
            print('editions_browser=passed; separate_translations; video_only_H264_AAC_decoded; WAV_resume; page_audio_cues; speed; real_upload; local_cover_search; external_links_only_no_transfer; desktop_mobile; synthetic_only=true; nas_changed=false')
        finally:server.shutdown();server.server_close();thread.join(timeout=5)


if __name__=='__main__':main()
