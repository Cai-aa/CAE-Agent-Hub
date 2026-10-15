import json,os
from pathlib import Path
import pytest,yaml
import core

@pytest.fixture
def isolated(tmp_path,monkeypatch):
    original=core.config();original['root']=str(tmp_path)
    cfg=tmp_path/'local.json';core.save(cfg,original);monkeypatch.setenv('PERIDIGM_CONFIG',str(cfg))
    return tmp_path

def confirmed():
    r=core.start_context('Verify a small elastic case',actor='test_harness')
    rid=r['run_id'];s=core.answer_context(rid,{'template_id':core.PROFILE},actor='test_harness')
    h=core.canonical(s['specification']);answer=core.answer_context(rid,{'confirm_spec_sha256':h},actor='test_harness')
    assert answer['status']=='SUCCEEDED';return rid,core.directory(rid)

def test_missing_context_cannot_submit(isolated):
    r=core.start_context('An elastic simulation',actor='test_harness')
    assert r['status']=='NEEDS_INPUT' and r['questions']
    assert core.submit_case(r['run_id'])['error_type']=='missing_context'
    assert not (core.directory(r['run_id'])/'job.json').exists()

def test_unsupported_geometry_model_is_explicit(isolated):
    r=core.start_context('Predict steel fracture',actor='test_harness')
    assert core.answer_context(r['run_id'],{'template_id':'steel-fracture'})['error_type']=='unsupported'

def test_confirmation_is_bound_to_exact_spec(isolated):
    r=core.start_context('elastic');rid=r['run_id'];core.answer_context(rid,{'template_id':core.PROFILE})
    assert core.answer_context(rid,{'confirm_spec_sha256':'incorrect'})['status']=='BLOCKED'
    assert not (core.directory(rid)/'frozen.json').exists()

def test_frozen_physics_tamper_not_repaired(isolated):
    rid,p=confirmed();s=core.load(p/'spec.json');s['physics']['material']['bulk_modulus_pa']=1e9;core.save(p/'spec.json',s)
    assert core.validate_case(rid)['error_type']=='physical_semantic'
    assert core.repair_case(rid)['status']=='BLOCKED'
    assert core.submit_case(rid)['status']=='BLOCKED'

def test_input_material_drift_cannot_launch(isolated):
    rid,p=confirmed();d=yaml.safe_load((p/'input.yaml').read_text());d['Peridigm']['Materials']['My Elastic Material']['Bulk Modulus']=1e9
    (p/'input.yaml').write_text(yaml.safe_dump(d))
    assert core.submit_case(rid)['error_type']=='input_alignment'
    assert not (p/'job.json').exists()

def test_syntax_repair_preserves_physics_and_evidence(isolated):
    rid,p=confirmed();h=core.canonical(core.load(p/'spec.json'));(p/'input.yaml').write_text('Peridigm: [')
    assert core.validate_case(rid)['error_type']=='input_syntax'
    repaired=core.repair_case(rid)
    assert repaired['validation']['status']=='SUCCEEDED'
    assert core.canonical(core.load(p/'spec.json'))==h and (p/'repair-1.diff').exists()

def test_repair_stops_at_three(isolated):
    rid,p=confirmed()
    for _ in range(3):
        (p/'input.yaml').write_text('bad: [');assert core.repair_case(rid)['status']=='SUCCEEDED'
    (p/'input.yaml').write_text('bad: [');assert core.repair_case(rid)['error_type']=='repair_limit'

@pytest.mark.parametrize('field,value',[('units','unknown'),('horizon_m',0),('contact','unqualified'),('damage','Critical Stretch')])
def test_unqualified_physics_blocked(isolated,field,value):
    rid,p=confirmed();s=core.load(p/'spec.json');s['physics'][field]=value;core.save(p/'spec.json',s)
    # Even a modified lock cannot qualify an unsupported model against the reference profile.
    core.save(p/'frozen.json',{'spec_sha256':core.canonical(s)})
    assert core.validate_case(rid)['error_type']=='physical_semantic'

def test_workspace_escape_blocked(isolated):
    with pytest.raises(ValueError):core.directory('../other-project')

def test_uncalculated_case_has_no_result_claim(isolated):
    rid,p=confirmed()
    assert core.collect_results(rid)['error_type']=='not_completed'
    assert not (p/'validation.json').exists()

def test_complete_questions_are_recorded(isolated):
    rid,p=confirmed();events=[json.loads(x) for x in (p/'events.jsonl').read_text().splitlines()]
    assert [x['kind'] for x in events].count('question')==2
    assert any(x['kind']=='spec_frozen' and x['actor']=='test_harness' for x in events)
