#!/usr/bin/env python3
"""Turn-level, claim-time intake of a pinned AgentSuite trajectory file.

No outcome labels are read. Treat outputs as annotation CANDIDATES, never as gold.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re

DATASET = 'AgentSuite/tau-bench-trajectories'
FILE = 'gpt-4o-20240806.jsonl'
REVISION = '382e57d1784b55c5155f4ef394ef48f1c747a287'
SHA256 = '718ebc29c86c691ca6b4e253ca109c4beb150887101ebeeb649d92075109b2a4'
STOP = '###STOP###'
CLAIM = re.compile(r'\b(?:successfully|complet(?:ed|e)|finished|done|booked|cancel(?:l)?ed|refunded|changed|updated|modified|upgraded|created|added|removed|processed|issued|sent|confirmed|applied)\b', re.I)
WRITE = re.compile(r'(?:^|_)(?:book|cancel|refund|change|modify|update|upgrade|create|add|remove|delete|send|issue|transfer|purchase|buy|pay|reserve|edit)(?:_|$)', re.I)
ALLOWED_FIELDS = ('role', 'content', 'turn_idx', 'tool_calls', 'tool_call_id', 'name')


def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()


def text_content(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return '\n'.join(v.get('text', '') for v in value if isinstance(v, dict) and v.get('type') in ('text','input_text') and isinstance(v.get('text'),str))
    return ''


def remove_terminal_stop(messages):
    if messages and isinstance(messages[-1],dict) and messages[-1].get('role')=='user' and isinstance(messages[-1].get('content'),str) and messages[-1]['content'].strip()==STOP:
        return messages[:-1], True
    return messages, False


def visible_projection(msg):
    return {key: msg[key] for key in ALLOWED_FIELDS if key in msg}


def action_names(prefix):
    names=[]
    for m in prefix:
        if m.get('role')!='assistant': continue
        for c in m.get('tool_calls') or []:
            if not isinstance(c,dict): continue
            f=c.get('function') or {}
            if isinstance(f,dict) and isinstance(f.get('name'),str): names.append(f['name'])
    return names


def has_missing_tool_reply(prefix):
    calls=[c.get('id') for m in prefix if m.get('role')=='assistant' for c in (m.get('tool_calls') or []) if isinstance(c,dict) and c.get('id')]
    replies={str(m.get('tool_call_id')) for m in prefix if m.get('role')=='tool' and m.get('tool_call_id')}
    return sum(str(id_) not in replies for id_ in calls)


def candidate_turns(row, source_line):
    if not isinstance(row,dict) or not isinstance(row.get('messages'),list):
        return [], 'invalid_messages'
    raw=row['messages']
    if not all(isinstance(m,dict) and isinstance(m.get('role'),str) for m in raw):
        return [], 'invalid_messages'
    msgs, stopped=remove_terminal_stop(raw)
    final_index=len(msgs)-1 if msgs and msgs[-1].get('role')=='assistant' and not msgs[-1].get('tool_calls') and text_content(msgs[-1].get('content')).strip() else -1
    out=[]; tool_seen=False; user_seen=False; excludes=Counter()
    for j,m in enumerate(msgs):
        role=m.get('role')
        if role=='user' and text_content(m.get('content')).strip(): user_seen=True
        if role=='tool': tool_seen=True
        if role!='assistant': continue
        if m.get('tool_calls'):
            if text_content(m.get('content')).strip(): excludes['text_plus_tool_calls_not_analyzed']+=1
            continue
        response=text_content(m.get('content'))
        if not response.strip(): continue
        if not (user_seen and tool_seen):
            excludes['before_tool_observation']+=1
            continue
        prefix=msgs[:j+1]
        names=action_names(prefix)
        if not names:
            excludes['no_linked_tool_calls']+=1
            continue
        # Include the original tool-call request and replies, but NEVER later messages.
        projected=[visible_projection(p) for p in prefix]
        missing=has_missing_tool_reply(prefix)
        out.append({
            'schema':'naacl-evidence-frontier-turn-prefix-v1',
            'source_line':source_line,
            'turn_index':j,
            'turn_type':'final' if j==final_index else 'intermediate',
            'terminal_stop_after_final': bool(stopped and j==final_index),
            'task_domain':str(row.get('task_name','UNKNOWN')),
            'agent_response':response,
            'heuristic_completion_cue_NOT_GOLD':bool(CLAIM.search(response)),
            'heuristic_mutating_tool_NOT_GOLD':any(WRITE.search(n) for n in names),
            'missing_tool_response_links':missing,
            'agent_visible_prefix':projected,
        })
    return out, dict(excludes)


def choose(candidates, count, seed):
    # Maximum one candidate per trajectory, to avoid repeated-source dependence.
    by_line=defaultdict(list)
    for c in candidates: by_line[c['source_line']].append(c)
    representatives=[]
    for line, options in by_line.items():
        def rank(c):
            stable=hash_bytes(f"{seed}:{line}:{c['turn_index']}".encode())
            return (-int(c['heuristic_completion_cue_NOT_GOLD']), -int(c['turn_type']=='final'), stable)
        representatives.append(sorted(options,key=rank)[0])
    # Balance heuristically claim-like vs nonclaim and domains, without asserting gold labels.
    pools=defaultdict(list)
    for c in representatives:
        key=(c['heuristic_completion_cue_NOT_GOLD'], c['task_domain'], c['turn_type'])
        pools[key].append(c)
    for key in pools: pools[key].sort(key=lambda c: hash_bytes(f"{seed}:{c['source_line']}:{c['turn_index']}".encode()))
    pos=sorted((key for key in pools if key[0]),key=str)
    neg=sorted((key for key in pools if not key[0]),key=str)
    selected=[]
    while len(selected)<count and any(pools.values()):
        for keys in (pos,neg):
            for k in keys:
                if len(selected)>=count: break
                if pools[k]: selected.append(pools[k].pop(0))
    return selected


def csv_template(ids, reviewer):
    return [dict(blind_id=id_, reviewer=reviewer, claim_presence='', claim_exact_quote='',
                 obligation_action_and_target='', stance='', evidence_label='',
                 supporting_message_indices='', uncertainty_or_contradiction_reason='', notes='') for id_ in ids]


def write_csv(path, rows):
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else list(csv_template(['x'],'R1')[0]));w.writeheader();w.writerows(rows)


def make_review_page(out_dir, selected):
    # A self-contained OFFLINE viewer. Data is embedded locally, not transmitted.
    review_data=[{
        'blind_id':f'blind_{i:03}',
        'agent_response':c['agent_response'],
        'task_domain':c['task_domain'],
        'turn_type':c['turn_type'],
        'agent_visible_prefix':c['agent_visible_prefix'],
    } for i,c in enumerate(selected,1)]
    payload=json.dumps(review_data,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    page=r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NAACL Evidence Frontier — Blind annotation (local)</title><style>
    body{font:15px system-ui,sans-serif;max-width:1060px;margin:25px auto;padding:0 20px;background:#0c1423;color:#edf3fb}a{color:#7cc9ef}.panel{background:#14243a;border:1px solid #324b65;border-radius:9px;padding:16px;margin:12px 0}pre{white-space:pre-wrap;word-break:break-word;padding:9px;background:#091527;border-radius:6px}button,select,input,textarea{padding:8px;background:#192d46;color:#fff;border:1px solid #58728a;border-radius:5px}button{cursor:pointer}label{display:block;margin:12px 0 5px}textarea{width:97%;min-height:64px}input{max-width:95%}.muted{color:#aebdd0}.msg{border-bottom:1px solid #324b65;padding:8px 0}#original{font-weight:600}.controls{display:flex;gap:10px;flex-wrap:wrap}small{color:#aebdd0}</style></head><body>
    <h1>Evidence Frontier — blind claim annotation</h1><p class="muted">Offline review only. Everything you see comes from the candidate agent-visible prefix. Later messages and benchmark outcomes are not included. Heuristic candidate labels are hidden.</p>
    <div class="panel"><label>Reviewer identity (use different independent reviewers/files)</label><input id="reviewer" placeholder="R1 or R2" value="R1"><div class="controls" style="margin-top:12px"><button onclick="prevCase()">Previous</button><select id="chooser" onchange="showCase()"></select><button onclick="nextCase()">Next</button><button onclick="exportCSV()">Export annotations CSV</button><input id="load" type="file" accept=".csv" onchange="loadCSV(this)"></div></div>
    <div class="panel"><h2 id="heading"></h2><p id="meta" class="muted"></p><div id="original"></div></div>
    <div class="panel"><h3>Agent-visible evidence up to this response</h3><div id="messages"></div></div>
    <div class="panel"><h3>Reviewer labels (NOT automated)</h3><small>If multiple independent completion claims exist, record the principal one and document additional claims in notes. A later adjudication pass may split multi-claim records.</small>
    <label>Is there an action-completion claim?</label><select id="claim_presence"><option value=""></option><option>yes</option><option>no</option><option>uncertain</option></select>
    <label>Exact claim quote (copy from response)</label><textarea id="claim_exact_quote"></textarea>
    <label>Action and target / obligation</label><input id="obligation_action_and_target" style="width:90%">
    <label>Stance</label><select id="stance"><option value=""></option><option>asserted_complete</option><option>pending</option><option>hedged</option><option>negated</option><option>other</option><option>uncertain</option></select>
    <label>Evidence judgment AT THIS TURN (not eventual truth)</label><select id="evidence_label"><option value=""></option><option>supported_under_tool_contract</option><option>contradicted</option><option>unknown</option><option>out_of_scope</option></select>
    <label>Supporting message indices (comma-separated)</label><input id="supporting_message_indices" style="width:70%">
    <label>Why unknown/contradicted?</label><textarea id="uncertainty_or_contradiction_reason"></textarea>
    <label>Notes / other claims / limitations</label><textarea id="notes"></textarea>
    <div class="controls"><button onclick="saveCase()">Save in browser session</button><button onclick="nextCase()">Save + Next</button></div><p class="muted" id="saveMessage">Export CSV regularly. Unsaved browser state is lost when page closes.</p></div>
    <script>const cases=__DATA__;let saved={}; const cols=['blind_id','reviewer','claim_presence','claim_exact_quote','obligation_action_and_target','stance','evidence_label','supporting_message_indices','uncertainty_or_contradiction_reason','notes'];const formFields=cols.slice(2);const elem=id=>document.getElementById(id);
    function textTo(node,value){node.textContent=value}function escapeCSV(s){return '"'+String(s??'').replace(/"/g,'""')+'"'}
    for(const c of cases){const o=document.createElement('option');o.value=c.blind_id;o.textContent=c.blind_id;elem('chooser').appendChild(o)}
    function saveCase(){const id=elem('chooser').value;let row={};for(const field of formFields)row[field]=elem(field).value;saved[id]=row;elem('saveMessage').textContent='Saved in this browser session. Export CSV before closing.'}
    function showCase(){const c=cases.find(x=>x.blind_id===elem('chooser').value);if(!c)return;textTo(elem('heading'),c.blind_id);textTo(elem('meta'),'Domain '+c.task_domain+' | '+c.turn_type+' utterance | prefix only');textTo(elem('original'),c.agent_response);const box=elem('messages');box.replaceChildren();c.agent_visible_prefix.forEach((m,i)=>{const section=document.createElement('div');section.className='msg';const h=document.createElement('strong');h.textContent='['+i+'] '+m.role+(m.name?' • '+m.name:'');section.appendChild(h);let pre=document.createElement('pre');pre.textContent=JSON.stringify(m,null,2);section.appendChild(pre);box.appendChild(section)});for(const field of formFields)elem(field).value=(saved[c.blind_id]||{})[field]||'';elem('saveMessage').textContent='Current case not exported yet.'}
    function prevCase(){saveCase();elem('chooser').selectedIndex=Math.max(0,elem('chooser').selectedIndex-1);showCase()}
    function nextCase(){saveCase();elem('chooser').selectedIndex=Math.min(cases.length-1,elem('chooser').selectedIndex+1);showCase()}
    function exportCSV(){saveCase();const reviewer=elem('reviewer').value||'UNSPECIFIED';let lines=[cols.map(escapeCSV).join(',')];for(const c of cases){let row={blind_id:c.blind_id,reviewer,...(saved[c.blind_id]||{})};lines.push(cols.map(k=>escapeCSV(row[k])).join(','))}const blob=new Blob([lines.join('\r\n')+'\r\n'],{type:'text/csv;charset=utf-8'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='annotations_'+reviewer+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}
    function loadCSV(input){alert('For safety, import is not implemented; use your exported CSV as the persistent annotation record. You may start a new reviewer session separately.');input.value=''}
    showCase()</script></body></html>'''.replace('__DATA__',payload)
    (out_dir/'LOCAL_PRIVATE_BLIND_REVIEW.html').write_text(page,encoding='utf-8')


def run(args):
    source=Path(args.input).expanduser().resolve()
    manifest=json.loads(Path(args.source_manifest).expanduser().read_text(encoding='utf-8'))
    if manifest.get('dataset')!=DATASET or manifest.get('file')!=FILE or manifest.get('commit')!=REVISION or manifest.get('sha256')!=SHA256 or source.name!=FILE:
        raise ValueError('Source revision, filename, or manifest does not match the pinned dataset')
    if hash_bytes(source.read_bytes())!=SHA256:raise ValueError('Source bytes differ from pinned SHA-256')
    stats=Counter(); candidates=[]; omitted=Counter(); per_record=Counter()
    with source.open('r',encoding='utf-8') as f:
        for i,line in enumerate(f,1):
            if i>args.max_records:break
            if not line.strip():continue
            record=json.loads(line)
            stats['records_seen']+=1
            msgs=record.get('messages',[]) if isinstance(record,dict) else []
            if msgs and isinstance(msgs[-1],dict):
                stats['raw_last_role_'+str(msgs[-1].get('role','unknown'))]+=1
                if msgs[-1].get('role')=='user' and isinstance(msgs[-1].get('content'),str) and msgs[-1]['content'].strip()==STOP:stats['terminal_exact_stop']+=1
            turns,reject=candidate_turns(record,i)
            if isinstance(reject,str):stats['records_'+reject]+=1;continue
            omitted.update(reject)
            if turns: stats['records_with_turn_candidates']+=1
            for c in turns:
                stats['turn_candidates']+=1
                stats['turn_'+c['turn_type']]+=1
                if c['heuristic_completion_cue_NOT_GOLD']:stats['heuristic_cue_turns']+=1
                if c['turn_type']=='intermediate' and c['heuristic_completion_cue_NOT_GOLD']:stats['intermediate_cue_turns']+=1
                if c['missing_tool_response_links']:stats['turns_with_unanswered_tool_calls']+=1
                candidates.append(c);per_record[i]+=1
    chosen=choose(candidates,args.sample_size,args.seed)
    root=Path(args.out_dir).expanduser().resolve();root.mkdir(parents=True,exist_ok=True)
    private=root/'REVIEW_LOCAL_PRIVATE';private.mkdir(exist_ok=True)
    ids=[]; mapping=[]
    for j,c in enumerate(chosen,1):
        blind=f'blind_{j:03}';ids.append(blind)
        export={key:value for key,value in c.items() if key not in ('source_line','turn_index','heuristic_completion_cue_NOT_GOLD','heuristic_mutating_tool_NOT_GOLD')}
        export['blind_id']=blind
        (private/(blind+'.json')).write_text(json.dumps(export,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        mapping.append(dict(blind_id=blind,source_line=c['source_line'],turn_index=c['turn_index'],turn_type=c['turn_type'],cue=c['heuristic_completion_cue_NOT_GOLD']))
    (private/'SOURCE_MAPPING_PRIVATE.json').write_text(json.dumps(mapping,indent=2)+'\n',encoding='utf-8')
    write_csv(private/'annotation_R1_blank.csv',csv_template(ids,'R1'))
    write_csv(private/'annotation_R2_blank.csv',csv_template(ids,'R2'))
    make_review_page(private,chosen)
    counts=dict(stats)
    summary={
        'schema':'naacl2027-turn-level-census-v1','dataset':DATASET,
        'source_revision':REVISION,'file_sha256':SHA256,
        'records_limit':args.max_records,'counts':counts,
        'omitted_candidate_turn_reasons':dict(omitted),
        'selected_count':len(chosen),
        'selected_final':sum(c['turn_type']=='final' for c in chosen),
        'selected_intermediate':sum(c['turn_type']=='intermediate' for c in chosen),
        'selected_heuristic_completion_cue':sum(c['heuristic_completion_cue_NOT_GOLD'] for c in chosen),
        'selected_distinct_source_trajectories':len(set(c['source_line'] for c in chosen)),
        'sampling':'Deterministic claim-cue/domain/turn-type strata; at most 1 utterance per source trajectory. Nonrepresentative targeted annotation sample.',
        'source_outcome_used':False,'annotations_completed':0,'model_performance_measured':False,
        'claim_cues_are_gold':False,'real_llm_evaluation_completed':False,
        'limitations':['No final-task inference from intermediate turns','Future observations are excluded from each prefix','A successful tool response is only supported under its simulator contract','Human labels and baselines still required','Candidate sampling is not representative'],
        'privacy':'Original traces and browser review page remain in REVIEW_LOCAL_PRIVATE. Do not upload without a source-specific redistribution/PII audit.'
    }
    (root/'UPLOAD_THIS_CENSUS_ONLY.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print('TURN_INTAKE=PASS_SOURCE_PINNED')
    print('RECORDS=',counts.get('records_seen',0),'WITH_ANY_TURN_CANDIDATE=',counts.get('records_with_turn_candidates',0))
    print('ALL_TURN_CANDIDATES=',counts.get('turn_candidates',0),'FINAL=',counts.get('turn_final',0),'INTERMEDIATE=',counts.get('turn_intermediate',0))
    print('HEURISTIC_CLAIM_CUE_TURNS=',counts.get('heuristic_cue_turns',0),'INTERMEDIATE_CUE_TURNS=',counts.get('intermediate_cue_turns',0))
    print('BLIND_SELECTED=',len(chosen),'FINAL=',summary['selected_final'],'INTERMEDIATE=',summary['selected_intermediate'])
    print('GOLD_LABELS=NONE BASELINE_COMPARISON=NOT_RUN')
    print('UPLOAD_ONLY=',root/'UPLOAD_THIS_CENSUS_ONLY.json')
    print('REVIEW_LOCAL=',private/'LOCAL_PRIVATE_BLIND_REVIEW.html')


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input',required=True)
    ap.add_argument('--source-manifest',required=True)
    ap.add_argument('--out-dir',required=True)
    ap.add_argument('--max-records',type=int,default=165)
    ap.add_argument('--sample-size',type=int,default=40)
    ap.add_argument('--seed',default='naacl2027-utterance-sample-v1')
    a=ap.parse_args()
    if a.max_records<1 or a.sample_size<1 or a.sample_size>200:ap.error('Invalid sample size or records limit')
    run(a)
