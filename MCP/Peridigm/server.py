"""Thin MCP adapter; no alternate solver implementation or arbitrary execution."""
from mcp.server.fastmcp import FastMCP
import core
mcp=FastMCP("Peridigm evidence workflow",instructions="Use start_context and answer_context before submission. Never change frozen physics to obtain solver success. Exact reviewed elastic and synthetic precracked tensile damage profiles are supported; inspect their individual scope and MPI limits. Fracture front is a bond-failure indicator, not an exact crack surface.")
for name,fn in {
    "peridigm_doctor":core.doctor,"peridigm_templates":core.list_templates,
    "peridigm_start_context":core.start_context,"peridigm_answer_context":core.answer_context,
    "peridigm_validate":core.validate_case,"peridigm_repair":core.repair_case,
    "peridigm_submit":core.submit_case,"peridigm_status":core.job_status,
    "peridigm_log":core.read_log,"peridigm_cancel":core.cancel_job,
    "peridigm_collect":core.collect_results,"peridigm_report":core.make_report,
}.items(): mcp.add_tool(fn,name=name)
if __name__=="__main__":mcp.run(transport="stdio")
