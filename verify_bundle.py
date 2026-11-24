#!/usr/bin/env python3
"""Offline integrity and scope check (no network, no original language corpus)."""
from server import load_files
from study import load_study,probe_public,study_public
from stress import build, execute
from release_results import load_results

if __name__=='__main__':
    visible=load_files()
    study=load_study()
    probe=probe_public(study)
    human=study_public(study)
    print('INTEGRITY=PASS_PINNED_SOURCE_HASHES')
    print('SCRIPTED_TRACES=',len(visible),'SCRIPTED_PROBE_RUNS=',len(probe['runs']))
    print('READBACK_POSITIVES=',probe['readback_positive_count'],'FULL_TASK_CERTIFICATIONS=',probe['full_task_certified_count'])
    print('HUMAN_R1_CASES=',human['R1_all']['n'],'UNGUIDED_R1=',human['R1_unguided']['n'])
    print('BASELINE=',human['published_tool'],human['published_version'],'CONFIGURATIONS=',len(human['comparisons']))
    print('REAL_LLM_PROBE_EXPERIMENT=NO NEW_NLP_ACCURACY_MEASURED=NO')

    result=load_results()
    pairs=build()
    for kind in ('original','format_only','wrong_target','missing_target','malformed_target'):
        r=execute(pairs,'synthetic_cancel',kind)
        expected='SUPPORTED_UNDER_TOOL_CONTRACT' if kind in ('original','format_only') else 'UNKNOWN'
        assert r['guarded_prediction']['verdict']==expected
    print('LIVE_RECEIPT_STRESS=PASS_SYNTHETIC')
    print('FROZEN_HOLDOUT_F1=',result['holdout']['f1'])
    print('ORIGINAL_MODEL_SOURCE_BUNDLED=NO')
