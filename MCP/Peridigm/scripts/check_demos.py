"""Check curated replay identities and point/time semantics without a solver."""
import hashlib,json
from pathlib import Path

def check(repo):
    results=[]
    for directory,points,frames in [('peridigm-elastic',2,6),('peridigm-notched-tension',3200,31)]:
        root=Path(repo)/'models'/directory
        manifest=json.loads((root/'manifest.json').read_text())
        for name,item in manifest.items():
            if Path(name).name!=name:raise ValueError('Manifest path must be a single filename')
            p=root/name
            assert p.stat().st_size==item['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256'],p.name
        m=json.loads((root/'result_mesh.json').read_text());v=json.loads((root/'validation.json').read_text())
        assert v['passed'] and m['validation']==v and m['representation']=='material-points' and not m['elements']
        assert len(m['nodes'])==points and len(m['dynamicFrames'])==frames
        times=[f['time'] for f in m['dynamicFrames']]
        assert times[0]==0 and all(b>a for a,b in zip(times,times[1:]))
        assert all(len(f['nodes'])==points and not f['elements'] for f in m['dynamicFrames'])
        if directory.endswith('tension'):
            assert all(0<=n['damage']<=1 for f in m['dynamicFrames'] for n in f['nodes'])
        results.append({'fixture':directory,'points':points,'display_frames':frames,'passed':True})
    return results

if __name__=='__main__':print(json.dumps(check(Path(__file__).resolve().parents[3]),indent=2))
