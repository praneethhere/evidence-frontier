import json
import sys
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request,urlopen
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from server import make_server

class RealCaseAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prefix=[{'role':'user','content':'Please change the address','turn_idx':0},
                {'role':'tool','name':'modify_user_address','content':'{"address":"Denver"}','turn_idx':1},
                {'role':'assistant','content':'I updated the address.','turn_idx':2}]
        real={'cases':{'blind_035':{'blind_id':'blind_035','agent_response':'I updated the address.',
            'task_domain':'retail','turn_type':'intermediate','agent_visible_prefix':prefix}},
            'R1':{'blind_035':{'claim_presence':'yes','evidence_label':'contradicted'}}}
        cls.server=make_server(0,real);cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start();cls.base=f'http://127.0.0.1:{cls.server.server_address[1]}'
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def post(self,path,case):
        req=Request(self.base+path,method='POST',data=json.dumps({'case':case}).encode(),headers={'Content-Type':'application/json'})
        with urlopen(req) as rep:return json.load(rep)
    def test_catalog_and_case_no_label_leak(self):
        with urlopen(self.base+'/api/real-cases') as rep:catalog=json.load(rep)
        self.assertTrue(catalog['enabled'])
        case=self.post('/api/real-case','blind_035')
        self.assertEqual(case['agent_visible_prefix'][-1]['role'],'assistant')
        self.assertNotIn('contradicted',json.dumps(case))
        self.assertFalse(case['private_outcome_included'])
        label=self.post('/api/real-r1','blind_035')
        self.assertEqual(label['label']['evidence_label'],'contradicted')
        self.assertFalse(label['adjudicated_gold'])
    def test_guided_case_post_denied(self):
        req=Request(self.base+'/api/real-case',method='POST',data=b'{"case":"blind_001"}',headers={'Content-Type':'application/json'})
        with self.assertRaises(HTTPError) as e:urlopen(req)
        self.assertEqual(e.exception.code,400);e.exception.close()
if __name__=='__main__':unittest.main()
