"""Build-specific fracture profile and independent bond-history verification."""
from pathlib import Path
import csv, html, json, math
import numpy as np
from scipy.spatial import cKDTree
import core
import yaml

class QuotedExpression(str):pass
yaml.SafeDumper.add_representer(QuotedExpression,lambda dumper,value:dumper.represent_scalar('tag:yaml.org,2002:str',value,style='"'))

PROFILE='notched-tension-damage-v1'
def template():return core.load(Path(__file__).parent/'examples/notched-tension.json')

def points(f):
    g=f['geometry']; counts=g['points']; dx=np.array(g['lengths_m'])/counts
    xyz=np.array([[g['origin_m'][0]+(i+.5)*dx[0],g['origin_m'][1]+(j+.5)*dx[1],g['origin_m'][2]+(k+.5)*dx[2]] for k in range(counts[2]) for j in range(counts[1]) for i in range(counts[0])])
    return xyz,dx

def mesh_text(f):
    xyz,dx=points(f); volume=float(np.prod(dx))
    return '# x y z block_id volume\n'+''.join(' '.join(format(v,'.17g') for v in x)+f' 1 {volume:.17g}\n' for x in xyz)

def grip_displacement(t,f):
    b=f['boundary'];r=b['ramp_time_s'];v=b['grip_speed_m_s']
    return v*np.where(t<r,t*t/(2*r),t-r/2)

def deck(spec):
    f=spec['physics'];m=f['material'];b=f['boundary'];so=f['solver'];xyz,dx=points(f)
    ny=f['geometry']['points'][1];nx=f['geometry']['points'][0];nr=b['grip_rows']
    bottom=[i+1 for i in range(len(xyz)) if i//nx%ny<nr]
    top=[i+1 for i in range(len(xyz)) if i//nx%ny>=ny-nr]
    bc={'Bottom Node Set':' '.join(map(str,bottom)),'Top Node Set':' '.join(map(str,top)),'All Node Set':' '.join(map(str,range(1,len(xyz)+1)))}
    r=b['ramp_time_s'];v=b['grip_speed_m_s']
    for name,sign in [('Bottom',-1),('Top',1)]:bc[name+' Loading']={'Type':'Prescribed Displacement','Node Set':name+' Node Set','Coordinate':'y','Value':QuotedExpression(f'if(t < {r:.17g}){{ value = {sign*v:.17g}*t*t/(2*{r:.17g}); }} else {{ value = {sign*v:.17g}*(t-{r/2:.17g}); }}')}
    bc['Out Of Plane']={'Type':'Prescribed Displacement','Node Set':'All Node Set','Coordinate':'z','Value':'0.0'}
    crack=f['precrack'];flt={'Type':'Rectangular_Plane','Normal_X':0.,'Normal_Y':1.,'Normal_Z':0.,'Lower_Left_Corner_X':crack['left_x_m'],'Lower_Left_Corner_Y':0.,'Lower_Left_Corner_Z':-.01,'Bottom_Unit_Vector_X':1.,'Bottom_Unit_Vector_Y':0.,'Bottom_Unit_Vector_Z':0.,'Bottom_Length':crack['tip_x_m']-crack['left_x_m'],'Side_Length':.02}
    return {'Peridigm':{'Discretization':{'Type':'Text File','Input Mesh File':'points.txt','Bond Filters':{'Starter Crack':flt}},
        'Materials':{'Solid':{'Material Model':m['model'],'Apply Shear Correction Factor':False,'Density':m['density_kg_m3'],'Bulk Modulus':m['bulk_modulus_pa'],'Shear Modulus':m['shear_modulus_pa']}},
        'Damage Models':{'Brittle':{'Damage Model':'Critical Stretch','Critical Stretch_tension':f['damage']['critical_stretch_tension'],'Critical Stretch_compression':f['damage']['critical_stretch_compression']}},
        'Blocks':{'Plate':{'Block Names':'block_1','Material':'Solid','Damage Model':'Brittle','Horizon':f['horizon_m']}},'Boundary Conditions':bc,
        'Solver':{'Initial Time':0.,'Final Time':so['final_time_s'],'Verlet':{'Fixed dt':so['dt_s']}},
        'Output':{'Output File Type':'ExodusII','Output Format':'BINARY','Output Filename':'result','Output Frequency':so['output_frequency'],'Parallel Write':True,'Output Variables':{x:True for x in f['output_variables']}}}}

def neighbors(x,f):
    pairs=cKDTree(x).query_pairs(f['horizon_m']*(1+1e-12),output_type='ndarray')
    a,b=pairs[:,0],pairs[:,1];cross=x[a,1]*x[b,1]<0
    intersection=np.full(len(pairs),np.nan);intersection[cross]=x[a[cross],0]+(x[b[cross],0]-x[a[cross],0])*(-x[a[cross],1])/(x[b[cross],1]-x[a[cross],1])
    omitted=cross&(intersection<=f['precrack']['tip_x_m']+1e-14)
    return pairs[~omitted],intersection[~omitted],int(omitted.sum())

def validate(p,s,t):
    import copy
    issues=[]
    def issue(rule,msg):issues.append({'rule':rule,'message':msg})
    if core.canonical(s)!=core.load(p/'frozen.json')['spec_sha256']:issue('intent_lock','Frozen fracture specification changed')
    f=s.get('physics',{});expected=copy.deepcopy(t['physics']);dt=f.get('solver',{}).get('dt_s')
    if dt in (expected['solver']['dt_s'],expected['solver']['dt_s']/2):expected['solver']['dt_s']=dt
    if f!=expected or s.get('validation')!=t['validation']:issue('profile_support','Only this exact reviewed fracture profile, base or half time step, single process, is qualified')
    if s.get('reference_sha256')!=core.digest(core.reference_path(PROFILE)):issue('reference','Fracture profile/rule identity changed')
    # The identity test covers every parameter. Explicit rules explain critical failures to clients.
    if f.get('units')!='SI':issue('units','Fracture example requires SI')
    damage=f.get('damage',{})
    if not isinstance(damage,dict) or damage.get('model')!='Critical Stretch' or damage.get('critical_stretch_tension')!=.001 or damage.get('critical_stretch_compression')!=-1.:issue('damage_model','Build requires separate tension/compression thresholds; do not substitute upstream Critical Stretch key or infer calibrated fracture energy')
    if f.get('contact')!='none':issue('contact','Contact is not qualified in this tensile profile')
    kind='physical_semantic' if issues else None
    try:
        if yaml.safe_load((p/'input.yaml').read_text())!=deck(s):issue('input_alignment','Input differs from the confirmed fracture specification');kind=kind or 'input_alignment'
        if not (p/'points.txt').exists() or (p/'points.txt').read_text()!=mesh_text(f):issue('mesh_alignment','Material-point coordinates or volumes differ from confirmed geometry');kind=kind or 'input_alignment'
    except (yaml.YAMLError,OSError,KeyError,ValueError,TypeError):issue('syntax','Invalid fracture input or missing geometry');kind=kind or 'input_syntax'
    r=core.result('BLOCKED' if issues else 'SUCCEEDED',error_type=kind,run_id=p.name,issues=issues,rules_file='rules/fracture.json');core.save(p/'preflight.json',r);return r

def analyze(data,spec,job):
    f=spec['physics'];v=spec['validation'];x=data['coords'];t=data['time'];n=data['nodal'];e=data['elemental'];checks={}
    def gate(name,ok,**kw):checks[name]={'passed':bool(ok),**kw}
    count=round(f['solver']['final_time_s']/f['solver']['dt_s'])+1
    gate('normal_solver_exit',job['state']=='completed' and job['exit_code']==0)
    gate('expected_size',len(x)==v['expected_points'] and len(t)==count,points=len(x),frames=len(t),expected_frames=count)
    gate('complete_fields',all(k in n for k in ['Displacement'+a for a in 'XYZ']) and all(k in e for k in ['Damage','Volume','Element_Id','Number_Of_Neighbors']))
    gate('finite_fields',all(np.isfinite(q).all() for q in [t,x,*n.values(),*e.values()]))
    gate('time_sequence',len(t)>1 and abs(t[0])<v['time_atol_s'] and abs(t[-1]-f['solver']['final_time_s'])<v['time_atol_s'] and np.allclose(np.diff(t),f['solver']['dt_s'],rtol=0,atol=v['time_atol_s']))
    if not all(q['passed'] for q in checks.values()):return {'passed':False,'checks':checks},None
    expected,dx=points(f); labels=data['labels']; order=np.argsort(labels)
    gate('geometry',np.array_equal(np.sort(labels),np.arange(1,len(x)+1)) and np.allclose(x[order],expected,rtol=0,atol=1e-12))
    # Exodus elements store point fields; align explicitly by Element_Id, not assumed FE connectivity.
    eorder=np.argsort(e['Element_Id'][0]);gate('element_alignment',np.array_equal(np.sort(e['Element_Id'][0]).astype(int),np.sort(labels)))
    damage=e['Damage'][:,eorder][:,np.argsort(order)]
    gate('positive_volumes',np.allclose(e['Volume'],np.prod(dx),rtol=1e-10,atol=1e-20))
    gate('damage_bounds',damage.min()>=-v['damage_atol'] and damage.max()<=1+v['damage_atol'],minimum=float(damage.min()),maximum=float(damage.max()))
    gate('irreversible_damage',np.diff(damage,axis=0).min()>=-v['damage_atol'])
    gate('initial_damage_zero',np.max(np.abs(damage[0]))<=v['damage_atol'],note='Starter crack bonds omitted from neighborhood; initial Damage is zero, not the precrack length.')
    u=np.stack([n['Displacement'+a] for a in 'XYZ'],axis=2)
    row=np.round((x[:,1]-f['geometry']['origin_m'][1])/dx[1]-.5).astype(int);nr=f['boundary']['grip_rows'];ny=f['geometry']['points'][1]
    prescribed=grip_displacement(t,f)
    bc_error=max(np.max(np.abs(u[:,row<nr,1]+prescribed[:,None])),np.max(np.abs(u[:,row>=ny-nr,1]-prescribed[:,None])),np.max(np.abs(u[:,:,2])))
    gate('confirmed_loading',bc_error<=v['boundary_displacement_atol_m'],max_error_m=float(bc_error))
    pairs,intersections,omitted=neighbors(x,f);a,b=pairs.T;r0=np.linalg.norm(x[b]-x[a],axis=1)
    degree=np.bincount(pairs.ravel(),minlength=len(x));gate('initial_neighbors',np.array_equal(degree,e['Number_Of_Neighbors'][0,eorder][np.argsort(order)]),omitted_undirected_bonds=omitted)
    broken=np.zeros(len(pairs),bool);hist=[];front=[];maxerr=0.;cross=np.isfinite(intersections);tip=f['precrack']['tip_x_m'];right=f['geometry']['origin_m'][0]+f['geometry']['lengths_m'][0]
    bins=np.floor((intersections[cross]-tip)/dx[0]+1e-10).astype(int);nb=math.ceil((right-tip)/dx[0]);tot=np.bincount(np.clip(bins,0,nb-1),minlength=nb)
    # Source order: damage uses current coordinates before force update; solver writes that same coordinate state.
    for i in range(len(t)):
        y=x+u[i];stretch=(np.linalg.norm(y[b]-y[a],axis=1)-r0)/r0
        broken|=(stretch>f['damage']['critical_stretch_tension'])|(stretch<f['damage']['critical_stretch_compression'])
        reconstructed=np.bincount(pairs[broken].ravel(),minlength=len(x))/degree
        maxerr=max(maxerr,float(np.max(np.abs(reconstructed-damage[i]))))
        hist.append(int(broken.sum()))
        fraction=np.bincount(np.clip(bins,0,nb-1),weights=broken[cross].astype(float),minlength=nb)/np.maximum(tot,1)
        connected=0
        for frac in fraction:
            if frac<v['crack_indicator_broken_fraction']:break
            connected+=1
        front.append(min(right,tip+connected*dx[0]))
    gate('independent_bond_history',maxerr<=v['bond_reconstruction_atol'],max_point_damage_error=maxerr,tolerance=v['bond_reconstruction_atol'],retained_undirected_bonds=len(pairs))
    extension=np.array(front)-tip; advances=int(np.count_nonzero(np.diff(extension)>dx[0]/2))
    gate('new_bond_failure',hist[-1]>hist[0],initial_broken=hist[0],final_broken=hist[-1])
    gate('crack_extension_indicator',extension[-1]>=v['minimum_crack_extension_m'] and advances>=v['minimum_advancing_frames'],extension_m=float(extension[-1]),advancing_saved_frames=advances,criterion=f"contiguous midplane bins with >= {v['crack_indicator_broken_fraction']:.0%} broken crossing bonds; indicator, not a crack surface")
    wave=math.sqrt((f['material']['bulk_modulus_pa']+4*f['material']['shear_modulus_pa']/3)/f['material']['density_kg_m3']);ratio=wave*f['solver']['dt_s']/min(dx)
    gate('time_step_screen',ratio<v['max_dt_wave_ratio'],wave_speed_m_s=wave,dt_wave_over_dx=ratio,note='Conservative screening; not a universal nonlocal stability proof. A separate dt/2 run checks sensitivity.')
    stats={'damage':damage,'u':u,'broken':hist,'front':front,'mean_damage':damage.mean(axis=1),'damaged_points':np.sum(damage>1e-12,axis=1),'max_damage':damage.max(axis=1)}
    metrics={'new_broken_undirected_bonds':hist[-1],'omitted_precrack_bonds':omitted,'crack_extension_indicator_m':float(extension[-1]),'advancing_saved_frames':advances,'max_point_damage_reconstruction_error':maxerr,'final_mean_damage':float(damage[-1].mean()),'final_damaged_points':int(np.sum(damage[-1]>1e-12))}
    return {'passed':all(q['passed'] for q in checks.values()),'checks':checks,'metrics':metrics,'scope':spec['capability_scope'],'not_verified':{'experimental_accuracy':'Synthetic inputs without calibration, experiment or spatial convergence.','crack_surface':'No exact crack surface exported; front is a thresholded connected bond-failure indicator.','energy_balance':'No full energy/reaction-work accounting; not verified.','mpi':'This fracture profile is qualified for one process only.'}},stats

def collect(p,spec,cfg,job):
    from postprocess import read_run
    data,paths=read_run(p,job['mpi_processes']);val,stats=analyze(data,spec,job)
    val['evidence']={'solver_sha256':job['solver_sha256'],'spec_sha256':job['spec_sha256'],'input_sha256':job['input_sha256'],'result_sha256':{x.name:core.digest(x) for x in paths},'mesh_sha256':core.digest(p/'points.txt')}
    core.save(p/'validation.json',val)
    if stats is None:return core.blocked('incomplete_output','Incomplete fracture result',validation=val)
    with (p/'response.csv').open('w',newline='') as s:
        w=csv.writer(s);w.writerow(['time_s','mean_damage','max_damage','damaged_points','new_broken_bonds','crack_front_indicator_x_m']);w.writerows(zip(data['time'],stats['mean_damage'],stats['max_damage'],stats['damaged_points'],stats['broken'],stats['front']))
    indices=np.unique(np.r_[np.linspace(0,len(data['time'])-1,31).round().astype(int),len(data['time'])-1]);frames=[]
    for i in indices:
        nodes=[]
        for j,(label,x) in enumerate(zip(data['labels'],data['coords'])):
            u=stats['u'][i,j];d=float(stats['damage'][i,j]);nodes.append({'label':int(label),'coordinates':x.tolist(),'deformed':(x+u).tolist(),'displacement':u.tolist(),'damage':d,'value':d})
        frames.append({'frame':int(i),'time':float(data['time'][i]),'timeMs':float(data['time'][i])*1000,'nodes':nodes,'elements':[],'crackFrontIndicatorX':stats['front'][i]})
    mesh={'schemaVersion':1,'source':'Peridigm','instance':'precracked tensile thin layer','step':'dynamic fracture demonstration','analysisType':'dynamic','representation':'material-points','elementType':'PD_POINT','fieldLabel':'Damage (broken-bond fraction)','deformationScale':1,'pointSize':5,'fieldRanges':{'valueMin':0,'valueMax':1},'nodes':frames[-1]['nodes'],'elements':[],'dynamicFrames':frames,'validation':val,'precrack':spec['physics']['precrack'],'semantics':{'field':'Damage: fraction of retained neighbor bonds broken','damage':'Critical Stretch; tensile/compressive thresholds specific to inspected build','no_elements':'No invented FE elements or crack surface','deformation_scale':1},'history':{'time':data['time'].tolist(),'meanDamage':stats['mean_damage'].tolist(),'brokenBonds':stats['broken'],'crackFrontIndicatorX':stats['front']}}
    (p/'result_mesh.json').write_text(json.dumps(mesh,separators=(',',':'),ensure_ascii=False,allow_nan=False),encoding='utf-8');core.event(p,'results_verified',passed=val['passed'],metrics=val.get('metrics'))
    return core.result('SUCCEEDED' if val['passed'] else 'BLOCKED',run_id=job['run_id'],validation=val,files=['validation.json','response.csv','result_mesh.json'])

def report(p):
    s=core.load(p/'spec.json');v=core.load(p/'validation.json');m=core.load(p/'result_mesh.json');job=core.load(p/'job.json')
    checks=''.join(f'<tr><td>{html.escape(k)}</td><td>{"PASS" if q["passed"] else "FAIL"}</td><td>{html.escape(json.dumps({k:v for k,v in q.items() if k!="passed"}))}</td></tr>' for k,q in v['checks'].items())
    # Data come only from verified native output. Animation interpolates nothing.
    display={**m,'nodes':[], 'dynamicFrames':[{**f,'nodes':[{k:n[k] for k in ['deformed','displacement','damage']} for n in f['nodes']]} for f in m['dynamicFrames']]}
    data=json.dumps(display,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
    doc='''<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Agentic PD 损伤与裂纹扩展</title>
<style>body{font:16px/1.65 system-ui;margin:30px auto;padding:0 24px;max-width:1100px;color:#172b3a;background:#f6f8fb}h1{font-size:28px}h2{font-size:21px;margin-top:30px}canvas{width:100%;background:#fff;border-radius:12px;border:1px solid #d7dee6}button,select,input{font:inherit;margin:8px}table{border-collapse:collapse;width:100%}td,th{padding:8px;text-align:left;border-bottom:1px solid #ccd3d9}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eaf0f4;padding:16px}.controls{display:flex;flex-wrap:wrap;align-items:center}a{margin-right:12px}.key{padding:12px;background:#e4eff4;border-radius:8px}</style>
<h1>Agentic PD · 损伤与裂纹扩展</h1><p class="key">__STATUS__ · 真实 Peridigm · 3,200 个材料点 · 新断键独立重建</p><p>合成薄层拉伸演示，采用三维 Elastic 本构；没有实验标定或空间收敛结论。初始预裂纹为左侧 10 mm 的断键过滤面。Damage 是剩余邻域中新断键的比例，初始预裂纹处不必有非零 Damage。</p>
<div class="controls"><button id="play">播放</button><button id="reset">起始帧</button><label>场 <select id="field"><option value="damage">损伤 Damage（0–1）</option><option value="displacement">位移幅值（m）</option></select></label><label>保存帧 <input id="frame" type="range" min="0" value="0" max="30"></label><output id="time"></output></div>
<canvas id="plate" width="1100" height="590" aria-label="真实材料点损伤与裂纹扩展时间序列"></canvas><p id="legend"></p><p id="state"></p><p>灰色虚线：初始预裂纹位置。橙线：由逐步断键历史计算的连通裂纹前沿指标，非精确裂纹面。位置按真实位移显示（比例 1），时间帧未插值。</p>
<h2>新断键数量与裂纹前沿指标</h2><canvas id="history" width="1100" height="270" aria-label="实际新断键数量与裂纹前沿指标随时间曲线"></canvas>
<h2>时间步复核</h2><pre>__SENS__</pre><h2>验证与证据</h2><pre>__METRICS__</pre><table><tr><th>检查</th><th>结论</th><th>证据与门槛</th></tr>__CHECKS__</table><h2>未验证项</h2><pre>__LIMITS__</pre><details><summary>确认规格及参数来源</summary><pre>__SPEC__</pre></details><details><summary>运行记录</summary><pre>__JOB__</pre></details><p><a href="input.yaml">输入</a><a href="points.txt">离散</a><a href="stdout.log">日志</a><a href="events.jsonl">问答</a><a href="validation.json">验证</a><a href="response.csv">曲线CSV</a><a href="result_mesh.json">Hub数据</a><a href="time-step-check.json">时间步复核</a></p>
<script>const m=__DATA__;const frames=m.dynamicFrames,slider=document.getElementById('frame'),field=document.getElementById('field'),canvas=document.getElementById('plate'),c=canvas.getContext('2d');slider.max=frames.length-1;let timer=null;const px=x=>65+(x+.02)/.04*970,py=y=>535-(y+.01)/.02*480;const allU=frames.flatMap(f=>f.nodes.map(n=>Math.hypot(...n.displacement))),umax=allU.reduce((a,b)=>Math.max(a,b),0);function draw(){const f=frames[+slider.value];c.clearRect(0,0,1100,590);for(const n of f.nodes){const q=field.value==='damage'?n.damage:Math.hypot(...n.displacement)/umax;c.fillStyle=`hsl(${230*(1-q)},80%,${45+10*(1-q)}%)`;c.fillRect(px(n.deformed[0])-2.5,py(n.deformed[1])-2.5,5,5);}c.setLineDash([8,5]);c.strokeStyle='#555';c.lineWidth=2;c.beginPath();c.moveTo(px(-.02),py(0));c.lineTo(px(-.01),py(0));c.stroke();c.setLineDash([]);c.strokeStyle='#e6760c';c.lineWidth=3;c.beginPath();c.moveTo(px(-.01),py(0));c.lineTo(px(f.crackFrontIndicatorX),py(0));c.stroke();c.fillStyle='#25394d';c.font='18px system-ui';c.fillText('x: −20 → +20 mm; y: −10 → +10 mm',65,575);document.getElementById('time').textContent=`${(f.time*1e6).toFixed(2)} μs · ${+slider.value+1}/${frames.length}`;document.getElementById('legend').textContent=field.value==='damage'?'蓝 → 红：Damage 0 → 1（比例为 1 的实际材料点位置）':`蓝 → 红：位移幅值 0 → ${umax.toExponential(4)} m（比例 1）`;document.getElementById('state').textContent=`本帧最大损伤 ${Math.max(...f.nodes.map(n=>n.damage)).toFixed(3)}；连通裂纹前沿指标 x = ${(f.crackFrontIndicatorX*1000).toFixed(2)} mm`;}
slider.oninput=draw;field.onchange=draw;document.getElementById('reset').onclick=()=>{clearInterval(timer);timer=null;document.getElementById('play').textContent='播放';slider.value=0;draw();};document.getElementById('play').onclick=()=>{if(timer){clearInterval(timer);timer=null;document.getElementById('play').textContent='播放';return;}document.getElementById('play').textContent='暂停';timer=setInterval(()=>{if(+slider.value>=frames.length-1){clearInterval(timer);timer=null;document.getElementById('play').textContent='播放';return;}slider.value=+slider.value+1;draw();},180);};
const h=document.getElementById('history').getContext('2d'),times=m.history.time,broken=m.history.brokenBonds,front=m.history.crackFrontIndicatorX;function line(v,color,min,max){h.strokeStyle=color;h.lineWidth=2;h.beginPath();v.forEach((q,i)=>{const x=65+970*times[i]/times.at(-1),y=215-160*(q-min)/Math.max(max-min,1e-20);i?h.lineTo(x,y):h.moveTo(x,y);});h.stroke();}h.font='17px system-ui';h.fillStyle='#25394d';h.fillText(`时间 0 → ${times.at(-1)*1e6} μs`,430,255);h.fillText(`蓝：新断键 0 → ${Math.max(...broken)}；橙：前沿 x −10 → +20 mm（右轴范围）`,65,30);line(broken,'#246ac3',0,Math.max(...broken));line(front,'#e6760c',-.01,.02);draw();</script></html>'''
    sensitivity=core.load(p/'time-step-check.json') if (p/'time-step-check.json').exists() else {'status':'Not performed for this run; no convergence claim'}
    values={'SENS':html.escape(json.dumps(sensitivity,ensure_ascii=False,indent=2)),'STATUS':'数值与断键一致性检查通过' if v['passed'] else '验证未通过','METRICS':html.escape(json.dumps(v.get('metrics'),ensure_ascii=False,indent=2)),'CHECKS':checks,'LIMITS':html.escape(json.dumps(v.get('not_verified'),ensure_ascii=False,indent=2)),'SPEC':html.escape(json.dumps(s,ensure_ascii=False,indent=2)),'JOB':html.escape(json.dumps(job,ensure_ascii=False,indent=2)),'DATA':data}
    for k,value in values.items():doc=doc.replace('__'+k+'__',value)
    (p/'report.html').write_text(doc,encoding='utf-8')
