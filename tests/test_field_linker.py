import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from field_linker import check_case
import json

def case(text,tools=None,additional=None):
    msgs=[{'role':'user','content':'Please complete the requested action','turn_idx':0}]
    for j,(name,args,result) in enumerate(tools or []):
        callid='call'+str(j)
        msgs.append({'role':'assistant','content':None,'turn_idx':len(msgs),'tool_calls':[{'id':callid,'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]})
        msgs.append({'role':'tool','content':result if isinstance(result,str) else json.dumps(result),'turn_idx':len(msgs),'tool_call_id':callid,'name':name})
    msgs.append({'role':'assistant','content':text,'turn_idx':len(msgs)})
    return {'schema':'naacl-evidence-frontier-turn-prefix-v1','agent_response':text,'agent_visible_prefix':msgs,'missing_tool_response_links':0}

class LinkerTests(unittest.TestCase):
 def test_real_shape_cabin_mismatch(self):
    text='Your reservation has been successfully updated to the new economy class flights on May 24, 2024. Flight HAT110 and Flight HAT172.'
    src=case(text,[('update_reservation_flights',{'reservation_id':'M05KNL','cabin':'economy'},
       {'reservation_id':'M05KNL','cabin':'business','flights':[{'flight_number':'HAT110'},{'flight_number':'HAT172'}]})])
    r=check_case(src)
    self.assertEqual(r['verdict'],'CONTRADICTED_UNDER_TOOL_CONTRACT')
    self.assertEqual(r['claims'][0]['evidence_message_indices'],[1,2])
 def test_booking_supported_receipt(self):
    r=check_case(case('Your flight has been successfully booked. Reservation ID: HATHAT. Cabin Class: Economy.',[
      ('book_reservation',{'user_id':'test'}, {'reservation_id':'HATHAT','cabin':'economy','flights':[]})]))
    self.assertEqual(r['verdict'],'SUPPORTED_UNDER_TOOL_CONTRACT')
 def test_wrong_flight_contradiction(self):
    r=check_case(case('Your flight has been successfully booked. Flight HAT111.',[
      ('book_reservation',{}, {'reservation_id':'HATHAT','flights':[{'flight_number':'HAT333'}]})]))
    self.assertEqual(r['verdict'],'CONTRADICTED_UNDER_TOOL_CONTRACT')
 def test_missing_tool_unknown(self):
    r=check_case(case('Your flight has been successfully booked.'))
    self.assertEqual(r['verdict'],'UNKNOWN')
 def test_address_positive(self):
    r=check_case(case('Your address has been successfully reverted back to:\n- **Address 1:** 667 Highland Drive\n- **City:** Denver',[
     ('modify_user_address',{'user_id':'person'}, {'address':{'address1':'667 Highland Drive','city':'Denver'}})]))
    self.assertEqual(r['verdict'],'SUPPORTED_UNDER_TOOL_CONTRACT')
 def test_wrong_street(self):
    r=check_case(case('Your address has been successfully reverted back to:\n- **Address 1:** 667 Highland Drive',[
     ('modify_user_address',{}, {'address':{'address1':'101 Highway'}})]))
    self.assertEqual(r['verdict'],'CONTRADICTED_UNDER_TOOL_CONTRACT')
 def test_return_request_scope(self):
    r=check_case(case('The return request has been successfully processed for Order #W1234567.',[
      ('return_delivered_order_items',{'order_id':'#W1234567'},{'order_id':'#W1234567','status':'return requested'})]))
    self.assertEqual(r['verdict'],'SUPPORTED_UNDER_TOOL_CONTRACT')
 def test_return_missing_one_unknown(self):
    r=check_case(case('The return requests have been successfully processed for Order #W1234567 and Order #W9999999.',[
      ('return_delivered_order_items',{'order_id':'#W1234567'},{'order_id':'#W1234567','status':'return requested'})]))
    self.assertEqual(r['verdict'],'UNKNOWN')
 def test_explicit_error_contradicts(self):
    r=check_case(case('The exchange request has been successfully processed.',[
      ('exchange_delivered_order_items',{'order_id':'#W1234567'},'Error: non-delivered order cannot be exchanged')]))
    self.assertEqual(r['verdict'],'CONTRADICTED_UNDER_TOOL_CONTRACT')
 def test_negation_no_claim(self):
    r=check_case(case('Your reservation is in basic economy class, which cannot be modified. I am unable to change the date.'))
    self.assertFalse(r['claim_detected'])
 def test_future_promise_no_claim(self):
    r=check_case(case('Please confirm and I will update your address.'))
    self.assertFalse(r['claim_detected'])
 def test_no_oracle_leakage(self):
    x=case('Your flight has been successfully booked.',[('book_reservation',{}, {'reservation_id':'ABCDEF'})])
    original=check_case(x)
    x['final_grade']={'TS':False}
    with self.assertRaises(ValueError):check_case(x)
    del x['final_grade']
    self.assertEqual(check_case(x),original)
 def test_future_not_read(self):
    x=case('Your flight has been successfully booked.')
    first=check_case(x)
    x['agent_visible_prefix'].append({'role':'tool','name':'book_reservation','content':'{}','tool_call_id':'future'})
    with self.assertRaises(ValueError):check_case(x)
    x['agent_visible_prefix'].pop()
    self.assertEqual(check_case(x),first)
 def test_not_certify_exactly_once(self):
    r=check_case(case('Your flight has been successfully booked.',[('book_reservation',{}, {'reservation_id':'ABCDEF'})]))
    self.assertIn('simulator receipt',r['warning'])

if __name__=='__main__':unittest.main()
