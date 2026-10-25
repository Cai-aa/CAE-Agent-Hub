"""Launch or reuse a local COMSOL shared server and optionally its Desktop.

The Desktop and thin-client bridge must use the same prefs directory, port,
and exact model tag. This command never stops pre-existing processes.
"""
from __future__ import annotations
import argparse,json,socket,subprocess,sys,time
from pathlib import Path
from .detect import find_comsol_root,runs_dir

def commands(root:Path,runtime:Path,port:int):
    bin_dir=root/'bin'/'win64'; prefs=runtime/'preferences'
    server=[str(bin_dir/'comsolmphserver.exe'),'-np','1','-prefsdir',str(prefs),'-port',str(port),'-multi','on','-login','auto','-silent','-graphics','-portfile',str(runtime/'server.port')]
    desktop=[str(bin_dir/'comsolmphclient.exe'),'-prefsdir',str(prefs),'-configuration',str(runtime/'desktop_configuration'),'-data',str(runtime/'desktop_workspace'),'-server','127.0.0.1','-port',str(port)]
    return server,desktop

def listening(port):
    try:
        with socket.create_connection(('127.0.0.1',port),timeout=.3): return True
    except OSError: return False

def launch(port=2036,runtime=None,desktop=True,timeout=45,open_file=None):
    root=find_comsol_root()
    if root is None: raise FileNotFoundError('COMSOL installation not found.')
    runtime=Path(runtime).resolve() if runtime else runs_dir()/'shared_desktop'
    runtime.mkdir(parents=True,exist_ok=True); (runtime/'preferences').mkdir(exist_ok=True); (runtime/'scripts').mkdir(exist_ok=True)
    server_cmd,desktop_cmd=commands(root,runtime,int(port))
    server_pid=None
    if listening(port):
        marker=runtime/'launch.json'
        if not marker.exists():
            raise RuntimeError('Port is already in use without this runtime ownership record. Choose another port.')
        state=json.loads(marker.read_text(encoding='utf-8-sig'))
        recorded=int(state.get('port',state.get('Port',0)))
        if recorded!=port: raise RuntimeError('Existing runtime does not match the requested port.')
    else:
        stdout=(runtime/'server.stdout.log').open('a',encoding='utf8'); stderr=(runtime/'server.stderr.log').open('a',encoding='utf8')
        try:
            process=subprocess.Popen(server_cmd,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        finally: stdout.close(); stderr.close()
        server_pid=process.pid
        deadline=time.monotonic()+timeout
        while not listening(port):
            if process.poll() is not None: raise RuntimeError('COMSOL server launcher exited; inspect runtime logs.')
            if time.monotonic()>deadline: raise TimeoutError('COMSOL shared server startup timed out; inspect runtime logs.')
            time.sleep(.25)
        (runtime/'launch.json').write_text(json.dumps({'port':port,'server_pid':server_pid,'runtime':str(runtime),'command':server_cmd},indent=2),encoding='utf8')
    desktop_pid=None
    if desktop:
        if open_file:
            model_path=Path(open_file).resolve()
            if model_path.suffix.lower()!='.mph' or not model_path.is_file(): raise ValueError('Expected an existing MPH file.')
            desktop_cmd.extend(['-open',str(model_path)])
        # A visible Desktop is the explicit purpose of this command.
        desktop_pid=subprocess.Popen(desktop_cmd).pid
    return {'host':'127.0.0.1','port':port,'runtime':str(runtime),'server_launcher_pid':server_pid,'desktop_launcher_pid':desktop_pid,'prefs_dir':str(runtime/'preferences'),
            'bridge_command':[sys.executable,'-u','-m','tools.shared_bridge','--host','127.0.0.1','--port',str(port),'--prefs-dir',str(runtime/'preferences'),'--script-root',str(runtime/'scripts')],
            'model_selection':'List models, then attach the exact tag shown/imported in Desktop; loading the same MPH twice creates separate models.'}

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--port',type=int,default=2036); p.add_argument('--runtime'); p.add_argument('--no-desktop',action='store_true'); p.add_argument('--open-file')
    a=p.parse_args(); print(json.dumps(launch(a.port,a.runtime,not a.no_desktop,open_file=a.open_file),ensure_ascii=False,indent=2))
if __name__=='__main__': main()
