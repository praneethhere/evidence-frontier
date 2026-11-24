#!/usr/bin/env python3
"""Freeze agent-claimcheck v0.1.2 decisions on the same heldout cases BEFORE R1 labels.

Uses the previously developed tau-bench domain pack without changing it. All
trace-level results are PRIVATE. Outputs only aggregate counts/afterward scores.
"""
from __future__ import annotations
import argparse, importlib.metadata, json, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'frozen'))
import adapter
from holdout import (N, audit_source, audit_frozen, make_selection, hash_file,
                     _read_labels, write_json)
ADAPTER_HASH='74330204a70c81260f3ef1a399ca75f262e5271bb1f40bf0bbd74186401b8391'
RULES_HASH='3d52c626d2c93fc883f4a4326e245cdffb460e91496dcd38ad936d7153efd877'
PIN='0.1.2'
CONFIGS=('rules_shipped','rules_domain_adapted','cascade-offline_shipped','cascade-offline_domain_adapted')

def verify(root,source,manifest):
    audit_frozen()
    folder=Path(__file__).resolve().parent/'frozen'
    if hash_file(folder/'adapter.py')!=ADAPTER_HASH or hash_file(folder/'tau_rules.yaml')!=RULES_HASH:
        raise ValueError('Published adapter or pre-existing adapted rules changed')
    audit_source(source,manifest)
    private=Path(root)/'LOCAL_PRIVATE_DO_NOT_UPLOAD'
    frozen=json.loads((private/'manifest.json').read_text(encoding='utf8'))
    if frozen['prediction_sha256']!=hash_file(private/'frozen_predictions.json') or frozen['cases_sha256']!=hash_file(private/'cases.json'):
        raise ValueError('Prior prospective freeze changed')
    cases=json.loads((private/'cases.json').read_text(encoding='utf8'))['cases']
    recalculated=make_selection(Path(source))[0]
    if cases!=recalculated or len(cases)!=N:raise ValueError('Heldout cases no longer pinned')
    return cases,private

def run_predict(args):
    import agent_claimcheck
    if importlib.metadata.version('agent-claimcheck')!=PIN:
        raise ValueError('Must install published agent-claimcheck=='+PIN)
    from agent_claimcheck import Checker,load_traces
    cases,private=verify(args.out_dir,args.source,args.source_manifest)
    # Adapter's original case-ID contract expects blind_NNN: use a reversible,
    # collision-free mapping. No original trajectory text or labels added.
    converted=[];unconvertible={}
    for c in cases:
        case=dict(c);case['blind_id']=c['blind_id'].replace('heldout_','blind_')
        try:
            converted.append(adapter.convert_case(case))
        except (ValueError,KeyError,TypeError,AttributeError) as exc:
            # A hard-case schema error must stay in denominator and not make
            # the selected holdout disappear. No post-selection replacement.
            unconvertible[c['blind_id']]=type(exc).__name__
    target_dir=private/'PUBLISHED_BASELINE_DO_NOT_UPLOAD'
    if target_dir.exists() and any(target_dir.iterdir()):
        raise ValueError('Refusing to overwrite previously frozen published baseline')
    target_dir.mkdir(parents=True,exist_ok=True)
    tracepath=target_dir/'trace_input_private.jsonl'
    tracepath.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in converted),encoding='utf8')
    parsed=load_traces(str(tracepath),strict=True) if converted else []
    if len(parsed)!=len(converted):raise ValueError('Published tool silently dropped valid adapter records')
    output={}
    for conf in CONFIGS:
        mode='rules' if conf.startswith('rules') else 'cascade-offline'
        ext=(str(Path(__file__).resolve().parent/'frozen'/'tau_rules.yaml'),) if conf.endswith('domain_adapted') else ()
        checker=Checker(detector=mode,rules=ext)
        res=list(checker.check(parsed))
        if len(res)!=len(converted):raise ValueError('Missing published-baseline decisions')
        got={r.trace_id.replace('blind_','heldout_'):r.verdict for r in res}
        if any(bid in got for bid in unconvertible):raise ValueError('Adapter result collision')
        got.update({bid:'UNPROCESSABLE' for bid in unconvertible})
        if set(got)!={c['blind_id'] for c in cases}:raise ValueError('Invalid baseline output identifiers')
        output[conf]=got
    output_file=target_dir/'published_predictions_PRIVATE.json'
    write_json(output_file,{'schema':'naacl-heldout-published-v1','published_version':PIN,'predictions':output})
    summary={'schema':'naacl-heldout-published-frozen-aggregate-v1','published_version':PIN,
             'configurations':list(CONFIGS),'cases':N,'n_adapter_unprocessable':len(unconvertible),'published_prediction_sha256':hash_file(output_file),
             'rule_pack_sha256':RULES_HASH,'adapter_sha256':ADAPTER_HASH,
             'r1_labels_loaded':False,'prediction_time_before_human_labels':True,
             'scope':'Published v0.1.2 and the old domain pack frozen on trajectory-disjoint same-dataset holdout'}
    write_json(target_dir/'published_manifest_PRIVATE.json',summary)
    write_json(Path(args.out_dir)/'UPLOAD_PUBLISHED_FROZEN_AGGREGATE_ONLY.json',summary)
    print('PUBLISHED_BASELINE_FROZEN_BEFORE_REVIEW=YES 4_CONFIGS=YES N=',N)
    print('UPLOAD_ONLY=',Path(args.out_dir)/'UPLOAD_PUBLISHED_FROZEN_AGGREGATE_ONLY.json')

def score(args):
    cases,private=verify(args.out_dir,args.source,args.source_manifest)
    d=private/'PUBLISHED_BASELINE_DO_NOT_UPLOAD'
    m=json.loads((d/'published_manifest_PRIVATE.json').read_text(encoding='utf8'))
    if m['published_prediction_sha256']!=hash_file(d/'published_predictions_PRIVATE.json'):
        raise ValueError('Published predictions changed after freeze')
    data=json.loads((d/'published_predictions_PRIVATE.json').read_text(encoding='utf8'))
    gold=_read_labels(args.r1,cases,'R1')
    results={}
    for conf,pred in data['predictions'].items():
        outcomes=Counter();confusion=Counter()
        for bid,row in gold.items():
            guess=pred[bid]
            outcomes[guess]+=1
            if row['claim_presence']=='uncertain' or guess=='UNPROCESSABLE':continue
            flag=guess!='skipped'
            pos=row['claim_presence']=='yes'
            confusion['TP' if flag and pos else 'FP' if flag else 'FN' if pos else 'TN']+=1
        tp,fp,fn=confusion['TP'],confusion['FP'],confusion['FN']
        p=tp/(tp+fp) if tp+fp else None;r=tp/(tp+fn) if tp+fn else None
        f1=2*p*r/(p+r) if p is not None and r is not None and p+r else None
        results[conf]={'published_verdict_counts':dict(outcomes),'claim_detection_vs_single_R1':dict(confusion),
                       'precision':p,'recall':r,'f1':f1,'n_unprocessable':outcomes['UNPROCESSABLE']}
    aggregate={'schema':'naacl-heldout-published-score-v1','n':N,
               'frozen_prediction_sha256':m['published_prediction_sha256'],
               'r1_sha256':hash_file(args.r1),'published_version':PIN,
               'results':results,
               'limitations':['Single-reviewer labels are not gold','Adapted rules were authored after older development cases',
                              'Receipt-only and state-probe verification contracts differ',
                              'Stratified same-dataset holdout; no general domain shift']}
    target=Path(args.out_dir)/'UPLOAD_PUBLISHED_SCORE_AGGREGATE_ONLY.json'
    write_json(target,aggregate)
    print('PUBLISHED_BASELINE_SCORED=YES N=',N)
    print('UPLOAD_ONLY=',target)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage',choices=('predict','score'))
    p.add_argument('--source',required=True);p.add_argument('--source-manifest',required=True);p.add_argument('--out-dir',required=True);p.add_argument('--r1')
    a=p.parse_args()
    if a.stage=='predict':
        if a.r1:p.error('Predict must not receive --r1')
        run_predict(a)
    else:
        if not a.r1:p.error('Score requires --r1')
        score(a)
if __name__=='__main__':main()
