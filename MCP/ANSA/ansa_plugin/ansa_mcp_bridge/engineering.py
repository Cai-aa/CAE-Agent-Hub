"""Bounded engineering operations. Native completion is not solver validation.

prepare() is read-only: all mutations occur in the returned callable, after the
shared operation ledger has been reserved. Never retry a different signature.
"""
import hashlib
import math
import re
import tempfile
from pathlib import Path

from .handlers import _jsonable, _validate_bool, _validate_entity_id, _validate_integer

SCOPE = {'entity_type': 'explicit type, see operation', 'entity_ids': '1..200 unique existing IDs'}
SPECS = {
    'topology_paste': ('base', 'Topo', dict(SCOPE, use_current_tolerances='true; shared boundaries may change', paste_different_pids='boolean')),
    'set_perimeter_length': ('mesh', 'ApplyNewLengthToMacros', dict(SCOPE, length='positive model-unit length; CONS or FE PERIMETER')),
    'generate_surface_mesh': ('mesh', 'Create4SidedMesh', dict(SCOPE, element_type='quad|mixed|ortho_tria; FACE; only four-sided faces')),
    'mesh_faces': ('mesh', 'Mesh', dict(SCOPE, use_current_mesh_settings='true; FACE; current algorithm/type/order; mesh_change_option temporarily set to mesh then restored')),
    'generate_volume_mesh': ('mesh', 'VolumesMeshV', dict(SCOPE, mesh_type='TETRA FEM|TETRA RAPID|TETRA CFD; VOLUME; current mesh settings')),
    'remesh_shells': ('mesh', 'RemeshShells', dict(SCOPE, generator='CFD|ADVFRNT|FREE|SPOT|GRADUAL; current mesh settings')),
    'repair_geometry': ('base', 'Check', dict(SCOPE, check='cracks|needle_faces|collapsed_cons; FACE', repair='boolean; false=inspect only', allow_adjacent_changes='must be true for repair')),
    'repair_mesh_quality': ('base', 'Check', dict(SCOPE, repair='boolean; SHELL or SOLID; current quality criteria', allow_adjacent_changes='must be true for repair', repair_method='native_fix|smooth_shells|reconstruct_shells; one pass, no automatic fallback')),
    'set_mesh_quality_criterion': ('base', 'Check', {'entity_type': 'SHELL|SOLID', 'criterion': 'aspect ratio|min length|max length|skewness|warpage|jacobian', 'enabled': 'boolean', 'calculation': 'explicit ANSA method string; empty preserves current', 'value': 'positive threshold', 'expected_values': 'exact current {status, calculation, value} from API readback'}),
    'create_isotropic_material': ('base', 'CreateEntity', {'name': 'unique name', 'young_modulus': 'positive', 'poisson_ratio': '-1 < nu < 0.5', 'density': 'positive', 'unit_system': 'explicit unit convention; no conversion'}),
    'create_nodal_load': ('base', 'CreateEntity', {'node_id': 'ABAQUS NODE ID', 'step_id': 'existing ABAQUS STEP ID', 'dof': '1..6', 'magnitude': 'finite, per-node value', 'unit_system': 'explicit unit convention; no conversion'}),
    'create_nodal_constraint': ('base', 'CreateEntity', {'node_id': 'ABAQUS NODE ID', 'dofs': 'unique ascending digits 1..6', 'value': 'prescribed value for all supplied DOFs', 'unit_system': 'explicit unit convention; no conversion'}),
    'create_contact_pair': ('base', 'CreateEntity', {'secondary_set_id': 'ABAQUS nonempty shell SET', 'main_set_id': 'different nonempty shell SET', 'interaction_id': 'existing SURFACE_INTERACTION', 'secondary_side': 'SPOS|SNEG', 'main_side': 'SPOS|SNEG', 'name': 'unique name'}),
    'set_entity_references': ('base', 'GetEntity', {'entity_type': 'exact current-deck target type', 'entity_id': 'existing target ID', 'references': '1..10 card-field -> {entity_type, entity_id}; e.g. property MID -> material', 'expected_values': 'same fields -> current referenced ID or null; compare-and-set'}),
    'import_solver_deck': ('base', 'CollectNewModelEntities', {'solver': 'ABAQUS|NASTRAN; must match current deck', 'path': 'absolute flat ASCII input within allowed_roots; external references rejected', 'sha256': 'expected file SHA256; merge only with offset IDs'}),
    'export_solver_deck': ('base', 'CollectEntities', {'solver': 'ABAQUS|NASTRAN; must match current deck', 'path': 'absolute NEW .inp/.bdf/.nas file within allowed_roots; monolithic all-model export'}),
}
CHECK_FACTORIES = {'cracks': 'Cracks', 'needle_faces': 'NeedleFaces', 'collapsed_cons': 'CollapsedCons'}


def number(value, name, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or (positive and value <= 0):
        raise ValueError(name + ' must be a finite ' + ('positive number' if positive else 'number'))
    return value


def label(value, name):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_. -]{0,79}', value):
        raise ValueError(name + ' requires 1..80 ASCII name characters')
    return value


def flat_deck(data, solver):
    """Conservative flat-input gate, not a solver syntax/security sandbox."""
    if not data or len(data) > 32 * 1024 * 1024:
        raise ValueError('Solver file must contain 1..32 MiB')
    text = data.decode('ascii')
    if '\x00' in text:
        raise ValueError('Binary input is unsupported')
    for line in text.splitlines():
        line = line.strip().upper()
        if not line or line.startswith(('**', '$')):
            continue
        if (re.search(r'\b(INCLUDE|ASSIGN|RESTART|DMIIN|DBLOCATE|ALTER|DMAP|INPUT|FILE|LIBRARY|USER|IMPORT|SUBSTRUCTURE)\b', line)
                or '\\' in line or '/' in line):
            raise ValueError('External references/advanced directives unsupported; supply a flattened basic solver deck')
    if solver == 'ABAQUS' and '*NODE' not in text.upper():
        raise ValueError('Abaqus import requires a *NODE section')
    if solver == 'NASTRAN' and not re.search(r'^\s*GRID[*, ]', text, re.M | re.I):
        raise ValueError('Nastran import requires GRID data')
    return text


class EngineeringOperations:
    def __init__(self, general):
        self.g = general
        self.r = general.r

    def availability(self, operation):
        """Symbol/deck checks only. No model modification or signature trial."""
        supported = ('ABAQUS',) if operation in ('create_nodal_load', 'create_nodal_constraint', 'create_contact_pair') else (
            ('NASTRAN', 'ABAQUS') if operation in ('create_isotropic_material', 'import_solver_deck', 'export_solver_deck') else ())
        dependencies = {
            'mesh_faces': [('base', 'BCSettingsGetValues'), ('base', 'BCSettingsSetValues'), ('base', 'CollectEntities')],
            'set_entity_references': [('base', 'GetEntity')],
            'set_mesh_quality_criterion': [('base', 'F11ShellsOptionsGet'), ('base', 'F11ShellsOptionsSet'),
                                           ('base', 'F11SolidsOptionsGet'), ('base', 'F11SolidsOptionsSet')],
            'import_solver_deck': [('base', 'CollectNewModelEntities')],
            'export_solver_deck': [],
        }.get(operation, [])
        base = self.g.module('base')
        current = base.CurrentDeck()
        if supported:
            constants = self.g.module('constants')
            matches = [name for name in supported if getattr(constants, name, None) == current]
            if not matches:
                return {'available': False, 'supported_decks': list(supported), 'reason': 'current_deck_unsupported'}
            if operation in ('import_solver_deck', 'export_solver_deck'):
                dependencies = dependencies + [('base', ('Input' if operation == 'import_solver_deck' else 'Output') + ('Abaqus' if matches[0] == 'ABAQUS' else 'Nastran'))]
        for module, name in dependencies:
            self.g.api(module, name)
        if operation in ('repair_geometry', 'repair_mesh_quality'):
            group = getattr(getattr(base, 'checks', None), 'geometry' if operation == 'repair_geometry' else 'mesh', None)
            names = list(CHECK_FACTORIES.values()) if operation == 'repair_geometry' else ['MeshQuality']
            if not all(callable(getattr(group, n, None)) for n in names):
                raise ValueError('UNSUPPORTED_CAPABILITY: Check factories')
        return {'available': True, 'supported_decks': list(supported) or ['runtime_dependent']}

    def resolve(self, base, deck, kind, identity):
        _validate_entity_id(identity)
        value = base.GetEntity(deck, kind, identity)
        if value is None:
            raise ValueError('Missing %s ID %s' % (kind, identity))
        return value

    def scope(self, base, deck, p, kinds):
        if p['entity_type'] not in kinds:
            raise ValueError('entity_type must be one of ' + ', '.join(kinds))
        ids = p['entity_ids']
        if not isinstance(ids, list) or not 1 <= len(ids) <= 200:
            raise ValueError('entity_ids requires 1..200 explicit IDs')
        for identity in ids:
            _validate_entity_id(identity)
        if len(set(ids)) != len(ids):
            raise ValueError('Duplicate entity IDs')
        return [self.resolve(base, deck, p['entity_type'], i) for i in ids]

    def deck(self, deck, name):
        if name not in ('ABAQUS', 'NASTRAN') or deck != getattr(self.g.module('constants'), name, None):
            raise ValueError('Unsupported solver or current deck mismatch: ' + str(name))

    def unique_name(self, base, deck, kind, name):
        label(name, 'name')
        for entity in base.CollectEntities(deck, None, kind) or []:
            if base.GetEntityCardValues(deck, entity, ('Name',)).get('Name') == name:
                raise ValueError('An entity of this type already uses that name')

    def create(self, base, deck, kind, fields, units=None):
        def run():
            entity = base.CreateEntity(deck, kind, dict(fields))
            if entity is None:
                raise RuntimeError('CreateEntity returned no entity for ' + kind)
            values = base.GetEntityCardValues(deck, entity, tuple(fields))
            mismatches = []
            for key, expected in fields.items():
                actual = values.get(key) if isinstance(values, dict) else None
                equal = (math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-14)
                         if isinstance(expected, (int, float)) and isinstance(actual, (int, float)) else actual == expected)
                if not equal:
                    mismatches.append(key)
            if mismatches:
                raise RuntimeError('Created %s ID %s but card readback differs: %s' % (kind, entity._id, mismatches))
            return {'created_entity': {'id': entity._id, 'entity_type': kind},
                    'readback': _jsonable(values), 'model_effect_verified': True, 'unit_system': units}
        return run

    def prepare(self, operation, p, base, deck):
        if operation == 'mesh_faces':
            entities = self.scope(base, deck, p, ('FACE',))
            if p['use_current_mesh_settings'] is not True:
                raise ValueError('Explicit use_current_mesh_settings=true required')
            function = self.g.api('mesh', 'Mesh')
            get_settings = self.g.api('base', 'BCSettingsGetValues')
            set_settings = self.g.api('base', 'BCSettingsSetValues')
            previous = get_settings(('mesh_change_option',))
            if not isinstance(previous, dict) or not isinstance(previous.get('mesh_change_option'), str):
                raise ValueError('UNSUPPORTED_CAPABILITY: mesh_change_option readback unavailable')
            def run_faces():
                try:
                    if set_settings({'mesh_change_option': 'mesh'}) != 0 or get_settings(('mesh_change_option',)) != {'mesh_change_option': 'mesh'}:
                        raise RuntimeError('Mesh mode readback mismatch')
                    if function(entities) != 1:
                        raise RuntimeError('mesh.Mesh returned failure')
                    counts = {str(e._id): len(base.CollectEntities(deck, e, 'SHELL') or []) for e in entities}
                finally:
                    if set_settings(previous) != 0 or get_settings(('mesh_change_option',)) != previous:
                        raise RuntimeError('Mesh mode restoration failed; inspect application settings')
                return {'shell_counts_by_face': counts, 'settings_restored': True,
                        'model_effect_verified': False, 'quality_verified': False}
            return run_faces
        if operation in ('topology_paste', 'set_perimeter_length', 'generate_surface_mesh', 'generate_volume_mesh', 'remesh_shells'):
            kinds = {'topology_paste': ('CONS',), 'set_perimeter_length': ('CONS', 'FE PERIMETER'),
                     'generate_surface_mesh': ('FACE',), 'generate_volume_mesh': ('VOLUME',), 'remesh_shells': ('SHELL',)}[operation]
            entities = self.scope(base, deck, p, kinds)
            module, api, _ = SPECS[operation]
            function = self.g.api(module, api)
            args, kwargs = (entities,), {}
            if operation == 'topology_paste':
                if p['use_current_tolerances'] is not True:
                    raise ValueError('Explicit use_current_tolerances=true required')
                kwargs = {'paste_with_frozen_faces': False, 'paste_different_pids': _validate_bool(p['paste_different_pids'], 'paste_different_pids')}
            elif operation == 'set_perimeter_length':
                args = (str(number(p['length'], 'length', True)), entities)
                kwargs = {'use_ansa_defaults_values': False}
            elif operation == 'generate_surface_mesh':
                if p['element_type'] not in ('quad', 'mixed', 'ortho_tria'):
                    raise ValueError('Unsupported element_type')
                kwargs = dict(only_4sided=True, only_aligned=False, corner_angle=40., smooth_type='standard',
                              split_method='hybrid', spacing='isospace', elem_type=p['element_type'], quad_pattern='radial')
            elif operation == 'generate_volume_mesh':
                if p['mesh_type'] not in ('TETRA FEM', 'TETRA RAPID', 'TETRA CFD'):
                    raise ValueError('Unsupported mesh_type')
                args = (entities, p['mesh_type'])
            else:
                if p['generator'] not in ('CFD', 'ADVFRNT', 'FREE', 'SPOT', 'GRADUAL'):
                    raise ValueError('Unsupported generator')
                args = (entities, p['generator'])
            def run():
                returned = function(*args, **kwargs)
                if operation in ('topology_paste', 'generate_volume_mesh') and returned != 1:
                    raise RuntimeError(api + ' returned failure')
                result = {'api_return': _jsonable(returned), 'model_effect_verified': False,
                          'scope': {'entity_type': p['entity_type'], 'entity_ids': p['entity_ids']},
                          'quality_verified': False, 'warning': 'Shared boundary/adjacent connectivity may change; current mesh settings/criteria apply.'}
                if operation == 'generate_surface_mesh':
                    meshed = getattr(returned, 'meshed_ents', None)
                    if meshed is None:
                        raise RuntimeError('Create4SidedMesh supplied no meshed_ents evidence')
                    result['meshed_entities'] = _jsonable(list(meshed))
                    result['all_requested_meshed'] = {e._id for e in entities} <= {e._id for e in meshed}
                elif operation == 'remesh_shells':
                    if returned is None:
                        raise RuntimeError('RemeshShells supplied no result')
                    result['new_shells'] = _jsonable(returned)
                return result
            return run
        if operation in ('repair_geometry', 'repair_mesh_quality'):
            return self.prepare_repair(operation, p, base, deck)
        if operation == 'set_mesh_quality_criterion':
            if p['entity_type'] not in ('SHELL', 'SOLID') or p['criterion'] not in ('aspect ratio', 'min length', 'max length', 'skewness', 'warpage', 'jacobian'):
                raise ValueError('Unsupported quality criterion/type')
            prefix = 'F11ShellsOptions' if p['entity_type'] == 'SHELL' else 'F11SolidsOptions'
            getter, setter = self.g.api('base', prefix + 'Get'), self.g.api('base', prefix + 'Set')
            enabled = _validate_bool(p['enabled'], 'enabled')
            threshold = number(p['value'], 'value', True)
            calculation = p['calculation']
            if not isinstance(calculation, str) or len(calculation) > 80:
                raise ValueError('Invalid calculation name')
            old = getter(p['criterion'])
            if not isinstance(old, dict) or set(old) != {'status', 'calculation', 'value'}:
                raise ValueError('UNSUPPORTED_CAPABILITY: criterion readback unavailable')
            if not isinstance(p['expected_values'], dict) or old != p['expected_values']:
                raise ValueError('Quality criterion compare-and-set mismatch; current=' + repr(old))
            def run_criterion():
                if setter(p['criterion'], enabled, calculation, threshold) != 1:
                    raise RuntimeError('Quality criterion setter failed')
                after = getter(p['criterion'])
                target_calculation = calculation if calculation else old['calculation']
                if not isinstance(after, dict) or bool(after.get('status')) != enabled or after.get('calculation') != target_calculation or after.get('value') != threshold:
                    raise RuntimeError('Quality criterion readback mismatch')
                return {'before': old, 'after': after, 'model_effect_verified': True, 'warning': 'Changes global ANSA quality criteria; not saved as defaults automatically.'}
            return run_criterion
        if operation == 'create_isotropic_material':
            units = label(p['unit_system'], 'unit_system')
            e, nu, rho = number(p['young_modulus'], 'young_modulus', True), number(p['poisson_ratio'], 'poisson_ratio'), number(p['density'], 'density', True)
            if not -1 < nu < .5:
                raise ValueError('Isotropic elasticity requires -1 < poisson_ratio < 0.5')
            if deck == getattr(self.g.module('constants'), 'NASTRAN', None):
                kind, fields = 'MAT1', {'Name': p['name'], 'E': e, 'NU': nu, 'RHO': rho, 'DEFINED': 'YES'}
            else:
                self.deck(deck, 'ABAQUS')
                kind, fields = 'MATERIAL', {'Name': p['name'], '*ELASTIC': 'YES', 'ELASTIC_TYPE': 'ISOTROPIC',
                    'YOUNG': e, 'POISSON': nu, '*DENSITY': 'YES', 'DENS': rho, 'DEFINED': 'YES'}
            self.unique_name(base, deck, kind, p['name'])
            return self.create(base, deck, kind, fields, units)
        if operation in ('create_nodal_load', 'create_nodal_constraint'):
            self.deck(deck, 'ABAQUS')
            self.resolve(base, deck, 'NODE', p['node_id'])
            units = label(p['unit_system'], 'unit_system')
            if operation == 'create_nodal_load':
                self.resolve(base, deck, 'STEP', p['step_id'])
                dof = _validate_integer(p['dof'], 'dof')
                if dof not in range(1, 7):
                    raise ValueError('dof must be 1..6')
                fields = {'STEP': p['step_id'], 'by': 'node', 'NODE': p['node_id'],
                          'DOF': ('1: Fx', '2: Fy', '3: Fz', '4: Mx', '5: My', '6: Mz')[dof-1], 'magn': number(p['magnitude'], 'magnitude')}
                return self.create(base, deck, 'CLOAD', fields, units)
            dofs = p['dofs']
            if not isinstance(dofs, str) or not re.fullmatch('[1-6]{1,6}', dofs) or ''.join(sorted(set(dofs))) != dofs:
                raise ValueError('dofs must be unique ascending digits 1..6')
            return self.create(base, deck, 'BOUNDARY', {'by': 'node', 'NODE': p['node_id'],
                'format': 'direct', 'DOF': dofs, 'Magn': number(p['value'], 'value')}, units)
        if operation == 'create_contact_pair':
            self.deck(deck, 'ABAQUS')
            self.unique_name(base, deck, 'CONTACT_PAIR', p['name'])
            if p['secondary_set_id'] == p['main_set_id']:
                raise ValueError('Contact sets must be different')
            members = []
            for key in ('secondary_set_id', 'main_set_id'):
                group = self.resolve(base, deck, 'SET', p[key])
                shells = base.CollectEntities(deck, group, 'SHELL', recursive=True) or []
                all_elements = base.CollectEntities(deck, group, '__ELEMENTS__', recursive=True) or []
                if not shells or {e._id for e in shells} != {e._id for e in all_elements}:
                    raise ValueError('Contact requires nonempty shell-only element sets')
                members.append({e._id for e in shells})
            if members[0] & members[1]:
                raise ValueError('Contact sets must not share shell elements')
            self.resolve(base, deck, 'SURFACE_INTERACTION', p['interaction_id'])
            for key in ('secondary_side', 'main_side'):
                if p[key] not in ('SPOS', 'SNEG'):
                    raise ValueError(key + ' must be SPOS or SNEG')
            return self.create(base, deck, 'CONTACT_PAIR', {'Name': p['name'], 'TYPE': 'CONTACT PAIR', 'STEP': 0,
                'SECONDARY': 'ELEMENT', 'SSID': p['secondary_set_id'], 'MAIN': 'ELEMENT', 'MSID': p['main_set_id'],
                'INTERACTION': p['interaction_id'], 'ORIENT_S': p['secondary_side'], 'ORIENT_M': p['main_side'],
                'TYPE_tie_coefficients': 'SURFACE TO SURFACE', 'TIED': 'NO', 'SMALL SLIDING': 'NO'})
        if operation == 'set_entity_references':
            from .handlers import _validate_entity_type
            target = self.resolve(base, deck, _validate_entity_type(p['entity_type']), p['entity_id'])
            refs, expected = p['references'], p['expected_values']
            if not isinstance(refs, dict) or not 1 <= len(refs) <= 10 or not isinstance(expected, dict) or set(refs) != set(expected):
                raise ValueError('references/expected_values must have the same 1..10 fields')
            getter, setter = getattr(target, 'get_entity_values', None), getattr(target, 'set_entity_values', None)
            if not callable(getter) or not callable(setter):
                raise ValueError('UNSUPPORTED_CAPABILITY: entity reference API')
            fields = set(target.card_fields(deck))
            resolved = {}
            for key, ref in refs.items():
                if not isinstance(key, str) or key.startswith('__') or key not in fields:
                    raise ValueError('Not a current card field: ' + str(key))
                if not isinstance(ref, dict) or set(ref) != {'entity_type', 'entity_id'}:
                    raise ValueError('Each reference requires entity_type and entity_id')
                resolved[key] = self.resolve(base, deck, _validate_entity_type(ref['entity_type']), ref['entity_id'])
                if expected[key] is not None:
                    _validate_entity_id(expected[key])
            current = getter(deck, tuple(refs))
            if not isinstance(current, dict) or any(k not in current or (current[k] is not None and not hasattr(current[k], '_id')) for k in refs):
                raise ValueError('Only native entity-reference fields are supported')
            if {k: None if current[k] is None else current[k]._id for k in refs} != expected:
                raise ValueError('Reference compare-and-set mismatch')
            def run_refs():
                identities = {k: (v._id, v.ansa_type(deck)) for k, v in resolved.items()}
                # ANSA 25.1.2 mutates the passed mapping, replacing Entities by IDs.
                if setter(deck, dict(resolved)) != 0:
                    raise RuntimeError('Reference setter returned failure')
                after = getter(deck, tuple(refs))
                for k, identity in identities.items():
                    actual = after.get(k)
                    if actual is None or not hasattr(actual, '_id') or (actual._id, actual.ansa_type(deck)) != identity:
                        raise RuntimeError('Reference readback mismatch: ' + k)
                return {'entity_id': target._id, 'references': refs, 'model_effect_verified': True}
            return run_refs
        if operation in ('import_solver_deck', 'export_solver_deck'):
            return self.prepare_file(operation, p, base, deck)
        raise ValueError('Unknown engineering operation')

    def prepare_repair(self, operation, p, base, deck):
        geometry = operation == 'repair_geometry'
        entities = self.scope(base, deck, p, ('FACE',) if geometry else ('SHELL', 'SOLID'))
        repair = _validate_bool(p['repair'], 'repair')
        adjacent = _validate_bool(p['allow_adjacent_changes'], 'allow_adjacent_changes')
        if repair and not adjacent:
            raise ValueError('Native fixes can affect adjacent connectivity; explicit allow_adjacent_changes=true required')
        if geometry and p['check'] not in CHECK_FACTORIES:
            raise ValueError('Unsupported geometry check')
        group = getattr(getattr(base, 'checks', None), 'geometry' if geometry else 'mesh', None)
        factory = getattr(group, CHECK_FACTORIES[p['check']] if geometry else 'MeshQuality', None)
        if not callable(factory):
            raise ValueError('UNSUPPORTED_CAPABILITY: selected Check factory')
        check = factory()
        if not check.is_available_in_deck(deck):
            raise ValueError('Check unavailable in current deck')
        method = 'native_fix' if geometry else p['repair_method']
        if method not in ('native_fix', 'smooth_shells', 'reconstruct_shells'):
            raise ValueError('Unsupported repair_method')
        repair_api = None
        if method != 'native_fix':
            if p['entity_type'] != 'SHELL':
                raise ValueError('Shell repair methods require SHELL entities')
            repair_api = self.g.api('mesh', 'SmoothShells' if method == 'smooth_shells' else 'ReconstructShells')
        def inspect():
            remaining = [200]
            current = [base.GetEntity(deck, p['entity_type'], i) for i in p['entity_ids']]
            if any(e is None for e in current):
                return [], {'reports': [], 'truncated': False, 'scope_changed': True, 'recheck_required': True}
            reports = list(check.execute(exec_mode=base.Check.EXEC_ON_SELECTED,
                report=base.Check.REPORT_NONE, history=base.Check.CLEAR_OLD, entities=current) or [])
            serialized = [self.r._serialize_report(r, remaining) for r in reports[:200]]
            return reports, {'reports': serialized, 'truncated': len(reports) > 200 or remaining[0] <= 0}
        def run():
            reports, before = inspect()
            attempts = 0
            repair_return = None
            if repair and repair_api is not None and any(getattr(h, 'status', '') in ('error', 'warning') for h in reports):
                repair_return = repair_api(entities)
            elif repair and repair_api is None:
                # One native pass only; do not auto-loop or fix an entire model.
                for header in reports[:200]:
                    issues = list(getattr(header, 'issues', []) or [])
                    if getattr(header, 'has_fix', False) and issues:
                        header.try_fix(False, issues=issues[:200])
                        attempts += 1
            _, after = inspect()
            selected_pass = (None if after.get('scope_changed') or after['truncated'] or not after['reports']
                             else all(h['status'] == 'ok' for h in after['reports']))
            return {'before': before, 'after': after, 'fix_headers_attempted': attempts,
                    'repair_method': method, 'repair_api_return': _jsonable(repair_return),
                    'selected_check_passed': selected_pass,
                    'model_effect_verified': False, 'quality_verified': False,
                    'scope': p['entity_ids'], 'warning': 'Only selected check/current criteria evaluated; inspect remaining reports and adjacent entities. No global quality/geometry certificate.'}
        return run

    def prepare_file(self, operation, p, base, deck):
        solver = p['solver']
        self.deck(deck, solver)
        value = p['path']
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise ValueError('path must be absolute')
        path = self.r._allowed_output(value)
        suffixes = ('.inp',) if solver == 'ABAQUS' else ('.bdf', '.nas', '.dat')
        if path.suffix.lower() not in suffixes:
            raise ValueError('Wrong solver file extension')
        importing = operation == 'import_solver_deck'
        function = self.g.api('base', ('Input' if importing else 'Output') + ('Abaqus' if solver == 'ABAQUS' else 'Nastran'))
        if importing:
            if not isinstance(p['sha256'], str) or not re.fullmatch('[0-9a-fA-F]{64}', p['sha256']):
                raise ValueError('Expected SHA256 required')
            if not path.is_file() or path.stat().st_size > 32 * 1024 * 1024:
                raise ValueError('Input must be an existing file <=32 MiB')
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            if digest != p['sha256'].lower():
                raise ValueError('Input SHA256 mismatch')
            flat_deck(data, solver)
            collector_api = self.g.api('base', 'CollectNewModelEntities')
            def run():
                # Import verified bytes, not a mutable original path; flat gate disallows includes.
                collector = collector_api(deck)
                with tempfile.TemporaryDirectory(prefix='ansa-mcp-import-', dir=str(path.parent)) as directory:
                    staged = Path(directory) / path.name
                    staged.write_bytes(data)
                    code = function(str(staged), model_action='merge_model', new_include='off',
                        nodes_id='offset', elements_id='offset', properties_id='offset', materials_id='offset',
                        sets_id='offset', merge_sets_by_name='off', paste_nodes_by_name='off',
                        paste_nodes_by_id='off', merge_parts='off', read_comments='off', header='merge')
                    if code != 1:
                        raise RuntimeError('Native import failed')
                added = list(collector.report() or [])
                return {'source_sha256': digest, 'created_count': len(added), 'created_entities': _jsonable(added[:200]),
                        'truncated': len(added) > 200, 'model_effect_verified': bool(added), 'mode': 'merge-offset', 'unsupported_keywords_may_be_omitted': True}
            return run
        if path.exists() or not path.parent.is_dir():
            raise ValueError('Export requires a NEW target and existing parent directory')
        def run():
            # All native output goes into a private new directory. Publish with exclusive
            # creation only after checking for nonempty monolithic output; never overwrite.
            with tempfile.TemporaryDirectory(prefix='ansa-mcp-export-', dir=str(path.parent)) as directory:
                staged = Path(directory) / path.name
                kwargs = dict(filename=str(staged), mode='all', disregard_includes='on', include_output_mode='contents',
                    output_parts_in_xml='off', update_include_fname='off', output_all_same_directory='on',
                    monolithic_output='on', write_comments='off')
                if solver == 'ABAQUS':
                    kwargs['solver'] = 'standard'
                else:
                    kwargs.update(format='long', enddata='on')
                if function(**kwargs) != 1 or not staged.is_file() or staged.stat().st_size == 0:
                    raise RuntimeError('Native export produced no nonempty solver file')
                data = staged.read_bytes()
                # Refuse references before claiming a standalone deliverable.
                flat_deck(data, solver)
                if any(f.is_file() and f != staged for f in Path(directory).rglob('*')):
                    raise RuntimeError('Unexpected additional output files; monolithic export not established')
                with path.open('xb') as output:
                    output.write(data)
                if path.stat().st_size != len(data) or hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(data).digest():
                    raise RuntimeError('Published file readback mismatch')
            return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                    'file_verified': True, 'model_effect_verified': False, 'solver_validation': 'not_run'}
        return run
