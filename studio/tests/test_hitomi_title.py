import hashlib
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from site_sessions import hitomi_title_index
from metadata import counterpart_candidates


def fixture(entries):
    records=[];data=b''
    for word,values in entries.items():
        block=len(values).to_bytes(4,'big')+b''.join(value.to_bytes(4,'big') for value in values)
        records.append((hashlib.sha256(word.encode()).digest()[:4],len(data),len(block)));data+=block
    records.sort();node=len(records).to_bytes(4,'big')+b''.join((4).to_bytes(4,'big')+record[0] for record in records)
    node+=len(records).to_bytes(4,'big')+b''.join(start.to_bytes(8,'big')+length.to_bytes(4,'big') for _,start,length in records)+bytes(17*8)
    node=node.ljust(464,b'\0');calls=[]
    def read(path,start,length):
        calls.append((path,start,length))
        if path.endswith('/version'):return b'123'
        if path.endswith('.index'):return node
        if path.endswith('.data'):return data[start:start+length]
        raise AssertionError(path)
    return read,calls


class TitleTests(unittest.TestCase):
    def test_title_words_intersect_paginate_and_share_root(self):
        read,calls=fixture({'garden':list(range(1,20)),'a':list(range(5,20))})
        first=hitomi_title_index('A  Garden',read=read)
        self.assertEqual(first,{'ids':[str(i) for i in range(19,11,-1)],'complete':False})
        self.assertEqual(sum(path.endswith('.index') for path,_,_ in calls),1)
        second=hitomi_title_index('a garden',8,read)
        self.assertEqual(second,{'ids':[str(i) for i in range(11,4,-1)],'complete':True})
        self.assertEqual(hitomi_title_index('missing',read=read),{'ids':[],'complete':True})

    def test_malformed_or_unbounded_index_is_rejected(self):
        for bad in [b'not version',b'1'*65]:
            with self.assertRaises(ValueError):hitomi_title_index('a',read=lambda *args:bad)
        read,_=fixture({'a':[1]})
        def broken(path,start,length):return b'\xff'*464 if path.endswith('.index') else read(path,start,length)
        with self.assertRaises(ValueError):hitomi_title_index('a',read=broken)
        for title,offset in [('',0),('a\n',0),('a',True),('a',100001)]:
            with self.assertRaises(ValueError):hitomi_title_index(title,offset,read)

    def test_candidate_search_without_artist_uses_title_not_a_fake_artist(self):
        from test_metadata import hitomi_js
        queries=[]
        def index(query,offset=None):queries.append(query);return {'ids':['123456'],'complete':True}
        value=counterpart_candidates({'provider':'local','title':'A Garden','artists':[],'languages':['korean'],'tags':[],'pages':6},lambda url:hitomi_js(),index,target='hitomi',cursor={})
        self.assertEqual(queries,['title:A Garden']);self.assertEqual(value['search_basis'],'title')
        self.assertEqual(len(value['items']),1)
        self.assertFalse(value['items'][0]['comparison']['automatic_eligible'])


if __name__=='__main__':unittest.main()
