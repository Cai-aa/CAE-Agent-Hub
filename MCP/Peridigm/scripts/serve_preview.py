"""Read-only loopback preview of external viewer build and one selected run."""
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path
import argparse,sys,urllib.parse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core
p=argparse.ArgumentParser();p.add_argument('run_id');p.add_argument('--port',type=int,default=8765);a=p.parse_args()
run=core.directory(a.run_id);dist=Path(core.config()['root'])/'runtime/viewer-dist'
class Handler(SimpleHTTPRequestHandler):
    def translate_path(self,path):
        parsed=urllib.parse.urlsplit(path).path
        base=run if parsed.startswith('/run/') else dist
        relative=urllib.parse.unquote(parsed[5:] if base==run else parsed.lstrip('/'))
        target=(base/relative).resolve()
        if not target.is_relative_to(base.resolve()):return str(base/'__blocked__')
        return str(target)
    def end_headers(self):
        self.send_header('Cache-Control','no-store');super().end_headers()
server=ThreadingHTTPServer(('127.0.0.1',a.port),Handler)
print(f'Loopback preview: http://127.0.0.1:{a.port}/peridigm.html?result=/run/result_mesh.json',flush=True)
server.serve_forever()
