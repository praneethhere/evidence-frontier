#!/usr/bin/env python3
"""Post-hoc target-binding repair; original frozen rules and scores remain intact.
Requires the existing audit script and frozen holdout package. No labels or private outcomes.
"""
import argparse, copy, json, sys
from pathlib import Path
from collections import Counter
import NAACL2027_receipt_binding_audit as audit

HOME=Path.home()/'Downloads'
SUP='SUPPORTED_UNDER_TOOL_CONTRACT'
UNK='UNKNOWN'
CON='CONTRADICTED_UNDER_TOOL_CONTRACT'

def guarded(case, base=None):
    """Only downgrade supported findings with inadequate identity evidence.
    Invalid/missing receipt identity is insufficient evidence, not world-state contradiction.
    No claims added, no original evidence selection changed.
    """
    base=copy.deepcopy(h.predict_safe(case) if base is None else base)
    if not any(f['verdict']==SUP for f in base['claims']): return base
    events=fl._tool_events(case['agent_visible_prefix'][:-1])
    for finding in base['claims']:
        if finding['verdict']!=SUP: continue
        ids=set(finding['evidence_message_indices'])
        invalid=[]
        for e in events:
            field=audit.TOOLS.get(e['name'])
            if not field or not {e['call_index'],e['result_index']} <= ids: continue
            p=e['payload']
            a=e['args'].get(field); b=p.get(field) if isinstance(p,dict) else None
            if not audit.valid_id(a,field) or not audit.valid_id(b,field):
                invalid.append('Missing or invalid request/receipt '+field)
            elif a.upper()!=b.upper():
                invalid.append('Request/receipt '+field+' disagree')
        if invalid:
            finding['verdict']=UNK
            finding['reason']='; '.join(invalid)+'; prior positive evidence insufficient'
    statuses={f['verdict'] for f in base['claims']}
    if CON in statuses: base['verdict']=CON
    elif UNK in statuses: base['verdict']=UNK
    else: base['verdict']=SUP
    return base

def variant(case,e,field,kind):
    c=copy.deepcopy(case); p=copy.deepcopy(e['payload'])
    if kind=='wrong_target': p[field]=audit.replacement(p[field],field,case['agent_visible_prefix'])
    elif kind=='missing_target': del p[field]
    elif kind=='malformed_target': p[field]=None
    elif kind!='format_only': raise ValueError(kind)
    c['agent_visible_prefix'][e['result_index']]['content']=json.dumps(p,sort_keys=True,indent=2,ensure_ascii=False)
    return c

def self_test():
    text='Your order #W1234567 has been successfully cancelled.'
    c={'agent_response':text,'agent_visible_prefix':[{'role':'user','content':'Cancel my order.'},{'role':'assistant','content':None,'tool_calls':[{'id':'x','function':{'name':'cancel_pending_order','arguments':'{"order_id":"#W1234567"}'}}]},{'role':'tool','name':'cancel_pending_order','tool_call_id':'x','content':'{"order_id":"#W1234567","status":"cancelled"}'},{'role':'assistant','content':text}]}
    original=h.predict_safe(c); assert original['verdict']==SUP
    assert guarded(c)==original
    event=fl._tool_events(c['agent_visible_prefix'][:-1])[0]
    for kind in ('wrong_target','missing_target','malformed_target'):
        v=variant(c,event,'order_id',kind)
        assert h.predict_safe(v)['verdict']==SUP
        assert guarded(v)['verdict']==UNK
    assert guarded(variant(c,event,'order_id','format_only'))['verdict']==SUP
    assert h.predict_safe(c)==original
    print('GUARD_SYNTHETIC_SELF_TEST=PASS')

def main():
    global h,fl
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--holdout-dir',type=Path,default=HOME/'NAACL2027_Frozen_Holdout_20261123')
    p.add_argument('--source',type=Path,default=HOME/'naacl2027_public_source/gpt-4o-20240806.jsonl')
    p.add_argument('--manifest',type=Path,default=HOME/'naacl2027_public_source/source_manifest.json')
    p.add_argument('--prior-report',type=Path,default=HOME/'naacl2027_receipt_binding_audit/UPLOAD_RECEIPT_BINDING_AGGREGATE_ONLY.json')
    p.add_argument('--out',type=Path,default=HOME/'naacl2027_receipt_binding_guard')
    p.add_argument('--self-test-only',action='store_true'); a=p.parse_args()
    sys.path.insert(0,str(a.holdout_dir.resolve()))
    import holdout as h
    import field_linker as fl
    audit.h=h; audit.fl=fl
    hashes=h.audit_frozen()
    assert Path(fl.__file__).resolve()==(a.holdout_dir/'frozen/field_linker.py').resolve()
    self_test()
    if a.self_test_only:return
    source=h.audit_source(a.source,a.manifest)
    prior=json.loads(a.prior_report.read_text())
    assert prior['audit_script_sha256']==h.hash_file(audit.__file__)
    assert prior['source_sha256']==h.hash_file(source) and prior['frozen_rule_sha256']==hashes
    candidates=h.load_candidates(source)
    original,rows=audit.audit(candidates)
    for key,val in original.items(): assert prior[key]==val, key
    print('ORIGINAL_AUDIT_REPRODUCED=YES')
    lookup={}; transitions=Counter(); finding_changes=0
    for i,cand in enumerate(candidates,1):
        c=h.case_projection(cand,i); lookup[(cand['source_line'],cand['turn_index'])]=c
        b=h.predict_safe(c); g=guarded(c,b)
        assert b['claim_detected']==g['claim_detected']
        transitions[b['verdict']+' -> '+g['verdict']]+=1
        finding_changes+=sum(x['verdict']!=y['verdict'] for x,y in zip(b['claims'],g['claims']))
    matrix=Counter(); private=[]
    for row in rows:
        c=lookup[(row['source_line'],row['turn_index'])]; field=row['id_field']
        e=next(e for e in fl._tool_events(c['agent_visible_prefix'][:-1]) if e['result_index']==row['result_index'])
        results={}
        for kind in ('format_only','wrong_target','missing_target','malformed_target'):
            v=variant(c,e,field,kind)
            b=h.predict_safe(v); g=guarded(v,b)
            bf=audit.claim_for(b,row['action']); gf=audit.claim_for(g,row['action'])
            assert bf is not None and gf is not None
            matrix[(kind,'original_finding_'+bf['verdict'])]+=1
            matrix[(kind,'guarded_finding_'+gf['verdict'])]+=1
            matrix[(kind,'original_case_'+b['verdict'])]+=1
            matrix[(kind,'guarded_case_'+g['verdict'])]+=1
            results[kind]={'original_finding':bf['verdict'],'guarded_finding':gf['verdict'],'original_case':b['verdict'],'guarded_case':g['verdict']}
        private.append({'source_line':row['source_line'],'turn_index':row['turn_index'],'action':row['action'],'result_index':row['result_index'],'results':results})
    grouped={kind:{k:v for (c,k),v in matrix.items() if c==kind} for kind in ('format_only','wrong_target','missing_target','malformed_target')}
    assert h.audit_frozen()==hashes
    h.audit_source(a.source,a.manifest)
    a.out.mkdir(parents=True,exist_ok=False)
    d=a.out/'LOCAL_PRIVATE_DO_NOT_UPLOAD';d.mkdir()
    audit.write_new(d/'pairs.json',private)
    result={'schema':'naacl-receipt-binding-guard-posthoc-v1','source_sha256':h.hash_file(source),'frozen_rule_sha256':hashes,'guard_sha256':h.hash_file(__file__),'prior_report_sha256':h.hash_file(a.prior_report),'original_audit_reproduced':True,'n_original_utterances':len(candidates),'n_pairs':len(rows),'n_trajectories':original['n_distinct_eligible_trajectories'],'original_corpus_verdict_transitions':dict(transitions),'original_corpus_finding_verdict_changes':finding_changes,'paired_results':grouped,'scope':'Post-hoc repair evaluated on the same selected receipt/action pairs; not independent validation. Missing and malformed target controls are additional synthetic variants.','limitations':['No claim detection improvement, no new human labels, no baseline superiority, no proof of persistent state.','Guard detects request/receipt ID consistency only for mapped tools; matching IDs are not sufficient for claim correctness.','Original corpus transitions measure output stability, not accuracy.','No statistical independence assumed between receipt/action pairs.'],'original_rules_modified':False,'original_annotations_read':False,'private_outcomes_used':False}
    dest=a.out/'UPLOAD_RECEIPT_BINDING_GUARD_AGGREGATE_ONLY.json';audit.write_new(dest,result)
    print('N_PAIRS=',len(rows),'N_TRAJECTORIES=',result['n_trajectories'])
    print('ORIGINAL_CORPUS_TRANSITIONS=',dict(transitions));print('ORIGINAL_FINDING_CHANGES=',finding_changes)
    print('PAIRED_RESULTS=',json.dumps(grouped,sort_keys=True));print('UPLOAD_ONLY=',dest)

if __name__=='__main__':main()
