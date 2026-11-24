import json, unittest, threading, urllib.request, urllib.error, copy
from pathlib import Path
from unittest.mock import patch
import stress
import server
from release_results import load_results
class StressTests(unittest.TestCase):
    def test_execution_not_lookup(self):
        with patch.object(stress.h,'predict_safe', wraps=stress.h.predict_safe) as predict, patch.object(stress.guard,'guarded', wraps=stress.guard.guarded) as guard:
            r=stress.execute(stress.build(),'synthetic_cancel','wrong_target')
            self.assertEqual(predict.call_count,2);self.assertEqual(guard.call_count,1)
            self.assertEqual(r['selected_prediction']['verdict'],stress.audit.SUP)
            self.assertEqual(r['guarded_prediction']['verdict'],'UNKNOWN')
    def test_all_variants_and_input_stability(self):
        pairs=stress.build(); old=copy.deepcopy(pairs)
        for pair in ('synthetic_cancel','synthetic_return'):
            for kind in stress.VARIANTS:
                r=stress.execute(pairs,pair,kind)
                self.assertEqual(r['selected_prediction']['verdict'],stress.audit.SUP)
                self.assertEqual(r['guarded_prediction']['verdict'],stress.audit.SUP if kind in ('original','format_only') else 'UNKNOWN')
                self.assertEqual(r['tool_calls_executed'],0)
                self.assertEqual(r['guarded_prediction']['claims'][0]['evidence_message_indices'],[1,2])
        self.assertEqual(pairs,old)
    def test_airline_counterexample(self):
        r=stress.execute(stress.build(),'synthetic_airline','wrong_target')
        self.assertEqual(r['selected_prediction']['verdict'],'CONTRADICTED_UNDER_TOOL_CONTRACT')
        self.assertEqual(r['selected_prediction'],r['guarded_prediction'])
    def test_invalid_pair_condition_and_source(self):
        for pair,kind in [('unknown','original'),('synthetic_cancel','made-up'),([],{}),('corpus_01','original')]:
            with self.assertRaises(ValueError):stress.execute(stress.build(),pair,kind)
        with self.assertRaises(ValueError):stress.build(Path('fake.jsonl'))
    def test_pinned_aggregates(self):
        r=load_results();self.assertEqual(r['holdout']['confusion'],{'TP':2,'FP':2,'FN':8,'TN':28});self.assertEqual(r['guard']['pairs'],42);self.assertEqual(r['guard']['original_utterances'],893)
    def test_guard_self_test(self):
        stress.guard.self_test()
class ReleaseHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s=server.make_server(0);cls.url=f'http://127.0.0.1:{cls.s.server_address[1]}';cls.t=threading.Thread(target=cls.s.serve_forever,daemon=True);cls.t.start()
    @classmethod
    def tearDownClass(cls):cls.s.shutdown();cls.s.server_close();cls.t.join()
    def get(self,path):
        with urllib.request.urlopen(self.url+path) as r:return json.load(r)
    def post(self,path,payload):
        req=urllib.request.Request(self.url+path,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req) as r:return json.load(r)
    def test_catalog_default_only_synthetic(self):
        r=self.get('/api/stress');self.assertEqual(len(r['pairs']),3);self.assertTrue(all(p['origin']=='authored_synthetic_fixture' for p in r['pairs']));self.assertFalse(self.get('/api/real-cases')['enabled'])
    def test_http_execution_all_conditions(self):
        for kind in stress.VARIANTS:
            r=self.post('/api/stress',{'pair':'synthetic_cancel','condition':kind});self.assertTrue(r['live_execution']);self.assertEqual(r['guarded_prediction']['verdict'],stress.audit.SUP if kind in ('original','format_only') else 'UNKNOWN')
    def test_bad_payload(self):
        with self.assertRaises(urllib.error.HTTPError) as c:self.post('/api/stress',{'pair':'corpus_01','condition':'original'})
        self.assertEqual(c.exception.code,400);c.exception.close()
    def test_no_file_oracle_endpoint(self):
        for path in ['/research/final/UPLOAD_HELDOUT_SCORE_AGGREGATE_ONLY.json','/data/evaluator_private/episode_001.json','/NAACL2027_receipt_binding_guard.py']:
            with self.assertRaises(urllib.error.HTTPError) as c:self.get(path)
            self.assertEqual(c.exception.code,404);c.exception.close()
    def test_html_and_results(self):
        with urllib.request.urlopen(self.url+'/') as r: html=r.read().decode()
        for x in ('stress-pair','stress-run','stress-before','stress-after','final-metrics','guard-matrix'):self.assertIn(f'id="{x}"',html)
        self.assertEqual(self.get('/api/final-results')['holdout']['recall'],.2)
