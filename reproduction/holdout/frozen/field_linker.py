"""Conservative, explainable *baseline* for action-claim-to-tool-result linking.

Research limits:
- Rule-driven English/tau-bench-specific, not a trained NLP component.
- A tool-contract-level receipt is not independent persistent-state proof.
- NO R1 annotations, private benchmark outcomes or later turns are accepted.
- No tool calls or changes to the benchmark environment are made here.
"""
from __future__ import annotations
import json
import re
from typing import Any

VERSION = 'evidence-frontier-structured-linker-exp-1'

_ACTIONS = (
    ('address',r'\b(?:address|shipping address|user address)\b.{0,110}\b(?:successfully\s+)?(?:updated|changed|reverted|modified)\b'),
    ('booking',r'\b(?:flight|reservation|booking)\b.{0,140}\b(?:successfully\s+booked|has\s+been\s+booked|is\s+confirmed)\b|\b(?:booking\s+is\s+confirmed|flight\s+is\s+booked)\b'),
    ('cancellation',r'\b(?:order|reservation|flight|trip)\b.{0,130}\b(?:successfully\s+cancelled|successfully\s+canceled|has\s+been\s+cancelled|has\s+been\s+canceled)\b'),
    ('reservation_change',r'\b(?:reservation|flight\s+details|flights)\b.{0,130}\b(?:successfully\s+updated|has\s+been\s+updated|successfully\s+changed|has\s+been\s+changed|successfully\s+modified|has\s+been\s+modified)\b'),
    ('return_request',r'\b(?:return\s+request|return\s+process|returns?)\b.{0,150}\b(?:successfully\s+)?(?:processed|initiated|submitted)\b|\b(?:initiating\s+the\s+return|status\s+changed\s+to\s+["\']?return\s+requested)\b'),
    ('exchange_request',r'\b(?:exchange\s+request|exchange\s+process|exchanges?)\b.{0,150}\b(?:successfully\s+)?(?:processed|initiated|submitted)\b|\b(?:has\s+been\s+exchanged)\b'),
    ('item_change',r'\b(?:item|order|laptop|speaker|puzzle)\b.{0,110}\b(?:successfully\s+modified|has\s+been\s+modified|successfully\s+updated|has\s+been\s+updated)\b'),
    ('refund',r'\b(?:refund|refunded)\b.{0,75}\b(?:successfully\s+)?(?:has\s+been\s+)?(?:processed|issued|completed)\b|\bhas\s+been\s+refunded\b'),
)

_WRITE_TOOLS = {
    'address': ('modify_user_address',),
    'booking': ('book_reservation',),
    'cancellation': ('cancel_reservation','cancel_pending_order'),
    'reservation_change': ('update_reservation_flights','update_reservation_baggages','update_reservation_cabin','update_reservation'),
    'return_request': ('return_delivered_order_items',),
    'exchange_request': ('exchange_delivered_order_items','modify_pending_order_items'),
    'item_change': ('modify_pending_order_items',),
    'refund': ('issue_refund','refund_payment','cancel_reservation','cancel_pending_order','modify_pending_order_items','update_reservation_flights','update_reservation_baggages'),
}

# Do not read or trust model-produced provenance/annotations embedded elsewhere.
_ALLOWED_CASE = {'schema','blind_id','task_domain','turn_type','terminal_stop_after_final',
                 'agent_response','missing_tool_response_links','agent_visible_prefix',
                 'heuristic_completion_cue_NOT_GOLD','heuristic_mutating_tool_NOT_GOLD'}
_ALLOWED_MESSAGE = {'role','content','turn_idx','tool_calls','tool_call_id','name'}


def _negated_or_future(text: str, start: int) -> bool:
    before = text[max(0,start-65):start].lower()
    span = text[start:start+160].lower()
    # Reject future, refusal and quoted hypotheticals, not already-done assertions.
    if re.search(r"(?:\bcannot\b|\bcan't\b|\bunable\b|\bdid\s+not\b|\bnot\s+yet\b|\bwill\b|\bwould\b|\bcould\b|\bcan\s+be\b)\s+(?:.{0,65})$",before):
        return True
    if re.search(r'\b(?:not\s+successfully|not\s+yet\s+processed|was\s+not\s+completed)\b',span[:75]):
        return True
    return False


def _claims(text: str) -> list[dict]:
    if not isinstance(text,str) or not text.strip():return []
    out=[]
    for action,raw in _ACTIONS:
        for match in re.finditer(raw,text,re.I|re.S):
            if _negated_or_future(text,match.start()):continue
            # Only one principal claim per action type. This is not span F1 evaluation.
            if any(x['action']==action for x in out):break
            out.append({'action':action,'span':[match.start(),match.end()],
                        'excerpt':text[match.start():match.end()].strip()})
            break
    return sorted(out,key=lambda x:x['span'][0])


def _get_args(call):
    fn=call.get('function')
    if not isinstance(fn,dict) or not isinstance(fn.get('name'),str):raise ValueError('Invalid call function')
    args=fn.get('arguments','{}')
    try: val=json.loads(args) if isinstance(args,str) else args
    except (ValueError,TypeError):raise ValueError('Malformed tool arguments')
    if not isinstance(val,dict):raise ValueError('Non-object tool args')
    return fn['name'],val


def _tool_events(prefix:list[dict]) -> list[dict]:
    calls={};out=[]
    for index,m in enumerate(prefix):
        if not isinstance(m,dict) or (set(m)-_ALLOWED_MESSAGE):raise ValueError('Unknown/possibly private message field')
        role=m.get('role')
        if role=='assistant':
            for c in m.get('tool_calls') or []:
                if not isinstance(c,dict) or not isinstance(c.get('id'),str) or c['id'] in calls:
                    raise ValueError('Invalid tool call ID')
                name,args=_get_args(c)
                calls[c['id']]={'name':name,'args':args,'call_index':index,'result_index':None}
        elif role=='tool':
            ident=m.get('tool_call_id')
            if ident not in calls or calls[ident]['result_index'] is not None:raise ValueError('Unlinked or duplicate tool result')
            event=calls[ident]
            if m.get('name')!=event['name']:raise ValueError('Tool-result name mismatch')
            raw=m.get('content')
            if not isinstance(raw,str):raise ValueError('Tool result missing')
            is_error=bool(re.match(r'^\s*(?:error\s*:|exception\s*:|traceback\b)',raw,re.I))
            try:obj=json.loads(raw)
            except ValueError:obj=raw
            if isinstance(obj,dict) and (obj.get('ok') is False or obj.get('error')):is_error=True
            event.update({'result_index':index,'payload':obj,'error':is_error})
            out.append(dict(event))
        elif role not in ('user','system'):
            raise ValueError('Unrecognized message role')
    if any(v['result_index'] is None for v in calls.values()):
        raise ValueError('Pending unmatched tool call before response')
    return out


def _field_claims(text):
    cabin=None
    if re.search(r'\bbasic[ -]economy\b',text,re.I):cabin='basic_economy'
    elif re.search(r'\beconomy\s+class\b|\bclass\s*:\s*\**\s*economy\b',text,re.I):cabin='economy'
    elif re.search(r'\bbusiness\s+class\b|\bclass\s*:\s*\**\s*business\b',text,re.I):cabin='business'
    flight_ids=list(dict.fromkeys(re.findall(r'\bHAT\d{3}\b',text,re.I)))
    order_ids=list(dict.fromkeys(re.findall(r'#W\d{7,9}\b',text,re.I)))
    reservation_ids=list(dict.fromkeys(re.findall(r'\breservation\s+(?:id\s*)?[:#]?\s*\*{0,2}([A-Z0-9]{6})\b',text,re.I)))
    address1=re.search(r'\bAddress\s*1\b\s*\*{0,2}\s*:\s*\*{0,2}\s*([^\n,]+)',text,re.I)
    if not address1:
        address1=re.search(r'\b(?:address\s+(?:has\s+been\s+)?(?:updated|changed|reverted)\s+to)\s*:\s*([^,\n]+)',text,re.I)
    baggage=re.search(r'\b(?:Checked\s+Bags?|total[_ ]baggages?)\s*:\s*\**\s*(\d+)\s*(?:total)?\b',text,re.I)
    return {'cabin':cabin,'flights':[s.upper() for s in flight_ids],
            'orders':[s.upper() for s in order_ids],
            'reservation_ids':[s.upper() for s in reservation_ids],
            'address1':address1.group(1).strip(' *-') if address1 else None,
            'baggage':int(baggage.group(1)) if baggage else None}


def _payload_dict(event):
    return event.get('payload') if isinstance(event.get('payload'),dict) else {}


def _field_checks(text,action,event):
    """Returns (contradictions, confirmed_facets, unverified_facets)."""
    p=_payload_dict(event)
    features=_field_claims(text)
    contradictions=[];positive=[];unverified=[]
    if action in ('booking','reservation_change'):
        if features['cabin']:
            cabin=p.get('cabin')
            if cabin is None:unverified.append('claim names cabin class but tool reply has no cabin field')
            elif str(cabin).lower()!=features['cabin']:contradictions.append('claimed cabin '+features['cabin']+' but result cabin='+str(cabin))
            else:positive.append('cabin='+str(cabin))
        if features['flights']:
            actual={str(f.get('flight_number','')).upper() for f in p.get('flights',[]) if isinstance(f,dict)}
            if not actual:unverified.append('claimed flight numbers absent from result')
            elif not set(features['flights']).issubset(actual):contradictions.append('claimed flights differ from observed reservation flights')
            else:positive.append('flight IDs matched')
        if features['reservation_ids'] and p.get('reservation_id'):
            if str(p['reservation_id']).upper() not in features['reservation_ids']:
                contradictions.append('claimed reservation ID differs from tool result')
            else:positive.append('reservation ID matched')
    if action=='address':
        actual=p.get('address')
        if not isinstance(actual,dict):unverified.append('address absent from response')
        elif features['address1']:
            expected=features['address1'].lower().strip()
            got=str(actual.get('address1','')).lower().strip()
            if got and got!=expected:contradictions.append('claimed street address differs from tool-returned street address')
            elif got:positive.append('address1 matched')
            else:unverified.append('returned address has no street')
        elif isinstance(actual,dict):positive.append('structured address returned')
    if action in ('return_request','exchange_request','cancellation','item_change'):
        want={'return_request':('return requested',),
              'exchange_request':('exchange requested','pending (item modified)','pending (items modified)'),
              'cancellation':('cancelled','canceled'),
              'item_change':('pending (item modified)','pending (items modified)')}[action]
        state=str(p.get('status','')).lower()
        if not state:unverified.append('no resulting action status')
        elif state not in want:contradictions.append('result status '+state+' incompatible with completed '+action)
        else:positive.append('state='+state)
    if action=='booking':
        if not p.get('reservation_id'):unverified.append('no created reservation id')
        else:positive.append('created reservation receipt')
    if action=='reservation_change' and not p.get('reservation_id'):
        unverified.append('no reservation identifier in result')
    if action=='refund':
        # Refund mechanics differ; a write receipt is insufficient without an explicit transaction.
        history=p.get('payment_history',[])
        if not isinstance(history,list) or not any(isinstance(r,dict) and
              (str(r.get('transaction_type','')).lower() in ('refund','refund_processed') or
               isinstance(r.get('amount'),(int,float)) and r['amount']<0) for r in history):
            unverified.append('no explicit refund transaction in observed tool result')
        else:positive.append('refund transaction in result')
    return contradictions,positive,unverified


def check_case(case:dict) -> dict:
    if not isinstance(case,dict) or set(case)-_ALLOWED_CASE:raise ValueError('Unexpected case keys')
    prefix=case.get('agent_visible_prefix')
    response=case.get('agent_response')
    if not isinstance(prefix,list) or not prefix or not isinstance(response,str):raise ValueError('Bad case')
    if case.get('missing_tool_response_links',0)!=0:raise ValueError('Source tool link incomplete')
    if prefix[-1].get('role')!='assistant' or prefix[-1].get('content')!=response or prefix[-1].get('tool_calls'):
        raise ValueError('Not an agent-text cutoff')
    # Only evidence preceding selected response is used.
    events=_tool_events(prefix[:-1])
    claims=_claims(response)
    if not claims:
        return {'method':VERSION,'claim_detected':False,'verdict':'NOT_A_COMPLETION_CLAIM',
                'claims':[],'tool_receipts_inspected':len(events),'uses_private_outcome':False,
                'uses_later_messages':False}
    findings=[]
    for claim in claims:
        action=claim['action']
        eligible=[e for e in events if e['name'] in _WRITE_TOOLS[action]]
        if not eligible:
            findings.append({**claim,'verdict':'UNKNOWN','evidence_message_indices':[],
                             'reason':'No linked, relevant write-tool result before the claim'})
            continue
        features=_field_claims(response)
        matching=[]
        # For a claim naming several orders, every order must have its own witness.
        if features['orders'] and action in ('return_request','exchange_request','item_change','cancellation'):
            for target in features['orders']:
                per=[e for e in eligible if str(e['args'].get('order_id',_payload_dict(e).get('order_id',''))).upper()==target]
                if not per:
                    findings.append({**claim,'verdict':'UNKNOWN','evidence_message_indices':[],
                                     'reason':'No linked write receipt for claimed order '+target})
                    matching=[]
                    break
                matching.append(per[-1])
            if not matching:continue
        elif features['reservation_ids'] and action in ('reservation_change','cancellation','booking'):
            per=[e for e in eligible if str(e['args'].get('reservation_id',_payload_dict(e).get('reservation_id',''))).upper() in features['reservation_ids']]
            if not per:
                findings.append({**claim,'verdict':'UNKNOWN','evidence_message_indices':[],
                                 'reason':'No relevant write receipt for named reservation'})
                continue
            matching=[per[-1]]
        else:
            matching=[eligible[-1]]
        issues=[]; positives=[]; missing=[]; evid=[]
        for e in matching:
            evid.extend([e['call_index'],e['result_index']])
            if e['error']:
                issues.append('Latest relevant attempt returned an explicit tool error')
                continue
            c,p,u=_field_checks(response,action,e)
            issues.extend(c);positives.extend(p);missing.extend(u)
        if issues: verdict='CONTRADICTED_UNDER_TOOL_CONTRACT'
        elif missing or not positives:verdict='UNKNOWN'
        else:verdict='SUPPORTED_UNDER_TOOL_CONTRACT'
        findings.append({**claim,'verdict':verdict,
                         'evidence_message_indices':sorted(set(evid)),
                         'reason':'; '.join(issues+missing+positives)})
    statuses=[c['verdict'] for c in findings]
    if 'CONTRADICTED_UNDER_TOOL_CONTRACT' in statuses:verdict='CONTRADICTED_UNDER_TOOL_CONTRACT'
    elif 'UNKNOWN' in statuses:verdict='UNKNOWN'
    else:verdict='SUPPORTED_UNDER_TOOL_CONTRACT'
    return {'method':VERSION,'claim_detected':True,'verdict':verdict,'claims':findings,
            'tool_receipts_inspected':len(events),'uses_private_outcome':False,
            'uses_later_messages':False,
            'warning':'Rule-based, domain-bound exploratory baseline; simulator receipt != independent real-world state.'}
