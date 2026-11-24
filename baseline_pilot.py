"""Three-scripted-episode descriptive comparison; no model, independent annotations or significance claims."""
from __future__ import annotations
import argparse,json,csv
from pathlib import Path
from evidence import CASES,assess,visible_signature,sha_bytes

def run(root):
    r=Path(root)
    cases={name:json.loads((r/'agent_visible'/f'{name}.json').read_text()) for name in CASES}
    private={name:json.loads((r/'evaluator_private'/f'{name}.json').read_text()) for name in CASES}
    rows=[]
    for name in CASES:
        v=cases[name]; a=assess(v,v['claim']); truth=private[name]['final_grade']['TS']
        if a['private_oracle_used'] or type(truth) is not bool: raise ValueError('Invalid evidence or private truth')
        row={'episode':name,'visible_verdict':a['aggregate_verdict'],
             'scripted_finish_only_baseline':'SUPPORTED',
             'error_means_failed_baseline':'SUPPORTED' if all(s['parsed_observation'].get('ok') is True for s in v['steps'][:-1]) else 'VIOLATED',
             'retrospective_limbo_TS_evaluator_only':truth,
             'private_mode_evaluator_only':private[name].get('mode')}
        rows.append(row)
    identical=visible_signature(cases['episode_002'])==visible_signature(cases['episode_003'])
    different_truth=private['episode_002']['final_grade']['TS']!=private['episode_003']['final_grade']['TS']
    if not (identical and different_truth):raise ValueError('Expected matching-prefix, differing-truth witness not supported')
    report={'schema':'evidence-frontier-v03-descriptive-pilot',
            'provenance':'Three deterministic scripted LIMBO episodes; claim text identical and scripted; no independent human labels or LLM results',
            'rows':rows,
            'matched_visible_pair':{'episodes':['episode_002','episode_003'],'identical':identical,'different_eventual_truth_evaluator_only':different_truth},
            'counts':{'n_scripted_episodes':len(rows),
                'supported_by_complete_visible_ack':sum(x['visible_verdict']=='SUPPORTED_UNDER_SIMULATOR_ACK' for x in rows),
                'unknown_at_claim_time':sum(x['visible_verdict']=='UNKNOWN' for x in rows),
                'finish_only_supported_despite_unknown':sum(x['scripted_finish_only_baseline']=='SUPPORTED' and x['visible_verdict']=='UNKNOWN' for x in rows),
                'error_is_failure_definitive_without_certificate':sum(x['error_means_failed_baseline']=='VIOLATED' and x['visible_verdict']=='UNKNOWN' for x in rows),
                'eventual_success_but_unknown_at_claim_time':sum(x['retrospective_limbo_TS_evaluator_only'] and x['visible_verdict']=='UNKNOWN' for x in rows)},
            'interpretation':'Descriptive sanity check only. Not extraction accuracy, error rate, benchmark result, evidence intervention, LLM experiment or novelty finding.'}
    return report

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--data',default='data');ap.add_argument('--out-dir',default='pilot_results');args=ap.parse_args()
    report=run(args.data);out=Path(args.out_dir);out.mkdir(parents=True,exist_ok=True)
    (out/'descriptive_comparison.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    with (out/'descriptive_comparison.csv').open('w',newline='') as fh:
        w=csv.DictWriter(fh,fieldnames=list(report['rows'][0]));w.writeheader();w.writerows(report['rows'])
    print('PILOT=PASS_PINNED_SCRIPTED_COMPARISON')
    print('VISIBLE_IDENTICAL_TIMEOUT_PAIR=',report['matched_visible_pair']['identical'])
    print('COUNT=',report['counts'])
    print('REPORT=',(out/'descriptive_comparison.json').resolve())
if __name__=='__main__':main()
