"""Explicit disposable-model native contract smoke; not a solver benchmark."""
import hashlib
import json
import os
import shutil
import sys
import traceback
from pathlib import Path
from ansa import base, constants, session

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'ansa_plugin'))
from ansa_mcp_bridge.handlers import HandlerRegistry

root = Path(os.environ['ANSA_MCP_ENGINEERING_PROBE']).resolve(strict=True)
report = {'pid': os.getpid(), 'operations': [], 'errors': []}
sequence = 0
r = HandlerRegistry([str(root)])


def op(name, params):
    global sequence
    sequence += 1
    info = r.get_session_info()
    payload = dict(operation=name, parameters=params, expected_database=info['database'],
        expected_session_nonce=info['session_nonce'], expected_deck=info['deck'], confirm=True,
        operation_id='engineering-smoke-%03d' % sequence)
    result = r.dispatch('execute_operation', payload)
    assert r.dispatch('execute_operation', payload)['idempotent_replay']
    report['operations'].append(result)
    return result


def attempt(name, work):
    try:
        work()
    except Exception:
        report['errors'].append({'test': name, 'error': traceback.format_exc()})


def cards_and_files():
    base.SetCurrentDeck(constants.ABAQUS)
    source = root / 'patch.inp'
    shutil.copy2(PROJECT / 'tests/fixtures/engineering_patch.inp', source)
    op('import_solver_deck', {'solver': 'ABAQUS', 'path': str(source), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()})
    material = op('create_isotropic_material', {'name': 'MCP_STEEL', 'young_modulus': 200000., 'poisson_ratio': .29,
                                    'density': 7.8e-9, 'unit_system': 'mm-N-tonne'})
    prop = base.CollectEntities(constants.ABAQUS, None, 'SHELL_SECTION')[0]
    old = prop.get_entity_values(constants.ABAQUS, ('MID',))['MID']
    op('set_entity_references', {'entity_type': 'SHELL_SECTION', 'entity_id': prop._id,
        'references': {'MID': {'entity_type': 'MATERIAL', 'entity_id': material['created_entity']['id']}},
        'expected_values': {'MID': old._id}})
    step = base.CollectEntities(constants.ABAQUS, None, 'STEP')[-1]
    nodes = base.CollectEntities(constants.ABAQUS, None, 'NODE')
    op('create_nodal_load', {'node_id': nodes[-1]._id, 'step_id': step._id, 'dof': 3, 'magnitude': -25., 'unit_system': 'mm-N-tonne'})
    op('create_nodal_constraint', {'node_id': nodes[1]._id, 'dofs': '123', 'value': 0., 'unit_system': 'mm-N-tonne'})
    # Read actual imported shell sets rather than infer IDs from file numbering.
    sets = [e for e in base.CollectEntities(constants.ABAQUS, None, 'SET')
            if base.CollectEntities(constants.ABAQUS, e, 'SHELL', recursive=True)]
    interaction = base.CollectEntities(constants.ABAQUS, None, 'SURFACE_INTERACTION')[0]
    op('create_contact_pair', {'secondary_set_id': sets[1]._id, 'main_set_id': sets[0]._id,
        'interaction_id': interaction._id, 'secondary_side': 'SNEG', 'main_side': 'SPOS', 'name': 'MCP_CONTACT'})
    op('export_solver_deck', {'solver': 'ABAQUS', 'path': str(root / 'export.inp')})
    exported = (root / 'export.inp').read_text()
    assert 'MCP_STEEL' in exported and '*CONTACT PAIR' in exported and '*CLOAD' in exported
    report['abaqus_export_cards_verified'] = True


def geometry_mesh():
    base.SetCurrentDeck(constants.NASTRAN)
    op('create_isotropic_material', {'name': 'MCP_NASTRAN_STEEL', 'young_modulus': 210000., 'poisson_ratio': .3,
                                    'density': 7.85e-9, 'unit_system': 'mm-N-tonne'})
    face = base.SurfacePlane3d([0., 0., 10., 1., 0., 0., 0., 1., 0.], [0., 0., 10.], [20., 20., 10.])
    assert face is not None
    cons = base.CollectEntities(constants.NASTRAN, face, 'CONS')
    scope = {'entity_type': 'CONS', 'entity_ids': [e._id for e in cons]}
    op('topology_paste', dict(scope, use_current_tolerances=True, paste_different_pids=False))
    op('set_perimeter_length', dict(scope, length=5.))
    op('repair_geometry', {'entity_type': 'FACE', 'entity_ids': [face._id], 'check': 'cracks', 'repair': True, 'allow_adjacent_changes': True})
    op('generate_surface_mesh', {'entity_type': 'FACE', 'entity_ids': [face._id], 'element_type': 'quad'})
    shells = base.CollectEntities(constants.NASTRAN, face, 'SHELL')
    assert shells, 'Real generated shell elements required'
    report['generated_shell_count'] = len(shells)
    report['aspect_criterion'] = base.F11ShellsOptionsGet('aspect ratio')
    op('set_mesh_quality_criterion', {'entity_type': 'SHELL', 'criterion': 'aspect ratio', 'enabled': True,
        'calculation': 'NASTRAN', 'value': 3., 'expected_values': report['aspect_criterion']})
    nodes = base.CollectEntities(constants.NASTRAN, face, 'GRID')
    for node in nodes:
        xyz = base.GetEntityCardValues(constants.NASTRAN, node, ('X1', 'X2', 'X3'))
        if abs(xyz['X1'] - 10.) < .01 and abs(xyz['X2'] - 10.) < .01:
            assert base.SetEntityCardValues(constants.NASTRAN, node, {'X1': 14.95}) == 0
            report['distorted_node_id'] = node._id
            break
    op('repair_mesh_quality', {'entity_type': 'SHELL', 'entity_ids': [e._id for e in shells], 'repair': True, 'allow_adjacent_changes': True, 'repair_method': 'native_fix'})
    repaired = op('repair_mesh_quality', {'entity_type': 'SHELL', 'entity_ids': [e._id for e in shells], 'repair': True, 'allow_adjacent_changes': True, 'repair_method': 'smooth_shells'})
    assert repaired['before']['reports'][0]['status'] == 'error'
    assert repaired['selected_check_passed'] is True
    op('remesh_shells', {'entity_type': 'SHELL', 'entity_ids': [e._id for e in shells], 'generator': 'FREE'})
    op('export_solver_deck', {'solver': 'NASTRAN', 'path': str(root / 'export.bdf')})
    exported = root / 'export.bdf'
    op('import_solver_deck', {'solver': 'NASTRAN', 'path': str(exported), 'sha256': hashlib.sha256(exported.read_bytes()).hexdigest()})


def volume_mesh():
    base.SetCurrentDeck(constants.NASTRAN)
    faces = base.CreateVolumeBox([100., 0., 0.], [101., 0., 0.], [100., 1., 0.], 10., 10., 10.)
    assert len(faces) == 6
    cons = base.CollectEntities(constants.NASTRAN, faces, 'CONS')
    op('set_perimeter_length', {'entity_type': 'CONS', 'entity_ids': list({e._id for e in cons}), 'length': 5.})
    op('mesh_faces', {'entity_type': 'FACE', 'entity_ids': [e._id for e in faces], 'use_current_mesh_settings': True})
    volumes = base.CollectEntities(constants.NASTRAN, None, 'VOLUME')
    assert volumes
    volume = volumes[-1]
    op('generate_volume_mesh', {'entity_type': 'VOLUME', 'entity_ids': [volume._id], 'mesh_type': 'TETRA FEM'})
    solids = base.CollectEntities(constants.NASTRAN, volume, 'SOLID')
    assert solids
    report['generated_solid_count'] = len(solids)


try:
    assert not base.DataBaseName()
    attempt('cards_and_files', cards_and_files)
    attempt('geometry_mesh', geometry_mesh)
    attempt('volume_mesh', volume_mesh)
    report['ok'] = not report['errors']
finally:
    (root / 'engineering_report.json').write_text(json.dumps(report, default=str, indent=2), encoding='utf-8')
    session.Quit(0)
