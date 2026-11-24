import copy
import hashlib
import json
import re
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import study
from server import make_server

class StudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.data=study.load_study()
    def test_pinned_source_hashes(self):
        m=json.loads((ROOT/'research/manifest.json').read_text())
        for entry in m['files']:
            self.assertEqual(hashlib.sha256((ROOT/entry['path']).read_bytes()).hexdigest(),entry['sha256'])
    def test_source_pin_and_matrix(self):
        self.assertEqual(self.data['probes']['source_pin'],'2db09fba22a0572a70639162a808906409f612a8')
        self.assertEqual(len(self.data['by_key']),16)
        self.assertEqual(set(self.data['by_key']),set((m,s) for m in study.MODES for s in study.STRATEGIES))
    def test_no_added_writes(self):
        for r in self.data['by_key'].values():
            self.assertEqual(r['refund_count'],1)
            self.assertEqual(r['mail_send_count'],1)
            self.assertFalse(r['full_task_certified'])
    def test_expected_positive_readbacks(self):
        x=study.probe_public(self.data)
        self.assertEqual(x['readback_positive_count'],5)
        self.assertEqual(x['full_task_certified_count'],0)
        positive={(r['scenario'],r['strategy']) for r in x['runs'] if r['positive_readback']}
        self.assertEqual(positive,{('none','wait_120'),('none','wait_240'),
                                   ('timeout_post','wait_120'),('timeout_post','wait_240'),
                                   ('timeout_late','wait_240')})
    def test_unknown_not_definitive_failure(self):
        x=study.probe_public(self.data)
        for r in x['runs']:
            if r['scenario']=='timeout_pre':self.assertEqual(r['mail_status'],'UNKNOWN')
            if r['strategy']=='search_now':self.assertFalse(r['positive_readback'])
    def test_no_private_outcomes_public_probe(self):
        x=json.dumps(study.probe_public(self.data))
        for forbidden in ('private_final_task_success_evaluator_only','source_mode_evaluator_only',
                          'eventual_task_success','final_task_success','final_grade','grader'):
            self.assertNotIn(forbidden,x)
    def test_reveal_separate_and_consistent(self):
        for m,expected in [('none',True),('timeout_pre',False),('timeout_post',True),('timeout_late',True)]:
            x=study.probe_reveal(self.data,m)
            self.assertIs(x['eventual_task_success'],expected)
        with self.assertRaises(ValueError):study.probe_reveal(self.data,'../../bad')
    def test_r1_and_baseline_aggregate(self):
        x=study.study_public(self.data)
        self.assertEqual(x['R1_all']['n'],40)
        self.assertEqual(x['R1_unguided']['yes'],16)
        self.assertEqual(x['R1_unguided']['no'],20)
        d={z['key']:z for z in x['comparisons']}
        self.assertEqual(d['rules_shipped']['claim_detection']['TP'],0)
        self.assertEqual(d['cascade-offline_domain_adapted']['claim_detection']['TP'],10)
        self.assertEqual(d['cascade-offline_domain_adapted']['evidence_verdicts_for_R1_yes']['abstain'],3)
    def test_aggregates_do_not_include_original_cases(self):
        x=json.dumps(study.study_public(self.data))
        self.assertNotIn('agent_response',x)
        self.assertNotIn('claim_exact_quote',x)
        self.assertNotIn('PRIVATE_BASELINE_OUTPUT',x)
    def test_fails_on_mutated_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            from shutil import copytree
            copytree(ROOT/'research',Path(tmp)/'research')
            original=study.ROOT
            try:
                study.ROOT=Path(tmp)
                f=Path(tmp)/'research'/'executed_probe_16.json'
                f.write_text(f.read_text()+' ')
                with self.assertRaisesRegex(ValueError,'hash changed'):study.load_study()
            finally:study.ROOT=original
    def test_frontend_ids_present(self):
        markup=(ROOT/'index.html').read_text()
        js=(ROOT/'app.js').read_text()
        selected=set(re.findall(r"\$\('([^']+)'\)",js))
        present=set(re.findall(r'\bid="([a-zA-Z0-9-]+)"',markup))
        self.assertEqual(selected-present,set())

class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=make_server(0)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.server.server_address[1]}'
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def get(self,path):
        with urlopen(self.base+path) as response:return json.load(response)
    def post(self,path,payload):
        req=Request(self.base+path,method='POST',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
        with urlopen(req) as response:return json.load(response)
    def test_probe_route(self):
        r=self.get('/api/probes')
        self.assertEqual(len(r['runs']),16)
        self.assertEqual(r['readback_positive_count'],5)
        self.assertNotIn('private_final_task_success_evaluator_only',json.dumps(r))
    def test_study_route(self):
        x=self.get('/api/study')
        self.assertEqual(x['published_version'],'0.1.2')
        self.assertEqual(x['R1_unguided']['n'],36)
    def test_probe_reveal_opt_in(self):
        x=self.post('/api/probe-reveal',{'scenario':'timeout_pre'})
        self.assertFalse(x['eventual_task_success'])
        self.assertTrue(x['evaluator_only'])
    def test_unknown_reveal_rejected(self):
        req=Request(self.base+'/api/probe-reveal',method='POST',data=json.dumps({'scenario':'../bad'}).encode(),headers={'Content-Type':'application/json'})
        with self.assertRaises(HTTPError) as cm:
            urlopen(req)
        self.assertEqual(cm.exception.code,400)
        cm.exception.close()
    def test_no_raw_files_route(self):
        with self.assertRaises(HTTPError) as cm:urlopen(self.base+'/research/executed_probe_16.json')
        self.assertEqual(cm.exception.code,404)
        cm.exception.close()

if __name__=='__main__':unittest.main()
