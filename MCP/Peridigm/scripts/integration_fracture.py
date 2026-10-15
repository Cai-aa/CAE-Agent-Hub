"""Real STDIO fracture integration with explicitly labeled scripted answers."""
import asyncio,json,os,sys,time
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core

async def run():
    transcript=[];variant=sys.argv[1] if len(sys.argv)>1 else 'base'
    params=StdioServerParameters(command=sys.executable,args=[str(Path(__file__).resolve().parents[1]/'server.py')],env=dict(os.environ))
    async with stdio_client(params) as (reader,writer):
        async with ClientSession(reader,writer) as client:
            init=await client.initialize();listed=await client.list_tools()
            async def call(name,args):
                r=await client.call_tool(name,args);data=r.structuredContent or json.loads(r.content[0].text);transcript.append({'at':core.stamp(),'tool':name,'arguments':args,'result':data})
                if r.isError or data.get('status')=='BLOCKED':raise RuntimeError(str(data))
                return data
            templates=await call('peridigm_templates',{});assert any(t['id']=='notched-tension-damage-v1' for t in templates['templates'])
            r=await call('peridigm_start_context',{'request':'Scripted integration: synthetic precracked tensile fracture with independently reconstructed damage; time-step variant '+variant,'actor':'scripted_integration_test'});rid=r['run_id']
            selected=await call('peridigm_answer_context',{'run_id':rid,'answers':{'template_id':'notched-tension-damage-v1','time_step_variant':variant},'actor':'scripted_integration_test'})
            await call('peridigm_answer_context',{'run_id':rid,'answers':{'confirm_spec_sha256':core.canonical(selected['specification'])},'actor':'scripted_integration_test'})
            await call('peridigm_submit',{'run_id':rid,'timeout_seconds':120})
            deadline=time.monotonic()+130
            while time.monotonic()<deadline:
                status=await call('peridigm_status',{'run_id':rid})
                if status['job']['state'] in core.TERMINAL:break
                await asyncio.sleep(.5)
            assert status['job']['state']=='completed',status
            report=await call('peridigm_report',{'run_id':rid})
            artifact={'passed':report['validation']['passed'],'run_id':rid,'variant':variant,'mcp_protocol':init.protocolVersion,'tool_count':len(listed.tools),'validation':report['validation'],'transcript':transcript}
            core.save(core.directory(rid)/'mcp-transcript.json',artifact)
            print(json.dumps({k:v for k,v in artifact.items() if k!='transcript'},indent=2))
if __name__=='__main__':asyncio.run(run())
