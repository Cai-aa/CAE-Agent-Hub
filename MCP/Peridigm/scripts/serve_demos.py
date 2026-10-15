"""Serve an already built replay bundle on loopback, with portable JS MIME types."""
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import argparse

class ReplayHandler(SimpleHTTPRequestHandler):
    extensions_map={**SimpleHTTPRequestHandler.extensions_map,'.js':'text/javascript','.mjs':'text/javascript','.json':'application/json','.css':'text/css','.csv':'text/csv'}
    def send_head(self):
        if 'If-Modified-Since' in self.headers:del self.headers['If-Modified-Since']
        return super().send_head()
    def end_headers(self):
        self.send_header('Cache-Control','no-store');super().end_headers()
    def translate_path(self,path):
        target=Path(super().translate_path(path)).resolve();root=Path(self.directory).resolve()
        return str(target if target.is_relative_to(root) else root/'__blocked__')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--directory',required=True);p.add_argument('--port',type=int,default=4179);a=p.parse_args();directory=Path(a.directory).resolve()
    if not (directory/'peridigm.html').is_file():p.error('Directory must contain the built peridigm.html entry')
    handler=partial(ReplayHandler,directory=str(directory));server=ThreadingHTTPServer(('127.0.0.1',a.port),handler)
    print(f'Recorded demos only: http://127.0.0.1:{a.port}/peridigm.html',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:server.server_close()
