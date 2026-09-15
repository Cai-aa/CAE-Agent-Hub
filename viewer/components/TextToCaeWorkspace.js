import { useMemo, useState } from "react";
import {
  Activity,
  ArrowUpRight,
  Bot,
  Box,
  CheckCircle2,
  ChevronRight,
  CircleStop,
  Cpu,
  FileDown,
  FolderOpen,
  Gauge,
  Grid3X3,
  History,
  MessageSquare,
  Play,
  Radio,
  RefreshCw,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  Wind,
  X,
} from "lucide-react";

const LOCKED_RULES = [
  ["全局增长率", "1.20"],
  ["翼后缘尺寸", "0.5–2 mm"],
  ["机身/尾翼表面", "3–5 mm"],
  ["外流场尺寸", "2–15 mm"],
  ["边界层", "10 层 · 1.20"],
  ["收敛标准", "1e-5 + 曲线平稳"],
];

const DEFAULT_PARAMS = {
  velocity: "22",
  aoa: "3",
  sideslip: "0",
  density: "1.225",
  viscosity: "1.7894e-5",
  model: "k-ω SST",
  angles: "−4, 0, 3, 6, 9",
};

const WORKFLOW = [
  ["geometry", "几何预处理", "清理 < 0.5 mm 特征 · 坐标校正"],
  ["domain", "外流场与边界", "入口 10L · 横向/上下 10B"],
  ["mesh", "自动网格与质检", "边界层 y+≈1 · 质量门禁"],
  ["solve", "双精度求解", "实时残差与升阻力监测"],
  ["post", "后处理与报告", "云图 · 迹线 · PDF · 气动极曲线"],
];

function Field({ label, unit, value, onChange, disabled }) {
  return (
    <label className="cfd-field">
      <span>{label}<em>{unit}</em></span>
      <input value={value} onChange={(event) => onChange(event.target.value)} disabled={disabled} />
    </label>
  );
}

function Status({ children, tone = "cyan" }) {
  return <span className={`cfd-status cfd-status-${tone}`}><i />{children}</span>;
}

export default function TextToCaeWorkspace() {
  const [params, setParams] = useState(DEFAULT_PARAMS);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(38);
  const [activeStep, setActiveStep] = useState(2);
  const [chatInput, setChatInput] = useState("");
  const [messages, setMessages] = useState([
    { role: "ai", text: "工程已就绪。核心规范已锁定，等待导入无人机几何或启动标准工况。" },
    { role: "ai", text: "当前坐标系：X 机头前向 · Y 机身右侧 · Z 垂直向下。Fluent GUI 将在求解开始时保持打开。" },
  ]);

  const update = (key, value) => setParams((current) => ({ ...current, [key]: value }));
  const currentStep = WORKFLOW[activeStep];
  const completion = useMemo(() => `${progress}%`, [progress]);

  const sendCommand = () => {
    const text = chatInput.trim();
    if (!text) return;
    setMessages((current) => [...current, { role: "user", text }]);
    setChatInput("");
    const isStop = /停止|stop/i.test(text);
    const isOptimize = /优化|网格|mesh/i.test(text);
    setTimeout(() => {
      if (isStop) {
        setRunning(false);
        setMessages((current) => [...current, { role: "ai", text: "已收到停止指令。正在关闭 Fluent 可视化会话、释放进程并保存当前日志。" }]);
      } else if (isOptimize) {
        setActiveStep(2);
        setMessages((current) => [...current, { role: "ai", text: "已进入人工网格优化轮次。核心尺寸与增长率不会修改，当前质量门禁：歪斜度 ≤ 0.85、正交质量 ≥ 0.20、长宽比 ≤ 20。" }]);
      } else {
        setMessages((current) => [...current, { role: "ai", text: "指令已解析为标准外流场任务。请确认右侧参数后点击“启动全自动仿真”。" }]);
      }
    }, 250);
  };

  const startSimulation = () => {
    setRunning(true);
    setProgress(42);
    setActiveStep(2);
    setMessages((current) => [...current, { role: "ai", text: "Fluent 3ddp GUI 已请求启动。正在执行网格质检，实时过程会同步到本窗口。" }]);
  };

  return (
    <main className="cfd-shell">
      <header className="cfd-topbar">
        <div className="cfd-brand"><div className="cfd-logo"><Wind size={22} /></div><div><strong>FLUENT<span>·</span>OPS</strong><small>OFFLINE CFD INTELLIGENCE</small></div></div>
        <div className="cfd-project"><span className="cfd-live-dot" />项目 / UAV-2026-0915-01 <ChevronRight size={13} /> <b>标准外流场</b></div>
        <div className="cfd-top-actions"><Status>本地引擎在线</Status><button className="cfd-icon-btn" title="项目管理"><FolderOpen size={16} /></button><button className="cfd-icon-btn" title="设置"><Settings2 size={16} /></button></div>
      </header>

      <div className="cfd-layout">
        <aside className="cfd-sidebar">
          <div className="cfd-section-label">SIMULATION CONTROL</div>
          <button className="cfd-nav active"><Activity size={16} />仿真控制 <span>01</span></button>
          <button className="cfd-nav"><History size={16} />历史工程 <span>12</span></button>
          <button className="cfd-nav"><Radio size={16} />CODESYS 联动 <span className="cfd-nav-off">待机</span></button>
          <div className="cfd-sidebar-block">
            <div className="cfd-section-label">CURRENT MODEL</div>
            <div className="cfd-model-card"><Box size={18} /><div><b>uav_concept_v4.step</b><small>STEP · 2.84 MB</small></div><CheckCircle2 size={15} className="cfd-ok" /></div>
            <button className="cfd-outline-btn"><FolderOpen size={14} />导入新模型</button>
          </div>
          <div className="cfd-sidebar-block">
            <div className="cfd-section-label">LOCKED STANDARD <ShieldCheck size={13} /></div>
            <div className="cfd-lock-list">{LOCKED_RULES.map(([name, value]) => <div key={name}><span>{name}</span><b>{value}</b></div>)}</div>
          </div>
          <div className="cfd-sidebar-footer"><Cpu size={14} /><span>Ansys Fluent<br /><b>待连接本地许可</b></span><span className="cfd-fluent-dot" /></div>
        </aside>

        <section className="cfd-main">
          <div className="cfd-main-head"><div><div className="cfd-eyebrow">AUTONOMOUS AERODYNAMICS / 001</div><h1>无人机外流场仿真</h1><p>航空级标准流程 · 双精度 k-ω SST · 全程 GUI 可视化</p></div><div className="cfd-head-status"><Status tone={running ? "amber" : "green"}>{running ? "仿真运行中" : "系统就绪"}</Status><span className="cfd-time">2026-09-15 20:43 CST</span></div></div>

          <div className="cfd-workflow">{WORKFLOW.map(([id, title, detail], index) => <div key={id} className={`cfd-step ${index === activeStep ? "active" : ""} ${index < activeStep ? "done" : ""}`}><div className="cfd-step-number">{index < activeStep ? "✓" : `0${index + 1}`}</div><div><b>{title}</b><small>{detail}</small></div>{index < WORKFLOW.length - 1 && <div className="cfd-step-line" />}</div>)}</div>

          <div className="cfd-dashboard">
            <div className="cfd-viewport cfd-panel">
              <div className="cfd-panel-head"><span><span className="cfd-panel-icon"><Wind size={14} /></span>流场预览 / LIVE MONITOR</span><Status tone={running ? "amber" : "cyan"}>{running ? "FLUENT GUI · LIVE" : "预览模式"}</Status></div>
              <div className="cfd-viewport-art"><div className="cfd-grid-bg" /><div className="cfd-flow-line line-a" /><div className="cfd-flow-line line-b" /><div className="cfd-flow-line line-c" /><div className="cfd-drone"><div className="wing wing-left" /><div className="wing wing-right" /><div className="fuselage" /><div className="tail" /></div><div className="cfd-axis"><span>X</span><span>Y</span><span>Z</span></div><div className="cfd-viewport-caption"><span>VELOCITY MAGNITUDE</span><b>22.0 m/s</b><span>PRESSURE COEFFICIENT</span><b className="orange">−0.84</b></div></div>
              <div className="cfd-viewport-tabs"><button className="selected">速度云图</button><button>压力云图</button><button>流线动画</button><button>网格质量</button><ArrowUpRight size={14} /></div>
            </div>

            <div className="cfd-panel cfd-metrics"><div className="cfd-panel-head"><span><span className="cfd-panel-icon"><Gauge size={14} /></span>实时气动监测</span><span className="cfd-mini-live"><i />SYNC</span></div><div className="cfd-metric-grid"><div><small>升力系数 CL</small><b>0.684</b><em>▲ 2.8%</em></div><div><small>阻力系数 CD</small><b>0.041</b><em>▲ 0.6%</em></div><div><small>升阻比 L/D</small><b>16.68</b><em className="blue">STABLE</em></div><div><small>残差 / continuity</small><b>1.2e−5</b><em className="amber">收敛中</em></div></div><div className="cfd-sparkline"><svg viewBox="0 0 420 70" preserveAspectRatio="none"><polyline points="0,57 35,54 70,58 105,42 140,45 175,31 210,35 245,22 280,27 315,16 350,21 385,11 420,13" fill="none" stroke="#39d9c5" strokeWidth="2" /><polyline points="0,69 420,69" fill="none" stroke="#23394b" /></svg><span>ITERATION 184 / 500</span></div></div>
          </div>

          <div className="cfd-bottom-grid"><div className="cfd-panel cfd-progress"><div className="cfd-panel-head"><span><RefreshCw size={14} className={running ? "spin" : ""} /> 自动流程状态</span><b>{completion}</b></div><div className="cfd-progress-track"><span style={{ width: completion }} /></div><div className="cfd-log"><div><span className="cfd-log-time">20:43:18</span><CheckCircle2 size={13} className="cfd-ok" />坐标系校正完成 · 右手系 X/Y/Z</div><div><span className="cfd-log-time">20:43:21</span><CheckCircle2 size={13} className="cfd-ok" />外流场创建完成 · 10L × 10B</div><div><span className="cfd-log-time">20:43:26</span><Grid3X3 size={13} className="cfd-amber" />网格质检进行中 · 第 1 / 3 次</div></div></div><div className="cfd-panel cfd-outputs"><div className="cfd-panel-head"><span><FileDown size={14} />输出成果</span><button className="cfd-link-btn">打开工程目录 <ArrowUpRight size={13} /></button></div><div className="cfd-output-list"><div><span className="file-icon cyan">∿</span><span><b>压力云图 / 速度云图</b><small>PNG · Fluent scene</small></span><CheckCircle2 size={14} className="cfd-ok" /></div><div><span className="file-icon blue">↗</span><span><b>气动极曲线</b><small>CSV · CL/CD/CM</small></span><CheckCircle2 size={14} className="cfd-ok" /></div><div><span className="file-icon orange">▤</span><span><b>完整仿真报告</b><small>PDF · 中文工程报告</small></span><span className="cfd-file-pending">等待求解</span></div></div></div></div>

          <div className="cfd-action-row"><button className="cfd-primary-btn" onClick={startSimulation} disabled={running}><Play size={16} fill="currentColor" />{running ? "仿真运行中…" : "启动全自动仿真"}<span>⌘ ↵</span></button><button className="cfd-stop-btn" onClick={() => { setRunning(false); setMessages((current) => [...current, { role: "ai", text: "仿真已停止，资源清理指令已发送。" }]); }}><CircleStop size={16} />停止仿真</button><span className="cfd-action-hint"><Sparkles size={14} />固定规范已启用 · AI 不会修改核心参数</span></div>
        </section>

        <aside className="cfd-chat">
          <div className="cfd-chat-head"><div><div className="cfd-ai-title"><span className="cfd-ai-orb"><Bot size={16} /></span>FLUENT AI COPILOT</div><small>本地离线工程助手</small></div><button className="cfd-icon-btn"><X size={15} /></button></div>
          <div className="cfd-chat-context"><MessageSquare size={14} /><span>正在监测：<b>UAV-2026-0915-01</b></span><span className="cfd-chat-online">●</span></div>
          <div className="cfd-messages">{messages.map((message, index) => <div key={`${message.role}-${index}`} className={`cfd-message ${message.role}`}><span className="cfd-message-avatar">{message.role === "ai" ? <Bot size={13} /> : "你"}</span><div>{message.role === "ai" && <small>AI ENGINE · {index === 0 ? "READY" : "LIVE"}</small>}<p>{message.text}</p></div></div>)}</div>
          <div className="cfd-suggest"><span>快捷指令</span><button onClick={() => setChatInput("继续优化网格")}>继续优化网格</button><button onClick={() => setChatInput("显示当前收敛状态")}>查看收敛</button></div>
          <div className="cfd-chat-input"><textarea value={chatInput} onChange={(event) => setChatInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); sendCommand(); } }} placeholder="输入仿真指令，例如：启动 0°–9° 批量攻角计算…" /><button onClick={sendCommand}><Send size={16} /></button><small>ENTER 发送 · SHIFT+ENTER 换行</small></div>
        </aside>
      </div>

      <div className="cfd-params-drawer"><div className="cfd-drawer-title"><span><Settings2 size={15} />工况参数 <small>SI 单位</small></span><span className="cfd-validated"><CheckCircle2 size={13} />参数已校验</span></div><div className="cfd-fields"><Field label="入口速度" unit="m/s" value={params.velocity} onChange={(value) => update("velocity", value)} disabled={running} /><Field label="攻角" unit="deg" value={params.aoa} onChange={(value) => update("aoa", value)} disabled={running} /><Field label="侧滑角" unit="deg" value={params.sideslip} onChange={(value) => update("sideslip", value)} disabled={running} /><Field label="密度" unit="kg/m³" value={params.density} onChange={(value) => update("density", value)} disabled={running} /><Field label="动力粘度" unit="Pa·s" value={params.viscosity} onChange={(value) => update("viscosity", value)} disabled={running} /><Field label="批量攻角" unit="deg list" value={params.angles} onChange={(value) => update("angles", value)} disabled={running} /></div></div>
    </main>
  );
}
