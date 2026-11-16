"""Construct a read-only part mesh query for the Abaqus kernel."""
import json


def mesh_query(model_name: str, part_name: str, analysis_checks: bool, label_limit: int) -> str:
    if not model_name or not part_name:
        raise ValueError("model_name and part_name must not be empty")
    if type(label_limit) is not int or not 0 <= label_limit <= 200:
        raise ValueError("label_limit must be between 0 and 200")
    arguments = json.dumps([model_name, part_name, analysis_checks, label_limit])
    return "import json\nmodel_name, part_name, run_checks, label_limit = json.loads(" + repr(arguments) + ")\n" + '''
from abaqus import mdb
from abaqusConstants import ANALYSIS_CHECKS, SIZE
from collections import Counter
from itertools import islice

part = mdb.models[model_name].parts[part_name]
element_types = Counter(str(element.type) for element in part.elements)
element_count = len(part.elements)
quality = {"status": "not_requested"}
if run_checks:
    if not element_count:
        quality = {"status": "unmeshed"}
    else:
        checks = part.verifyMeshQuality(criterion=ANALYSIS_CHECKS)
        quality = {"status": "returned", "reported_element_count": checks.get("numElements")}
        for key, prefix in (("failedElements", "failed"), ("warningElements", "warning"),
                            ("naElements", "not_applicable")):
            selection = checks.get(key, ())
            quality[prefix + "_count"] = len(selection)
            quality[prefix + "_labels"] = [e.label for e in islice(selection, label_limit)]

has_geometry = bool(len(part.cells) or len(part.faces) or len(part.edges) or len(part.vertices))
result = {
    "model": model_name,
    "part": part_name,
    "node_count": len(part.nodes),
    "element_count": element_count,
    "element_types": dict(element_types),
    "global_seed_size": float(part.getPartSeeds(attribute=SIZE)) if has_geometry else None,
    "analysis_checks": quality,
}
'''
