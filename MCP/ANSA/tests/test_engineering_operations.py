import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from ansa_mcp_bridge.handlers import HandlerRegistry
from ansa_mcp_bridge.engineering import flat_deck


class Entity:
    def __init__(self, identity, kind, fields=None):
        self._id, self.kind, self.fields = identity, kind, fields or {}
    def card_fields(self, deck): return list(self.fields)
    def ansa_type(self, deck): return self.kind
    def get_entity_values(self, deck, fields): return {k: self.fields[k] for k in fields}
    def set_entity_values(self, deck, fields):
        self.fields.update(fields)
        fields.update({k: v._id for k, v in fields.items()})  # native mutates caller mapping
        return 0


@pytest.fixture
def env(tmp_path):
    class Check:
        EXEC_ON_SELECTED, REPORT_NONE, CLEAR_OLD = 2, 0, 0
        def is_available_in_deck(self, deck): return True
        def execute(self, **kwargs):
            assert kwargs['exec_mode'] == self.EXEC_ON_SELECTED and kwargs['entities']
            b.inspections += 1
            issue = SimpleNamespace(entities=kwargs['entities'], issues=[], status='error', description='skew', type='quality')
            def fix(request_gui, issues):
                assert request_gui is False and issues == [issue]
                b.calls += 1
                b.fixed = True
            return [SimpleNamespace(has_fix=True, issues=[] if b.fixed else [issue], try_fix=fix,
                                    status='ok' if b.fixed else 'error', description='check', type='header')]
    class Base:
        def __init__(self):
            self.calls, self.inspections, self.fixed, self.deck = 0, 0, False, 8
            self.entities = {(kind, i): Entity(i, kind) for kind in ('NODE','STEP','SHELL','SOLID','FACE','VOLUME','CONS','SET','SURFACE_INTERACTION','MATERIAL') for i in (1, 2)}
            self.settings = {'mesh_change_option': 'macro perimeters'}
            self.criterion = {'status': 0, 'calculation': 'NASTRAN', 'value': 3.}
        def CurrentDeck(self): return self.deck
        def DataBaseName(self): return ''
        def RedrawAll(self): return 1
        def GetEntity(self, deck, kind, identity): return self.entities.get((kind, identity))
        def GetEntityCardValues(self, deck, entity, fields): return {f: entity.fields.get(f) for f in fields}
        def CollectEntities(self, deck, parent, kind, recursive=False):
            if parent is not None:
                return [self.entities[('SHELL', parent._id)]] if kind in ('SHELL', '__ELEMENTS__') else []
            return [e for (k, _), e in self.entities.items() if k == kind]
        def CreateEntity(self, deck, kind, fields):
            self.calls += 1
            entity = Entity(100 + self.calls, kind, fields.copy())
            self.entities[(kind, entity._id)] = entity
            return entity
        def BCSettingsGetValues(self, fields): return self.settings.copy()
        def BCSettingsSetValues(self, values): self.calls += 1; self.settings.update(values); return 0
        def F11ShellsOptionsGet(self, criterion): return self.criterion.copy()
        def F11ShellsOptionsSet(self, criterion, status, calculation, value):
            self.calls += 1
            self.criterion = dict(status=int(status), calculation=calculation or self.criterion['calculation'], value=value)
            return 1
        def Topo(self, ents, **kwargs): self.calls += 1; return 1
        def OutputAbaqus(self, filename, **kwargs):
            self.calls += 1
            Path(filename).write_bytes(b'*NODE\n1,0,0,0\n')
            return 1
        def OutputNastran(self, filename, **kwargs):
            self.calls += 1
            Path(filename).write_bytes(b'GRID,1,,0,0,0\n')
            return 1
        def InputAbaqus(self, filename, **kwargs):
            self.calls += 1
            assert kwargs['model_action'] == 'merge_model' and kwargs['nodes_id'] == 'offset'
            assert Path(filename).read_bytes() == b'*NODE\n1,0,0,0\n'
            return 1
        def CollectNewModelEntities(self, deck):
            return SimpleNamespace(report=lambda: [self.entities[('NODE', 1)]])
    b = Base()
    b.Check = Check
    b.checks = SimpleNamespace(geometry=SimpleNamespace(Cracks=Check, NeedleFaces=Check, CollapsedCons=Check), mesh=SimpleNamespace(MeshQuality=Check))
    def mesh_call(*args, **kwargs): b.calls += 1; return 1
    mesh = SimpleNamespace(Mesh=mesh_call, VolumesMeshV=mesh_call, ApplyNewLengthToMacros=mesh_call,
        Create4SidedMesh=lambda ents, **kw: SimpleNamespace(meshed_ents=ents), RemeshShells=lambda ents, generator: ents)
    r = HandlerRegistry([str(tmp_path)], modules={'base': b, 'session': SimpleNamespace(DeckName=lambda d: str(d)),
        'constants': SimpleNamespace(ABAQUS=8, NASTRAN=1), 'checks': b.checks, 'mesh': mesh})
    def call(name, params, operation_id='engineering-test-001', **updates):
        args = dict(operation=name, parameters=params, expected_database='', expected_session_nonce=r.session_nonce,
                    expected_deck=b.deck, confirm=True, operation_id=operation_id)
        args.update(updates)
        return r.dispatch('execute_operation', args)
    return r, b, call, tmp_path


MATERIAL = dict(name='Steel', young_modulus=210000., poisson_ratio=.3, density=7.85e-9, unit_system='mm-N-tonne')
CONTACT = dict(secondary_set_id=1, main_set_id=2, interaction_id=1, secondary_side='SPOS', main_side='SNEG', name='pair')


@pytest.mark.parametrize('deck,kind', [(8, 'MATERIAL'), (1, 'MAT1')])
def test_material_readback_replay_and_deck_specific_cards(env, deck, kind):
    r, b, call, _ = env
    b.deck = deck
    result = call('create_isotropic_material', MATERIAL)
    assert result['created_entity']['entity_type'] == kind and result['model_effect_verified']
    assert call('create_isotropic_material', MATERIAL)['idempotent_replay']
    assert b.calls == 1


@pytest.mark.parametrize('key,value', [('young_modulus', 0), ('young_modulus', True), ('poisson_ratio', .5),
    ('poisson_ratio', -1), ('density', float('inf')), ('density', -1), ('unit_system', ''), ('name', '../x')])
def test_bad_material_before_write(env, key, value):
    r, b, call, _ = env
    with pytest.raises(ValueError): call('create_isotropic_material', dict(MATERIAL, **{key:value}))
    assert b.calls == 0 and not r._operation_results


@pytest.mark.parametrize('name,params', [
    ('create_nodal_load', dict(node_id=1, step_id=1, dof=3, magnitude=-10., unit_system='mm-N-tonne')),
    ('create_nodal_constraint', dict(node_id=1, dofs='123', value=0., unit_system='mm-N-tonne')),
    ('create_contact_pair', CONTACT),
])
def test_linked_cards_read_back(env, name, params):
    _, b, call, _ = env
    assert call(name, params)['model_effect_verified']
    assert b.calls == 1


@pytest.mark.parametrize('params', [dict(CONTACT, main_set_id=1), dict(CONTACT, interaction_id=99),
    dict(CONTACT, main_side='S1'), dict(CONTACT, secondary_set_id=True)])
def test_bad_contact_rejected_before_write(env, params):
    r, b, call, _ = env
    with pytest.raises(ValueError): call('create_contact_pair', params)
    assert b.calls == 0 and not r._operation_results


def test_unsupported_load_deck_rejected(env):
    _, b, call, _ = env
    b.deck = 1
    with pytest.raises(ValueError, match='deck mismatch'):
        call('create_nodal_load', dict(node_id=1, step_id=1, dof=3, magnitude=10., unit_system='mm-N-tonne'))
    assert b.calls == 0


@pytest.mark.parametrize('name,params', [
    ('topology_paste', dict(entity_type='CONS', entity_ids=[1], use_current_tolerances=True, paste_different_pids=False)),
    ('set_perimeter_length', dict(entity_type='CONS', entity_ids=[1], length=2.)),
    ('generate_surface_mesh', dict(entity_type='FACE', entity_ids=[1], element_type='quad')),
    ('generate_volume_mesh', dict(entity_type='VOLUME', entity_ids=[1], mesh_type='TETRA FEM')),
    ('remesh_shells', dict(entity_type='SHELL', entity_ids=[1], generator='FREE')),
    ('mesh_faces', dict(entity_type='FACE', entity_ids=[1], use_current_mesh_settings=True)),
])
def test_scoped_mesh_never_claims_quality(env, name, params):
    _, b, call, _ = env
    result = call(name, params)
    assert result['quality_verified'] is False
    if name == 'mesh_faces':
        assert result['settings_restored']
    assert b.settings == {'mesh_change_option': 'macro perimeters'}


@pytest.mark.parametrize('ids', [[], [1,1], [True], [99], list(range(201))])
def test_invalid_scope_before_mesh(env, ids):
    r, b, call, _ = env
    with pytest.raises(ValueError): call('generate_volume_mesh', dict(entity_type='VOLUME', entity_ids=ids, mesh_type='TETRA FEM'))
    assert b.calls == 0 and not r._operation_results


def test_repair_is_one_selected_pass_followed_by_new_report(env):
    _, b, call, _ = env
    result = call('repair_mesh_quality', dict(entity_type='SHELL', entity_ids=[1], repair=True, allow_adjacent_changes=True, repair_method='native_fix'))
    assert b.calls == 1 and b.inspections == 2
    assert result['before']['reports'][0]['status'] == 'error'
    assert result['after']['reports'][0]['status'] == 'ok'
    assert not result['quality_verified']


def test_inspect_only_and_adjacent_consent(env):
    r, b, call, _ = env
    p = dict(entity_type='FACE', entity_ids=[1], check='cracks', repair=True, allow_adjacent_changes=False)
    with pytest.raises(ValueError): call('repair_geometry', p)
    assert not r._operation_results
    result = call('repair_geometry', dict(p, repair=False))
    assert b.calls == 0 and result['fix_headers_attempted'] == 0


def test_mesh_setting_restored_after_native_error_and_no_retry(env):
    r, b, call, _ = env
    def fail(entities): b.calls += 1; raise TypeError('native error')
    r._modules_override['mesh'].Mesh = fail
    p = dict(entity_type='FACE', entity_ids=[1], use_current_mesh_settings=True)
    for _ in range(2):
        with pytest.raises(RuntimeError, match='OUTCOME_UNKNOWN'): call('mesh_faces', p)
    assert b.calls == 3 and b.settings['mesh_change_option'] == 'macro perimeters'


def test_reference_assignment_compare_and_set(env):
    _, b, call, _ = env
    target = b.entities[('SHELL', 1)]
    target.fields['PID'] = b.entities[('MATERIAL', 1)]
    p = dict(entity_type='SHELL', entity_id=1, references={'PID': {'entity_type':'MATERIAL','entity_id':2}}, expected_values={'PID':1})
    with pytest.raises(ValueError, match='compare-and-set'): call('set_entity_references', dict(p, expected_values={'PID':2}))
    assert call('set_entity_references', p)['model_effect_verified']
    assert target.fields['PID']._id == 2


@pytest.mark.parametrize('line', [b'*INCLUDE, INPUT=a.inp', b'*INITIAL CONDITIONS, FILE=x', b'INCLUDE \'a.bdf\'', b'ASSIGN X=Y', b'*USER MATERIAL', b'*IMPORT', b'..\\outside'])
def test_flat_decks_reject_external_references(line):
    with pytest.raises(ValueError): flat_deck(b'*NODE\n1,0,0,0\n' + line, 'ABAQUS')


def test_import_digest_and_flat_preflight(env):
    _, b, call, root = env
    source = root / 'test.inp'
    data = b'*NODE\n1,0,0,0\n'
    source.write_bytes(data)
    p = dict(solver='ABAQUS', path=str(source), sha256=hashlib.sha256(data).hexdigest())
    with pytest.raises(ValueError, match='SHA256 mismatch'): call('import_solver_deck', dict(p, sha256='0'*64))
    assert b.calls == 0
    assert call('import_solver_deck', p)['created_count'] == 1
    assert source.read_bytes() == data
    assert call('import_solver_deck', p)['idempotent_replay']
    assert b.calls == 1


def test_export_exclusive_verified_bytes_and_replay(env):
    _, b, call, root = env
    path = root / 'out.inp'
    p = dict(solver='ABAQUS', path=str(path))
    result = call('export_solver_deck', p)
    assert result['file_verified'] and result['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert call('export_solver_deck', p)['idempotent_replay']
    with pytest.raises(ValueError, match='NEW target'): call('export_solver_deck', p, operation_id='export-another-001')
    assert b.calls == 1


def test_export_refuses_path_escape(env):
    _, b, call, root = env
    with pytest.raises(ValueError): call('export_solver_deck', dict(solver='ABAQUS', path=str(root.parent / 'escape.inp')))
    assert b.calls == 0


def test_readback_failure_preserves_unknown_not_success(env):
    _, b, call, _ = env
    b.GetEntityCardValues = lambda *args: {}
    for _ in range(2):
        with pytest.raises(RuntimeError, match='OUTCOME_UNKNOWN'): call('create_isotropic_material', MATERIAL)
    assert b.calls == 1


def test_quality_criterion_cas_and_readback(env):
    _, b, call, _ = env
    p = dict(entity_type='SHELL', criterion='aspect ratio', enabled=True, calculation='NASTRAN', value=4., expected_values=b.criterion.copy())
    with pytest.raises(ValueError, match='compare-and-set'):
        call('set_mesh_quality_criterion', dict(p, expected_values={}))
    assert b.calls == 0
    assert call('set_mesh_quality_criterion', p)['after']['value'] == 4.
    assert call('set_mesh_quality_criterion', p)['idempotent_replay']
    assert b.calls == 1


@pytest.mark.parametrize('method,kind', [('anything','SHELL'), ('smooth_shells','SOLID'), ('reconstruct_shells','SOLID')])
def test_invalid_repair_strategy_before_mutation(env, method, kind):
    r, b, call, _ = env
    with pytest.raises(ValueError):
        call('repair_mesh_quality', dict(entity_type=kind, entity_ids=[1], repair=True, allow_adjacent_changes=True, repair_method=method))
    assert not r._operation_results and b.calls == 0 and b.inspections == 0


def test_smoothing_has_no_implicit_fallback_and_reports_remaining_errors(env):
    r, b, call, _ = env
    def smooth(entities): b.calls += 1; return 0
    r._modules_override['mesh'].SmoothShells = smooth
    result = call('repair_mesh_quality', dict(entity_type='SHELL', entity_ids=[1], repair=True, allow_adjacent_changes=True, repair_method='smooth_shells'))
    assert b.calls == 1 and b.inspections == 2
    assert result['selected_check_passed'] is False
    assert result['fix_headers_attempted'] == 0


def test_deleted_scope_after_repair_is_not_a_pass(env):
    r, b, call, _ = env
    def reconstruct(entities):
        b.entities.pop(('SHELL', 1))
        return 1
    r._modules_override['mesh'].ReconstructShells = reconstruct
    result = call('repair_mesh_quality', dict(entity_type='SHELL', entity_ids=[1], repair=True, allow_adjacent_changes=True, repair_method='reconstruct_shells'))
    assert result['after']['recheck_required'] and result['selected_check_passed'] is None
    assert b.inspections == 1


def test_catalog_honors_deck_and_settings_api_requirements(env):
    r, b, _, _ = env
    b.deck = 1
    entries = r.general.catalog()['operations']
    assert not entries['create_contact_pair']['available']
    assert entries['create_contact_pair']['reason'] == 'current_deck_unsupported'
    b.BCSettingsSetValues = None
    assert not r.general.catalog()['operations']['mesh_faces']['available']


def test_invalid_contact_contents_never_create(env):
    _, b, call, _ = env
    b.CollectEntities = lambda *args, **kwargs: []
    with pytest.raises(ValueError, match='nonempty'): call('create_contact_pair', CONTACT)
    assert b.calls == 0


def test_native_card_input_mutation_cannot_forge_readback(env):
    _, b, call, _ = env
    real_create = b.CreateEntity
    def mutation(deck, kind, fields):
        fields['E' if kind == 'MAT1' else 'YOUNG'] = 100.
        return real_create(deck, kind, fields)
    b.CreateEntity = mutation
    with pytest.raises(RuntimeError, match='OUTCOME_UNKNOWN'): call('create_isotropic_material', MATERIAL)
    assert b.calls == 1
