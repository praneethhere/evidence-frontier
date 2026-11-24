import csv, hashlib, json, sys, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import holdout as h

class FrozenHoldoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.source=Path(cls.tmp.name)/'fixture.jsonl'
        with cls.source.open('w',encoding='utf8') as f:
            for i in range(165):
                act=('modify_user_address' if i%2==0 else 'book_reservation')
                user='Can you help me update an address?' if i%2==0 else 'Please book a flight.'
                content=('Your address has been successfully updated to: 1 Main St' if i%4<2 else 'Could you confirm the new address?') if i%2==0 else ('The reservation has been successfully booked.' if i%4<2 else 'Which flight would you prefer?')
                payload={'address':{'address1':'1 Main St'}} if i%2==0 else {'reservation_id':'ABC123','flights':[]}
                msgs=[{'role':'system','content':'Test'}, {'role':'user','content':user},
                     {'role':'assistant','content':None,'tool_calls':[{'id':'a','type':'function','function':{'name':act,'arguments':json.dumps({'user_id':'example'})}}]},
                     {'role':'tool','name':act,'tool_call_id':'a','content':json.dumps(payload)},
                     {'role':'assistant','content':content},
                     {'role':'user','content':'###STOP###'}]
                f.write(json.dumps({'task_name':'retail' if i%2==0 else 'airline','messages':msgs,'reward':1.0 if i%3==0 else 0.0})+'\n')
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_frozen_hashes(self):self.assertEqual(len(h.audit_frozen()),2)
    def test_disjoint_selection(self):
        c,m,old,pool=h.make_selection(self.source)
        self.assertEqual(len(c),40);self.assertEqual(len(m),40)
        self.assertTrue(all(x['source_line'] not in old for x in m))
        self.assertEqual(len({x['source_line'] for x in m}),40)
        self.assertGreaterEqual(pool,40)
    def test_no_private_oracle(self):
        c,m,old,pool=h.make_selection(self.source)
        self.assertNotIn('reward',repr(c))
        self.assertTrue(all('reward' not in x for case in c for x in case['agent_visible_prefix']))
        self.assertTrue(all(x['agent_visible_prefix'][-1]['content']==x['agent_response'] for x in c))
        self.assertTrue(all(x['blind_id'].startswith('heldout_') for x in c))
    def test_determinism(self):
        a=h.make_selection(self.source)[1];b=h.make_selection(self.source)[1]
        self.assertEqual(a,b)
    def test_no_raw_or_predictions_in_html(self):
        c,_,_,_=h.make_selection(self.source);page=h._html(c)
        self.assertNotIn('frozen_predictions',page)
        self.assertNotIn('reward',page)
        self.assertIn('textContent=c.agent_response',page)
        self.assertIn('function importCSV(',page)
    def test_unknown_on_unprocessable_not_dropped(self):
        c,m,_,_=h.make_selection(self.source)
        mutate=dict(c[0]);mutate['missing_tool_response_links']=1
        r=h.predict_safe(mutate)
        self.assertEqual(r['verdict'],'UNPROCESSABLE')
        self.assertIsNone(r['claim_detected'])
    def test_end_to_end_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(h,'audit_source',return_value=self.source):
            root=Path(temp)/'experiment'
            args=SimpleNamespace(source=str(self.source),source_manifest='ignored',out_dir=str(root),r1=None,r2=None)
            h.prepare(args)
            report=json.loads((root/'UPLOAD_HELDOUT_PREPARED_AGGREGATE_ONLY.json').read_text())
            self.assertEqual(report['n'],40)
            self.assertEqual(report['overlap_with_previous_source_trajectories'],0)
            p=root/'LOCAL_PRIVATE_DO_NOT_UPLOAD'
            self.assertTrue((p/'BLIND_REVIEW_LOCAL.html').exists())
            self.assertTrue((p/'frozen_predictions.json').exists())
            with self.assertRaisesRegex(ValueError,'overwrite'):h.prepare(args)
            cases=json.loads((p/'cases.json').read_text())['cases']
            csvpath=Path(temp)/'R1.csv'
            with csvpath.open('w',newline='',encoding='utf8') as f:
                writer=csv.DictWriter(f,fieldnames=h.REVIEW_COLUMNS)
                writer.writeheader()
                for case in cases:
                    writer.writerow({'blind_id':case['blind_id'],'reviewer':'R1','claim_presence':'no','notes':'Independently reviewed'})
            args.r1=str(csvpath)
            h.score(args)
            results=json.loads((root/'UPLOAD_HELDOUT_SCORE_AGGREGATE_ONLY.json').read_text())
            self.assertEqual(results['n_total'],40)
            self.assertFalse(results['benchmark_truth_used'])
            self.assertEqual(results['source_trajectory_overlap_with_development'],0)
            # Tampering with frozen rule results invalidates the scoring run.
            pred=p/'frozen_predictions.json'
            pred.write_text(pred.read_text()+' ',encoding='utf8')
            with self.assertRaisesRegex(ValueError,'Changed frozen artifact'):h.score(args)
    def test_label_quote_rejects_paraphrase(self):
        c,_,_,_=h.make_selection(self.source)
        rows=[]
        for case in c:
            rows.append({'blind_id':case['blind_id'],'reviewer':'R1','claim_presence':'no',
                         'claim_exact_quote':'','stance':'','evidence_label':'',
                         'obligation_action_and_target':'','supporting_message_indices':'',
                         'uncertainty_or_contradiction_reason':'','notes':''})
        rows[0].update(claim_presence='yes',claim_exact_quote='This is my paraphrase',stance='asserted_complete',
                       evidence_label='supported_under_tool_contract',obligation_action_and_target='booking')
        with tempfile.TemporaryDirectory() as tmp:
            csvpath=Path(tmp)/'a.csv'
            with csvpath.open('w',newline='',encoding='utf8') as f:
                w=csv.DictWriter(f,fieldnames=h.REVIEW_COLUMNS);w.writeheader();w.writerows(rows)
            with self.assertRaisesRegex(ValueError,'Nonexact claim quote'):h._read_labels(csvpath,c,'R1')

if __name__=='__main__':unittest.main()

class PublishedAdapterFrozenTests(unittest.TestCase):
    def test_published_adapter_pinned(self):
        import baseline_frozen as b
        self.assertEqual(h.hash_file(ROOT/'frozen'/'adapter.py'),b.ADAPTER_HASH)
        self.assertEqual(h.hash_file(ROOT/'frozen'/'tau_rules.yaml'),b.RULES_HASH)
    def test_mapping_retains_agent_response_and_excludes_oracle(self):
        from adapter import convert_case
        c={'schema':'naacl-evidence-frontier-turn-prefix-v1','blind_id':'blind_001',
           'task_domain':'airline','turn_type':'intermediate',
           'missing_tool_response_links':0,'agent_response':'Booking is confirmed.',
           'terminal_stop_after_final':False,
           'agent_visible_prefix':[
                {'role':'system','content':'Airline policy'},
                {'role':'user','content':'Please book.'},
                {'role':'assistant','content':None,'tool_calls':[{'id':'x','function':{'name':'book_reservation','arguments':'{}'},'type':'function'}]},
                {'role':'tool','name':'book_reservation','tool_call_id':'x','content':'{"reservation_id":"ABC123"}'},
                {'role':'assistant','content':'Booking is confirmed.'}]}
        x=convert_case(c)
        self.assertEqual(x['final_claim']['text'],c['agent_response'])
        self.assertEqual(x['trace_id'],'blind_001')
        self.assertTrue(any(s['kind']=='tool_result' for s in x['steps']))
        self.assertNotIn('ground_truth',x)

class PublishedBaselineFixtureTests(unittest.TestCase):
    def test_freeze_and_score_with_fake_published_tool(self):
        import baseline_frozen as b
        import types
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as t:
            source=Path(t)/'source.jsonl'
            # Reuse fixture generator already tested above.
            FrozenHoldoutTests.setUpClass()
            try: source.write_bytes(FrozenHoldoutTests.source.read_bytes())
            finally: FrozenHoldoutTests.tearDownClass()
            root=Path(t)/'run';a=SimpleNamespace(source=str(source),source_manifest='ignore',out_dir=str(root),r1=None)
            with patch.object(h,'audit_source',return_value=source):h.prepare(a)
            class Checker:
                def __init__(self,**kwargs):pass
                def check(self,rows):
                    return [SimpleNamespace(trace_id=r['trace_id'],verdict='skipped') for r in rows]
            fake=types.ModuleType('agent_claimcheck');fake.Checker=Checker
            def load_traces(path,strict=True):
                return [json.loads(line) for line in Path(path).read_text(encoding='utf8').splitlines()]
            fake.load_traces=load_traces
            with patch.dict(sys.modules,{'agent_claimcheck':fake}),\
                 patch.object(b,'verify',return_value=(json.loads((root/'LOCAL_PRIVATE_DO_NOT_UPLOAD'/'cases.json').read_text())['cases'],root/'LOCAL_PRIVATE_DO_NOT_UPLOAD')),\
                 patch.object(b.importlib.metadata,'version',return_value='0.1.2'):
                b.run_predict(a)
            priv=root/'LOCAL_PRIVATE_DO_NOT_UPLOAD'/'PUBLISHED_BASELINE_DO_NOT_UPLOAD'
            preds=json.loads((priv/'published_predictions_PRIVATE.json').read_text())
            for k,v in preds['predictions'].items():
                self.assertEqual(len(v),40)
            self.assertEqual(len(preds['predictions']),4)
            c=json.loads((root/'LOCAL_PRIVATE_DO_NOT_UPLOAD'/'cases.json').read_text())['cases']
            anno=Path(t)/'R1.csv'
            with anno.open('w',newline='',encoding='utf8') as f:
                w=csv.DictWriter(f,fieldnames=h.REVIEW_COLUMNS);w.writeheader()
                w.writerows([{'blind_id':x['blind_id'],'reviewer':'R1','claim_presence':'no'} for x in c])
            a.r1=str(anno)
            with patch.object(b,'verify',return_value=(c,root/'LOCAL_PRIVATE_DO_NOT_UPLOAD')):
                b.score(a)
            aggregate=json.loads((root/'UPLOAD_PUBLISHED_SCORE_AGGREGATE_ONLY.json').read_text())
            self.assertEqual(aggregate['n'],40)
            self.assertEqual(set(aggregate['results']),set(b.CONFIGS))
