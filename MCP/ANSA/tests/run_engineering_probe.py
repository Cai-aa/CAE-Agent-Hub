"""Explicit isolated ANSA probe runner; does not touch the user's profile/model."""
import argparse
import os
import shutil
import subprocess
from pathlib import Path

p = argparse.ArgumentParser(__doc__)
p.add_argument('--root', type=Path, required=True)
p.add_argument('--ansa-launcher', type=Path, required=True)
p.add_argument('--accepted-license-profile', type=Path, required=True)
p.add_argument('--script', type=Path, default=Path(__file__).with_name('probe_engineering_host.py'))
a = p.parse_args()
root = a.root.resolve()
root.mkdir(parents=True, exist_ok=False)
profile = root / 'profile'
target = profile / '.BETA/ANSA/.ANSA_license'
target.parent.mkdir(parents=True)
shutil.copy2(a.accepted_license_profile / '.BETA/ANSA/.ANSA_license', target)
with (root / 'ansa.log').open('wb') as log:
    result = subprocess.run([str(a.ansa_launcher), '-nogui', '-uh', str(profile), '-exec',
        'load_script:' + str(a.script.resolve())], cwd=root,
        env=dict(os.environ, ANSA_MCP_ENGINEERING_PROBE=str(root)),
        stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW, timeout=180)
print('exit=', result.returncode, 'output=', root)
