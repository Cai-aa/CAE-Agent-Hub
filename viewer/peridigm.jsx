import { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import CaeResultViewer from "./components/CaeResultViewer";
import elasticUrl from "../models/peridigm-elastic/result_mesh.json?url&no-inline";
import fractureUrl from "../models/peridigm-notched-tension/result_mesh.json?url&no-inline";
import elasticCaseUrl from "../models/peridigm-elastic/case.json?url&no-inline";
import fractureCaseUrl from "../models/peridigm-notched-tension/case.json?url&no-inline";
import elasticCsvUrl from "../models/peridigm-elastic/response.csv?url&no-inline";
import fractureCsvUrl from "../models/peridigm-notched-tension/response.csv?url&no-inline";
import elasticManifestUrl from "../models/peridigm-elastic/manifest.json?url&no-inline";
import fractureManifestUrl from "../models/peridigm-notched-tension/manifest.json?url&no-inline";
import "./app/globals.css";

const DEMOS = {
  elastic: {title:"弹性基准 / Elastic",description:"2 个材料点 · 6 个真实时刻 · gold 与独立解析解验证",url:elasticUrl,caseUrl:elasticCaseUrl,csvUrl:elasticCsvUrl,manifestUrl:elasticManifestUrl},
  fracture: {title:"损伤与裂纹推进 / Fracture",description:"3,200 个材料点 · 31 个展示时刻 · 逐步断键独立重建",url:fractureUrl,caseUrl:fractureCaseUrl,csvUrl:fractureCsvUrl,manifestUrl:fractureManifestUrl},
};
const panel={padding:16,border:"1px solid #ccd6df",borderRadius:10,background:"#f5f8fb"};
const button={padding:"10px 14px",border:"1px solid #94a9bd",borderRadius:7,cursor:"pointer",background:"white"};

function checkMesh(data) {
  if (data.representation!=="material-points" || !Array.isArray(data.nodes) || data.elements?.length) throw new Error("Requires material-point results without invented FE connectivity");
  const frames=data.dynamicFrames?.length ? data.dynamicFrames : [data];
  for (const frame of frames) {
    if (!frame.nodes?.length || frame.nodes.some(n=>!Array.isArray(n.coordinates)||n.coordinates.length!==3||!n.coordinates.every(Number.isFinite))) throw new Error("Invalid saved material-point coordinates");
  }
  return data;
}

function HistoryPlot({title,times,values,unit}) {
  if (!times?.length || times.length!==values?.length) return null;
  const low=Math.min(0,...values),high=Math.max(...values),last=times.at(-1)||1;
  const path=values.map((v,i)=>`${i?'L':'M'}${60+880*times[i]/last},${140-100*(v-low)/Math.max(high-low,1e-30)}`).join(" ");
  return <div style={panel}><h3>{title}</h3><svg viewBox="0 0 1000 190" role="img" aria-label={title} style={{width:"100%",background:"white"}}><path d="M60 20V145H950" stroke="#8191a0" fill="none"/><path d={path} fill="none" stroke="#137da0" strokeWidth="2"/><text x="65" y="18">{low.toPrecision(4)} → {high.toPrecision(4)} {unit}</text><text x="400" y="178">时间 0 → {(last*1e6).toFixed(1)} μs</text></svg></div>;
}

function initialSource() {
  const params=new URLSearchParams(window.location.search);
  if(params.has('demo')) return {kind:'demo',id:params.get('demo')};
  if(params.has('result')) return {kind:'run',path:params.get('result')};
  return null;
}

function PeridigmViewer() {
  const [source,setSource]=useState(initialSource),[mesh,setMesh]=useState(null),[error,setError]=useState(''),[loading,setLoading]=useState(false),[field,setField]=useState('damage');
  const demo=source?.kind==='demo'?DEMOS[source.id]:null;
  useEffect(()=>{
    const controller=new AbortController();setMesh(null);setError('');setLoading(false);
    if(!source)return()=>controller.abort();
    if(source.kind==='file'){try{setMesh(checkMesh(source.data));}catch(e){setError(e.message);}return()=>controller.abort();}
    let url;
    try {
      if(source.kind==='demo') {if(!DEMOS[source.id])throw new Error('Unknown demo. Select one of the two reviewed cases.');url=DEMOS[source.id].url;}
      else {const target=new URL(source.path,window.location.href);if(target.origin!==window.location.origin||!target.pathname.startsWith('/run/'))throw new Error('Only same-origin /run/ results are accepted');url=target.href;}
    }catch(e){setError(e.message);return()=>controller.abort();}
    setLoading(true);
    fetch(url,{signal:controller.signal}).then(r=>{if(!r.ok)throw new Error('Result file unavailable');return r.json();}).then(checkMesh).then(data=>{if(!controller.signal.aborted){setMesh(data);setLoading(false);}}).catch(e=>{if(e.name!=='AbortError'){setError(e.message);setLoading(false);}});
    return()=>controller.abort();
  },[source]);
  function choose(id) {setSource({kind:'demo',id});setField('damage');const url=new URL(window.location.href);url.search='';url.searchParams.set('demo',id);window.history.replaceState({},'',url);}
  const hasDamage=mesh?.nodes.some(n=>Number.isFinite(n.damage));
  const displayMesh=useMemo(()=>{
    if(!mesh||!hasDamage)return mesh;
    const value=n=>field==='damage'?n.damage:Math.hypot(...n.displacement);
    const max=field==='damage'?1:mesh.dynamicFrames.reduce((a,f)=>f.nodes.reduce((b,n)=>Math.max(b,value(n)),a),0);
    return {...mesh,fieldLabel:field==='damage'?'Damage (broken-bond fraction)':'Displacement magnitude (m)',fieldRanges:{valueMin:0,valueMax:max},nodes:mesh.nodes.map(n=>({...n,value:value(n)})),dynamicFrames:mesh.dynamicFrames.map(f=>({...f,nodes:f.nodes.map(n=>({...n,value:value(n)}))}))};
  },[mesh,hasDamage,field]);
  const metrics=mesh?.validation?.metrics||{};
  return <main style={{padding:20,maxWidth:1250,margin:'auto',color:'#172b3a'}}>
    <header><h1 style={{fontSize:27,marginBottom:6}}>Agentic PD · CAE Agent Hub</h1><p>需求补全 → 确认规格 → PD 检查 → Peridigm 求解 → 独立验证 → 材料点展示</p></header>
    <nav aria-label="Peridigm demos" style={{display:'flex',gap:12,flexWrap:'wrap',margin:'18px 0'}}>{Object.entries(DEMOS).map(([id,item])=><button type="button" key={id} aria-pressed={source?.kind==='demo'&&source.id===id} style={{...button,background:source?.id===id?'#e5f2f8':'white',textAlign:'left'}} onClick={()=>choose(id)}><strong>{item.title}</strong><br/><small>{item.description}</small></button>)}</nav>
    {!source&&<p style={panel}>选择一个已记录的真实算例即可回放。不需要 Peridigm 或 SSH。重新求解须配置模块的 CLI/MCP；本页的 Demo 按钮只读取已有结果。</p>}
    <label style={{display:'block',margin:'14px 0'}}>或打开自己的 result_mesh.json <input aria-label="打开 Peridigm 结果" type="file" accept=".json" onChange={async e=>{try{const file=e.target.files?.[0];if(file)setSource({kind:'file',data:JSON.parse(await file.text())});}catch(err){setError(err.message);}}}/></label>
    {loading&&<p role="status">正在加载真实保存帧…</p>}{error&&<p role="alert">{error}</p>}
    {mesh&&<><section style={{...panel,marginBottom:14}}><p><strong>{demo?'已计算结果回放 / Recorded replay':'已保存结果 / Saved result'}</strong> · {mesh.nodes.length.toLocaleString()} 个材料点 · {mesh.dynamicFrames?.length||1} 个展示时刻 · 位移比例 {mesh.deformationScale}</p><p>验证：{mesh.validation?.passed?'已通过此算例的数值检查':'未通过或未验证'}。网页不调用模型或求解器，不代表当前服务器运行状态。</p>{demo&&<p style={{display:'flex',gap:18,flexWrap:'wrap'}}><a href={demo.caseUrl}>参数与假设 JSON</a><a href={demo.csvUrl}>真实曲线 CSV</a><a href={demo.manifestUrl}>文件摘要</a></p>}</section>
      {hasDamage&&<label style={{display:'block',marginBottom:12}}>显示场 <select aria-label="显示场" value={field} onChange={e=>setField(e.target.value)}><option value="damage">损伤 Damage（0–1）</option><option value="displacement">位移幅值（m）</option></select></label>}
      <CaeResultViewer resultMesh={displayMesh} project={{outputs:{status:mesh.validation?.passed?'verified':'unverified'}}} locale="en"/>
      {mesh.precrack&&<p style={{marginTop:14}}>初始预裂纹：x = −20 至 −10 mm，y = 0。它通过邻域过滤建立，初始 Damage 为零。新断键沿剩余邻域计算；连通前沿指标不是精确裂纹面。{source?.kind==='run'&&<> <a href="/run/report.html">查看当前运行报告</a></>}</p>}
      <section aria-label="Verification metrics" style={{...panel,margin:'18px 0'}}><h2 style={{fontSize:20}}>验证摘要 / Verification</h2>{hasDamage?<p>新增断键：{metrics.new_broken_undirected_bonds?.toLocaleString()} 对；连通前沿推进指标：{(metrics.crack_extension_indicator_m*1000).toFixed(2)} mm；点损伤独立重建最大差：{metrics.max_point_damage_reconstruction_error}。</p>:<p>与 gold 位移最大差：{mesh.validation?.checks?.gold_displacement?.max_abs_difference} m；独立解析位移误差：{(metrics.max_analytic_displacement_relative_error*100).toFixed(4)}%。</p>}</section>
      {mesh.history?<section style={{display:'grid',gap:14}}><HistoryPlot title="实际新增断键数量" times={mesh.history.time} values={mesh.history.brokenBonds} unit="对"/><HistoryPlot title="连通裂纹前沿推进指标（非精确裂纹面）" times={mesh.history.time} values={mesh.history.crackFrontIndicatorX.map(x=>(x-mesh.precrack.tip_x_m)*1000)} unit="mm"/></section>:<HistoryPlot title="材料点 1 的实际 x 位移" times={mesh.dynamicFrames.map(f=>f.time)} values={mesh.dynamicFrames.map(f=>f.nodes[0].displacement[0])} unit="m"/>}
      <section style={{...panel,marginTop:18}}><h2 style={{fontSize:20}}>适用范围与未验证项</h2><p>{mesh.validation?.scope}</p><ul>{Object.entries(mesh.validation?.not_verified||{}).map(([k,v])=><li key={k}>{k}: {v}</li>)}</ul><p>展示真实材料点，不虚构有限元连通、裂纹面或未计算的应力场。回放、数值一致性、实验验证是不同结论。</p></section>
    </>}
  </main>;
}
createRoot(document.getElementById('root')).render(<PeridigmViewer/>);
