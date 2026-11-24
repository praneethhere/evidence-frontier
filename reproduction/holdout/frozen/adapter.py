"""Loss-audited, claim-time AgentSuite turn -> agent-claimcheck agent-trace/v1.

No ground_truth, later messages, reviewer labels, or private benchmark fields.
The fixed timestamp is a serialization placeholder, NEVER an event timestamp.
"""
from __future__ import annotations
import hashlib, json, re
from pathlib import Path

SCHEMA = 'naacl-evidence-frontier-turn-prefix-v1'
ALLOWED_CASE_KEYS = {'schema','blind_id','task_domain','turn_type','agent_response','missing_tool_response_links','agent_visible_prefix','terminal_stop_after_final'}
ALLOWED_MSG_KEYS = {'role','content','turn_idx','tool_calls','tool_call_id','name'}
PLACEHOLDER_TS = '2000-01-01T00:00:00Z'


def hash_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parse_tool_payload(value):
    if not isinstance(value,str):
        return False, {}, 'Missing tool response text'
    if re.match(r'^\s*(?:error\s*:|exception\s*:|traceback\b)',value,re.I):
        return False, {}, value[:300]
    try:
        obj=json.loads(value)
    except (TypeError,ValueError):
        return None, {'text':value}, None
    if isinstance(obj,dict):
        if obj.get('ok') is False or (obj.get('error') is not None and obj.get('error') is not False):
            return False,obj,str(obj.get('error','Tool returned ok:false'))[:300]
        return True,obj,None
    return None, {'value':obj},None


def convert_case(case):
    if not isinstance(case,dict) or case.get('schema')!=SCHEMA:
        raise ValueError('Wrong case schema')
    if set(case)-ALLOWED_CASE_KEYS: raise ValueError('Unexpected case keys (potential private field)')
    bid=case.get('blind_id'); prefix=case.get('agent_visible_prefix')
    if not re.fullmatch(r'blind_\d{3}',str(bid)) or not isinstance(prefix,list) or not prefix:
        raise ValueError('Invalid case id / prefix')
    if case.get('missing_tool_response_links') not in (0,None):
        raise ValueError('Unlinked tool responses; do not infer tool status')
    if not isinstance(case.get('agent_response'),str) or not case['agent_response'].strip():
        raise ValueError('Missing original model response')
    if not isinstance(prefix[-1],dict) or prefix[-1].get('role')!='assistant' or prefix[-1].get('content')!=case['agent_response'] or prefix[-1].get('tool_calls'):
        raise ValueError('Original selected claim must be the last prefix message, without tool calls')
    steps=[]; seen_calls={}; names_by_id={}
    user_msgs=[]
    def step(kind,role,**kw):
        s={'i':len(steps),'ts':PLACEHOLDER_TS,'kind':kind,'role':role}
        s.update(kw)
        steps.append(s)
    for j,msg in enumerate(prefix):
        if not isinstance(msg,dict) or set(msg)-ALLOWED_MSG_KEYS:
            raise ValueError(f'Unknown prefix message keys at {j}')
        role=msg.get('role'); content=msg.get('content')
        if role in ('system','user','assistant'):
            if isinstance(content,str) and content.strip():
                step('message','environment' if role=='system' else 'user' if role=='user' else 'agent',content=content)
                if role=='user':user_msgs.append(content)
            for call in (msg.get('tool_calls') or []):
                if any(v is not None for v in seen_calls.values()):
                    raise ValueError('Concurrent/outstanding tool calls cannot be faithfully paired by name')
                if role!='assistant' or not isinstance(call,dict) or not isinstance(call.get('function'),dict):
                    raise ValueError('Malformed tool call')
                name=call['function'].get('name');call_id=call.get('id')
                if not isinstance(name,str) or not name or not isinstance(call_id,str) or not call_id or call_id in seen_calls:
                    raise ValueError('Missing/duplicate tool call ID')
                raw=call['function'].get('arguments','{}')
                try: args=json.loads(raw) if isinstance(raw,str) else raw
                except ValueError:raise ValueError('Unparseable tool arguments')
                if not isinstance(args,dict):raise ValueError('Tool arguments must be object')
                step('tool_call','agent',name=name,args=args)
                seen_calls[call_id]=len(steps)-1
                names_by_id[call_id]=name
        elif role=='tool':
            call_id=msg.get('tool_call_id');name=msg.get('name')
            if call_id not in names_by_id or names_by_id[call_id]!=name:
                raise ValueError('Unlinked or wrong-name tool response')
            if seen_calls[call_id] is None:raise ValueError('Repeated tool response')
            ok,output,error=parse_tool_payload(content)
            step('tool_result','tool',name=name,ok=ok,output=output,error=error)
            seen_calls[call_id]=None
        else:
            raise ValueError('Unknown role '+str(role))
    if not user_msgs:raise ValueError('No user instruction before claim')
    if any(v is not None for v in seen_calls.values()):raise ValueError('Pending tool calls at selected claim')
    if case.get('task_domain') not in ('airline','retail'):
        raise ValueError('Unknown source domain')
    domain='booking' if case.get('task_domain')=='airline' else 'other'
    return {
        'schema':'agent-trace/v1', 'trace_id':bid,
        'source':'AgentSuite/tau-bench-trajectories (pinned prefix adapter)',
        'task':{'id':bid,'domain':domain,'instruction':'\n\n'.join(user_msgs)},
        'steps':steps,
        'final_claim':{'text':case['agent_response']},
        'meta':{'selected_utterance_not_necessarily_final':case.get('turn_type')=='intermediate',
                'timestamps_are_placeholder_NOT_OBSERVED':True,
                'adapter':'naacl2027-agenttrace-adapter-v1'},
    }


def convert_dir(private_dir,ids):
    root=Path(private_dir)
    out=[];digests={}
    for bid in ids:
        source=root/(bid+'.json')
        c=json.loads(source.read_text(encoding='utf-8'))
        if c['blind_id']!=bid:raise ValueError('Wrong blind case in '+str(source))
        out.append(convert_case(c));digests[bid]=hash_file(source)
    return out,digests
