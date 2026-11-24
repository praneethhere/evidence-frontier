#!/usr/bin/env python3
"""Evidence Frontier v0.6 local-only, integrity-checked demo.

No API keys, cloud calls, LLM inference, or tool execution. Optional original model traces are read locally only. Private oracle is
only read in a separate explicit /api/reveal endpoint, never in /api/evaluate.
"""
from __future__ import annotations
import argparse,hashlib,json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from evidence import CASES,assess,validate_visible,visible_signature
from baseline_pilot import run
from study import load_study, probe_public, probe_reveal, study_public
from real_trajectories import load_local_real_cases, public_catalog, public_case, r1_reveal
from field_linker import check_case
from stress import build as stress_build, catalog as stress_catalog, execute as stress_execute
from release_results import load_results
ROOT=Path(__file__).resolve().parent

def load_files():
    m=json.loads((ROOT/'data/manifest_v03.json').read_text())
    for f in m['files']:
        q=ROOT/f['path']
        if hashlib.sha256(q.read_bytes()).hexdigest()!=f['sha256']:
            raise RuntimeError('Source file tampered: '+f['path'])
    visible={name:validate_visible(json.loads((ROOT/'data/agent_visible'/f'{name}.json').read_text())) for name in CASES}
    if visible_signature(visible['episode_002'])!=visible_signature(visible['episode_003']):
        raise RuntimeError('Source ambiguity pair changed')
    return visible

class App(BaseHTTPRequestHandler):
    VISIBLE={}
    STUDY=None
    REAL=None
    STRESS=None
    RESULTS=None
    def log_message(self,fmt,*args): pass
    def send_json(self,payload,status=200):
        data=json.dumps(payload,ensure_ascii=False).encode()
        self.send_response(status)
        for k,v in [('Content-Type','application/json; charset=utf-8'),('Content-Length',str(len(data))),('Cache-Control','no-store'),('X-Content-Type-Options','nosniff')]:self.send_header(k,v)
        self.end_headers();self.wfile.write(data)
    def send_file(self,filename,mimetype):
        data=(ROOT/filename).read_bytes();self.send_response(200)
        self.send_header('Content-Type',mimetype);self.send_header('Content-Length',str(len(data)))
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; object-src 'none'")
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers();self.wfile.write(data)
    def do_GET(self):
        path=self.path.split('?',1)[0]
        if path=='/':self.send_file('index.html','text/html; charset=utf-8');return
        if path=='/app.js':self.send_file('app.js','text/javascript; charset=utf-8');return
        if path=='/favicon.ico':self.send_response(204);self.end_headers();return
        if path=='/api/stress':
            self.send_json(stress_catalog(self.STRESS));return
        if path=='/api/final-results':
            self.send_json(self.RESULTS);return
        if path=='/api/probes':
            self.send_json(probe_public(self.STUDY));return
        if path=='/api/study':
            self.send_json(study_public(self.STUDY));return
        if path=='/api/real-cases':
            self.send_json(public_catalog(self.REAL));return
        if path=='/api/cases':
            self.send_json({'cases':[{'id':v,'claim':self.VISIBLE[v]['claim'],'cutoff':self.VISIBLE[v]['finish_time']} for v in CASES],
                'baseline':'Pinned scripted LIMBO conversations. Edited text is counterfactual, not an original LLM response.'});return
        if path=='/api/pilot':
            rep=run(ROOT/'data')
            # Avoid sending oracle truth via this summary endpoint; reveal is separate.
            self.send_json({'scope':rep['provenance'],'matched_visible_pair':rep['matched_visible_pair']['identical'],
                            'counts':rep['counts'],'note':'Counts are descriptive over three scripted executions; not independent evaluation.'});return
        self.send_json({'error':'Not found'},404)
    def do_POST(self):
        if self.path not in ('/api/evaluate','/api/reveal','/api/probe-reveal','/api/real-case','/api/real-r1','/api/real-auto','/api/stress'): self.send_json({'error':'Not found'},404);return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=12000:raise ValueError('Invalid request size')
            payload=json.loads(self.rfile.read(length))
            if not isinstance(payload,dict):raise ValueError('Invalid payload')
            if self.path=='/api/stress':
                self.send_json(stress_execute(self.STRESS,payload.get('pair'),payload.get('condition')));return
            if self.path=='/api/real-case':
                self.send_json(public_case(self.REAL,payload.get('case')));return
            if self.path=='/api/real-r1':
                self.send_json(r1_reveal(self.REAL,payload.get('case')));return
            if self.path=='/api/real-auto':
                bid=payload.get('case')
                if self.REAL is None or bid not in self.REAL['cases'] or bid not in tuple(f'blind_{i:03}' for i in range(5,41)):
                    raise ValueError('Original unguided case unavailable')
                self.send_json(check_case(self.REAL['cases'][bid]));return
            if self.path=='/api/probe-reveal':
                self.send_json(probe_reveal(self.STUDY,payload.get('scenario')));return
            if payload.get('episode') not in CASES:raise ValueError('Invalid episode')
            name=payload['episode']
            if self.path=='/api/evaluate':
                claim=payload.get('claim',self.VISIBLE[name]['claim'])
                self.send_json(assess(self.VISIBLE[name],claim));return
            # Only explicit reveal accesses private data; never passed to assess().
            private=json.loads((ROOT/'data/evaluator_private'/f'{name}.json').read_text())
            self.send_json({'episode_key':name,'evaluator_only':True,'final_task_success':private['final_grade']['TS'],
                  'limbo_overclaim':private.get('simulator_overclaim'),
                  'late_commit_time':next((e['t_start'] for e in private['late_effect_events'] if e.get('source')=='late_commit'),None)});
        except (TypeError,ValueError,KeyError,json.JSONDecodeError) as ex:
            self.send_json({'error':str(ex)},400)

def make_server(port=8775,real=None,stress_source=None):
    visible=load_files()
    study=load_study()
    return ThreadingHTTPServer(('127.0.0.1',port),type('BoundApp',(App,),{'VISIBLE':visible,'STUDY':study,'REAL':real,'STRESS':stress_build(stress_source),'RESULTS':load_results()}))

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--port',type=int,default=8775)
    p.add_argument('--source',type=Path)
    p.add_argument('--private-dir',type=Path)
    p.add_argument('--census',type=Path)
    p.add_argument('--annotations',type=Path)
    p.add_argument('--stress-source',type=Path,help='Optional pinned original source for 42 local receipt pairs')
    a=p.parse_args()
    args=(a.source,a.private_dir,a.census)
    if any(x is not None for x in args) and not all(x is not None for x in args):
        p.error('Use --source, --private-dir and --census together')
    if a.annotations is not None and not all(x is not None for x in args):
        p.error('--annotations requires the pinned real-trace source options')
    real=load_local_real_cases(a.source,a.private_dir,a.census,a.annotations) if a.source else None
    s=make_server(a.port,real,a.stress_source or a.source)
    print(f'EVIDENCE_FRONTIER_RC=http://127.0.0.1:{s.server_address[1]}/',flush=True)
    print('ORIGINAL_LLM_TRACES_BUNDLED=NO REAL_LOCAL_PREFIXES_VERIFIED='+str(real is not None),flush=True)
    print('EXECUTED_PROBES=RECORDED_REPLAY HUMAN_EVAL=R1_PILOT_ONLY',flush=True)
    print('LIVE_RECEIPT_STRESS=YES LOCAL_CORPUS_PAIRS='+str(bool(a.stress_source or a.source)),flush=True)
    try:s.serve_forever()
    except KeyboardInterrupt:pass
    finally:s.server_close()
