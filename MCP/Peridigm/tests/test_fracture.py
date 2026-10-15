import copy,json
import pytest,yaml,numpy as np
import core,fracture

@pytest.fixture
def isolated(tmp_path,monkeypatch):
    c=core.config();c['root']=str(tmp_path);p=tmp_path/'local.json';core.save(p,c);monkeypatch.setenv('PERIDIGM_CONFIG',str(p))

def confirm(variant='base'):
    rid=core.start_context('Demonstrate damage and propagating fracture',actor='test_harness')['run_id']
    r=core.answer_context(rid,{'template_id':fracture.PROFILE,'time_step_variant':variant},actor='test_harness')
    r=core.answer_context(rid,{'confirm_spec_sha256':core.canonical(r['specification'])},actor='test_harness')
    assert r['status']=='SUCCEEDED';return rid,core.directory(rid)

def test_no_silent_physical_override(isolated):
    rid=core.start_context('fracture')['run_id']
    assert core.answer_context(rid,{'template_id':fracture.PROFILE,'critical_stretch_tension':.0001})['status']=='BLOCKED'
    assert core.answer_context(rid,{'template_id':fracture.PROFILE,'mpi_processes':2})['status']=='BLOCKED'

def test_fracture_mesh_tamper_repair_with_diff(isolated):
    rid,p=confirm();h=core.canonical(core.load(p/'spec.json'));(p/'points.txt').write_text('0 0 0 1 -1\n')
    assert core.submit_case(rid)['error_type']=='input_alignment'
    assert not (p/'job.json').exists()
    assert core.repair_case(rid)['validation']['status']=='SUCCEEDED'
    assert (p/'points-repair-1.diff').is_file() and core.canonical(core.load(p/'spec.json'))==h

def test_damage_threshold_tamper_rejected(isolated):
    rid,p=confirm();s=core.load(p/'spec.json');s['physics']['damage']['critical_stretch_tension']/=2;core.save(p/'spec.json',s)
    assert core.repair_case(rid)['status']=='BLOCKED' and core.submit_case(rid)['status']=='BLOCKED'

def test_text_discretization_build_and_quoted_loading(isolated):
    rid,p=confirm();s=core.load(p/'spec.json');d=yaml.safe_load((p/'input.yaml').read_text())['Peridigm']
    assert d['Discretization']['Type']=='Text File' and 'Bond Filters' in d['Discretization']
    assert set(d['Damage Models']['Brittle'])=={'Damage Model','Critical Stretch_tension','Critical Stretch_compression'}
    assert len((p/'points.txt').read_text().splitlines())==3201
    assert 'Value: "if(' in (p/'input.yaml').read_text()

def test_independent_neighbor_filter_and_ramp():
    f=fracture.template()['physics'];x,dx=fracture.points(f);pairs,cross,omitted=fracture.neighbors(x,f)
    assert omitted==354 and len(pairs)==42304
    assert np.all(cross[np.isfinite(cross)]>-.01)
    assert np.allclose(fracture.grip_displacement(np.array([0,5e-6,30e-6]),f),[0,2.5e-6,27.5e-6])

def test_half_step_explicit_confirmation(isolated):
    rid,p=confirm('half');assert core.load(p/'spec.json')['physics']['solver']['dt_s']==2.5e-8
    assert core.validate_case(rid)['status']=='SUCCEEDED'
