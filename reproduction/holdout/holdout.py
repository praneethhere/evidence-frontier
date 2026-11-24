#!/usr/bin/env python3
"""Prospective, frozen, trajectory-disjoint pilot of Evidence Frontier's v0.6 rules.

prepare: exact-source checks; exclude ALL 40 prior selected trajectories; freeze
40 new predictions BEFORE any labels; create an offline blind reviewer interface.
score: verify frozen source, code, selected cases and prediction file, then score
independent reviewer labels without any retraining or automatic correction.

All raw trajectories, label files, and case-level predictions are LOCAL PRIVATE.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'frozen'))
from turn_intake_pinned import DATASET, FILE, REVISION, SHA256, candidate_turns, choose
from field_linker import check_case, VERSION

OLD_SEED='naacl2027-utterance-sample-v1'
NEW_SEED='naacl2027-prospective-trajectory-disjoint-v1'
N=40
EXPECTED_FROZEN={
    'field_linker.py':'4cd840431a4bc583a6efc4bfea6d876973128749a944b67ee2ed4da5e23aa818',
    'turn_intake_pinned.py':'0195cb4adf00e3b8b79005e49e6ff28357c5acd316150509dad2616a90389e36',
}
REVIEW_COLUMNS=('blind_id','reviewer','claim_presence','claim_exact_quote','obligation_action_and_target','stance','evidence_label','supporting_message_indices','uncertainty_or_contradiction_reason','notes')
LABELS={'supported_under_tool_contract','contradicted','unknown','out_of_scope'}

def hash_file(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1048576), b''):h.update(chunk)
    return h.hexdigest()

def hash_text(value):return hashlib.sha256(value.encode('utf8')).hexdigest()

def write_json(path, obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,sort_keys=True,ensure_ascii=False)+'\n',encoding='utf8')

def audit_frozen():
    root=Path(__file__).resolve().parent
    for name,digest in EXPECTED_FROZEN.items():
        if hash_file(root/'frozen'/name)!=digest:raise ValueError('FROZEN_SOURCE_CHANGED: '+name)
    if VERSION!='evidence-frontier-structured-linker-exp-1':raise ValueError('Rule version changed')
    return EXPECTED_FROZEN.copy()

def audit_source(source, manifest):
    source=Path(source).expanduser().resolve()
    if source.name!=FILE or hash_file(source)!=SHA256:raise ValueError('Pinned source file hash/name mismatch')
    m=json.loads(Path(manifest).expanduser().read_text(encoding='utf8'))
    if any(m.get(k)!=v for k,v in [('dataset',DATASET),('file',FILE),('commit',REVISION),('sha256',SHA256)]):
        raise ValueError('Pinned source manifest mismatch')
    return source

def load_candidates(source):
    candidates=[]; records=0
    with source.open(encoding='utf8') as f:
        for lineno,line in enumerate(f,1):
            if lineno>165:break
            if not line.strip():continue
            records+=1
            cases, reject = candidate_turns(json.loads(line),lineno)
            if not isinstance(reject,str):candidates.extend(cases)
    if records!=165:raise ValueError('Expected exactly 165 records in pinned prefix')
    return candidates

def original_lines(candidates):
    first=choose(candidates,40,OLD_SEED)
    if len(first)!=40 or len({c['source_line'] for c in first})!=40:
        raise ValueError('Original 40-case source selection changed')
    return {c['source_line'] for c in first}

def pick_holdout(candidates):
    prior=original_lines(candidates)
    rest=defaultdict(list)
    for c in candidates:
        if c['source_line'] not in prior and c['missing_tool_response_links']==0:
            rest[c['source_line']].append(c)
    # One deterministic, cue-unaware turn per remaining source trajectory.
    reps=[]
    for line,turns in rest.items():
        reps.append(min(turns,key=lambda c:hash_text(f'{NEW_SEED}:turn:{line}:{c["turn_index"]}')))
    if len(reps)<N:raise ValueError('Insufficient source-distinct remaining trajectories')
    # Frozen, cue/domain stratification. This is intentionally NONrepresentative.
    buckets=defaultdict(list)
    for c in reps:
        key=(c['task_domain'],bool(c['heuristic_completion_cue_NOT_GOLD']))
        buckets[key].append(c)
    for key in buckets:
        buckets[key].sort(key=lambda c:hash_text(f'{NEW_SEED}:sample:{c["source_line"]}:{c["turn_index"]}'))
    # Round-robin across domains and lexical cue (NOT gold), deterministic seed.
    order=sorted(buckets,key=lambda k:(str(k[0]),str(k[1])))
    selected=[]
    while len(selected)<N and any(buckets.values()):
        for key in order:
            if len(selected)>=N:break
            if buckets[key]:selected.append(buckets[key].pop(0))
    if len(selected)!=N or len({x['source_line'] for x in selected})!=N:
        raise ValueError('Selection failed source disjointness')
    if {c['source_line'] for c in selected}&prior:raise ValueError('Development trajectory leaked')
    return selected,prior,len(reps)

def case_projection(candidate, idx):
    # Remove selection hints and hidden source identifiers from reviewer/predictor projection.
    omit={'source_line','turn_index','heuristic_completion_cue_NOT_GOLD','heuristic_mutating_tool_NOT_GOLD'}
    c={k:v for k,v in candidate.items() if k not in omit}
    c['blind_id']=f'heldout_{idx:03d}'
    return c

def predict_safe(case):
    try:return check_case(case)
    except (ValueError,TypeError,KeyError,AttributeError) as e:
        # Never silently drop a hard case after sampling. Count it as unprocessable.
        return {'claim_detected':None,'verdict':'UNPROCESSABLE','claims':[],
                'error_category':type(e).__name__,'uses_private_outcome':False,
                'uses_later_messages':False}

def _html(cases):
    shown=[{'blind_id':c['blind_id'],'domain':c['task_domain'],'turn_type':c['turn_type'],
            'agent_response':c['agent_response'],'agent_visible_prefix':c['agent_visible_prefix']} for c in cases]
    data=json.dumps(shown,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    # All original trajectory strings are inserted as JSON, rendered via textContent only.
    html=r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NAACL blind heldout review — local only</title>
<style>body{font:15px system-ui;background:#0b1525;color:#edf3fb;max-width:1000px;margin:24px auto;padding:0 16px}section{border:1px solid #304a64;background:#14243a;padding:16px;border-radius:9px;margin:14px 0}select,input,textarea,button{background:#1e3854;color:#eef7ff;border:1px solid #6885a0;border-radius:5px;padding:8px}button{cursor:pointer}label{display:block;margin:12px 0 4px}textarea{width:96%;height:75px}input{width:85%}pre{white-space:pre-wrap;word-break:break-word;background:#081526;padding:10px}details{padding:7px;border-bottom:1px solid #344960}.muted{color:#b5c7d9}#response{font-weight:600;white-space:pre-wrap}.bar{display:flex;gap:8px;flex-wrap:wrap}</style>
</head><body><h2>Evidence Frontier · prospective holdout annotation</h2><p class="muted">Independent human review. This page contains original agent-visible prefixes only. It does NOT contain machine predictions, prior R1 judgments, later tool messages or benchmark truth. Keep local and do not upload raw review packets.</p>
<section><label>Reviewer ID (use R1 or R2)</label><input id="reviewer" value="R1"/><div class="bar"><button onclick="previous()">Previous</button><select id="choose" onchange="show()"></select><button onclick="next()">Save + Next</button><button onclick="exportCSV()">Export CSV backup</button><input id="csvfile" type="file" accept=".csv" onchange="importCSV(this)" style="max-width:230px"/></div></section>
<section><h3 id="head"></h3><p id="response"></p></section>
<section><h3>Only evidence available at this turn</h3><div id="messages"></div></section>
<section><h3>Your labels — not generated by a model</h3><label>Is there an action-completion claim?</label><select id="claim_presence"><option value=""></option><option>yes</option><option>no</option><option>uncertain</option></select>
<label>Exact claim quote</label><textarea id="claim_exact_quote"></textarea><label>Action and target</label><input id="obligation_action_and_target"/><label>Stance</label><select id="stance"><option value=""></option><option>asserted_complete</option><option>pending</option><option>hedged</option><option>negated</option><option>other</option><option>uncertain</option></select>
<label>Evidence at this turn</label><select id="evidence_label"><option value=""></option><option>supported_under_tool_contract</option><option>contradicted</option><option>unknown</option><option>out_of_scope</option></select>
<label>Supporting message indices</label><input id="supporting_message_indices"/><label>Why unknown or contradicted?</label><textarea id="uncertainty_or_contradiction_reason"></textarea><label>Notes and other claims</label><textarea id="notes"></textarea><div class="bar"><button onclick="save()">Save current case</button><button onclick="next()">Save + Next</button></div><p id="status" class="muted">Export CSV periodically; browser state is not durable.</p></section>
<script>
const cases=__DATA__;const cols=['blind_id','reviewer','claim_presence','claim_exact_quote','obligation_action_and_target','stance','evidence_label','supporting_message_indices','uncertainty_or_contradiction_reason','notes'];const fields=cols.slice(2);const el=id=>document.getElementById(id);let saved={};
function options(){cases.forEach(c=>{const o=document.createElement('option');o.value=c.blind_id;o.textContent=c.blind_id;el('choose').append(o)})}
function save(){const id=el('choose').value;let row={};fields.forEach(f=>row[f]=el(f).value);saved[id]=row;el('status').textContent='Saved in this browser session. Export CSV for a durable backup.'}
function show(){const c=cases.find(x=>x.blind_id===el('choose').value);if(!c)return;el('head').textContent=c.blind_id+' · '+c.domain+' · '+c.turn_type;el('response').textContent=c.agent_response;el('messages').replaceChildren();c.agent_visible_prefix.forEach((m,i)=>{const d=document.createElement('details'),s=document.createElement('summary'),p=document.createElement('pre');s.textContent='['+i+'] '+m.role+(m.name?' · '+m.name:'');p.textContent=JSON.stringify(m,null,2);d.append(s,p);el('messages').append(d)});fields.forEach(f=>el(f).value=(saved[c.blind_id]||{})[f]||'');el('status').textContent='Review this case independently, then save.'}
function next(){save();el('choose').selectedIndex=Math.min(cases.length-1,el('choose').selectedIndex+1);show()}
function previous(){save();el('choose').selectedIndex=Math.max(0,el('choose').selectedIndex-1);show()}
function quote(s){return '"'+String(s??'').replaceAll('"','""')+'"'}
function exportCSV(){save();const rev=el('reviewer').value.trim()||'R1';const lines=[cols.map(quote).join(',')];cases.forEach(c=>{const r={blind_id:c.blind_id,reviewer:rev,...(saved[c.blind_id]||{})};lines.push(cols.map(f=>quote(r[f])).join(','))});const blob=new Blob([lines.join('\r\n')+'\r\n'],{type:'text/csv;charset=utf-8'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='heldout_annotations_'+rev+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}
function parseCSV(str){const rows=[];let row=[],cell='',q=false;for(let i=0;i<str.length;i++){const ch=str[i];if(q){if(ch==='"'&&str[i+1]==='"'){cell+='"';i++}else if(ch==='"'){q=false}else cell+=ch}else if(ch==='"')q=true;else if(ch===','){row.push(cell);cell=''}else if(ch==='\n'){row.push(cell);rows.push(row);row=[];cell=''}else if(ch!=='\r'){cell+=ch}}if(q)throw Error('Bad CSV quoting');if(cell||row.length){row.push(cell);rows.push(row)}return rows}
async function importCSV(input){if(!input.files?.length)return;try{const rows=parseCSV(await input.files[0].text());if(JSON.stringify(rows[0])!==JSON.stringify(cols))throw Error('Unexpected headers');const incoming={};for(const arr of rows.slice(1)){if(arr.length!==cols.length)throw Error('Column count mismatch');const r=Object.fromEntries(cols.map((c,i)=>[c,arr[i]]));if(!cases.some(c=>c.blind_id===r.blind_id)||incoming[r.blind_id])throw Error('Unknown/duplicate ID');if(r.reviewer!==el('reviewer').value)throw Error('Reviewer mismatch');incoming[r.blind_id]=Object.fromEntries(fields.map(f=>[f,r[f]]))}saved=incoming;show();el('status').textContent='Imported '+Object.keys(incoming).length+' rows; export a new CSV after edits.'}catch(e){alert('Import rejected: '+e.message)}finally{input.value=''}}
options();show();</script></body></html>'''
    return html.replace('__DATA__',data)

def make_selection(source):
    candidates=load_candidates(source)
    selection,old,pool=pick_holdout(candidates)
    cases=[case_projection(c,i) for i,c in enumerate(selection,1)]
    mapping=[{'id':c['blind_id'],'source_line':x['source_line'],'turn_index':x['turn_index']} for c,x in zip(cases,selection)]
    return cases,mapping,old,pool

def prepare(args):
    hashes=audit_frozen();source=audit_source(args.source,args.source_manifest)
    cases,mapping,old,pool=make_selection(source)
    root=Path(args.out_dir).expanduser().resolve();private=root/'LOCAL_PRIVATE_DO_NOT_UPLOAD'
    if root.exists() and any(root.iterdir()):raise ValueError('Refusing to overwrite existing holdout; choose a fresh --out-dir')
    private.mkdir(parents=True)
    predictions={c['blind_id']:predict_safe(c) for c in cases}
    write_json(private/'frozen_predictions.json',{'schema':'naacl-heldout-predictions-v1','predictions':predictions})
    write_json(private/'cases.json',{'schema':'naacl-heldout-cases-v1','cases':cases})
    write_json(private/'mapping.json',mapping)
    (private/'BLIND_REVIEW_LOCAL.html').write_text(_html(cases),encoding='utf8')
    freeze={'schema':'naacl-frozen-heldout-manifest-v1','source_sha256':SHA256,'source_revision':REVISION,
            'selection_seed':NEW_SEED,'old_selection_seed':OLD_SEED,'old_source_trajectories_excluded':len(old),
            'frozen_code_sha256':hashes,'n_selected':N,'prediction_sha256':hash_file(private/'frozen_predictions.json'),
            'cases_sha256':hash_file(private/'cases.json'),
            'review_html_sha256':hash_file(private/'BLIND_REVIEW_LOCAL.html'),
            'sampling_policy':'One deterministic random turn per remaining trajectory; round-robin by domain and original lexical cue; stratified targeted sample, not population representative.'}
    write_json(private/'manifest.json',freeze)
    tally=Counter((c['task_domain'],c['turn_type']) for c in cases)
    summary={'schema':'naacl-heldout-prepared-aggregate-v1','prepared':True,
             'n':N,'n_remaining_source_trajectories_with_candidates':pool,
             'development_source_trajectories_excluded':len(old),'overlap_with_previous_source_trajectories':0,
             'selection_seed':NEW_SEED,'frozen_code_sha256':hashes,
             'source_sha256':SHA256,'source_revision':REVISION,'predictions_sha256':freeze['prediction_sha256'],
             'case_counts_by_domain_turn':{str(k):v for k,v in sorted(tally.items())},
             'model_accuracy_measured':False,'review_labels_loaded':False,
             'warning':'Pre-specified rules; SAME DATASET, different source trajectories. No heldout accuracy until blind human labels. Nonrepresentative stratified sample.'}
    write_json(root/'UPLOAD_HELDOUT_PREPARED_AGGREGATE_ONLY.json',summary)
    print('HOLDOUT_PREPARED=YES SOURCE_TRAJECTORY_OVERLAP=0 COUNT=',N)
    print('PREDICTIONS_FROZEN_BEFORE_LABELS=YES')
    print('REVIEW_LOCAL=',private/'BLIND_REVIEW_LOCAL.html')
    print('UPLOAD_ONLY=',root/'UPLOAD_HELDOUT_PREPARED_AGGREGATE_ONLY.json')

def _read_labels(path,cases,reviewer):
    with Path(path).expanduser().open(newline='',encoding='utf-8-sig') as f:
        r=csv.DictReader(f)
        if tuple(r.fieldnames or ())!=REVIEW_COLUMNS:raise ValueError('Changed annotation CSV headers')
        rows=list(r)
    mapping={c['blind_id']:c for c in cases};out={}
    if len(rows)!=N:raise ValueError('Expected 40 annotation rows')
    for row in rows:
        bid=row['blind_id']
        if bid not in mapping or bid in out or row['reviewer']!=reviewer:raise ValueError('Unknown/duplicate case or reviewer: '+bid)
        val=row['claim_presence']
        if val not in ('yes','no','uncertain'):raise ValueError('Missing or invalid claim label: '+bid)
        if val=='yes':
            if row['stance'] not in ('asserted_complete','pending','hedged','negated','other','uncertain'):
                raise ValueError('Missing stance: '+bid)
            if row['evidence_label'] not in LABELS:raise ValueError('Missing evidence judgment: '+bid)
            if not row['claim_exact_quote'] or row['claim_exact_quote'] not in mapping[bid]['agent_response']:
                raise ValueError('Nonexact claim quote: '+bid)
            if not row['obligation_action_and_target'].strip():raise ValueError('Action and target missing: '+bid)
            for token in row['supporting_message_indices'].split(','):
                if token.strip():
                    if not token.strip().isdigit() or int(token.strip())>=len(mapping[bid]['agent_visible_prefix']):
                        raise ValueError('Invalid evidence index: '+bid)
        out[bid]=row
    if set(out)!=set(mapping):raise ValueError('Incomplete reviewer cases')
    return out

def score(args):
    hashes=audit_frozen();source=audit_source(args.source,args.source_manifest)
    root=Path(args.out_dir).expanduser().resolve();private=root/'LOCAL_PRIVATE_DO_NOT_UPLOAD'
    manifest=json.loads((private/'manifest.json').read_text(encoding='utf8'))
    if manifest['frozen_code_sha256']!=hashes or manifest['source_sha256']!=SHA256 or manifest['selection_seed']!=NEW_SEED:
        raise ValueError('Not matching locked code or source')
    for name,expected in [('frozen_predictions.json',manifest['prediction_sha256']),('cases.json',manifest['cases_sha256']),('BLIND_REVIEW_LOCAL.html',manifest['review_html_sha256'])]:
        if hash_file(private/name)!=expected:raise ValueError('Changed frozen artifact: '+name)
    cases,mapping,old,pool=make_selection(source)
    saved=json.loads((private/'cases.json').read_text(encoding='utf8'))
    if saved['cases']!=cases:raise ValueError('Reconstruction of frozen cases differs')
    fixed=json.loads((private/'frozen_predictions.json').read_text(encoding='utf8'))
    if fixed.get('schema')!='naacl-heldout-predictions-v1' or set(fixed['predictions'])!={c['blind_id'] for c in cases}:
        raise ValueError('Frozen predictions missing or changed')
    for case in cases:
        if fixed['predictions'][case['blind_id']]!=predict_safe(case):
            raise ValueError('Stored prediction changed from exact frozen rule computation')
    r1=_read_labels(args.r1,cases,'R1')
    r2=_read_labels(args.r2,cases,'R2') if args.r2 else None
    n_unknown_labels=sum(r['claim_presence']=='uncertain' for r in r1.values())
    confusion=Counter();evidence=Counter();unproc=0
    for bid in sorted(r1):
        label=r1[bid];prediction=fixed['predictions'][bid]
        pred=prediction.get('claim_detected')
        if pred is None:unproc+=1;continue
        if label['claim_presence']=='uncertain':continue
        yes=label['claim_presence']=='yes'
        confusion['TP' if pred and yes else 'FP' if pred and not yes else 'FN' if yes else 'TN']+=1
        if yes:
            evidence[(label['evidence_label'],prediction['verdict'] if pred else 'CLAIM_MISSED')]+=1
    tp,fp,fn=confusion['TP'],confusion['FP'],confusion['FN']
    precision=tp/(tp+fp) if tp+fp else None;recall=tp/(tp+fn) if tp+fn else None
    f1=2*precision*recall/(precision+recall) if precision is not None and recall is not None and precision+recall else None
    result={'schema':'naacl-heldout-r1-aggregate-v1','n_total':N,'n_undecidable_human_claim_presence':n_unknown_labels,
            'n_unprocessable_predictions':unproc,'source_trajectory_overlap_with_development':0,
            'human_R1_positive':sum(r['claim_presence']=='yes' for r in r1.values()),
            'human_R1_negative':sum(r['claim_presence']=='no' for r in r1.values()),
            'confusion_vs_single_R1':dict(confusion),'precision':precision,'recall':recall,'f1':f1,
            'evidence_crosstab':{str(k):v for k,v in sorted(evidence.items())},
            'frozen_prediction_sha256':manifest['prediction_sha256'],
            'frozen_rule_sha256':hashes,'R1_csv_sha256':hash_file(args.r1),
            'R2_present':r2 is not None,'benchmark_truth_used':False,
            'limitations':['Single dataset, same model and domains; trajectory-disjoint, not independent-domain evaluation',
                           'Case selection is stratified and nonrepresentative',
                           'R1 alone is not adjudicated gold','Development of v0.6 rules involved previous R1 examples',
                           'Receipt support is not independent real-world state verification']}
    if r2 is not None:
        agreed_presence=sum(r1[k]['claim_presence']==r2[k]['claim_presence'] for k in r1)
        both_yes=[k for k in r1 if r1[k]['claim_presence']==r2[k]['claim_presence']=='yes']
        agreed_evidence=sum(r1[k]['evidence_label']==r2[k]['evidence_label'] for k in both_yes)
        result.update({'R2_csv_sha256':hash_file(args.r2),
                       'reviewer_agreement_on_claim_presence':{'count':agreed_presence,'n':N},
                       'reviewer_agreement_on_evidence_given_both_yes':{'count':agreed_evidence,'n':len(both_yes)}})
    target=root/'UPLOAD_HELDOUT_SCORE_AGGREGATE_ONLY.json';write_json(target,result)
    print('HELDOUT_SCORE_COMPLETED=YES EVAL_CASES=',N,'R2_PRESENT=',bool(r2))
    print('R1_CONFUSION=',dict(confusion),'R1_F1=',f1)
    print('UPLOAD_ONLY=',target)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage',choices=('prepare','score'))
    p.add_argument('--source',required=True)
    p.add_argument('--source-manifest',required=True)
    p.add_argument('--out-dir',required=True)
    p.add_argument('--r1');p.add_argument('--r2')
    args=p.parse_args()
    if args.stage=='prepare':
        if args.r1 or args.r2:p.error('Preparation must NOT receive human labels')
        prepare(args)
    else:
        if not args.r1:p.error('Scoring requires --r1');
        score(args)
if __name__=='__main__':main()
