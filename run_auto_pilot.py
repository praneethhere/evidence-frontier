#!/usr/bin/env python3
"""Run a conservative, deterministic claim/evidence linker on pinned real trajectories.

Two explicit stages make the inference/label boundary auditable:
  predict: load source-verified traces, NEVER read R1 labels, freeze private predictions.
  score: read frozen predictions + R1 single-reviewer labels, produce aggregate exploratory metrics.
"""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from field_linker import check_case, VERSION
from real_trajectories import load_local_real_cases, CASE_IDS, _load_r1, sha_file


def write_json(path,obj):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,sort_keys=True,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')


def predict(source,private,census,out_dir):
    data=load_local_real_cases(source,private,census,annotations=None)
    predictions={bid:check_case(data['cases'][bid]) for bid in sorted(CASE_IDS)}
    out_dir=Path(out_dir)
    local=out_dir/'LOCAL_PRIVATE_DO_NOT_UPLOAD'
    prediction_file=local/'frozen_predictions.json'
    write_json(prediction_file,{'schema':'naacl-frozen-auto-pilot-v1','source_sha256':data['source_sha256'],
                                'rule_version':VERSION,'predictions':predictions})
    summary={'schema':'naacl-autolinker-predict-census-v1','run_status':'COMPLETE_SOURCE_VERIFIED',
             'n_cases':len(predictions),'source_sha256':data['source_sha256'],
             'rule_version':VERSION,'predicted_claims':sum(r['claim_detected'] for r in predictions.values()),
             'verdict_counts':dict(sorted(Counter(r['verdict'] for r in predictions.values()).items())),
             'r1_labels_read':False,'private_outcomes_read':False,
             'prediction_file_sha256':sha_file(prediction_file),
             'disclaimer':'Exploratory domain rules, developed after seeing parts of R1. NOT held-out superiority.'}
    dest=out_dir/'UPLOAD_AUTO_PREDICTION_COUNTS_ONLY.json'
    write_json(dest,summary)
    print('SOURCE_VERIFIED=YES INFERENCE_WITHOUT_R1=YES CASES=',len(predictions))
    print('AUTO_VERDICTS=',summary['verdict_counts'])
    print('PRIVATE_FROZEN_PREDICTIONS=',prediction_file)
    print('AGGREGATE_ONLY=',dest)


def score(source,private,census,annotations,inputs,out_dir):
    data=load_local_real_cases(source,private,census,annotations=None)
    fixed=json.loads(Path(inputs).read_text(encoding='utf-8'))
    if fixed.get('schema')!='naacl-frozen-auto-pilot-v1' or fixed.get('source_sha256')!=data['source_sha256'] or fixed.get('rule_version')!=VERSION:
        raise ValueError('Unexpected/stale frozen predictions')
    predictions=fixed['predictions']
    if set(predictions)!=set(CASE_IDS):raise ValueError('Case set incomplete')
    labels=_load_r1(annotations,data['cases'])
    tp=fp=tn=fn=0
    yes_count=0
    evidence=Counter()
    for bid in CASE_IDS:
        result=predictions[bid]
        # Explicitly re-run local computation and compare frozen outputs; catches tampering.
        if result!=check_case(data['cases'][bid]):raise ValueError('Frozen prediction differs from deterministic rule computation: '+bid)
        r=labels[bid]
        if r['claim_presence'] not in ('yes','no'):
            raise ValueError('Cannot score uncertain/missing R1 label')
        true=r['claim_presence']=='yes';pred=result['claim_detected']
        if true and pred:tp+=1
        elif true and not pred:fn+=1
        elif not true and pred:fp+=1
        else:tn+=1
        if true:
            yes_count+=1
            evidence[(r['evidence_label'],result['verdict'] if pred else 'MISSED')]+=1
    precision=tp/(tp+fp) if tp+fp else None
    recall=tp/(tp+fn) if tp+fn else None
    f1=2*precision*recall/(precision+recall) if precision is not None and recall is not None and precision+recall else None
    metrics={'schema':'naacl-evidence-frontier-auto-pilot-score-v1','rule_version':VERSION,
       'source_sha256':data['source_sha256'],'r1_csv_sha256':sha_file(annotations),
       'frozen_predictions_sha256':sha_file(inputs),'n_unguided':36,'n_guided_excluded':4,
       'r1_completion_claims':yes_count,'claim_detection':{'TP':tp,'FP':fp,'TN':tn,'FN':fn,
         'precision':precision,'recall':recall,'f1':f1},
       'evidence_cross_tab_R1_vs_auto':[
         {'R1_label':k[0],'auto_verdict':k[1],'n':v} for k,v in sorted(evidence.items())],
       'scope':'Single-reviewer, nonrepresentative, exploratory in-domain development sample',
       'MUST_NOT_CLAIM':['No adjudicated gold','R1 was partly visible during rule design',
         'Tool receipt is not independent real-world state verification',
         'Not a held-out performance or superiority result','No R2 agreement','No natural Unknown claims in R1 pilot']}
    dest=Path(out_dir)/'UPLOAD_EXPLORATORY_AUTO_SCORE_ONLY.json'
    write_json(dest,metrics)
    print('SOURCE_VERIFIED=YES FROZEN_PREDICTIONS_VERIFIED=YES R1_SCORING=EXPLORATORY')
    print('CLAIM_DETECTION=',metrics['claim_detection'])
    print('EVIDENCE_CROSS_TAB=',metrics['evidence_cross_tab_R1_vs_auto'])
    print('AGGREGATE_ONLY=',dest)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage',choices=('predict','score'))
    for field in ('source','private-dir','census','out-dir'):
        p.add_argument('--'+field,required=True)
    p.add_argument('--annotations')
    p.add_argument('--predictions')
    a=p.parse_args()
    if a.stage=='predict':
        if a.annotations or a.predictions:p.error('Predict MUST NOT receive annotations or predictions')
        predict(a.source,a.private_dir,a.census,a.out_dir)
    else:
        if not a.annotations or not a.predictions:p.error('Score needs --annotations and --predictions')
        score(a.source,a.private_dir,a.census,a.annotations,a.predictions,a.out_dir)

if __name__=='__main__':main()
