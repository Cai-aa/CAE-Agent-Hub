"""Independent reference/analytic checks and honest material-point export."""
from pathlib import Path
import csv, html, json, math
import numpy as np
from netCDF4 import Dataset, chartostring
import core

def read_exodus(path):
    with Dataset(path) as d:
        coords=np.column_stack([np.asarray(d['coord'+axis][:],float) for axis in 'xyz'])
        nodal={str(name):np.asarray(d[f'vals_nod_var{i+1}'][:],float) for i,name in enumerate(chartostring(d['name_nod_var'][:]))}
        elemental={str(name):np.asarray(d[f'vals_elem_var{i+1}eb1'][:],float) for i,name in enumerate(chartostring(d['name_elem_var'][:]))}
        labels=np.asarray(d['node_num_map'][:],int) if 'node_num_map' in d.variables else np.arange(1,len(coords)+1)
        return {'time':np.asarray(d['time_whole'][:],float),'coords':coords,'labels':labels,'nodal':nodal,'elemental':elemental}

def read_run(p,processes):
    paths=[p/'result.e'] if processes==1 else [p/f'result.e.{processes}.{i}' for i in range(processes)]
    if not all(x.is_file() for x in paths):raise ValueError('Missing MPI shard or single-process output')
    shards=[read_exodus(x) for x in paths]
    if len(shards)==1:return shards[0],paths
    t=shards[0]['time']
    if any(not np.array_equal(x['time'],t) for x in shards):raise ValueError('MPI shards have different time sequences')
    ids=np.concatenate([x['labels'] for x in shards]);order=np.argsort(ids)
    if len(np.unique(ids))!=len(ids):raise ValueError('Duplicate owned point IDs across shards')
    eids=np.concatenate([x['elemental']['Element_Id'][0] for x in shards]);eo=np.argsort(eids)
    merged={'time':t,'labels':ids[order],'coords':np.concatenate([x['coords'] for x in shards])[order],
        'nodal':{k:np.concatenate([x['nodal'][k] for x in shards],axis=1)[:,order] for k in shards[0]['nodal']},
        'elemental':{k:np.concatenate([x['elemental'][k] for x in shards],axis=1)[:,eo] for k in shards[0]['elemental']}}
    return merged,paths

def collect(p,spec,cfg,job):
    p=Path(p);actual,paths=read_run(p,job['mpi_processes']);gold=read_exodus(cfg['reference']);v=spec['validation'];f=spec['physics']
    t=actual['time'];n=actual['nodal'];e=actual['elemental'];checks={};metrics={}
    def gate(name,ok,**values): checks[name]={'passed':bool(ok),**values}
    gate('normal_solver_exit',job['state']=='completed' and job.get('exit_code')==0)
    gate('expected_size',len(t)==v['expected_frames'] and len(actual['coords'])==v['expected_points'],frames=len(t),points=len(actual['coords']))
    finite=all(np.isfinite(a).all() for a in [t,actual['coords'],*n.values(),*e.values()])
    gate('finite_fields',finite)
    gate('time_sequence',len(t)>1 and np.all(np.diff(t)>0) and abs(t[0])<=v['time_atol_s'] and abs(t[-1]-f['solver']['final_time_s'])<=v['time_atol_s'])
    required=['Displacement'+a for a in 'XYZ']+['Velocity'+a for a in 'XYZ']+['ForceX']
    gate('required_fields',all(k in n for k in required) and 'Dilatation' in e,required=required+['Dilatation'])
    if not checks['expected_size']['passed'] or not checks['required_fields']['passed'] or not finite:
        val={'passed':False,'checks':checks,'scope':spec['capability_scope']};core.save(p/'validation.json',val)
        return core.blocked('incomplete_output','Output failed shape/field/finite checks',validation=val)
    gate('reference_time',actual['time'].shape==gold['time'].shape and np.allclose(t,gold['time'],rtol=0,atol=v['time_atol_s']))
    gate('reference_geometry',np.allclose(actual['coords'],gold['coords'],rtol=0,atol=1e-12))
    for prefix,tolkey,axes in [('Displacement','gold_displacement_atol_m','XYZ'),('Velocity','gold_velocity_atol_m_s','XYZ'),('Force','gold_force_atol_N','XYZ')]:
        diffs=[float(np.max(np.abs(n[prefix+a]-gold['nodal'][prefix+a]))) for a in axes]
        gate('gold_'+prefix.lower(),max(diffs)<=v[tolkey],max_abs_difference=max(diffs),tolerance=v[tolkey])
    diff=float(np.max(np.abs(e['Dilatation']-gold['elemental']['Dilatation'])))
    gate('gold_dilatation',diff<=v['gold_dilatation_atol'],max_abs_difference=diff,tolerance=v['gold_dilatation_atol'])
    # Independent solution for this two-point LPS volumetric oscillator only.
    rho=f['material']['density_kg_m3'];bulk=f['material']['bulk_modulus_pa'];r0=2.0;volume=2.0
    omega=math.sqrt(36*bulk/(rho*r0*r0));u_exact=np.sin(omega*t)/omega;vel_exact=np.cos(omega*t)
    u=n['DisplacementX'][:,0];vel=n['VelocityX'][:,0]
    rel=float(np.max(np.abs(u-u_exact))/max(np.max(np.abs(u_exact)),1e-30))
    velerr=float(np.max(np.abs(vel-vel_exact)))
    gate('analytic_displacement',rel<=v['analytic_displacement_relative_tolerance'],relative_max_error=rel,tolerance=v['analytic_displacement_relative_tolerance'])
    gate('analytic_velocity',velerr<=v['analytic_velocity_absolute_tolerance_m_s'],max_abs_error_m_s=velerr,tolerance=v['analytic_velocity_absolute_tolerance_m_s'])
    sym=float(np.max(np.abs(n['DisplacementX'].sum(axis=1))))
    gate('antisymmetry',sym<=v['symmetry_atol_m'],max_displacement_sum_m=sym)
    momentum=rho*volume*n['VelocityX'].sum(axis=1)
    gate('linear_momentum',np.max(np.abs(momentum))<=1e-8,max_abs_kg_m_s=float(np.max(np.abs(momentum))),tolerance_kg_m_s=1e-8)
    metrics={'omega_rad_s':omega,'final_displacement_m':float(u[-1]),'analytic_final_displacement_m':float(u_exact[-1]),'final_velocity_m_s':float(vel[-1]),'max_analytic_displacement_relative_error':rel}
    # This build reports a zero stored-energy field. Do not convert it into an energy-conservation claim.
    not_verified={'energy_balance':'Stored_Elastic_Energy is zero in this build/reference despite nonzero response; full energy balance not verified.', 'fracture':'No damage/contact model in the elastic verification profile.', 'engineering_validation':'Two-point code verification only, not a resolved specimen or experimental validation.'}
    val={'passed':all(x['passed'] for x in checks.values()),'checks':checks,'metrics':metrics,'not_verified':not_verified,'scope':spec['capability_scope'],
         'evidence':{'solver_sha256':job['solver_sha256'],'input_sha256':job['input_sha256'],'spec_sha256':job['spec_sha256'],'result_sha256':{x.name:core.digest(x) for x in paths},'reference_sha256':core.digest(cfg['reference'])}}
    core.save(p/'validation.json',val)
    with (p/'response.csv').open('w',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['time_s','point_1_ux_m','point_2_ux_m','analytic_point_1_ux_m','point_1_vx_m_s'])
        writer.writerows(zip(t,u,n['DisplacementX'][:,1],u_exact,vel))
    frames=[]
    for i,at in enumerate(t):
        nodes=[]
        for j,(label,x) in enumerate(zip(actual['labels'],actual['coords'])):
            displacement=[float(n['Displacement'+a][i,j]) for a in 'XYZ']
            nodes.append({'label':int(label),'coordinates':x.tolist(),'displacement':displacement,'deformed':(x+displacement).tolist(),'value':float(np.linalg.norm(displacement))})
        frames.append({'frame':i,'time':float(at),'timeMs':float(at)*1000,'nodes':nodes,'elements':[]})
    mesh={'schemaVersion':1,'source':'Peridigm','instance':'two-material-point verification','step':'elastic dynamics','frame':len(t)-1,
          'analysisType':'dynamic','representation':'material-points','elementType':'PD_POINT','fieldLabel':'Displacement magnitude (m)',
          'deformationScale':1,'fieldRanges':{'valueMin':0,'valueMax':float(np.max(np.abs(u))),'maxDisplacement':float(np.max(np.abs(u)))},
          'nodes':frames[-1]['nodes'],'elements':[],'dynamicFrames':frames,'validation':val,
          'semantics':{'field':'point displacement magnitude','no_elements':'No invented finite-element connectivity','damage':'not simulated','deformation_scale':1}}
    core.save(p/'result_mesh.json',mesh);core.event(p,'results_verified',passed=val['passed'],metrics=metrics)
    return core.result('SUCCEEDED' if val['passed'] else 'BLOCKED',run_id=job['run_id'],validation=val,files=['result.e','validation.json','response.csv','result_mesh.json'])

def report(p):
    p=Path(p);s=core.load(p/'spec.json');v=core.load(p/'validation.json');m=core.load(p/'result_mesh.json');job=core.load(p/'job.json')
    frames=m['dynamicFrames'];times=[f['time'] for f in frames];ys=[f['nodes'][0]['displacement'][0] for f in frames]
    omega=v['metrics']['omega_rad_s'];exact=[math.sin(omega*t)/omega for t in times]
    def line(values):return ' '.join(f'{55+620*t/times[-1]:.3f},{225-175*y/max(exact):.3f}' for t,y in zip(times,values))
    checks=''.join(f'<tr><td>{html.escape(k)}</td><td>{"PASS" if a["passed"] else "FAIL"}</td><td><code>{html.escape(json.dumps({k:v for k,v in a.items() if k!="passed"}))}</code></td></tr>' for k,a in v['checks'].items())
    raw_links=' '.join(f'<a href="{html.escape(x["name"],quote=True)}">{html.escape(x["name"])}</a>' for x in job['outputs'])
    rows=''.join(f'<tr><td>{t:.8g}</td><td>{u:.9g}</td><td>{ex:.9g}</td></tr>' for t,u,ex in zip(times,ys,exact))
    script=json.dumps({'frames':frames},ensure_ascii=False).replace('</','<\\/')
    document=f'''<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Agentic PD 弹性基准验证报告</title>
<style>body{{font:16px/1.65 system-ui,sans-serif;margin:32px auto;padding:0 22px;max-width:1050px;color:#172b3a;background:#fafafa}}h1{{font-size:26px}}h2{{font-size:20px;margin-top:32px}}table{{border-collapse:collapse;width:100%;margin:16px 0}}td,th{{text-align:left;padding:8px;border-bottom:1px solid #ccd3d9}}pre{{white-space:pre-wrap;word-break:break-word;background:#edf1f3;padding:16px}}code{{word-break:break-all}}svg{{width:100%;height:auto;background:white}}button,input{{font:inherit}}.files a{{margin-right:16px}}section{{margin:24px 0}}</style>
<h1>Agentic PD 弹性动力基准验证</h1><p>状态：<strong>{'基准检查通过' if v['passed'] else '验证未通过'}</strong>。真实 Peridigm 求解；2 个材料点，6 个保存时刻。位移显示比例为 1，未模拟损伤或断裂。</p>
<p>{html.escape(s['capability_scope'])}</p><p>最大解析位移相对误差：{v['metrics']['max_analytic_displacement_relative_error']*100:.4f}%；预先定义容差：0.5%。标准参考位移最大差：{v['checks']['gold_displacement']['max_abs_difference']:.5g} m。</p>
<h2>材料点与真实时间序列</h2><label>保存帧 <input id="frame" type="range" min="0" max="{len(frames)-1}" value="{len(frames)-1}"></label> <output id="at"></output>
<svg viewBox="0 0 740 125" role="img" aria-label="两个材料点的真实位置，无虚构网格"><line x1="40" x2="700" y1="75" y2="75" stroke="#c7ced4"/><circle id="point0" cy="65" r="12" fill="#237a9b"/><circle id="point1" cy="65" r="12" fill="#237a9b"/><text x="50" y="110">参考位置 x = −1 m</text><text x="470" y="110">参考位置 x = +1 m</text></svg><p id="displacements"></p>
<h2>第一材料点位移与独立解析解</h2><svg viewBox="0 0 740 280" role="img" aria-label="位移随时间曲线，实际求解与解析解对照"><path d="M55 30V225H680" fill="none" stroke="#5c6770"/><polyline points="{line(exact)}" fill="none" stroke="#8a5b25" stroke-width="4"/><polyline points="{line(ys)}" fill="none" stroke="#237a9b" stroke-width="2"/><text x="280" y="265">Time (s), 0 → {times[-1]:g}</text><text x="55" y="20">Displacement x (m), 0 → {max(exact):.6g}</text><text x="90" y="52" fill="#237a9b">Peridigm</text><text x="90" y="75" fill="#8a5b25">Analytic oscillator</text></svg>
<table><tr><th>Time (s)</th><th>Peridigm u₁ (m)</th><th>Analytic u₁ (m)</th></tr>{rows}</table>
<h2>独立验证结果</h2><table><tr><th>检查</th><th>结论</th><th>误差与门槛</th></tr>{checks}</table>
<h2>边界与未验证项</h2><pre>{html.escape(json.dumps(v['not_verified'],ensure_ascii=False,indent=2))}</pre>
<h2>确认规格与参数来源</h2><pre>{html.escape(json.dumps(s,ensure_ascii=False,indent=2))}</pre>
<h2>运行证据</h2><pre>{html.escape(json.dumps(job,ensure_ascii=False,indent=2))}</pre>
<p class="files"><a href="input.yaml">输入</a><a href="stdout.log">日志</a><a href="events.jsonl">交互轨迹</a><a href="validation.json">验证JSON</a><a href="response.csv">曲线CSV</a><a href="result_mesh.json">Hub点云数据</a>{raw_links}</p>
<script>const data={script};const slider=document.getElementById('frame');function draw(){{const f=data.frames[Number(slider.value)];document.getElementById('at').textContent='t = '+f.time.toPrecision(6)+' s';for(let i=0;i<2;i++)document.getElementById('point'+i).setAttribute('cx',370+f.nodes[i].deformed[0]*220);document.getElementById('displacements').textContent=f.nodes.map(n=>'点 '+n.label+': uₓ = '+n.displacement[0].toPrecision(7)+' m').join('；');}}slider.addEventListener('input',draw);draw();</script></html>'''
    (p/'report.html').write_text(document,encoding='utf-8')
