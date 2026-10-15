"""Summarize an actual run, without guessing external-client model usage."""
import argparse,json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core
p=argparse.ArgumentParser();p.add_argument('run_id');p.add_argument('--model-version');a=p.parse_args()
d=core.directory(a.run_id);events=[json.loads(x) for x in (d/'events.jsonl').read_text().splitlines()]
job=core.load(d/'job.json') if (d/'job.json').exists() else {};v=core.load(d/'validation.json') if (d/'validation.json').exists() else {}
out={'run_id':a.run_id,'kind':'integration_episode_not_comparative_benchmark','model_version':a.model_version,'model_tokens':None,'model_cost':None,
     'process_completed':job.get('state')=='completed','verification_passed':v.get('passed',False),'questions':sum(x['kind']=='question' for x in events),
     'answers':sum(x['kind']=='answer' for x in events),'repair_attempts':sum(x['kind']=='repair' for x in events),
     'actors':sorted({x['actor'] for x in events}),'elapsed_solver_seconds':job.get('elapsed_seconds'),
     'physical_spec_alignment':core.validate_case(a.run_id)['status']=='SUCCEEDED','scope':v.get('scope')}
core.save(d/'evaluation.json',out);print(json.dumps(out,indent=2))
