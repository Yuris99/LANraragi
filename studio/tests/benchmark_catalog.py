"""Reproducible synthetic catalog timings; never opens an existing database."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from store import Store


def main(count=20000):
    with tempfile.TemporaryDirectory() as directory:
        store=Store(Path(directory)/'synthetic.db')
        now=time.time()
        with store.db() as db:
            db.executemany('INSERT INTO works(id,title,artist,tags,pages,bytes,added) VALUES(?,?,?,?,?,?,?)',
                [(f'{n:032x}',f'Synthetic book {n:06}',f'Artist {n%100}',json.dumps(['language:synthetic',f'group:{n%50}']),32,1000000,now+n) for n in range(count)])
            db.executemany('INSERT INTO sources(id,work_id,provider,external_id,url,tags) VALUES(?,?,?,?,?,?)',
                [(f'{n+count:032x}',f'{n:032x}','hitomi',str(n+1),f'https://hitomi.la/galleries/{n+1}.html',json.dumps([f'collection:{n%50}'])) for n in range(count)])
        def measure(query):
            samples=[]
            for _ in range(10):
                start=time.perf_counter();result=store.list_works(query=query,limit=120)
                samples.append((time.perf_counter()-start)*1000)
                assert len(result['items'])<=120
            return {'median_ms':round(statistics.median(samples),2),'max_ms':round(max(samples),2)}
        start=time.perf_counter()
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _:store.list_works(query='collection:7',limit=48),range(8)))
        concurrent_ms=(time.perf_counter()-start)*1000
        result={'synthetic_works':count,'source_records':count,'list_120':measure(''),
                'search_source_tag_120':measure('collection:7'),'search_title_120':measure('019999'),
                'eight_searches_four_threads_ms':round(concurrent_ms,2)}
        print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main(int(sys.argv[1]) if len(sys.argv)>1 else 20000)
