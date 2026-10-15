"""Actual two-rank solve through STDIO MCP; explicitly a scripted integration test."""
import asyncio,json,os,sys,time
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core

async def run():
    transcript=[]
    params=StdioServerParameters(command=sys.executable,args=[str(Path(__file__).resolve().parents[1]/'server.py')],env=dict(os.environ))
    async with stdio_client(params) as (reader,writer):
        async with ClientSession(reader,writer) as client:
            init=await client.initialize()
            async def call(name,args):
                r=await client.call_tool(name,args)
                if r.isError:raise RuntimeError(str(r))
                data=r.structuredContent or json.loads(r.content[0].text)
                transcript.append({'at':core.stamp(),'tool':name,'arguments':args,'response':data,'actor':'scripted_integration_test'})
                if data['status']=='BLOCKED':raise AssertionError(data)
                return data
            r=await call('peridigm_start_context',{'request':'Qualify the reviewed elastic benchmark with explicit two-process execution','actor':'scripted_integration_test'})
            rid=r['run_id']
            s=await call('peridigm_answer_context',{'run_id':rid,'answers':{'template_id':core.PROFILE,'mpi_processes':2},'actor':'scripted_integration_test'})
            await call('peridigm_answer_context',{'run_id':rid,'answers':{'confirm_spec_sha256':core.canonical(s['specification'])},'actor':'scripted_integration_test'})
            await call('peridigm_validate',{'run_id':rid})
            await call('peridigm_submit',{'run_id':rid,'timeout_seconds':120})
            deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                state=await call('peridigm_status',{'run_id':rid})
                if state['job']['state'] in core.TERMINAL:break
                await asyncio.sleep(.2)
            assert state['job']['state']=='completed',state
            await call('peridigm_log',{'run_id':rid,'stream':'stdout','tail_chars':2000})
            report=await call('peridigm_report',{'run_id':rid})
            assert report['validation']['passed']
            payload={'passed':True,'run_id':rid,'protocol':init.protocolVersion,'transcript':transcript}
            core.save(core.directory(rid)/'mcp-transcript.json',payload)
            core.save(Path(core.config()['root'])/'runtime/mpi-integration.json',payload)
            print(json.dumps({'passed':True,'run_id':rid,'mpi_processes':2,'validation':report['validation']},indent=2))
if __name__=='__main__':asyncio.run(run())
