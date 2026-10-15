"""Real STDIO handshake/list/calls. No solver launch; actual result retained by caller."""
import asyncio,json,os,sys
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

async def run():
    parameters=StdioServerParameters(command=sys.executable,args=[str(Path(__file__).resolve().parents[1]/'server.py')],env=dict(os.environ))
    async with stdio_client(parameters) as (reader,writer):
        async with ClientSession(reader,writer) as session:
            initialized=await session.initialize();listed=await session.list_tools();calls={}
            for name,args in [('peridigm_doctor',{}),('peridigm_templates',{}),('peridigm_start_context',{'request':'Small elastic verification, unspecified material and geometry','actor':'protocol_test'})]:
                r=await session.call_tool(name,args)
                if r.isError:raise AssertionError(str(r))
                data=r.structuredContent or json.loads(r.content[0].text)
                calls[name]=data
            assert calls['peridigm_doctor']['status']=='SUCCEEDED'
            assert calls['peridigm_start_context']['status']=='NEEDS_INPUT'
            assert len(listed.tools)>=12
            print(json.dumps({'protocol':initialized.protocolVersion,'server':initialized.serverInfo.model_dump(),'tool_count':len(listed.tools),'tools':[t.name for t in listed.tools],'calls':calls,'passed':True},indent=2))
if __name__=='__main__':asyncio.run(run())
