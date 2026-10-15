"""Portable unit-test configuration; no solver or reference-result claim."""
import os
import pytest
import core

@pytest.fixture(autouse=True)
def unit_config_if_unconfigured(tmp_path,monkeypatch):
    if os.environ.get('PERIDIGM_CONFIG'):return
    reference=tmp_path/'unit-reference.bin';reference.write_bytes(b'unit identity fixture, not a solver reference')
    path=tmp_path/'unit-config.json'
    core.save(path,{'root':str(tmp_path),'reference':str(reference),'solver':str(tmp_path/'no-solver'),'mpirun':str(tmp_path/'no-mpi'),'library_dirs':[]})
    monkeypatch.setenv('PERIDIGM_CONFIG',str(path))
