import csv
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen,Request
from urllib.error import HTTPError
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import real_trajectories as r
from server import make_server

class LocalRealCases(unittest.TestCase):
    @staticmethod
    def make_case(bid,with_future=False):
        prefix=[{'role':'user','content':'Please change the address','turn_idx':0},
                {'role':'assistant','content':None,'turn_idx':1,'tool_calls':[{'id':'c1','function':{'name':'modify_user_address','arguments':'{}'}}]},
                {'role':'tool','name':'modify_user_address','tool_call_id':'c1','turn_idx':2,'content':'{"status":"ok"}'},
                {'role':'assistant','content':'I updated the address.','turn_idx':3}]
        if with_future:prefix.append({'role':'tool','content':'future','turn_idx':4})
        return {'schema':'naacl-evidence-frontier-turn-prefix-v1','blind_id':bid,'agent_response':'I updated the address.',
                'task_domain':'retail','turn_type':'intermediate','terminal_stop_after_final':False,
                'missing_tool_response_links':0,'agent_visible_prefix':prefix}
    def test_exact_source_prefix_accepts(self):
        c=self.make_case('blind_035')
        self.assertEqual(r._check_case(c,c,'blind_035'),c)
    def test_future_message_rejected(self):
        c=self.make_case('blind_035');bad=self.make_case('blind_035',True)
        with self.assertRaisesRegex(ValueError,'frozen selection'):
            r._check_case(bad,c,'blind_035')
    def test_hidden_outcome_key_rejected(self):
        c=self.make_case('blind_035');bad=dict(c,eval_result={'success':True})
        with self.assertRaisesRegex(ValueError,'Forbidden case keys'):
            r._check_case(bad,c,'blind_035')
    def test_claim_must_be_last_assistant(self):
        c=self.make_case('blind_035');bad=dict(c,agent_response='I updated a different record.')
        with self.assertRaises(ValueError):r._check_case(bad,c,'blind_035')
    def test_guided_cases_never_exposed(self):
        d={'cases':{'blind_035':self.make_case('blind_035'),'blind_001':self.make_case('blind_001')},'R1':None}
        with self.assertRaises(ValueError):r.public_case(d,'blind_001')
        with self.assertRaises(ValueError):r.r1_reveal(d,'blind_001')
    def test_no_labels_in_default_case(self):
        d={'cases':{'blind_035':self.make_case('blind_035')},'R1':{'blind_035':{'evidence_label':'contradicted'}}}
        x=r.public_case(d,'blind_035')
        self.assertEqual(x['R1_label_included'],False)
        self.assertNotIn('contradicted',json.dumps(x))
        self.assertNotIn('eval_result',json.dumps(x))
        self.assertEqual(r.r1_reveal(d,'blind_035')['label']['evidence_label'],'contradicted')
    def test_no_real_data_mode(self):
        self.assertFalse(r.public_catalog(None)['enabled'])
        with self.assertRaises(ValueError):r.public_case(None,'blind_035')
    def test_loader_rebuilds_and_checks_36_frozen_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);private=root/'REVIEW_LOCAL_PRIVATE';private.mkdir()
            source=root/r.FILE;source.write_text('{}\n')
            census=root/'census.json';census.write_text(json.dumps({'schema':'naacl2027-turn-level-census-v1',
              'source_revision':r.REVISION,'dataset':r.DATASET,'file_sha256':r.SHA256,
              'selected_count':40,'records_limit':165}))
            expected={bid:self.make_case(bid) for bid in r.CASE_IDS}
            for bid,c in expected.items():
                (private/(bid+'.json')).write_text(json.dumps(c))
            labels=root/'labels.csv'
            with labels.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=sorted(r.R1_FIELDS));w.writeheader()
                for j in range(1,41):
                    bid=f'blind_{j:03}'
                    row={k:'' for k in r.R1_FIELDS};row.update(blind_id=bid,reviewer='R1',claim_presence='yes',
                      claim_exact_quote='I updated the address.')
                    w.writerow(row)
            with patch.object(r,'sha_file',return_value=r.SHA256),patch.object(r,'_expected_cases',return_value=expected):
                result=r.load_local_real_cases(source,private,census,labels)
                self.assertEqual(len(result['cases']),36)
                self.assertEqual(len(result['R1']),36)
                self.assertNotIn('blind_001',result['cases'])
                bad=dict(expected['blind_035']);bad['agent_visible_prefix']=bad['agent_visible_prefix']+[{'role':'tool','content':'future'}]
                (private/'blind_035.json').write_text(json.dumps(bad))
                with self.assertRaises(ValueError):r.load_local_real_cases(source,private,census,labels)
    def test_source_integrity_rejects_nonpinned_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/r.FILE;source.write_text('corrupted')
            census=root/'census.json';census.write_text(json.dumps({'schema':'naacl2027-turn-level-census-v1',
              'source_revision':r.REVISION,'dataset':r.DATASET,'file_sha256':r.SHA256,
              'selected_count':40,'records_limit':165}))
            with self.assertRaisesRegex(ValueError,'SHA-256 mismatch'):
                r.load_local_real_cases(source,root,census)

class LocalRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=make_server(0)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base='http://127.0.0.1:'+str(cls.server.server_address[1])
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def test_catalog_disabled_until_local_optin(self):
        with urlopen(self.base+'/api/real-cases') as rep:
            self.assertFalse(json.load(rep)['enabled'])
    def test_get_original_denied_without_local_optin(self):
        req=Request(self.base+'/api/real-case',method='POST',data=b'{"case":"blind_035"}',headers={'Content-Type':'application/json'})
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req)
        self.assertEqual(ctx.exception.code,400)
        ctx.exception.close()
    def test_frontend_entrypoints_present(self):
        js=(ROOT/'app.js').read_text();html=(ROOT/'index.html').read_text()
        self.assertIn('/api/real-case',js);self.assertIn('id="real-select"',html)
        self.assertIn('No raw model traces are bundled',html)

if __name__=='__main__':unittest.main()
