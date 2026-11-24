"""Verified aggregate-only results; no case-level labels or predictions."""
import json, hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent/'research/final'
def load_results():
    manifest=json.loads((ROOT/'manifest.json').read_text())
    records={}
    for name,digest in manifest.items():
        data=(ROOT/name).read_bytes()
        if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Changed aggregate: '+name)
        records[name]=json.loads(data)
    dev=records['UPLOAD_EXPLORATORY_AUTO_SCORE_ONLY.json']; hold=records['UPLOAD_HELDOUT_SCORE_AGGREGATE_ONLY.json']; pub=records['UPLOAD_PUBLISHED_SCORE_AGGREGATE_ONLY.json']; guard=records['UPLOAD_RECEIPT_BINDING_GUARD_AGGREGATE_ONLY.json']
    prep=records['UPLOAD_HELDOUT_PREPARED_AGGREGATE_ONLY.json']; baseline=records['UPLOAD_PUBLISHED_FROZEN_AGGREGATE_ONLY.json']
    assert hold['R1_csv_sha256']==pub['r1_sha256'] and hold['frozen_prediction_sha256']==prep['predictions_sha256'] and pub['frozen_prediction_sha256']==baseline['published_prediction_sha256']
    return {'development':dev['claim_detection'],'holdout':{'n':hold['n_total'],'confusion':hold['confusion_vs_single_R1'],'f1':hold['f1'],'precision':hold['precision'],'recall':hold['recall']},'baseline':pub['results'],'guard':{'pairs':guard['n_pairs'],'trajectories':guard['n_trajectories'],'original_utterances':guard['n_original_utterances'],'transitions':guard['original_corpus_verdict_transitions'],'paired_results':guard['paired_results']}}
