"""Preserved workspace fault episodes; never presented as human interaction."""
import json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core

def create():
    r=core.start_context('Exercise authorized elastic workflow failure handling',actor='scripted_fault_test');rid=r['run_id']
    s=core.answer_context(rid,{'template_id':core.PROFILE},actor='scripted_fault_test')
    core.answer_context(rid,{'confirm_spec_sha256':core.canonical(s['specification'])},actor='scripted_fault_test')
    return rid,core.directory(rid)

missing=core.start_context('A simulation without specified physics',actor='scripted_fault_test')
missing_result=core.submit_case(missing['run_id'])
rid,p=create();frozen=core.canonical(core.load(p/'spec.json'))
core.event(p,'injected_test_fault',actor='scripted_fault_test',description='Malformed YAML, unchanged confirmed specification')
(p/'input.yaml').write_text('Peridigm: [')
invalid=core.validate_case(rid);repaired=core.repair_case(rid)
assert invalid['status']=='BLOCKED' and repaired['validation']['status']=='SUCCEEDED'
assert core.canonical(core.load(p/'spec.json'))==frozen
tamper_id,tamper=create();s=core.load(tamper/'spec.json');s['physics']['material']['density_kg_m3']=1
core.save(tamper/'spec.json',s);tamper_result=core.submit_case(tamper_id);repair_refusal=core.repair_case(tamper_id)
assert tamper_result['status']=='BLOCKED' and repair_refusal['status']=='BLOCKED'
cancel_id,cancel=create();submitted=core.submit_case(cancel_id);requested=core.cancel_job(cancel_id)
deadline=time.monotonic()+10
while time.monotonic()<deadline:
    cancelled=core.job_status(cancel_id)
    if cancelled['job']['state'] in core.TERMINAL:break
    time.sleep(.05)
assert cancelled['job']['state']=='cancelled',cancelled
assert core.collect_results(cancel_id)['status']=='BLOCKED'
out={'passed':True,'missing':{'run_id':missing['run_id'],'result':missing_result},
     'invalid_yaml_and_repair':{'run_id':rid,'invalid':invalid,'repaired':repaired,'spec_sha256_unchanged':frozen},
     'physical_tamper':{'run_id':tamper_id,'submit':tamper_result,'repair':repair_refusal},
     'owned_cancellation':{'run_id':cancel_id,'request':requested,'terminal':cancelled}}
core.save(Path(core.config()['root'])/'runtime/fault-checks.json',out)
print(json.dumps({'passed':True,'episodes':{k:v['run_id'] for k,v in out.items() if isinstance(v,dict) and 'run_id' in v}},indent=2))
