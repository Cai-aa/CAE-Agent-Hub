"""Real MPh thin-client backend for a Desktop-shared COMSOL server.

Run in its own process: ModelUtil/JVM singletons cannot switch an existing
stand-alone MPh client into a remote client. Never clears server models.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import traceback
from pathlib import Path
from typing import Any


def json_value(value: Any) -> Any:
    if hasattr(value, 'tolist'):
        return value.tolist()
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    return value


def checked_script(path: str, root: Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError('Shared API scripts must be inside the configured script root.')
    if resolved.suffix.lower() != '.py' or not resolved.is_file():
        raise ValueError('Expected an existing .py script.')
    return resolved


class SharedComsolBackend:
    def __init__(self, host='127.0.0.1', port=2036, prefs_dir=None, model_tag=None, script_root=None):
        self.host, self.port = host, int(port)
        self.prefs_dir = Path(prefs_dir).resolve() if prefs_dir else None
        self.model_tag = model_tag
        self.script_root = Path(script_root).resolve() if script_root else Path.cwd().resolve()
        self.client = None

    def connect(self):
        if self.client is not None:
            return
        import jpype
        import mph

        original = jpype.startJVM
        def start_jvm(*args, **kwargs):
            extra = ['-Dcs.prefsdir=' + str(self.prefs_dir)] if self.prefs_dir else []
            return original(*args, *extra, **kwargs)
        jpype.startJVM = start_jvm
        try:
            self.client = mph.Client(port=self.port, host=self.host)
        finally:
            jpype.startJVM = original
        # The Desktop briefly owns the server while updating its model tree.
        self.client.java.setServerBusyHandler(jpype.JClass('com.comsol.model.util.ServerBusyHandler')(10000))

    def model(self):
        self.connect()
        if not self.model_tag:
            raise ValueError('No shared model attached. List server models and attach its exact tag.')
        tags = [str(t) for t in self.client.java.tags()]
        if self.model_tag not in tags:
            raise ValueError('Shared model tag not found: ' + self.model_tag)
        import mph
        return mph.Model(self.client.java.model(self.model_tag))

    def list_models(self):
        self.connect()
        return [{'tag':str(m.java.tag()),'name':m.name(),'file':str(m.file())} for m in self.client.models()]

    def status(self):
        self.connect()
        return {'connected':True,'mode':'shared-server','backend':'MPh thin client / COMSOL Java API',
                'host':self.host,'port':self.port,'version':self.client.version,'standalone':False,
                'active_model_tag':self.model_tag,'models':self.list_models(),
                'desktop_sync':'Requires a Desktop connected to this endpoint and importing this exact model tag.',
                'disconnect_preserves_models':True}

    def info(self):
        model=self.model(); m=model.java
        components=[]
        for ct in m.component().tags():
            c=m.component(str(ct))
            components.append({'tag':str(ct),'geometries':[{'tag':str(gt),'domains':int(c.geom(str(gt)).getNDomains()),'boundaries':int(c.geom(str(gt)).getNBoundaries())} for gt in c.geom().tags()],
                               'materials':[str(t) for t in c.material().tags()],
                               'physics':[{'tag':str(t),'type':str(c.physics(str(t)).getType())} for t in c.physics().tags()],
                               'meshes':[str(t) for t in c.mesh().tags()]})
        solutions=[]
        for tag in m.sol().tags():
            s=m.sol(str(tag))
            solutions.append({'tag':str(tag),'empty':bool(s.isEmpty()),'size':[int(x) for x in s.getSize()],
                              'error':str(s.getErrorMessage() or ''),'warning':str(s.getWarningMessage() or '')})
        return {'model_tag':self.model_tag,'name':model.name(),'file':str(model.file()),'parameters':model.parameters(),
                'components':components,'studies':model.studies(),'solutions':solutions,
                'datasets':model.datasets(),'plots':model.plots(),'mode':'shared-server'}

    def dataset(self, requested=None):
        model=self.model()
        for node in model/'datasets':
            if (requested and (node.tag()==requested or node.name()==requested)) or (not requested and str(node.java.getType())=='Solution'):
                return node
        raise ValueError('No matching solution dataset: '+str(requested))

    def handle(self, method, params):
        if method in ('ping','sharedStatus'):
            return self.status()
        if method=='connect':
            host=params.get('host',self.host); port=int(params.get('port',self.port))
            if host!=self.host or port!=self.port:
                raise ValueError('Start a separate bridge process to change server endpoint.')
            return self.status()
        if method=='listModels':
            return {'models':self.list_models(),'mode':'shared-server'}
        if method=='attachModel':
            old=self.model_tag; self.model_tag=str(params['tag'])
            try: return self.info()
            except Exception:
                self.model_tag=old
                raise
        if method=='newModel':
            self.connect(); tag=str(params.get('tag','MCPModel'))
            if tag in [str(t) for t in self.client.java.tags()]:
                raise ValueError('Model tag already exists; attach explicitly instead of replacing it: '+tag)
            self.client.java.create(tag); self.model_tag=tag
            return self.info()
        if method=='openModel':
            self.connect(); path=Path(params['path']).resolve()
            if path.suffix.lower()!='.mph' or not path.is_file():
                raise ValueError('Expected an existing MPH file.')
            model=self.client.load(str(path)); self.model_tag=str(model.java.tag())
            return self.info()
        if method=='modelInfo':
            return self.info()
        if method=='listParameters':
            model=self.model()
            return {'model_tag':self.model_tag,'parameters':model.parameters(),'descriptions':model.descriptions()}
        if method=='setParameter':
            model=self.model(); model.parameter(params['name'],params['value'])
            if params.get('description'): model.description(params['name'],params['description'])
            return {'model_tag':self.model_tag,'parameter':params['name'],'value':model.parameter(params['name'])}
        if method=='listStudies':
            m=self.model().java
            return {'studies':[{'tag':str(t),'label':str(m.study(str(t)).label())} for t in m.study().tags()]}
        if method=='runStudy':
            m=self.model().java; tags=[str(t) for t in m.study().tags()]
            tag=params.get('studyTag') or (tags[0] if tags else None)
            if tag not in tags: raise ValueError('Study tag not found: '+str(tag))
            m.study(tag).run()
            info=self.info()
            if not any(not s['empty'] and s['size'][1]>0 and not s['error'] for s in info['solutions']):
                raise RuntimeError('Study returned without a valid nonempty solution.')
            return {'run_completed':True,'study':tag,'model':info}
        if method=='evaluateExpression':
            model=self.model(); node=self.dataset(params.get('dataset'))
            value=model.evaluate(params['expression'],unit=params.get('unit'),dataset=node)
            return {'model_tag':self.model_tag,'dataset':node.tag(),'expression':params['expression'],'unit':params.get('unit'),'value':json_value(value)}
        if method=='saveModel':
            model=self.model(); path=params.get('path')
            if path: model.save(Path(path).resolve())
            else: raise ValueError('Shared mode requires an explicit output path to avoid overwriting source models.')
            return {'saved':True,'model_tag':self.model_tag,'path':str(Path(path).resolve())}
        if method=='exportTable':
            self.model().java.result().table(params['table']).save(params['path'])
            return {'exported':True,'path':params['path']}
        if method=='exportPlot':
            m=self.model().java; pg=params['plotGroup']; tags=[str(t) for t in m.result().tags()]
            if pg not in tags: raise ValueError('Plot group tag not found: '+pg)
            tag='mcp_shared_image'; exports=m.result().export()
            if tag not in [str(t) for t in exports.tags()]: exports.create(tag,'Image')
            image=exports.get(tag)
            for key,val in {'sourceobject':pg,'imagetype':'png','pngfilename':params['path'],'size':'manualweb','unit':'px','width':float(params.get('width',1600)),'height':float(params.get('height',1000)),'options3d':'on','legend3d':'on','title3d':'on','logo3d':'off'}.items(): image.set(key,val)
            image.run()
            return {'exported':True,'path':params['path']}
        if method=='runScript':
            path=checked_script(params['path'],self.script_root)
            context={'model':self.model(),'client':self.client,'model_tag':self.model_tag}
            scope={'__name__':'comsol_shared_api_script','__file__':str(path)}
            captured=io.StringIO()
            with contextlib.redirect_stdout(captured):
                exec(compile(path.read_text(encoding='utf-8-sig'),str(path),'exec'),scope)
                if not callable(scope.get('run')): raise ValueError('Shared API script must define run(context).')
                result=scope['run'](context)
            return {'model_tag':self.model_tag,'script':str(path),'result':json_value(result),'stdout':captured.getvalue()[-12000:],'model':self.info()}
        if method in ('disconnect','shutdown'):
            if self.client is not None:
                self.client.disconnect()  # Deliberately never calls clear/remove.
                self.client=None
            return {'disconnected':True,'server_models_preserved':True}
        raise ValueError('Unsupported shared COMSOL method: '+method)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',default='127.0.0.1'); parser.add_argument('--port',type=int,default=2036)
    parser.add_argument('--prefs-dir'); parser.add_argument('--model-tag'); parser.add_argument('--script-root')
    args=parser.parse_args()
    backend=SharedComsolBackend(args.host,args.port,args.prefs_dir,args.model_tag,args.script_root)
    wire=sys.stdout
    for line in sys.stdin:
        request={}
        try:
            request=json.loads(line)
            with contextlib.redirect_stdout(sys.stderr):
                result=backend.handle(request['method'],request.get('params',{}))
            reply={'id':request['id'],'ok':True,'result':json_value(result)}
        except Exception:
            reply={'id':request.get('id'),'ok':False,'error':{'message':traceback.format_exc()}}
        wire.write(json.dumps(reply,ensure_ascii=True)+'\n'); wire.flush()
        if request.get('method')=='shutdown': break


if __name__=='__main__':
    main()
