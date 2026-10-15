import importlib.util,json
from pathlib import Path
import pytest
import core

def script(name):
    p=Path(__file__).resolve().parents[1]/'scripts'/f'{name}.py'
    s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def test_curated_replays_are_verifiable_without_solver():
    results=script('check_demos').check(Path(__file__).resolve().parents[3])
    assert len(results)==2 and all(r['passed'] for r in results)

def test_export_rejects_unverified_run(tmp_path):
    run=tmp_path/'run';run.mkdir();out=tmp_path/'public-fixture'
    core.save(run/'spec.json',{'template_id':core.PROFILE})
    core.save(run/'job.json',{'state':'failed','exit_code':1})
    core.save(run/'validation.json',{'passed':False});core.save(run/'result_mesh.json',{})
    with pytest.raises(ValueError,match='successfully verified'):script('export_demo').export(run,out)
    assert not out.exists()
