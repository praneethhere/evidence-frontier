import json
import sys
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request,urlopen
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from server import make_server

def make_case():
    msg='Your reservation has been successfully updated to the new economy class flights on May 24, 2024.'
    prefix=[{'role':'user','content':'Please update the flight','turn_idx':0},
      {'role':'assistant','content':None,'turn_idx':1,'tool_calls':[{'id':'c1','function':{'name':'update_reservation_flights','arguments':'{"reservation_id":"M05KNL","cabin":"economy"}'},'type':'function'}]},
      {'role':'tool','content':'{"reservation_id":"M05KNL","cabin":"business"}','name':'update_reservation_flights','tool_call_id':'c1','turn_idx':2},
      {'role':'assistant','content':msg,'turn_idx':3}]
    return {'schema':'naacl-evidence-frontier-turn-prefix-v1','blind_id':'blind_035','task_domain':'airline',
            'turn_type':'intermediate','agent_response':msg,'agent_visible_prefix':prefix,'missing_tool_response_links':0}

class AutoAPITests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
    cls.case=make_case()
    cls.real={'cases':{'blind_035':cls.case}, 'R1':{'blind_035':{'claim_presence':'no','evidence_label':'supported_under_tool_contract'}}}
    cls.server=make_server(0,cls.real)
    cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
    cls.thread.start()
    cls.base=f'http://127.0.0.1:{cls.server.server_address[1]}'
 @classmethod
 def tearDownClass(cls):
    cls.server.shutdown();cls.server.server_close();cls.thread.join()
 def post(self,bid):
    req=Request(self.base+'/api/real-auto',method='POST',data=json.dumps({'case':bid}).encode(),headers={'Content-Type':'application/json'})
    with urlopen(req) as resp:return json.load(resp)
 def test_verified_prefix_contradiction(self):
    result=self.post('blind_035')
    self.assertEqual(result['verdict'],'CONTRADICTED_UNDER_TOOL_CONTRACT')
    self.assertIn(2,result['claims'][0]['evidence_message_indices'])
    self.assertNotIn('ground_truth',json.dumps(result))
    self.assertNotIn('R1',json.dumps(result))
 def test_r1_cannot_change_prediction(self):
    before=self.post('blind_035')
    self.real['R1']['blind_035']['evidence_label']='contradicted'
    self.assertEqual(before,self.post('blind_035'))
 def test_guided_case_denied(self):
    with self.assertRaises(HTTPError) as x:self.post('blind_001')
    self.assertEqual(x.exception.code,400);x.exception.close()
 def test_no_future_oracle_fields_exposed(self):
    out=self.post('blind_035')
    self.assertFalse(out['uses_later_messages'])
    self.assertFalse(out['uses_private_outcome'])

if __name__=='__main__':unittest.main()
