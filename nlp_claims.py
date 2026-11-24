"""Scope-limited rule-baseline for claimed-completion extraction.

NOT an ML model; not an empirical NLP claim. Negative, hedged, future,
pending and attempted language must not become positive completion claims.
No grader/oracle access. All spans are offsets in the original user text.
"""
from __future__ import annotations
import re

MAX_CHARS=4000
# Split only at punctuation and explicit contrast; no hidden semantic model.
CUT=re.compile(r'(?<=[.!?;])\s+|\s*,?\s*\bbut\b\s+|\s+\band\b\s+(?=(?:I|we|the|customer|email|e-mail|refund|notifi|sent|emailed)\b)',re.I)
BROAD=re.compile(r'\b(all (?:requested )?(?:steps|tasks|operations)|everything|entire (?:task|request))\b.{0,45}\b(?:complete(?:d)?|done|finish(?:ed)?)\b|\b(?:completed|finished)\b.{0,25}\b(?:everything|all (?:requested )?(?:steps|tasks))\b|^\s*(?:done|completed|finished)\s*[.!]?\s*$',re.I)
REFUND=re.compile(r'\brefund(?:s|ed|ing)?\b|\breimburs(?:ed|e|ement)\b|\bcredited\b|\bcredit (?:was |has been )?(?:applied|issued)\b',re.I)
MAIL=re.compile(r'\b(?:e-?mail(?:ed|s|ing)?|mail(?:ed)?|notifi(?:ed|cation|cations|y)|notification(?:s)?|messag(?:e|ed))\b',re.I)
COMPLETED=re.compile(r'\b(?:refunded|reimbursed|emailed|mailed|notified|sent|completed|finished|done|processed|issued|delivered|successful(?:ly)?|success|complete|succeeded|confirmed)\b',re.I)
NEGATED=re.compile(r"\b(?:not|never|no|didn't|did not|couldn't|could not|can't|cannot|hasn't|has not|haven't|have not|isn't|is not|aren't|are not|won't|will not|wasn't|was not|weren't|were not|failed|unable)\b",re.I)
UNCERTAIN=re.compile(r"\b(?:maybe|perhaps|possibly|probably|might|may have|not sure|unsure|can't confirm|cannot confirm|don't know|do not know|I think|I believe|appears? to|seems? to|unverified|unknown)\b",re.I)
NOT_COMPLETE=re.compile(r'\b(?:pending|queued|scheduled|initiated|attempted|tried|trying|will|going to|plan to|started|in progress|still processing)\b',re.I)
TIMEOUT=re.compile(r'\b(?:time(?:d)? ?out|timeout|disconnected)\b',re.I)

def extract(text:str)->dict:
    if not isinstance(text,str): raise ValueError('Agent response must be a string')
    if len(text)>MAX_CHARS: raise ValueError('Agent response exceeds 4000 characters')
    spans=[]; uncovered=[]
    loc=0
    for match in CUT.finditer(text):
        spans.append((loc,match.start()));loc=match.end()
    spans.append((loc,len(text)))
    claims=[]
    for start,end in spans:
        raw=text[start:end]
        if not raw.strip():continue
        trimstart=len(raw)-len(raw.lstrip());trimend=len(raw.rstrip())
        start+=trimstart;end=(start-trimstart)+trimend
        raw=text[start:end]
        normalized=raw.replace("’", "\'").replace("‘", "\'")
        targets=[]
        if BROAD.search(normalized):targets=['refund','customer_email']; trigger='BROAD_COMPLETION'
        else:
            if REFUND.search(normalized):targets.append('refund')
            if MAIL.search(normalized):targets.append('customer_email')
            trigger='ACTION_LEXICON'
        if not targets:
            uncovered.append({'text':raw,'start':start,'end':end,'reason':'No target obligation recognized'})
            continue
        if NEGATED.search(normalized):stance='NEGATED'
        elif UNCERTAIN.search(normalized) or TIMEOUT.search(normalized):stance='UNCERTAIN'
        elif NOT_COMPLETE.search(normalized):stance='NONTERMINAL'
        elif trigger=='BROAD_COMPLETION' or COMPLETED.search(normalized):stance='ASSERTED_COMPLETE'
        else:stance='MENTION_ONLY'
        claims.append({'text':raw,'start':start,'end':end,'obligations':targets,'stance':stance,'extractor':'RULE_BASELINE_v0.2','trigger':trigger})
    return {'claims':claims,'unmapped_clauses':uncovered,'extractor':'RULE_BASELINE_v0.2','limitations':['fixed two-obligation domain','regex-based, English only','no semantic entailment','claim spans are clause-level','unmapped language cannot be certified']}
