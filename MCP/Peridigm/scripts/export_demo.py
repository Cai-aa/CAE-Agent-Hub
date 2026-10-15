"""Export a reviewed, verified run as a public replay fixture, never as a new solve."""
import argparse,json,sys,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core,yaml

def export(run,out):
    run=Path(run).resolve();out=Path(out).resolve()
    if out.exists():raise ValueError('Use a new output directory to preserve existing demo evidence')
    spec=core.load(run/'spec.json');job=core.load(run/'job.json');validation=core.load(run/'validation.json');mesh=core.load(run/'result_mesh.json')
    profile=spec['template_id'];core.template(profile)
    if job['state']!='completed' or job.get('exit_code')!=0 or not validation.get('passed'):raise ValueError('Only successfully verified native runs may be exported')
    if core.canonical(spec)!=job['spec_sha256'] or core.load(run/'frozen.json')['spec_sha256']!=job['spec_sha256']:raise ValueError('Confirmed specification identity mismatch')
    if core.digest(run/'input.yaml')!=job['input_sha256'] or yaml.safe_load((run/'input.yaml').read_text())!=core.deck(spec):raise ValueError('Input identity mismatch')
    for item in job['outputs']:
        if Path(item['name']).name!=item['name'] or core.digest(run/item['name'])!=item['sha256']:raise ValueError('Native result identity mismatch')
    if validation['evidence']['result_sha256']!={item['name']:item['sha256'] for item in job['outputs']}:raise ValueError('Validation result identity mismatch')
    if mesh['validation']!=validation:raise ValueError('Viewer validation differs from verified record')
    if mesh.get('representation')!='material-points' or mesh.get('elements'):raise ValueError('Requires honest material-point export')
    out.mkdir(parents=True)
    # A positive whitelist excludes credentials, paths, raw requests, process IDs and worker logs.
    case={k:spec[k] for k in ['schema_version','template_id','physics','validation','capability_scope']}
    provenance={'source_spec_sha256':job['spec_sha256'],'solver_sha256':job['solver_sha256'],'source_input_sha256':job['input_sha256'],'native_results':job['outputs'],'note':'Hashes identify the actual source run. The full native results remain outside this curated replay fixture; no new computation is performed by the browser.'}
    title='弹性代码验证 / Elastic verification' if profile==core.PROFILE else '损伤与裂纹推进 / Damage and crack advance'
    demo={'id':'elastic' if profile==core.PROFILE else 'fracture','title':title,'mode':'recorded-result-replay','source_run_id':run.name,'template_id':profile,'displayed_frames':len(mesh['dynamicFrames']),'points':len(mesh['nodes']),'interpolated':False,'parameters':'case.json','validation':'validation.json','response':'response.csv','mesh':'result_mesh.json','scope':spec['capability_scope'],'provenance':provenance}
    core.save(out/'demo.json',demo);core.save(out/'case.json',case);core.save(out/'validation.json',validation)
    (out/'result_mesh.json').write_text(json.dumps(mesh,separators=(',',':'),ensure_ascii=False,allow_nan=False),encoding='utf-8')
    shutil.copy2(run/'input.yaml',out/'input.yaml');shutil.copy2(run/'response.csv',out/'response.csv')
    if (run/'points.txt').exists():
        if core.digest(run/'points.txt')!=job['mesh_sha256']:raise ValueError('Mesh identity mismatch')
        shutil.copy2(run/'points.txt',out/'points.txt')
    if (run/'time-step-check.json').exists():core.save(out/'time-step-check.json',core.load(run/'time-step-check.json'))
    events=[]
    for line in (run/'events.jsonl').read_text().splitlines():
        source=json.loads(line);kind=source['kind']
        if kind not in ['request','question','answer','template_selected','spec_frozen','submitted','solver_terminal','results_verified']:continue
        e={'kind':kind,'actor':source['actor'] if source['actor'] in ['tool','codex_operator','scripted_integration_test'] else 'redacted'}
        if kind=='request':e['note']='Private request omitted from public replay; see case.json for the reviewed physical problem.'
        if kind=='question':e.update({k:source[k] for k in ['fields','question','missing','spec_sha256'] if k in source})
        if kind=='answer':e['answers']={k:v for k,v in source['answers'].items() if k in ['template_id','confirm_spec_sha256','mpi_processes','time_step_variant']}
        if kind=='template_selected':e['template_id']=source['template_id']
        if kind=='solver_terminal':e['state']=source['job']['state']
        if kind=='results_verified':e['passed']=source['passed']
        events.append(e)
    core.save(out/'workflow.json',{'privacy':'Curated trace; raw request, times, private paths and job details omitted. Operator roles retained honestly.','events':events})
    readme=f'''# {title}

This is a curated replay of a real Peridigm run, not a browser solve. / 这是实际求解结果的精选回放，网页不会重新求解。

- Profile / 模板: `{profile}`
- Material points / 材料点: {len(mesh['nodes'])}
- Displayed native frames / 真实展示帧: {len(mesh['dynamicFrames'])}; no interpolation / 未插值。
- Units and scope / 单位与能力边界: see `case.json` and `validation.json`.
- Run identity and original native-result hashes / 来源与原生结果摘要: `demo.json`.
- Progressive confirmation trace / 渐进确认轨迹: `workflow.json`, with the private request omitted.

From `viewer/`, install the locked dependencies with `npm ci`, then `npm run dev`. Open `/peridigm.html?demo={demo['id']}` at the printed loopback address. No Peridigm installation or SSH connection is needed for replay. To solve again, use the separately configured CLI/MCP workflow in [Peridigm](../../MCP/Peridigm/README.md).

在 `viewer/` 中安装依赖后启动网页，打开 `/peridigm.html?demo={demo['id']}`。回放不依赖求解器或SSH；重新计算需按模块说明配置独立环境。字段均为实际材料点结果，不虚构有限元连通或裂纹面。

{spec['capability_scope']}

Full native results, solver binaries, machine configuration, original private requests and worker logs are intentionally excluded from this redistributable fixture. This fixture is covered by the repository license; solver/template attribution remains in [THIRD_PARTY_NOTICES](../../MCP/Peridigm/THIRD_PARTY_NOTICES.md).
'''
    (out/'README.md').write_text(readme,encoding='utf-8')
    manifest={p.name:{'sha256':core.digest(p),'bytes':p.stat().st_size} for p in sorted(out.iterdir()) if p.is_file()}
    core.save(out/'manifest.json',manifest)
    return {'directory':out.name,'id':demo['id'],'files':len(manifest)+1,'bytes':sum(v['bytes'] for v in manifest.values()),'frames':demo['displayed_frames'],'points':demo['points']}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--out',required=True);args=p.parse_args()
    print(json.dumps(export(args.run,args.out),indent=2))
