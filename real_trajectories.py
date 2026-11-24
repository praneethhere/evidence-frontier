"""Read-only, exact-source-verified local τ-bench claim explorer.

No raw trajectory, source mapping, or R1 annotations are bundled. The loader
reconstructs the original frozen 40-case selection from a pinned source file,
then verifies each on-disk case against its reconstructed cutoff before any
case is served. Only unguided blind_005...blind_040 are exposed.
"""
from __future__ import annotations
import csv
import hashlib
import json
from pathlib import Path
import re
from turn_intake_pinned import (
    DATASET, FILE, REVISION, SHA256, candidate_turns, choose,
)

CASE_IDS=tuple(f'blind_{i:03}' for i in range(5,41))
SELECT_SEED='naacl2027-utterance-sample-v1'
ALLOWED_CASE_KEYS={'schema','agent_response','task_domain','turn_type','terminal_stop_after_final',
                   'heuristic_completion_cue_NOT_GOLD','heuristic_mutating_tool_NOT_GOLD',
                   'missing_tool_response_links','agent_visible_prefix','blind_id'}
ALLOWED_MESSAGE_KEYS={'role','content','turn_idx','tool_calls','tool_call_id','name'}
R1_FIELDS={'blind_id','reviewer','claim_presence','claim_exact_quote','obligation_action_and_target',
           'stance','evidence_label','supporting_message_indices','uncertainty_or_contradiction_reason','notes'}


def sha_file(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()


def _expected_cases(source):
    candidates=[]
    with source.open('r',encoding='utf-8') as f:
        for i,line in enumerate(f,1):
            if i>165:break
            if not line.strip():continue
            row=json.loads(line)
            turns,rejections=candidate_turns(row,i)
            if not isinstance(rejections,str):candidates.extend(turns)
    selected=choose(candidates,40,SELECT_SEED)
    if len(selected)!=40:raise ValueError('Source selection no longer yields 40 records')
    result={}
    for i,c in enumerate(selected,1):
        if i<5:continue
        export={k:v for k,v in c.items() if k not in (
            'source_line','turn_index','heuristic_completion_cue_NOT_GOLD','heuristic_mutating_tool_NOT_GOLD')}
        export['blind_id']=f'blind_{i:03}'
        result[export['blind_id']]=export
    return result


def _check_case(case,expected,bid):
    if set(case)-ALLOWED_CASE_KEYS:raise ValueError(f'Forbidden case keys: {bid}')
    # Prefix content, cutoff, type and selected original model response must
    # match a fresh reconstruction from the original pinned dataset bytes.
    for k in ('schema','blind_id','agent_response','task_domain','turn_type','terminal_stop_after_final',
              'missing_tool_response_links','agent_visible_prefix'):
        if case.get(k)!=expected.get(k):raise ValueError(f'Case not equal to original frozen selection ({bid}, {k})')
    if case['blind_id']!=bid or not case['agent_visible_prefix']:
        raise ValueError('Missing expected case or prefix')
    if case['missing_tool_response_links']!=0:
        raise ValueError('Unlinked original tool reply; cannot show matched evidence')
    for msg in case['agent_visible_prefix']:
        if set(msg)-ALLOWED_MESSAGE_KEYS:raise ValueError('Unsupported/possibly private message field')
    tail=case['agent_visible_prefix'][-1]
    if tail.get('role')!='assistant' or tail.get('content')!=case['agent_response'] or tail.get('tool_calls'):
        raise ValueError('Case cutoff did not end at selected original assistant text')
    return case


def _load_r1(path,cases):
    if path is None:return None
    with Path(path).expanduser().open(encoding='utf-8',newline='') as f:
        reader=csv.DictReader(f)
        if set(reader.fieldnames or [])!=R1_FIELDS:raise ValueError('R1 CSV headers changed')
        rows=list(reader)
    if len(rows)!=40 or {r['blind_id'] for r in rows}!={f'blind_{i:03}' for i in range(1,41)}:
        raise ValueError('R1 CSV must contain exactly the frozen 40 cases')
    labels={}
    for r in rows:
        if r['reviewer']!='R1':raise ValueError('Unexpected reviewer')
        bid=r['blind_id']
        if bid not in cases:continue
        if r['claim_presence'] not in ('yes','no','uncertain'):
            raise ValueError('Incomplete independent R1 label')
        if r['claim_presence']=='yes':
            if not r['claim_exact_quote'] or r['claim_exact_quote'] not in cases[bid]['agent_response']:
                raise ValueError('R1 quote mismatches original model response: '+bid)
        labels[bid]={k:r[k] for k in ('claim_presence','claim_exact_quote','obligation_action_and_target',
                       'stance','evidence_label','supporting_message_indices','uncertainty_or_contradiction_reason','notes')}
    if len(labels)!=36:raise ValueError('Expected 36 R1 unguided rows')
    return labels


def load_local_real_cases(source,private_dir,census,annotations=None):
    source=Path(source).expanduser().resolve()
    private=Path(private_dir).expanduser().resolve()
    census=Path(census).expanduser().resolve()
    meta=json.loads(census.read_text(encoding='utf-8'))
    if (meta.get('schema')!='naacl2027-turn-level-census-v1' or
        meta.get('source_revision')!=REVISION or meta.get('dataset')!=DATASET or
        meta.get('file_sha256')!=SHA256 or meta.get('selected_count')!=40 or
        meta.get('records_limit')!=165 or source.name!=FILE):
        raise ValueError('Changed/fabricated source census; refusing real trace integration')
    if sha_file(source)!=SHA256:raise ValueError('Original τ-bench source SHA-256 mismatch')
    expected=_expected_cases(source)
    cases={}
    for bid in CASE_IDS:
        p=private/(bid+'.json')
        case=json.loads(p.read_text(encoding='utf-8'))
        cases[bid]=_check_case(case,expected[bid],bid)
    labels=_load_r1(annotations,cases)
    return {'cases':cases,'R1':labels,'source_sha256':SHA256,'source_revision':REVISION}


def public_catalog(data):
    if data is None:
        return {'enabled':False,'scope':'Local original-model traces not loaded. Requires pinned source, frozen private cases and source census.',
                'selected_count':0,'cases':[]}
    return {'enabled':True,'source':'AgentSuite/tau-bench-trajectories, GPT-4o model-generated turns',
            'scope':'36 unguided source-verifiable prefix cases; local only, no oracle, no future messages',
            'selected_count':len(data['cases']),'R1_reveal_available':data['R1'] is not None,
            'cases':[{'blind_id':bid,'domain':c['task_domain'],'turn_type':c['turn_type']}
                     for bid,c in sorted(data['cases'].items())]}


def public_case(data,bid):
    if data is None:raise ValueError('Original-model trace source not loaded')
    if bid not in CASE_IDS or bid not in data['cases']:
        raise ValueError('Unknown/assisted case excluded')
    c=data['cases'][bid]
    return {'blind_id':bid,'agent_response':c['agent_response'],'task_domain':c['task_domain'],
            'turn_type':c['turn_type'],'agent_visible_prefix':c['agent_visible_prefix'],
            'cutoff_rule':'Exact selected original assistant turn; later messages never included',
            'R1_label_included':False,'private_outcome_included':False,
            'model_prediction':'NOT_RUN','note':'Raw original trajectory remains on local Mac; no novel model judgment is computed.'}


def r1_reveal(data,bid):
    if data is None or data['R1'] is None:raise ValueError('No locally loaded R1 annotation')
    if bid not in CASE_IDS or bid not in data['R1']:raise ValueError('Unknown/assisted case excluded')
    return {'blind_id':bid,'reviewer':'R1','single_reviewer_only':True,'adjudicated_gold':False,
            'label':data['R1'][bid]}
