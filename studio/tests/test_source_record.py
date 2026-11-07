import io
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from source_record import ArchiveRanges,archive_evidence,ehviewer_identity,preferred_evidence,source_record
from store import Store
from server import Studio


def cbor(value):
    if isinstance(value,int):
        return bytes([value]) if value<24 else b'\x1a'+value.to_bytes(4,'big')
    if isinstance(value,str):
        raw=value.encode();return (bytes([0x60+len(raw)]) if len(raw)<24 else b'\x78'+bytes([len(raw)]))+raw
    if isinstance(value,dict):return b'\xbf'+b''.join(cbor(k)+cbor(v) for k,v in value.items())+b'\xff'
    raise AssertionError('Generated fixture only')


def spider(gid=123,token='abcdefghij',pages=49):
    return cbor(dict(gid=gid,token=token,pages=pages,pTokenMap={0:'generated-page-token'},cookie='generated-excluded-secret'))


def archive(entries,zip64=False):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as book:
        for name,raw in entries:
            if zip64:
                with book.open(name,'w',force_zip64=True) as target:target.write(raw)
            else:book.writestr(name,raw)
    return stream.getvalue()


class RangeLRR:
    def __init__(self,raw,ignore_range=False):self.raw=raw;self.calls=[];self.ignore_range=ignore_range
    def open(self,path,headers=None):
        self.calls.append((path,headers))
        assert re.fullmatch('/api/archives/[0-9a-f]{40}/download',path)
        match=re.fullmatch(r'bytes=([0-9]+)-([0-9]+)',headers['Range']);assert match
        a,b=map(int,match.groups())
        response=io.BytesIO(self.raw[a:b+1]);response.status=200 if self.ignore_range else 206
        response.headers={'Content-Range':f'bytes {a}-{b}/{len(self.raw)}'}
        return response


class SourceRecordTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/'catalog.db')
        self.work=self.store.create_work('User accepted title','User artist',lrr_id='a'*40,tags=['kept'])

    def test_cbor_identity_excludes_account_and_page_tokens(self):
        value=ehviewer_identity(spider())
        self.assertEqual(value['external_id'],'123');self.assertEqual(value['pages'],49)
        self.assertEqual(value['origin']['encoding'],'cbor')
        self.assertNotIn('generated-excluded-secret',json.dumps(value))
        self.assertNotIn('generated-page-token',json.dumps(value))
        exported=source_record(self.work,[{**value,'cookie':'generated-excluded-secret'}])
        self.assertNotIn('generated-excluded-secret',json.dumps(exported))
        self.assertEqual(exported['evidence'][0]['verification']['state'],'local_metadata')

    def test_legacy_versions_and_validation(self):
        raw=b'00000000\n123\nabcdefghij\n1\n2\n20\n49\n0 page-token\n'
        for prefix in (b'',b'VERSION2\n'):
            self.assertEqual(ehviewer_identity(prefix+raw)['pages'],49)
        for data in (spider(gid=0),spider(token='short'),b'\xbf\xff',spider()+b'extra'):
            with self.subTest(data=data[:5]),self.assertRaises(ValueError):ehviewer_identity(data)
        with self.assertRaises(ValueError):ehviewer_identity(b'x'*(128*1024+1))

    def test_zip64_and_original_host_are_preserved_in_our_format(self):
        xml=b'<ComicInfo><Web>https://exhentai.org/g/123/abcdefghij/</Web><Title>Original title</Title><Writer>Generated artist</Writer><Genre>artist:generated, language:korean</Genre><LanguageISO>ko</LanguageISO><PageCount>49</PageCount></ComicInfo>'
        lrr=RangeLRR(archive([('nested/.ehviewer',spider()),('ComicInfo.xml',xml),('page.png',b'generated-only')],zip64=True))
        evidence=archive_evidence(lrr,self.work);chosen=preferred_evidence(evidence)
        self.assertEqual(chosen['provider'],'exhentai');self.assertFalse(any(e.get('conflict') for e in evidence))
        value=source_record(self.work,evidence)
        self.assertEqual((value['format'],value['version']),('yuri-studio-source',1))
        self.assertIn('language:korean',chosen['metadata']['tags'])
        self.assertEqual(chosen['metadata']['languages'],['korean'])
        self.assertTrue(all(headers['Range'].startswith('bytes=') for _,headers in lrr.calls))

    def test_conflicting_original_identities_require_manual_choice(self):
        xml=b'<ComicInfo><Web>https://exhentai.org/g/999/abcdefghij/</Web></ComicInfo>'
        evidence=archive_evidence(RangeLRR(archive([('.ehviewer',spider()),('ComicInfo.xml',xml)])),self.work)
        self.assertTrue(all(e['conflict'] for e in evidence));self.assertIsNone(preferred_evidence(evidence))

    def test_comicinfo_metadata_without_url_remains_available_for_search(self):
        evidence=archive_evidence(RangeLRR(archive([('ComicInfo.xml',b'<ComicInfo><Title>Original</Title><Genre>parody:original</Genre></ComicInfo>')])),self.work)
        self.assertEqual(evidence[0]['metadata']['title'],'Original')
        self.assertIsNone(preferred_evidence(evidence))

    def test_unsupported_range_and_oversized_metadata_stop_before_full_download(self):
        with self.assertRaises(ValueError):ArchiveRanges(RangeLRR(b'generated',ignore_range=True),'a'*40)
        with self.assertRaises(ValueError):archive_evidence(RangeLRR(archive([('.ehviewer',b'x'*(128*1024+1))])),self.work)
        xml=b'<!DOCTYPE x [<!ENTITY x "forbidden">]><ComicInfo />'
        with self.assertRaises(ValueError):archive_evidence(RangeLRR(archive([('ComicInfo.xml',xml)])),self.work)

    def test_restore_and_live_record_do_not_overwrite_user_metadata(self):
        lrr=RangeLRR(archive([('.ehviewer',spider())]));app=Studio(self.store,lrr)
        result=app.restore_source_record(self.work['id'])
        self.assertTrue(result['restored'])
        work=self.store.get_work(self.work['id'])
        self.assertEqual((work['title'],work['artist'],work['tags']),('User accepted title','User artist',['kept']))
        self.assertEqual(len(work['sources']),1)
        self.assertEqual(self.store.get_source_record(work['id'])['evidence'][0]['external_id'],'123')
        self.store.upsert_source(work['id'],{'url':work['sources'][0]['url'],'tags':['updated:source']})
        self.assertEqual(self.store.get_source_record(work['id'])['sources'][0]['tags'],['updated:source'])

    def test_original_tags_are_visible_before_remote_fetch_and_fetched_data_is_preserved(self):
        xml=b'<ComicInfo><Web>https://exhentai.org/g/123/abcdefghij/</Web><Title>Original</Title><Genre>parody:original</Genre><Writer>Fixture</Writer><LanguageISO>ko</LanguageISO><PageCount>49</PageCount></ComicInfo>'
        app=Studio(self.store,RangeLRR(archive([('.ehviewer',spider()),('ComicInfo.xml',xml)])))
        result=app.restore_source_record(self.work['id']);source=result['work']['sources'][0]
        self.assertEqual(source['status'],'manual')
        self.assertIn('parody:original',source['tags']);self.assertIn('language:korean',source['tags'])
        self.assertEqual(source['metadata']['collector'],'studio-embedded-source-v1')
        self.store.upsert_source(self.work['id'],{'url':source['url'],'tags':['newer:remote'],'status':'fetched'})
        again=app.restore_source_record(self.work['id'])['work']['sources'][0]
        self.assertEqual(again['status'],'fetched');self.assertEqual(again['tags'],['newer:remote'])


if __name__=='__main__':unittest.main()
