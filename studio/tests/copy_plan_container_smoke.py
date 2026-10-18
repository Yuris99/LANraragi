"""Optional real Docker regression using generated files only.

Requires a local Python stdlib image (STUDIO_COPY_PLAN_TEST_IMAGE); never pulls,
uses private services or mounts personal data. All inputs RO, network none.
"""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from test_copy_cleanup_plan import PlanTests
repo=Path(__file__).resolve().parents[1]
case=PlanTests();case.setUp()
try:
    with tempfile.TemporaryDirectory(prefix='studio-copy-plan-container-') as temp:
        root=Path(temp);code=root/'code';(code/'deploy').mkdir(parents=True)
        for name in ['deploy/plan-copy-cleanup.py','deploy/review-library-storage.py','deploy/archive_in_place.py','sources.py']:
            shutil.copyfile(repo/name,code/name)
        prior=root/'prior';prior.mkdir();(prior/'report.json').write_text(json.dumps(case.report))
        out=root/'out';out.mkdir();catalog=root/'catalog';catalog.mkdir()
        with sqlite3.connect(case.store.path) as source,sqlite3.connect(catalog/'studio.db') as target:source.backup(target)
        live=sqlite3.connect(catalog/'studio.db')
        live.execute('PRAGMA journal_mode=WAL');live.execute("INSERT INTO settings VALUES('synthetic-hot-wal','1')");live.commit()
        env={k:v for k,v in os.environ.items() if k not in ['DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH']}
        def run(dbroot,name):
            args=['docker','--host=unix:///var/run/docker.sock','run','--rm','--pull=never','--user','0:0','--network','none','--read-only','--memory','256m','--cap-drop','ALL','--cap-add','DAC_OVERRIDE','--security-opt','no-new-privileges:true']
            for src,dst,ro in [(case.library,'/nas-library',True),(case.copies,'/copies',True),(code,'/tools',True),(prior,'/prior',True),(dbroot,'/catalog',True),(out,'/reports',False)]:
                args+=['--mount',f'type=bind,src={src},dst={dst}'+(',readonly' if ro else '')]
            args+=['--entrypoint','python',os.environ.get('STUDIO_COPY_PLAN_TEST_IMAGE','lanraragi-studio:nas-baseline-root-check'),'-B','/tools/deploy/plan-copy-cleanup.py','--prior-report','/prior/report.json','--database','/catalog/studio.db','--library-root','/nas-library','--copies-root','/copies','--output','/reports/'+name+'.json']
            result=subprocess.run(args,env=env,capture_output=True,text=True,timeout=45)
            assert not result.stderr,result.stderr
            return result.returncode,json.loads(result.stdout)
        code1,result=run(catalog,'normal')
        assert code1==0 and result['catalog_pairs']==1,(code1,result)
        print('hot_wal_snapshot=passed')
        partial=root/'missing-shm';partial.mkdir()
        for name in ['studio.db','studio.db-wal']:shutil.copyfile(catalog/name,partial/name)
        code2,result2=run(partial,'missing-shm')
        assert code2==0 and result2['catalog_pairs']==1 and result2['catalog_snapshot']=='stable_db_and_wal_copy',(code2,result2)
        print('missing_shm_snapshot_recovery=passed; synthetic_only=true; nas_changed=false')
        live.close()
finally:case.doCleanups()
