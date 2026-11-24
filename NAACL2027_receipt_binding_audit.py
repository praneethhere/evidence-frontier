#!/usr/bin/env python3
"""Post-hoc, read-only receipt-binding stress test. No R1 or benchmark outcomes.
Run with the already-installed NAACL2027_Frozen_Holdout_20261123 package.
Synthetic receipt corruption is not a natural agent error or an accuracy label.
"""
import argparse
import copy
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HOME = Path.home() / 'Downloads'
TOOLS = {
    'cancel_pending_order': 'order_id',
    'modify_pending_order_items': 'order_id',
    'return_delivered_order_items': 'order_id',
    'exchange_delivered_order_items': 'order_id',
    'cancel_reservation': 'reservation_id',
    'update_reservation_flights': 'reservation_id',
    'update_reservation_baggages': 'reservation_id',
    'update_reservation_cabin': 'reservation_id',
    'update_reservation': 'reservation_id',
}
SUP = 'SUPPORTED_UNDER_TOOL_CONTRACT'

def valid_id(value, field):
    pattern = r'#W\d{7,9}' if field == 'order_id' else r'[A-Z0-9]{6}'
    return isinstance(value, str) and re.fullmatch(pattern, value, re.I) is not None

def replacement(original, field, prefix):
    # Preserve identifier shape and avoid existing visible identifiers.
    text = json.dumps(prefix, ensure_ascii=False).upper()
    for k in range(10000):
        if field == 'order_id':
            value = '#W' + str(10**(len(original)-3) + k).zfill(len(original)-2)
        else:
            value = 'Z' + format(k, '05X')
        if value.upper() not in text and value.upper() != original.upper():
            return value
    raise ValueError('No unused synthetic identifier')

def write_new(path, obj):
    with path.open('x', encoding='utf8') as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write('\n')

def case_of(candidate, idx):
    return h.case_projection(candidate, idx)

def claim_for(result, action):
    hits = [c for c in result.get('claims', []) if c.get('action') == action]
    return hits[0] if len(hits) == 1 else None

def variants(case, event, field, action):
    idx = event['result_index']
    control = copy.deepcopy(case)
    mutated = copy.deepcopy(case)
    payload = event['payload']
    new_id = replacement(payload[field], field, case['agent_visible_prefix'])
    control['agent_visible_prefix'][idx]['content'] = json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False)
    changed = dict(payload)
    changed[field] = new_id
    mutated['agent_visible_prefix'][idx]['content'] = json.dumps(changed, sort_keys=True, indent=2, ensure_ascii=False)
    # Assert precisely one semantic field changes, the request and utterance do not.
    assert {k for k in payload if payload[k] != changed[k]} == {field}
    for i in range(len(case['agent_visible_prefix'])):
        if i != idx:
            assert case['agent_visible_prefix'][i] == control['agent_visible_prefix'][i] == mutated['agent_visible_prefix'][i]
    assert json.loads(control['agent_visible_prefix'][idx]['content']) == payload
    assert control['agent_response'] == mutated['agent_response'] == case['agent_response']
    out = {}
    for name, c in [('control', control), ('wrong_target', mutated)]:
        pred = h.predict_safe(c)
        finding = claim_for(pred, action)
        out[name] = {'finding_verdict': finding['verdict'] if finding else 'MISSING_FINDING',
                     'case_verdict': pred['verdict']}
    return out, new_id

def audit(candidates):
    census = Counter()
    natural = Counter()
    by_field = defaultdict(Counter)
    receipt_seen = set()
    trial_seen = set()
    eligible_trajectories = set()
    private = []
    for i, cand in enumerate(candidates, 1):
        case = case_of(cand, i)
        line = cand['source_line']
        census['candidate_utterances'] += 1
        if case['missing_tool_response_links']:
            census['incomplete_tool_links'] += 1
            continue
        try:
            events = fl._tool_events(case['agent_visible_prefix'][:-1])
        except (ValueError, TypeError, KeyError, AttributeError):
            census['event_parse_failure'] += 1
            continue
        # Natural receipt census: count each observed tool result once per trajectory.
        for e in events:
            field = TOOLS.get(e['name'])
            if not field:
                continue
            key = (line, e['result_index'])
            if key in receipt_seen:
                continue
            receipt_seen.add(key)
            natural['listed_write_receipts'] += 1
            p = e['payload']
            if e['error'] or not isinstance(p, dict):
                natural['error_or_non_object'] += 1
                continue
            if not valid_id(e['args'].get(field), field) or not valid_id(p.get(field), field):
                natural['missing_or_nonstandard_identifier'] += 1
                continue
            natural['both_identifiers_present'] += 1
            if e['args'][field].upper() != p[field].upper():
                natural['natural_request_response_id_disagreement'] += 1
            else:
                natural['natural_request_response_id_agreement'] += 1
        result = h.predict_safe(case)
        census['original_' + result['verdict']] += 1
        if result['verdict'] != SUP:
            continue
        for finding in result['claims']:
            census['supported_findings_examined'] += 1
            ids = set(finding['evidence_message_indices'])
            cited = [e for e in events if e['result_index'] in ids and e['call_index'] in ids]
            if len(cited) != 1:
                census['excluded_not_single_cited_receipt'] += 1
                continue
            e = cited[0]
            field = TOOLS.get(e['name'])
            p = e['payload']
            if not field or e['error'] or not isinstance(p, dict):
                census['excluded_no_eligible_object_receipt'] += 1
                continue
            a, b = e['args'].get(field), p.get(field)
            if not valid_id(a, field) or not valid_id(b, field) or a.upper() != b.upper():
                census['excluded_unmatched_or_missing_request_response_id'] += 1
                continue
            # Require one explicit, unambiguous identity in the unchanged text,
            # using the frozen extractor's own interpretation, not human labels.
            features = fl._field_claims(case['agent_response'])
            extracted = features['orders' if field == 'order_id' else 'reservation_ids']
            if extracted != [a.upper()]:
                census['excluded_no_single_explicit_matching_text_id'] += 1
                continue
            key = (line, e['result_index'], finding['action'])
            if key in trial_seen:
                census['excluded_repeated_receipt_action'] += 1
                continue
            trial_seen.add(key)
            eligible_trajectories.add(line)
            outcomes, new_id = variants(case, e, field, finding['action'])
            counter = by_field[field]
            counter['eligible_pairs'] += 1
            if outcomes['control']['finding_verdict'] != SUP or outcomes['control']['case_verdict'] != SUP:
                counter['format_control_failed'] += 1
            else:
                counter['format_control_passed'] += 1
                counter['wrong_target_finding_' + outcomes['wrong_target']['finding_verdict']] += 1
                counter['wrong_target_case_' + outcomes['wrong_target']['case_verdict']] += 1
            private.append({'source_line': line, 'turn_index': cand['turn_index'],
                            'action': finding['action'], 'tool': e['name'], 'id_field': field,
                            'original_id': a, 'synthetic_wrong_id': new_id, 'result_index': e['result_index'],
                            'outcomes': outcomes})
    return {'census': dict(census), 'natural_receipt_census': dict(natural),
            'paired_results_by_id_field': {k: dict(v) for k,v in sorted(by_field.items())},
            'n_eligible_pairs': len(trial_seen), 'n_distinct_eligible_trajectories': len(eligible_trajectories)}, private

def self_test():
    def fixture(field, tool, action_text, payload, n):
        value = payload[field]
        return {'schema':'naacl-evidence-frontier-turn-prefix-v1','source_line':n,'turn_index':3,
                'task_domain':'retail' if field=='order_id' else 'airline','turn_type':'intermediate',
                'terminal_stop_after_final':False,'agent_response':action_text,'missing_tool_response_links':0,
                'agent_visible_prefix':[{'role':'user','content':'Please make the requested change.'},
                    {'role':'assistant','content':None,'tool_calls':[{'id':'x','function':{'name':tool,'arguments':json.dumps({field:value})}}]},
                    {'role':'tool','name':tool,'tool_call_id':'x','content':json.dumps(payload)},
                    {'role':'assistant','content':action_text}]}
    order=fixture('order_id','cancel_pending_order','Your order #W1234567 has been successfully cancelled.',{'order_id':'#W1234567','status':'cancelled'},1)
    airline=fixture('reservation_id','update_reservation_flights','Your reservation ABC123 has been updated to economy class.',{'reservation_id':'ABC123','cabin':'economy'},2)
    report, rows = audit([order, airline, copy.deepcopy(order)])
    assert report['n_eligible_pairs']==2, report
    assert report['natural_receipt_census']['both_identifiers_present']==2, report
    assert report['paired_results_by_id_field']['order_id']['wrong_target_finding_'+SUP]==1, report
    assert report['paired_results_by_id_field']['reservation_id']['wrong_target_finding_CONTRADICTED_UNDER_TOOL_CONTRACT']==1, report
    assert all(v['format_control_passed']==1 for v in report['paired_results_by_id_field'].values()), report
    # No accidental mutation of the original fixture.
    assert json.loads(order['agent_visible_prefix'][2]['content'])['order_id']=='#W1234567'
    print('SYNTHETIC_SELF_TEST=PASS (2 distinct receipt/action pairs; not corpus evidence)')

def main():
    global h, fl
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--holdout-dir',type=Path,default=HOME/'NAACL2027_Frozen_Holdout_20261123')
    p.add_argument('--source',type=Path,default=HOME/'naacl2027_public_source/gpt-4o-20240806.jsonl')
    p.add_argument('--manifest',type=Path,default=HOME/'naacl2027_public_source/source_manifest.json')
    p.add_argument('--out',type=Path,default=HOME/'naacl2027_receipt_binding_audit')
    p.add_argument('--self-test-only',action='store_true')
    args=p.parse_args()
    sys.path.insert(0,str(args.holdout_dir.resolve()))
    import holdout as h
    import field_linker as fl
    hashes=h.audit_frozen()
    assert Path(fl.__file__).resolve()==(args.holdout_dir/'frozen/field_linker.py').resolve()
    self_test()
    if args.self_test_only:
        return
    source=h.audit_source(args.source,args.manifest)
    candidates=h.load_candidates(source)
    report, details=audit(candidates)
    assert h.audit_frozen()==hashes
    h.audit_source(args.source,args.manifest)
    report.update({'schema':'naacl-receipt-binding-posthoc-v1', 'source_sha256':h.hash_file(source),
                   'frozen_rule_sha256':hashes,'audit_script_sha256':h.hash_file(Path(__file__)),
                   'scope':'Post-hoc entire pinned corpus, includes previous development and holdout trajectories; no new labels or new model runs.',
                   'limitations':['Synthetic wrong-target receipts are malformed/inconsistent observations, not naturally occurring model errors.',
                                  'Selection is conditional on existing supported verdicts, one cited receipt, explicit matching identifier and distinct receipt/action.',
                                  'An unchanged Supported verdict demonstrates failure to reject that inconsistent witness, not a proven false world-state claim.',
                                  'No baseline comparison or new NLP accuracy measurement; no human usefulness claim.'],
                   'human_labels_read':False,'private_outcomes_used':False,'original_files_modified':False})
    args.out.mkdir(parents=True,exist_ok=False)
    private=args.out/'LOCAL_PRIVATE_DO_NOT_UPLOAD';private.mkdir()
    write_new(private/'receipt_pairs.json',details)
    dest=args.out/'UPLOAD_RECEIPT_BINDING_AGGREGATE_ONLY.json';write_new(dest,report)
    print('CORPUS_SOURCE_AND_FROZEN_RULES=PASS')
    print('CANDIDATE_UTTERANCES=',len(candidates))
    print('NATURAL_RECEIPT_CENSUS=',report['natural_receipt_census'])
    print('ELIGIBLE_PAIRS=',report['n_eligible_pairs'],'DISTINCT_TRAJECTORIES=',report['n_distinct_eligible_trajectories'])
    print('PAIRED_RESULTS=',report['paired_results_by_id_field'])
    print('UPLOAD_ONLY=',dest)

if __name__=='__main__':main()
