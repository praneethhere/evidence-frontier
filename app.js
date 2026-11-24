const $=(x)=>document.getElementById(x);
const put=(name,text)=>{$(name).textContent=text};
const el=(tag,text,cls)=>{const n=document.createElement(tag);n.textContent=text||'';if(cls)n.className=cls;return n};
async function get(path){const r=await fetch(path);const data=await r.json();if(!r.ok)throw Error(data.error||r.status);return data}
async function post(path,payload){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const data=await r.json();if(!r.ok)throw Error(data.error||r.status);return data}
function resetPrivate(){ $('truth').classList.add('hidden');$('truth').replaceChildren(); }
async function analyze(){resetPrivate();put('verdict','Analyzing…');$('obligations').replaceChildren();$('claims').replaceChildren();$('timeline').replaceChildren();
  try{const res=await post('/api/evaluate',{episode:$('episode').value,claim:$('claim').value});put('verdict',res.aggregate_verdict);put('cut',`Source: full original agent-visible conversation · Evidence cutoff ${res.claim_time_seconds}s · Private oracle used: ${res.private_oracle_used}`);
    for(const [name,v] of Object.entries(res.obligations)){const d=el('div','','item');const h=el('div','','item-head');h.append(el('span',name),el('span',v.status,v.status==='SUPPORTED'?'good':'warning'));d.append(h,el('div',v.reason,'small'));$('obligations').append(d)}
    for(const claim of res.claims){const d=el('div','','evidence');d.append(el('strong',`“${claim.text}”`),el('div',`${claim.stance} · ${claim.verdict} · span ${claim.start}:${claim.end}`,'small'));if(claim.contract_warning)d.append(el('div',claim.contract_warning,'danger'));$('claims').append(d)}
    for(const c of res.unmapped_clauses){$('claims').append(el('p',`Not evaluated: “${c.text}”`,'small'))}
    for(const s of res.agent_visible_steps){const d=el('details','','evidence');const status=s.parsed_observation.ok===true?'ACK':'NO POSITIVE ACK';d.append(el('summary',`t=${s.t}s · ${s.name} · ${status}`));d.append(el('div','Arguments','small'),el('pre',JSON.stringify(s.args,null,2)),el('div','Agent-visible tool reply','small'),el('pre',s.tool_observation_text));$('timeline').append(d)}
  }catch(e){put('verdict','ERROR');put('cut',e.message)} }
$('episode').addEventListener('change',()=>{$('claim').value='All requested steps completed.';analyze()});$('analyze').addEventListener('click',analyze);
$('reset').addEventListener('click',()=>{$('claim').value='All requested steps completed.';analyze()});
$('explicit').addEventListener('click',()=>{$('claim').value='I emailed the customer.';analyze()});
$('wrong').addEventListener('click',()=>{$('claim').value='I refunded the original charge.';analyze()});
$('reveal').addEventListener('click',async()=>{if(!$('truth').classList.contains('hidden')){resetPrivate();return}try{const x=await post('/api/reveal',{episode:$('episode').value});const out=$('truth');out.replaceChildren();out.append(el('strong',`Eventual task success: ${x.final_task_success}`));out.append(el('p',`LIMBO retrospective overclaim: ${x.limbo_overclaim}; late commit at ${x.late_commit_time??'none'}s`,'small'));out.classList.remove('hidden')}catch(e){put('verdict','ERROR: '+e.message)}});
$('pair').addEventListener('click',async()=>{try{const x=await get('/api/pilot');$('comparison').replaceChildren(el('strong',x.matched_visible_pair?'YES — identical agent-visible prefixes':'NO — prefix mismatch'),el('p','Episode 2 and 3 outcomes differ only under evaluator-private final truth; inspect each with Reveal.','small'));$('comparison').classList.remove('hidden')}catch(e){$('comparison').replaceChildren(el('p',e.message))}});
(async()=>{try{const x=await get('/api/pilot');const c=x.counts;const table=el('table');table.innerHTML='<tr><th>Diagnostic (not a benchmark metric)</th><th>Count</th></tr>';for(const [k,v] of Object.entries(c)){const tr=el('tr');tr.append(el('td',k.replaceAll('_',' ')),el('td',String(v)));table.append(tr)}$('pilot').replaceChildren(table);await analyze()}catch(e){put('verdict','ERROR');put('cut',e.message)}})();

// v0.4: replay of separately executed, pinned aggregate-only experiments.
// No new simulator tool calls, human annotations, or model inference occur here.
let recordedProbes=null;
const probeNames={none:'No fault',timeout_pre:'Before-commit timeout',timeout_post:'After-commit timeout',timeout_late:'Late-commit timeout'};
const strategyNames={no_probe:'No probe',search_now:'Read immediately',wait_120:'Wait 120s + read',wait_240:'Wait 240s + read'};
function clearProbeReveal(){put('probe-truth','');$('probe-reveal').textContent='Reveal evaluator-only eventual outcome';}
function getProbeRow(mode,strategy){return recordedProbes?.runs.find(x=>x.scenario===mode&&x.strategy===strategy)}
function showProbeDetail(){
  if(!recordedProbes)return;
  const mode=$('probe-mode').value,strategy=$('probe-strategy').value;
  const r=getProbeRow(mode,strategy),out=$('probe-detail');out.replaceChildren();if(!r)return;
  out.append(el('strong',`${probeNames[mode]} · ${strategyNames[strategy]}`),
             el('p',`Agent-visible email evidence at its final claim: ${r.mail_status==='OBSERVED_POSITIVE'?'POSITIVE evidence':'UNKNOWN'}`,r.mail_status==='OBSERVED_POSITIVE'?'good':'warning'),
             el('p',`Recorded matching sent-folder results: ${r.search_counts.length?r.search_counts.join(', '):'no search executed'}`),
             el('p',`Read-only searches: ${r.read_probe_count} · Claim time: ${r.finish_virtual_seconds} simulated seconds`,'small'),
             el('p',`Full task / exactly-once certified: ${r.full_task_certified?'yes':'NO'} · Refund attempts: ${r.refund_count} · Mail send attempts: ${r.mail_send_count}`,'small'));
  if(r.mail_status==='UNKNOWN')out.append(el('p','An empty read is inconclusive under 120-second index lag; it is not evidence of a definitive failed write.','small'));
  if(r.positive_readback)out.append(el('p','The observed matching record provides positive evidence for the email obligation, not proof of exactly-once delivery.','small'));
  for(const b of document.querySelectorAll('#probe-matrix button[data-mode]'))b.classList.toggle('active',b.dataset.mode===mode&&b.dataset.strategy===strategy);
  clearProbeReveal();
}
function drawProbeMatrix(){
  const table=el('table');const h=el('tr');h.append(el('th','Fault condition / strategy'));
  for(const s of recordedProbes.strategies)h.append(el('th',strategyNames[s]));table.append(h);
  for(const m of recordedProbes.scenarios){const tr=el('tr');tr.append(el('th',probeNames[m]));
    for(const s of recordedProbes.strategies){const td=el('td'),r=getProbeRow(m,s),b=el('button','',r.mail_status==='OBSERVED_POSITIVE'?'statepos':'stateunknown');
      b.dataset.mode=m;b.dataset.strategy=s;
      b.append(el('div',r.mail_status==='OBSERVED_POSITIVE'?'Positive mail evidence':'Mail unknown'),
               el('div',r.positive_readback?'Read-back +':'No positive read-back','small'));
      b.addEventListener('click',()=>{$('probe-mode').value=m;$('probe-strategy').value=s;showProbeDetail()});td.append(b);tr.append(td)
    }table.append(tr)
  }
  $('probe-matrix').replaceChildren(table);
  showProbeDetail();
}
async function startProbeReplay(){
  try{recordedProbes=await get('/api/probes');drawProbeMatrix();}
  catch(e){$('probe-detail').replaceChildren(el('span',`Could not load pinned experiment: ${e.message}`,'danger'))}
}
$('probe-mode').addEventListener('change',showProbeDetail);
$('probe-strategy').addEventListener('change',showProbeDetail);
$('probe-reveal').addEventListener('click',async()=>{
  if($('probe-truth').textContent){clearProbeReveal();return}
  try{const x=await post('/api/probe-reveal',{scenario:$('probe-mode').value});
      put('probe-truth',`Evaluator-only eventual simulator task success: ${x.eventual_task_success}. Not accessible at agent claim time.`);
      $('probe-reveal').textContent='Hide eventual outcome';}
  catch(e){put('probe-truth','Error: '+e.message)}
});
async function startPublishedStudy(){
  try{const x=await get('/api/study'),table=el('table','','study-table');
    const h=el('tr');for(const title of ['Published configuration','Detected (of 16)','Missed','False positives (of 20)','Recall','F1'])h.append(el('th',title));table.append(h);
    for(const v of x.comparisons){const c=v.claim_detection,tr=el('tr');for(const val of [v.label,c.TP,c.FN,c.FP,(100*c.recall).toFixed(1)+'%',c.f1===null?'N/A':(100*c.f1).toFixed(1)+'%'])tr.append(el('td',String(val)));table.append(tr)}
    $('published-table').replaceChildren(table);
    const adapted=x.comparisons.find(y=>y.key==='cascade-offline_domain_adapted');
    const d=adapted.evidence_verdicts_for_R1_yes;
    $('baseline-verdicts').replaceChildren(el('strong','Exploratory adapted offline cascade — evidence outputs across 16 R1-positive claims'),
      el('p',`${d.contradicted_caught||0} R1 contradiction flagged · ${d.supported_marked_false_success||0} R1-supported receipts flagged as false success · ${d.abstain||0} abstentions · ${d.claim_missed||0} claims missed.`,''),
      el('p','The published checker intentionally demands stronger evidence than a simulator ACK for some claims. This is a disagreement analysis, not a measured error or improvement for Evidence Frontier.','small'));
  }catch(e){$('published-table').replaceChildren(el('p',`Error loading pinned study: ${e.message}`))}
}
startProbeReplay();startPublishedStudy();


// v0.5 optional, locally verified τ-bench original-turn explorer.
// This is NOT an NLP prediction or an independent human annotation procedure.
let realReady=false;
function clearR1(){$('real-annotation').classList.add('hidden');$('real-annotation').replaceChildren()}
function clearAuto(){$('real-auto-result').classList.add('hidden');$('real-auto-result').replaceChildren()}
function drawOriginalMessage(msg,i){
  const d=el('details','','evidence real-msg'),name=msg.role+(msg.name?' · '+msg.name:'');
  d.append(el('summary',`[${i}] ${name}${msg.tool_calls?' · tool call':''}`));
  d.append(el('pre',JSON.stringify(msg,null,2)));
  return d;
}
async function loadRealCase(){
  clearR1();clearAuto();$('real-messages').replaceChildren();put('real-response','Loading original model response…');
  try{const x=await post('/api/real-case',{case:$('real-select').value});
    put('real-response',x.agent_response);
    put('real-meta',`${x.blind_id} · ${x.task_domain} · ${x.turn_type} utterance · ${x.agent_visible_prefix.length} visible messages · later observations and private outcomes excluded · no automatic model verdict`);
    x.agent_visible_prefix.forEach((m,i)=>$('real-messages').append(drawOriginalMessage(m,i)));
  }catch(e){put('real-response',`Local source error: ${e.message}`)}
}
$('real-auto').addEventListener('click',async()=>{
  clearAuto();const out=$('real-auto-result');
  try{const r=await post('/api/real-auto',{case:$('real-select').value});
    out.append(el('strong',`Automated rule baseline: ${r.verdict}`));
    out.append(el('p',`Detected action-completion claim: ${r.claim_detected?'YES':'NO'} · Preclaim tool receipts: ${r.tool_receipts_inspected}`,'small'));
    for(const c of r.claims){const d=el('div','','evidence');d.append(el('strong',c.action+' · '+c.verdict),
      el('p',`Claim excerpt: ${c.excerpt}`,'small'),
      el('p',`Evidence message indices: ${c.evidence_message_indices.join(', ')||'none'}`,'small'),
      el('p',c.reason,'small'));out.append(d)}
    out.append(el('p','Exploratory hand-built English/domain rules. Simulator receipt ≠ independent state proof. Not trained NLP; NOT tested on unseen held-out gold; not a novelty claim.','small'));
    out.classList.remove('hidden');
  }catch(e){out.replaceChildren(el('p',`Rule baseline error: ${e.message}`));out.classList.remove('hidden')}
});
$('real-load').addEventListener('click',loadRealCase);
$('real-select').addEventListener('change',loadRealCase);
$('real-r1').addEventListener('click',async()=>{
  if(!$('real-annotation').classList.contains('hidden')){clearR1();return}
  try{const r=await post('/api/real-r1',{case:$('real-select').value}),out=$('real-annotation');
    out.replaceChildren(el('strong','Single R1 human judgment — NOT adjudicated gold'));
    for(const [k,v] of Object.entries(r.label))out.append(el('p',`${k.replaceAll('_',' ')}: ${v||'—'}`,'small'));
    out.classList.remove('hidden');
  }catch(e){$('real-annotation').replaceChildren(el('p',`R1 not available: ${e.message}`));$('real-annotation').classList.remove('hidden')}
});
(async()=>{
  try{const catalog=await get('/api/real-cases');
    if(!catalog.enabled){put('real-status','Original model cases not loaded. Start the server with the pinned --source, --private-dir, and --census options; see README. This package contains no raw model data.');return}
    realReady=true;
    put('real-status',`Verified ${catalog.selected_count} unguided original-model turn prefixes against pinned public source bytes; local-only read access. No oracle or future observations.`);
    $('real-controls').classList.remove('hidden');
    for(const c of catalog.cases){const o=el('option',`${c.blind_id} · ${c.domain} · ${c.turn_type}`);o.value=c.blind_id;$('real-select').append(o)}
    // The previously flagged contradictory example makes a useful audit walkthrough,
    // without embedding its text or R1 label in this distributed package.
    if(catalog.cases.some(c=>c.blind_id==='blind_035'))$('real-select').value='blind_035';
    if(!catalog.R1_reveal_available)$('real-r1').disabled=true;
    await loadRealCase();
  }catch(e){put('real-status',`Original model explorer unavailable: ${e.message}`)}
})();

// Release candidate: actual execution, not lookup of expected verdicts.
let stressRequest=0;
function renderStressPrediction(id,r){const out=$(id);out.replaceChildren(el('strong',r.verdict,r.verdict==='SUPPORTED_UNDER_TOOL_CONTRACT'?'good':r.verdict==='UNKNOWN'?'warning':'danger'));
  for(const c of r.claims){out.append(el('p',c.action+' · '+c.verdict),el('p','Evidence indices: '+(c.evidence_message_indices.join(', ')||'none'),'small'),el('p',c.reason,'small'))}}
async function executeStress(){const seq=++stressRequest;const button=$('stress-run');button.disabled=true;put('stress-meta','Executing local verifiers…');
  try{const r=await post('/api/stress',{pair:$('stress-pair').value,condition:$('stress-kind').value});if(seq!==stressRequest)return;
    put('stress-scope',r.origin==='pinned_source_pair'?'Pinned corpus pair · locally reconstructed; selected mutation is synthetic.':'Authored synthetic fixture · not a model-generated trace.');put('stress-claim',r.claim);put('stress-call-label',`Tool request [${r.call_index}] · ${r.tool}`);put('stress-request',JSON.stringify(r.request,null,2));put('stress-original',r.original_receipt);put('stress-selected',r.selected_receipt);renderStressPrediction('stress-before',r.selected_prediction);renderStressPrediction('stress-after',r.guarded_prediction);put('stress-meta',`Executed both methods on a trace copy. Receipt [${r.receipt_index}], claim [${r.claim_index}]. Unmodified input verdict: ${r.original_prediction.verdict}. Tool calls executed: ${r.tool_calls_executed}. ${r.note}`);
  }catch(e){if(seq===stressRequest)put('stress-meta','Execution error: '+e.message)}finally{if(seq===stressRequest)button.disabled=false}}
$('stress-run').addEventListener('click',executeStress);$('stress-pair').addEventListener('change',executeStress);$('stress-kind').addEventListener('change',executeStress);
(async()=>{try{const r=await get('/api/stress');for(const pair of r.pairs){const option=el('option',pair.label);option.value=pair.id;$('stress-pair').append(option)}await executeStress()}catch(e){put('stress-meta',e.message)}})();
function tableFrom(rows){const t=el('table');for(const [i,row] of rows.entries()){const tr=el('tr');for(const v of row)tr.append(el(i===0?'th':'td',String(v)));t.append(tr)}return t}
function pct(v){return v===null||v===undefined?'Undefined':(v*100).toFixed(1)+'%'}
(async()=>{try{const r=await get('/api/final-results');const d=r.development,h=r.holdout;const rows=[['Method / sample','Precision','Recall','F1'],['EF development (36)',pct(d.precision),pct(d.recall),pct(d.f1)],['EF holdout (40)',pct(h.precision),pct(h.recall),pct(h.f1)]];
  for(const [k,v] of Object.entries(r.baseline))rows.push(['AC holdout · '+k,pct(v.precision),pct(v.recall),pct(v.f1??0)]);$('final-metrics').replaceChildren(tableFrom(rows));const gr=[['Condition','Original Supported','Guarded Supported','Guarded Unknown']];for(const [k,v] of Object.entries(r.guard.paired_results))gr.push([k,v.original_case_SUPPORTED_UNDER_TOOL_CONTRACT||0,v.guarded_case_SUPPORTED_UNDER_TOOL_CONTRACT||0,v.guarded_case_UNKNOWN||0]);$('guard-matrix').replaceChildren(tableFrom(gr));}catch(e){put('final-metrics',e.message)}})();
