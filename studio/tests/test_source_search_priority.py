"""Generated requests: manual search waits safely instead of losing to background work."""
from pathlib import Path
import json
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import Studio
from store import Store
from auto_sources import AutoLinker
from metadata import result
from sources import parse_source


class SearchPriorityTests(unittest.TestCase):
    def test_manual_request_waits_for_an_existing_background_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'catalog.db');work=store.create_work('Generated local title')
            app=Studio(store,None);started=threading.Event();finished=threading.Event();errors=[];results=[]
            def manual():
                started.set()
                try:results.append(app.find_source_candidates(work['id'],{'method':'embedded'}))
                except Exception as error:errors.append(error)
                finally:finished.set()
            app.match_lock.acquire()
            with patch.object(app,'source_transport',return_value=(None,None,{})):
                thread=threading.Thread(target=manual);thread.start();self.assertTrue(started.wait(1))
                returned_early=finished.wait(.1)
                app.match_lock.release();thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors,[])
            self.assertFalse(returned_early)
            self.assertEqual(results[0]['status'],'no_candidates')

    def test_manual_priority_yields_background_without_losing_cursor_or_failure_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'catalog.db');work=store.create_work('Generated local title')
            metadata=result(parse_source('https://e-hentai.org/g/123/0123456789/'),'Generated source',
                ['artist:generated','language:korean'],pages=6,comments=[])
            store.import_metadata(work['id'],metadata,remote=True)
            previous={'sites':[{'provider':'hitomi','status':'scanning','next_cursor':{'offset':8},'items':[]}]}
            with store.db() as db:db.execute('UPDATE source_link_jobs SET result=? WHERE work_id=?',(json.dumps(previous),work['id']))
            app=Studio(store,None)
            with app.manual_source_access(),patch('metadata.fetch_metadata') as fetch,patch('metadata.public_artist_index') as index:
                self.assertFalse(app.acquire_automatic_source_slot())
                linker=AutoLinker(store,lambda:(fetch,index,{'exhentai':'session_required'}),pause=app.automatic_source_pause)
                self.assertTrue(linker.run_one())
                fetch.assert_not_called();index.assert_not_called()
            status=store.automatic_status(work['id'])
            self.assertEqual(status['state'],'queued');self.assertEqual(status['attempts'],0)
            self.assertEqual(status['result'],previous)
            self.assertIsNone(store.automatic_circuit('hitomi'))
            self.assertFalse(app.manual_source_pending.is_set())

    def test_exception_and_timeout_release_manual_priority(self):
        with tempfile.TemporaryDirectory() as directory:
            app=Studio(Store(Path(directory)/'catalog.db'),None)
            with self.assertRaisesRegex(RuntimeError,'generated'):
                with app.manual_source_access():raise RuntimeError('generated')
            self.assertFalse(app.manual_source_pending.is_set());self.assertFalse(app.match_lock.locked())
            with patch.object(app,'match_lock') as lock:
                lock.acquire.return_value=False
                with self.assertRaisesRegex(ValueError,'지연'):
                    with app.manual_source_access():self.fail('The slot was not acquired')
                lock.release.assert_not_called()
            self.assertFalse(app.manual_source_pending.is_set());self.assertEqual(app.source_waiter_count,0)


if __name__=='__main__':unittest.main()
