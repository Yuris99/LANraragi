"""HTTP benchmark for a separate isolated 48-archive synthetic project at :43122."""
from concurrent.futures import ThreadPoolExecutor
import base64
import json
from pathlib import Path
import statistics
import time
import urllib.request


def main():
    root=Path(__file__).resolve().parents[1]
    env=dict(line.split('=',1) for line in (root/'.env').read_text().splitlines() if '=' in line)
    auth='Basic '+base64.b64encode(('admin:'+env['STUDIO_PASSWORD']).encode()).decode()
    base='http://127.0.0.1:43122'
    def request(path,body=None):
        req=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers={
            'Authorization':auth,'Content-Type':'application/json'})
        return urllib.request.urlopen(req,timeout=20)
    for attempt in range(60):
        try:
            with request('/api/sync',{}) as response:json.load(response)
            with request('/api/works?limit=48') as response:works=json.load(response)
            if works['total']==48:break
        except OSError:
            if attempt==59:raise
        time.sleep(1)
    assert works['total']==48 and all(w['title'].startswith('Synthetic Benchmark ') for w in works['items'])
    def timing(work):
        start=time.perf_counter()
        with request('/api/media/'+work['lrr_id']+'/thumbnail') as response:
            assert response.headers.get_content_type().startswith('image/')
            assert len(response.read())>0
        return (time.perf_counter()-start)*1000
    results={}
    for label in ['first_pass','warm_pass']:
        start=time.perf_counter()
        with ThreadPoolExecutor(max_workers=4) as pool:samples=list(pool.map(timing,works['items']))
        results[label]={'total_ms':round((time.perf_counter()-start)*1000,2),
                        'median_ms':round(statistics.median(samples),2),'p95_ms':round(sorted(samples)[45],2)}
    print(json.dumps({'synthetic_archives':48,'concurrency':4,**results}))


if __name__=='__main__':main()
