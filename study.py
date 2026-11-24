"""Integrity-checked, aggregate-only study read-model for Evidence Frontier v0.4.

This is a display adapter for already executed experiments, not a new model
or benchmark. No raw τ-bench conversations or individual annotations are used.
"""
from __future__ import annotations
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
MODES=('none','timeout_pre','timeout_post','timeout_late')
STRATEGIES=('no_probe','search_now','wait_120','wait_240')


def _read_pinned():
    manifest=json.loads((ROOT/'research/manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema')!='evidence-frontier-study-pinned-v04' or len(manifest.get('files',[]))!=3:
        raise ValueError('Invalid research manifest')
    items={}
    for entry in manifest['files']:
        rel=entry['path']
        if rel not in ('research/executed_probe_16.json', 'research/published_baselines_36.json','research/reviewer_R1_40.json'):
            raise ValueError('Unknown research source: '+str(rel))
        data=(ROOT/rel).read_bytes()
        if hashlib.sha256(data).hexdigest()!=entry['sha256']:
            raise ValueError('Pinned study hash changed: '+rel)
        items[rel]=json.loads(data)
    if len(items)!=3:raise ValueError('Duplicate research source')
    return items


def load_study():
    p=_read_pinned()
    probes=p['research/executed_probe_16.json']
    baseline=p['research/published_baselines_36.json']
    r1=p['research/reviewer_R1_40.json']
    if probes.get('schema')!='naacl-limbo-executed-read-probe-pilot-v1':
        raise ValueError('Unknown probe schema')
    if probes.get('source_pin')!='2db09fba22a0572a70639162a808906409f612a8':
        raise ValueError('Unexpected LIMBO source pin')
    if probes.get('mail_visibility_sla_seconds')!=120.0:raise ValueError('Wrong visibility SLA')
    rows=probes['results']
    if len(rows)!=16:raise ValueError('Expected exactly 16 executed probes')
    expected={(m,s) for m in MODES for s in STRATEGIES}
    indexed={}
    for row in rows:
        key=(row['source_mode_evaluator_only'],row['probe_strategy'])
        if key not in expected or key in indexed:raise ValueError('Unexpected/duplicate probe branch')
        if row['refund_count']!=1 or row['mail_send_count']!=1:raise ValueError('Unexpected write count')
        if row['full_task_certified'] is not False:raise ValueError('Unfounded full-task certification')
        if not isinstance(row['claimed_complete'],bool) or not row['claimed_complete']:
            raise ValueError('Unexpected absence of completion claim')
        if row['mail_status'] not in ('OBSERVED_POSITIVE','UNKNOWN'):
            raise ValueError('Unexpected mail status')
        if not isinstance(row['private_final_task_success_evaluator_only'],bool):
            raise ValueError('Missing private task outcome')
        if row['positive_readback'] and row['search_counts']!=[1]:
            raise ValueError('Positive probe without recorded matching search')
        if row['mail_status']=='UNKNOWN' and row['positive_readback']:
            raise ValueError('Inconsistent unknown evidence')
        if row['probe_strategy']=='no_probe':
            if row['read_probe_count']!=0 or row['search_counts']!=[]:
                raise ValueError('No-probe branch executed search')
        else:
            if row['read_probe_count']!=1 or len(row['search_counts'])!=1:
                raise ValueError('Read-probe branch missing search')
        indexed[key]=row
    if set(indexed)!=expected:raise ValueError('Missing probe branch')
    # Count described observations, never infer a statistical model success rate.
    assert len(indexed)==16
    if baseline.get('published_system')!='agent-claimcheck' or baseline.get('published_version')!='0.1.2':
        raise ValueError('Unexpected published baseline')
    if baseline.get('no_future_oracle_or_r1_labels_passed_to_baseline') is not True:
        raise ValueError('No-blindness assertion missing')
    for key in ('rules_shipped','rules_domain_adapted','cascade-offline_shipped','cascade-offline_domain_adapted'):
        z=baseline['comparison'][key]
        if z['n_cases']!=36 or z['n_R1_completion_claims']!=16 or z['n_R1_nonclaims']!=20:
            raise ValueError('Baseline denominators disagree')
        c=z['claim_detection']
        if c['TP']+c['FN']!=16 or c['TN']+c['FP']!=20:
            raise ValueError('Invalid baseline detection confusion matrix')
    if r1['annotated_rows']!=40 or r1['claim_presence_counts']['yes']!=19 or r1['claim_presence_counts']['no']!=21:
        raise ValueError('Unexpected reviewer summary')
    if r1.get('gold_labels_created') is not False or r1.get('interannotator_agreement_measured') is not False:
        raise ValueError('Misrepresented reviewer status')
    return {'probes':probes,'baseline':baseline,'r1':r1,'by_key':indexed}


def probe_public(study):
    """Public replays: excludes the evaluator's eventual success and private mode metadata.

    Scenario names are *experimental condition labels*, NEVER evidence passed to
    the claim-time decision logic. They are provided for controlled comparison.
    """
    indexed=study['by_key']
    runs=[]
    for mode in MODES:
        for strategy in STRATEGIES:
            r=indexed[(mode,strategy)]
            runs.append({'scenario':mode,'strategy':strategy,
                         'finish_virtual_seconds':r['finish_virtual_seconds'],
                         'mail_status':r['mail_status'],
                         'positive_readback':r['positive_readback'],
                         'read_probe_count':r['read_probe_count'],
                         'search_counts':r['search_counts'],
                         'full_task_certified':r['full_task_certified'],
                         'mail_send_count':r['mail_send_count'],
                         'refund_count':r['refund_count']})
    return {'schema':'evidence-frontier-v04-probe-replay-v1',
            'scope':'Recorded 16 deterministic scripted simulator runs, NOT live probe execution in this web app',
            'scenarios':list(MODES),'strategies':list(STRATEGIES),
            'runs':runs,'readback_positive_count':sum(r['positive_readback'] for r in runs),
            'full_task_certified_count':sum(r['full_task_certified'] for r in runs),
            'mail_visibility_lag_seconds':study['probes']['mail_visibility_sla_seconds'],
            'source_commit':study['probes']['source_pin'],
            'limitations':['All runs were scripted, not live LLM policies',
                           'Wait/search occurred BEFORE the final agent claim in these runs',
                           'A zero eventually-consistent search is not proof of absence',
                           'Positive sent record is not exactly-once or real-world delivery proof',
                           'Mode labels are experimental metadata, not inputs to evidence judge']}


def probe_reveal(study,mode):
    if mode not in MODES:raise ValueError('Invalid experimental scenario')
    outcomes={study['by_key'][(mode,s)]['private_final_task_success_evaluator_only'] for s in STRATEGIES}
    if len(outcomes)!=1: raise ValueError('Private outcomes inconsistent within controlled mode')
    return {'scenario':mode,'evaluator_only':True,'eventual_task_success':next(iter(outcomes)),
            'note':'Retrospective simulation truth, not information available to the agent.'}


def study_public(study):
    b=study['baseline']['comparison']
    variants=[]
    for key,title in [('rules_shipped','Rules — shipped'),('rules_domain_adapted','Rules — τ-bench adapted'),
                      ('cascade-offline_shipped','Cascade — shipped'),('cascade-offline_domain_adapted','Cascade — τ-bench adapted')]:
        x=b[key]
        variants.append({'key':key,'label':title,
                         'claim_detection':x['claim_detection'],
                         'evidence_decision_coverage_over_all_R1_yes':x['evidence_decision_coverage_over_all_R1_yes'],
                         'evidence_verdicts_for_R1_yes':x['evidence_verdicts_for_R1_yes']})
    return {'schema':'evidence-frontier-v04-human-baseline-v1',
            'R1_all':{'n':40, 'yes':19,'no':21,'guided_cases':4,
                      'guided_case_ids':['blind_001','blind_002','blind_003','blind_004']},
            'R1_unguided':{'n':36,'yes':16,'no':20,
                           'labels':'Single R1 reviewer, NOT adjudicated gold and NOT completed model performance'},
            'published_tool':'agent-claimcheck','published_version':'0.1.2',
            'comparisons':variants,
            'limitations':['No second reviewer or adjudication','No unknown claim among R1 positives',
                           'Targeted, nonrepresentative 36-case selection',
                           'Adapted rules informed by pilot data; not held-out',
                           'Published checker treats receipt-only evidence as unverifiable by design',
                           'Verdict disagreements are not automatically system errors',
                           'Evidence Frontier accuracy on these 36 cases has NOT been measured']}
