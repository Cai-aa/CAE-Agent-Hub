"""Opt-in, disposable ANSA process only. Never load in an existing session."""
import json
import os
import traceback
from pathlib import Path
from ansa import base, constants, session

root = Path(os.environ['ANSA_MCP_ENGINEERING_PROBE']).resolve(strict=True)
report = {'pid': os.getpid(), 'cards': {}}
try:
    assert not base.DataBaseName(), 'Probe requires an empty, isolated process'
    for name, kinds in [('NASTRAN', ['MAT1', 'PSHELL', 'FORCE', 'SPC1', 'GRID']),
                        ('ABAQUS', ['MATERIAL', 'ELASTIC', 'CLOAD', 'BOUNDARY', 'CONTACT_PAIR', 'SURFACE_INTERACTION', 'SURFACE', 'SET'])]:
        deck = getattr(constants, name)
        base.SetCurrentDeck(deck)
        for kind in kinds:
            try:
                entity = base.CreateEntity(deck, kind)
                report['cards'][name + ':' + kind] = None if entity is None else {
                    'id': entity._id, 'fields': list(entity.card_fields(deck)),
                    'values': base.GetEntityCardValues(deck, entity, tuple(entity.card_fields(deck))) }
            except Exception as exc:
                report['cards'][name + ':' + kind] = {'error': str(exc)}
    report['settings'] = base.BCSettingsGetValues(('mesh_change_option',))
    deck = constants.ABAQUS
    base.SetCurrentDeck(deck)
    source = Path(__file__).parent / 'fixtures/engineering_patch.inp'
    report['import'] = base.InputAbaqus(str(source), model_action='merge_model')
    report['imported'] = {}
    for kind in ['MATERIAL', 'SHELL', 'SECTION_SHELL', 'CLOAD', 'LOAD', 'FORCE', 'BOUNDARY', 'BOUNDARY_SPC', 'CONTACT_PAIR', 'SURFACE_INTERACTION', 'SURFACE', 'STEP']:
        entities = base.CollectEntities(deck, None, kind) or []
        report['imported'][kind] = [{'id': e._id, 'fields': list(e.card_fields(deck)),
            'values': base.GetEntityCardValues(deck, e, tuple(e.card_fields(deck)))} for e in entities[:3]]
    report['contact_references'] = []
    for contact in base.CollectEntities(deck, None, 'CONTACT_PAIR'):
        refs = contact.get_entity_values(deck, ('SSID', 'MSID', 'INTERACTION'))
        report['contact_references'].append({k: {'id': v._id, 'type': v.ansa_type(deck),
            'fields': list(v.card_fields(deck)), 'values': base.GetEntityCardValues(deck, v, tuple(v.card_fields(deck)))} for k, v in refs.items()})
    report['ok'] = True
except Exception:
    report['error'] = traceback.format_exc()
finally:
    (root / 'probe.json').write_text(json.dumps(report, default=str, indent=2), encoding='utf-8')
    session.Quit(0)
