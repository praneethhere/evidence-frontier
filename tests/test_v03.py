import copy,hashlib,json,sys,unittest
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evidence import CASES, assess, evidence_status, visible_signature, validate_visible
from baseline_pilot import run
from server import make_server

class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v={i:json.loads((ROOT/'data/agent_visible'/f'{i}.json').read_text()) for i in CASES}
    def test_original_input_integrity(self):
        manifest=json.loads((ROOT/'data/manifest_v03.json').read_text())
        for e in manifest['files']:
            self.assertEqual(hashlib.sha256((ROOT/e['path']).read_bytes()).hexdigest(),e['sha256'])
    def test_observed_pair_identical(self):
        self.assertEqual(visible_signature(self.v['episode_002']),visible_signature(self.v['episode_003']))
    def test_full_source_ack_supported(self):
        a=assess(self.v['episode_001'],self.v['episode_001']['claim'])
        self.assertEqual(a['aggregate_verdict'],'SUPPORTED_UNDER_SIMULATOR_ACK')
        self.assertEqual(a['obligations']['refund']['status'],'SUPPORTED')
        self.assertEqual(a['obligations']['customer_email']['status'],'SUPPORTED')
    def test_identical_timeouts_unknown(self):
        for i in CASES[1:]:
            a=assess(self.v[i],self.v[i]['claim'])
            self.assertEqual(a['aggregate_verdict'],'UNKNOWN')
            self.assertEqual(a['obligations']['refund']['status'],'SUPPORTED')
            self.assertEqual(a['obligations']['customer_email']['status'],'UNKNOWN')
    def test_private_truth_not_required(self):
        v=copy.deepcopy(self.v['episode_003']); self.assertNotIn('final_grade',v)
        self.assertEqual(assess(v,v['claim'])['aggregate_verdict'],'UNKNOWN')
    def test_private_oracle_leakage_fails(self):
        v=copy.deepcopy(self.v['episode_001']); v['final_grade']={'TS':True}
        with self.assertRaises(ValueError):assess(v,v['claim'])
    def test_future_event_rejected(self):
        v=copy.deepcopy(self.v['episode_002']);v['steps'][1]['t']=999
        with self.assertRaises(ValueError):assess(v,v['claim'])
    def test_response_parse_mutant_fails(self):
        v=copy.deepcopy(self.v['episode_001']);v['steps'][1]['parsed_observation']['ok']=False
        with self.assertRaises(ValueError):assess(v,v['claim'])
    def test_wrong_charge_unknown(self):
        v=copy.deepcopy(self.v['episode_001']);v['steps'][0]['args']['charge_id']='ch_orig0'
        self.assertEqual(evidence_status(v)['refund']['status'],'UNKNOWN')
    def test_missing_mail_unknown(self):
        v=copy.deepcopy(self.v['episode_001']);v['steps'].pop(1)
        v['steps'][1]['index']=1
        self.assertEqual(evidence_status(v)['customer_email']['status'],'UNKNOWN')
    def test_repeated_mail_unknown(self):
        v=copy.deepcopy(self.v['episode_001']); x=copy.deepcopy(v['steps'][1]);x['index']=2
        v['steps'].insert(2,x);v['steps'][3]['index']=3
        self.assertEqual(evidence_status(v)['customer_email']['status'],'UNKNOWN')
    def test_original_charge_language_not_supported(self):
        a=assess(self.v['episode_001'],'I refunded the original charge.')
        self.assertEqual(a['aggregate_verdict'],'OUT_OF_CONTRACT')
    def test_different_recipient_not_supported(self):
        a=assess(self.v['episode_001'],'I emailed joe@another.example.')
        self.assertNotEqual(a['aggregate_verdict'],'SUPPORTED_UNDER_SIMULATOR_ACK')
    def test_explicit_email_only_supported(self):
        a=assess(self.v['episode_001'],'I emailed the customer.')
        self.assertEqual(a['aggregate_verdict'],'SUPPORTED_UNDER_SIMULATOR_ACK')
    def test_negation_not_completion(self):
        a=assess(self.v['episode_002'],"I couldn't email the customer.")
        self.assertNotEqual(a['aggregate_verdict'],'SUPPORTED_UNDER_SIMULATOR_ACK')
    def test_descriptive_pilot(self):
        p=run(ROOT/'data')
        self.assertTrue(p['matched_visible_pair']['identical'])
        self.assertTrue(p['matched_visible_pair']['different_eventual_truth_evaluator_only'])
        self.assertEqual(p['counts']['n_scripted_episodes'],3)
        self.assertEqual(p['counts']['unknown_at_claim_time'],2)
        self.assertEqual(p['counts']['eventual_success_but_unknown_at_claim_time'],1)

class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import threading
        cls.s=make_server(0)
        cls.th=threading.Thread(target=cls.s.serve_forever,daemon=True);cls.th.start()
        cls.base=f'http://127.0.0.1:{cls.s.server_address[1]}'
    @classmethod
    def tearDownClass(cls):cls.s.shutdown();cls.s.server_close();cls.th.join()
    def post(self,route,data):
        req=Request(self.base+route,data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})
        with urlopen(req) as resp:return json.loads(resp.read())
    def test_web_page_ok(self):
        with urlopen(self.base+'/') as r:self.assertEqual(r.status,200)
    def test_evaluate_does_not_expose_private(self):
        x=self.post('/api/evaluate',{'episode':'episode_003','claim':'All requested steps completed.'})
        self.assertEqual(x['aggregate_verdict'],'UNKNOWN')
        s=json.dumps(x)
        for k in ('final_grade','late_effect_events','final_task_success','retrospective_limbo_TS'):
            self.assertNotIn(k,s)
    def test_reveal_is_explicit(self):
        x=self.post('/api/reveal',{'episode':'episode_003'})
        self.assertTrue(x['final_task_success']);self.assertEqual(x['late_commit_time'],90.9)
    def test_reject_bad_episode(self):
        with self.assertRaises(HTTPError):self.post('/api/evaluate',{'episode':'../../other','claim':'Done'})
    def test_pilot_api_no_private_rows(self):
        with urlopen(self.base+'/api/pilot') as r:x=json.load(r)
        self.assertTrue(x['matched_visible_pair'])
        self.assertNotIn('rows',x)

if __name__=='__main__':unittest.main()
