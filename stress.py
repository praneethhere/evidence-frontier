"""Execute the frozen verifier and original guard on local trace copies.
Synthetic examples are authored fixtures; source-derived pairs require explicit local opt-in.
No tool calls are issued and no predictions or annotations are changed.
"""
import copy, hashlib, json, sys
from pathlib import Path
import field_linker as fl
import NAACL2027_receipt_binding_audit as audit
import NAACL2027_receipt_binding_guard as guard
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'reproduction/holdout'))
import holdout as h
# Both imported linker modules refer to the same byte-identical frozen code.
for path, digest in [(ROOT/'field_linker.py', h.EXPECTED_FROZEN['field_linker.py']), (ROOT/'turn_intake_pinned.py',h.EXPECTED_FROZEN['turn_intake_pinned.py']), (ROOT/'NAACL2027_receipt_binding_guard.py','85e8531f92990ea24412f7523a62b5a5d58310e458102926d9a8cfe86a285cc1'), (ROOT/'NAACL2027_receipt_binding_audit.py','b86b961b172bbe78131fae7eebc5c277b0498cece8ed7ce17e695b4d8e542c70')]:
    if h.hash_file(path)!=digest: raise RuntimeError('Frozen component hash mismatch: '+path.name)
h.audit_frozen()
audit.h=h; audit.fl=fl; guard.h=h; guard.fl=fl
VARIANTS=('original','format_only','wrong_target','missing_target','malformed_target')
def fixture(text, tool, field, target, receipt):
    return {'schema':'naacl-evidence-frontier-turn-prefix-v1','agent_response':text,'missing_tool_response_links':0,'agent_visible_prefix':[
      {'role':'user','content':'Please perform the requested change.'},
      {'role':'assistant','content':None,'tool_calls':[{'id':'call-1','function':{'name':tool,'arguments':json.dumps({field:target})}}]},
      {'role':'tool','name':tool,'tool_call_id':'call-1','content':json.dumps(receipt,separators=(',',':'))},
      {'role':'assistant','content':text}]}
def defaults():
    c=fixture('Your order #W1234567 has been successfully cancelled.','cancel_pending_order','order_id','#W1234567',{'order_id':'#W1234567','status':'cancelled'})
    r=fixture('The return request has been successfully processed for Order #W7654321.','return_delivered_order_items','order_id','#W7654321',{'order_id':'#W7654321','status':'return requested'})
    a=fixture('Your reservation ABC123 has been updated to economy class.','update_reservation_flights','reservation_id','ABC123',{'reservation_id':'ABC123','cabin':'economy'})
    return {k:{'case':v,'result_index':2,'field':f,'label':name,'origin':'authored_synthetic_fixture'} for k,v,f,name in [('synthetic_cancel',c,'order_id','Synthetic · cancel order'),('synthetic_return',r,'order_id','Synthetic · request return'),('synthetic_airline',a,'reservation_id','Synthetic · update reservation')]}
def build(source=None):
    pairs=defaults()
    if source is not None:
        source=Path(source).resolve()
        if source.name!=h.FILE or h.hash_file(source)!=h.SHA256: raise ValueError('Pinned source mismatch')
        candidates=h.load_candidates(source)
        original,rows=audit.audit(candidates)
        prior=json.loads((ROOT/'research/final/UPLOAD_RECEIPT_BINDING_AGGREGATE_ONLY.json').read_text())
        if any(prior.get(k)!=v for k,v in original.items()): raise RuntimeError('Recorded audit did not reproduce')
        lookup={(c['source_line'],c['turn_index']):h.case_projection(c,i) for i,c in enumerate(candidates,1)}
        for i,row in enumerate(rows,1):
            pairs[f'corpus_{i:02}']={'case':lookup[(row['source_line'],row['turn_index'])],'result_index':row['result_index'],'field':row['id_field'],'label':f"Local pair {i:02} · {row['tool']}",'origin':'pinned_source_pair','action':row['action']}
    return pairs

def catalog(pairs):
    return {'pairs':[{'id':k,'label':v['label'],'origin':v['origin']} for k,v in pairs.items()],'variants':list(VARIANTS)}
def execute(pairs, pair, kind):
    if not isinstance(pair,str) or pair not in pairs or not isinstance(kind,str) or kind not in VARIANTS: raise ValueError('Unknown pair or condition')
    p=pairs[pair]; case=copy.deepcopy(p['case']); ix=p['result_index']; field=p['field']
    event=next(e for e in fl._tool_events(case['agent_visible_prefix'][:-1]) if e['result_index']==ix)
    modified=copy.deepcopy(case) if kind=='original' else guard.variant(case,event,field,kind)
    # Verify transformations affect exactly the selected tool message and no future evidence.
    assert case['agent_response']==modified['agent_response']
    assert all(a==b for i,(a,b) in enumerate(zip(case['agent_visible_prefix'],modified['agent_visible_prefix'])) if i!=ix)
    before=case['agent_visible_prefix'][ix]['content']; after=modified['agent_visible_prefix'][ix]['content']
    b=json.loads(before); a=json.loads(after)
    if kind in ('original','format_only'): assert a==b
    else: assert {k for k in set(a)|set(b) if k not in a or k not in b or a[k]!=b[k]}=={field}
    original=h.predict_safe(case); current=h.predict_safe(modified); guarded=guard.guarded(modified,current)
    return {'pair':pair,'origin':p['origin'],'condition':kind,'claim':case['agent_response'],'tool':event['name'],'identifier_field':field,'request':event['args'],'original_receipt':before,'selected_receipt':after,'call_index':event['call_index'],'receipt_index':ix,'claim_index':len(case['agent_visible_prefix'])-1,'original_prediction':original,'selected_prediction':current,'guarded_prediction':guarded,'live_execution':True,'tool_calls_executed':0,'source_changed':False,'note':'Selected receipt is a controlled mutation, not a real tool response.' if kind not in ('original','format_only') else 'Original observation or formatting-only control; no semantic mutation.'}
