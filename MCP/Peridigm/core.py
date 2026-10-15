"""Shared, workspace-scoped CLI/MCP core. Solver and model provider are separate."""
from __future__ import annotations
import copy, difflib, hashlib, json, math, os, re, signal, subprocess, sys, time, uuid
from datetime import datetime, timezone
from pathlib import Path
import yaml

HERE = Path(__file__).resolve().parent
PROFILE = "compression-two-point-v1"
TERMINAL = {"completed", "failed", "timed_out", "cancelled", "orphaned"}

def stamp(): return datetime.now(timezone.utc).isoformat()
def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def canonical(obj): return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
def load(path): return json.loads(Path(path).read_text())
def save(path, obj):
    path=Path(path); tmp=path.with_name(path.name+"."+uuid.uuid4().hex+".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False)); tmp.replace(path)
def result(status="SUCCEEDED", **kw): return {"status":status, **kw}
def blocked(kind, message, **kw): return result("BLOCKED",error_type=kind,message=message,**kw)
def config():
    p=os.environ.get("PERIDIGM_CONFIG")
    if not p: raise ValueError("Set PERIDIGM_CONFIG to the project-local JSON config")
    c=load(p); c["root"]=str(Path(c["root"]).expanduser().resolve()); return c
def directory(run_id):
    if not re.fullmatch(r"[a-f0-9]{16}",run_id): raise ValueError("Invalid run_id")
    root=Path(config()["root"])/"runs"; p=(root/run_id).resolve()
    if p.parent != root.resolve() or not p.is_dir(): raise ValueError("Unknown run_id")
    return p
def event(p, kind, actor="tool", **data):
    with (p/"events.jsonl").open("a") as f:
        f.write(json.dumps({"time":stamp(),"kind":kind,"actor":actor,**data},ensure_ascii=False)+"\n")
def template(profile=PROFILE):
    if profile==PROFILE:return load(HERE/"examples"/"compression-two-point.json")
    import fracture
    if profile==fracture.PROFILE:return fracture.template()
    raise ValueError("Unsupported profile")

def reference_path(profile):
    return Path(config()["reference"]) if profile==PROFILE else HERE/"examples"/"notched-tension.json"
def parameter_sources(obj,prefix="physics"):
    sources={}
    for k,value in obj.items():
        path=prefix+"."+k
        if isinstance(value,dict):sources.update(parameter_sources(value,path))
        else:
            unit=next((unit for suffix,unit in [("_kg_m3","kg/m^3"),("_m_s","m/s"),("_pa","Pa"),("_m","m"),("_s","s")] if k.endswith(suffix)),"dimensionless or categorical")
            sources[path]={"source":"reviewed_template","unit":unit,"confirmed":False}
    return sources

def doctor():
    c=config(); exe=Path(c["solver"]); env=os.environ.copy()
    env["LD_LIBRARY_PATH"]=":".join(c["library_dirs"]+[env.get("LD_LIBRARY_PATH","")])
    if not exe.is_file() or not os.access(exe,os.X_OK): return blocked("environment","Solver executable missing")
    p=subprocess.run(["ldd",str(exe)],env=env,capture_output=True,text=True,timeout=15)
    missing=[s.strip() for s in p.stdout.splitlines() if "not found" in s]
    return result("BLOCKED" if missing else "SUCCEEDED",error_type="environment" if missing else None,
        solver=str(exe),solver_sha256=digest(exe),missing_libraries=missing,python=sys.version,
        reference_exists=Path(c["reference"]).is_file(),root=c["root"],mpi_supported=Path(c.get("mpirun","")).is_file(),qualified_process_counts=[1,2],
        note="Readiness only; a completed verified solve is a separate gate")

def list_templates():
    import fracture
    return result(templates=[{"id":profile,"description":t["description"],"parameters":t["physics"],
        "validation":t["validation"],"scope":t["scope"],"qualified_mpi_processes":[1,2] if profile==PROFILE else [1]} for profile in (PROFILE,fracture.PROFILE) for t in [template(profile)]])

def start_context(request: str, actor: str="ai_client"):
    if not request.strip(): return blocked("missing_context","A natural-language objective is required")
    root=Path(config()["root"])/"runs"; root.mkdir(parents=True,exist_ok=True)
    run_id=uuid.uuid4().hex[:16]; p=root/run_id; p.mkdir()
    save(p/"context.json",{"request":request,"phase":"choose_template","created":stamp()})
    event(p,"request",actor,request=request)
    choices=[t['id'] for t in list_templates()['templates']]
    event(p,"question",fields=["template_id"],question="Select an elastic verification or synthetic precracked tensile damage template; review its limits before confirmation.",missing=["geometry","material","initial_conditions","solver","validation"])
    return result("NEEDS_INPUT",run_id=run_id,questions=[{"field":"template_id","reason":"Geometry, material, loading and validation target are missing", "question":"Which reviewed template matches the task?", "choices":choices}],
        missing=["geometry","material","initial_conditions","solver","validation"],
        note="The current AI client conducts clarification; this tool does not call an external LLM")

def answer_context(run_id: str, answers: dict, actor: str="ai_client"):
    p=directory(run_id); ctx=load(p/"context.json"); event(p,"answer",actor,answers=answers)
    if ctx["phase"]=="frozen": return blocked("physical_semantic","Confirmed specification is immutable; start a new case")
    if ctx["phase"]=="choose_template":
        profile=answers.get('template_id')
        try:t=template(profile)
        except ValueError:return blocked("unsupported","Select a listed qualified profile")
        allowed=(1,2) if profile==PROFILE else (1,)
        if answers.get("mpi_processes",1) not in allowed:return blocked("unsupported","This profile is not qualified for that MPI process count")
        if set(answers)-{'template_id','mpi_processes','time_step_variant'}:return blocked('unsupported','Unreviewed parameter overrides are not accepted')
        variant=answers.get('time_step_variant','base')
        if variant not in ('base','half') or (profile==PROFILE and variant!='base'):return blocked('unsupported','Time-step variant is not qualified for this profile')
        if variant=='half':t['physics']['solver']['dt_s']/=2
        t["physics"]["solver"]["mpi_processes"]=answers.get("mpi_processes",1)
        s={"schema_version":1,"template_id":profile,"objective":ctx["request"],"physics":t["physics"],
           "validation":t["validation"],"reference_sha256":digest(reference_path(profile)),
           "provenance":{"physics":{"source":"reviewed_template","reference":t["source"],"confirmed":False},
                         "derived":{"point_volume_m3":2.0,"initial_separation_m":2.0,"basis":"geometry cell dimensions"}},
           "capability_scope":t["scope"]}
        if profile!=PROFILE:
            import fracture
            _,dx=fracture.points(t['physics'])
            s['provenance']['derived']={'point_volume_m3':float(math.prod(dx)),'spacing_m':dx.tolist(),'basis':'geometry cell dimensions'}
        s["provenance"]["fields"]=parameter_sources(t["physics"])
        save(p/"spec.json",s); ctx["phase"]="confirm_parameters";save(p/"context.json",ctx)
        event(p,"template_selected",actor,template_id=profile,spec_sha256=canonical(s))
        event(p,"question",fields=["confirm_spec_sha256"],question="Confirm the displayed synthetic verification parameters and scope?",spec_sha256=canonical(s))
        return result("NEEDS_INPUT",run_id=run_id,specification=s,questions=[{"field":"confirm_spec_sha256", "question":"Confirm these synthetic verification parameters and benchmark limitations?", "value":canonical(s)}])
    s=load(p/"spec.json")
    if answers != {"confirm_spec_sha256":canonical(s)}:
        return blocked("missing_context","Explicit confirmation must match the reviewed specification hash; no implicit defaults accepted")
    s["provenance"]["physics"].update(source="confirmed_template",confirmed=True,confirmed_by=actor,confirmed_at=stamp())
    for meta in s["provenance"].get("fields",{}).values():meta.update(source="confirmed_template",confirmed=True,confirmed_by=actor)
    save(p/"spec.json",s); save(p/"frozen.json",{"spec_sha256":canonical(s),"confirmed_by":actor,"at":stamp()})
    ctx["phase"]="frozen";save(p/"context.json",ctx)
    (p/"input.yaml").write_text(yaml.safe_dump(deck(s),sort_keys=False,width=1000000))
    if s['template_id']!=PROFILE:
        import fracture
        (p/'points.txt').write_text(fracture.mesh_text(s['physics']))
    event(p,"spec_frozen",actor,spec_sha256=canonical(s))
    return result(run_id=run_id,spec_sha256=canonical(s),validation=validate_case(run_id))

def deck(spec):
    if spec['template_id']!=PROFILE:
        import fracture
        return fracture.deck(spec)
    f=spec["physics"];g=f["geometry"];m=f["material"];so=f["solver"]
    grid={"Type":"PdQuickGrid"}
    for i,axis in enumerate("XYZ"):
        grid[axis+" Origin"]=g["origin_m"][i];grid[axis+" Length"]=g["lengths_m"][i];grid["Number Points "+axis]=g["points"][i]
    bc={"Min X Node Set":"1","Max X Node Set":"2"}
    for name,value in zip(["Min","Max"],f["initial_velocity_x_m_s"]):
        bc["Initial Velocity "+name+" X Face"]={"Type":"Initial Velocity","Node Set":name+" X Node Set","Coordinate":"x","Value":str(float(value))}
    return {"Peridigm":{"Discretization":{"Type":"PdQuickGrid","TensorProduct3DMeshGenerator":grid},
        "Materials":{"My Elastic Material":{"Material Model":m["model"],"Apply Shear Correction Factor":False,"Density":m["density_kg_m3"],"Bulk Modulus":m["bulk_modulus_pa"],"Shear Modulus":m["shear_modulus_pa"]}},
        "Blocks":{"My Group of Blocks":{"Block Names":"block_1","Material":"My Elastic Material","Horizon":f["horizon_m"]}},
        "Boundary Conditions":bc,"Solver":{"Verbose":False,"Initial Time":0.0,"Final Time":so["final_time_s"],"Verlet":{"Fixed dt":so["dt_s"]}},
        "Output":{"Output File Type":"ExodusII","Output Format":"BINARY","Output Filename":"result","Output Frequency":so["output_frequency"],"Parallel Write":True,"Output Variables":{k:True for k in f["output_variables"]}}}}

def validate_case(run_id: str):
    p=directory(run_id); issues=[]
    def issue(rule,msg):issues.append({"rule":rule,"message":msg})
    if not (p/"spec.json").exists() or not (p/"frozen.json").exists():
        return blocked("missing_context","Finish template selection and parameter confirmation first",questions=["Select a supported template","Confirm the exact specification"])
    s=load(p/"spec.json")
    try:t=template(s.get('template_id'))
    except ValueError:return blocked('unsupported','Unknown specification profile')
    if s['template_id']!=PROFILE:
        import fracture
        return fracture.validate(p,s,t)
    if canonical(s)!=load(p/"frozen.json")["spec_sha256"]:issue("intent_lock","Frozen specification changed")
    f=s.get("physics",{})
    expected=copy.deepcopy(t["physics"]);expected["solver"]["mpi_processes"]=f.get("solver",{}).get("mpi_processes")
    if f!=expected or s.get("validation")!=t["validation"]:issue("profile_support","This version supports the exact reviewed physical profile only; other configurations need a new qualified profile")
    if s.get("reference_sha256")!=digest(config()["reference"]):issue("reference","Reference data identity changed")
    if f.get("units")!="SI":issue("units","Only SI is supported")
    m=f.get("material",{});g=f.get("geometry",{});so=f.get("solver",{})
    if any(not isinstance(m.get(k),(int,float)) or not math.isfinite(m[k]) or m[k]<=0 for k in ["density_kg_m3","bulk_modulus_pa","shear_modulus_pa"]):issue("material","Positive finite density and moduli required")
    if g.get("points")!=[2,1,1] or g.get("lengths_m")!=[4.0,1.0,1.0]:issue("volume_nodes","Qualified grid has two positive-volume points and nonempty node sets 1,2")
    if f.get("horizon_m")!=2.0:issue("horizon","Qualified neighbor separation and horizon are both 2 m; not a general 3D resolution recommendation")
    if f.get("contact")!="none" or f.get("damage")!="none" or f.get("initial_velocity_x_m_s")!=[1.0,-1.0]:issue("initial_contact","This elastic benchmark has no contact/damage and opposing x velocities")
    if so.get("mpi_processes") not in (1,2):issue("mpi","Only 1/2-process runs of this profile are qualified")
    try:
        omega=math.sqrt(36*m["bulk_modulus_pa"]/(m["density_kg_m3"]*4))
        if not (0<so["dt_s"] and omega*so["dt_s"]<2 and so["final_time_s"]>=so["dt_s"] and so["output_frequency"]==1):issue("time","Verlet stability, physical time and complete output required")
    except (KeyError,TypeError,ValueError):issue("time","Missing or invalid numerical parameters")
    kind="physical_semantic" if issues else None
    try:
        actual=yaml.safe_load((p/"input.yaml").read_text())
        if actual!=deck(s):issue("input_alignment","Input differs from the frozen specification");kind=kind or "input_alignment"
    except (yaml.YAMLError,OSError,TypeError,KeyError):issue("syntax","Input is missing or not valid YAML");kind=kind or "input_syntax"
    r=result("BLOCKED" if issues else "SUCCEEDED",error_type=kind,run_id=run_id,issues=issues,rules_file="rules/verification.json")
    save(p/"preflight.json",r);return r

def repair_case(run_id: str):
    p=directory(run_id);check=validate_case(run_id)
    if check["status"]=="SUCCEEDED":return result(run_id=run_id,message="No repair needed")
    count=len(list(p.glob("repair-*.json")))
    if count>=3:return blocked("repair_limit","Three-attempt limit reached; retained failure evidence")
    if check.get("error_type") not in {"input_syntax","input_alignment"}:return blocked("physical_semantic","Repair cannot alter a frozen physical specification",issues=check.get("issues"))
    s=load(p/"spec.json");before=(p/"input.yaml").read_text() if (p/"input.yaml").exists() else ""
    after=yaml.safe_dump(deck(s),sort_keys=False,width=1000000);i=count+1
    (p/f"input.before-repair-{i}.txt").write_text(before)
    (p/f"repair-{i}.diff").write_text("".join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile="before",tofile="after")))
    save(p/f"repair-{i}.json",{"at":stamp(),"reason":check,"action":"Regenerate canonical deck from unchanged frozen specification","spec_sha256":canonical(s)})
    (p/"input.yaml").write_text(after);event(p,"repair",attempt=i,reason=check)
    if s['template_id']!=PROFILE:
        import fracture
        mesh=p/'points.txt';before_mesh=mesh.read_text() if mesh.exists() else '';after_mesh=fracture.mesh_text(s['physics'])
        if before_mesh!=after_mesh:
            (p/f'points.before-repair-{i}.txt').write_text(before_mesh)
            (p/f'points-repair-{i}.diff').write_text(''.join(difflib.unified_diff(before_mesh.splitlines(True),after_mesh.splitlines(True),fromfile='before',tofile='after')))
            mesh.write_text(after_mesh)
    return result(run_id=run_id,attempt=i,validation=validate_case(run_id))

def submit_case(run_id: str,timeout_seconds: int=120):
    import fcntl
    p=directory(run_id)
    if not 1<=timeout_seconds<=300:return blocked("budget","timeout_seconds must be between 1 and 300")
    with (p/"submit.lock").open("w") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if (p/"job.json").exists():return blocked("existing_job","A case is single-use; create a new case to rerun",job=load(p/"job.json"))
        check=validate_case(run_id)
        if check["status"]!="SUCCEEDED":return check
        ready=doctor()
        if ready["status"]!="SUCCEEDED":return ready
        state={"run_id":run_id,"state":"queued","created":stamp(),"timeout_seconds":timeout_seconds,
               "spec_sha256":canonical(load(p/"spec.json")),"input_sha256":digest(p/"input.yaml"),"solver_sha256":ready["solver_sha256"],"mpi_processes":load(p/"spec.json")["physics"]["solver"]["mpi_processes"]}
        if (p/'points.txt').exists():state['mesh_sha256']=digest(p/'points.txt')
        save(p/"job.json",state)
        with (p/"worker.log").open("w") as log:
            proc=subprocess.Popen([sys.executable,str(HERE/"pd.py"),"_worker",run_id],stdout=log,stderr=log,stdin=subprocess.DEVNULL,start_new_session=True,env=os.environ.copy())
        save(p/"worker.json",{"pid":proc.pid,"created":stamp()})
    event(p,"submitted",timeout_seconds=timeout_seconds)
    return result(run_id=run_id,job=state,worker_pid=proc.pid)

def worker(run_id):
    p=directory(run_id);s=load(p/"job.json");started=time.monotonic();proc=None
    try:
        check=validate_case(run_id)
        if check["status"]!="SUCCEEDED" or digest(p/"input.yaml")!=s["input_sha256"] or digest(config()["solver"])!=s["solver_sha256"]:raise ValueError("Specification/input/solver changed after submission")
        c=config();env=os.environ.copy();env["LD_LIBRARY_PATH"]=":".join(c["library_dirs"]+[env.get("LD_LIBRARY_PATH","")]);env["OMP_NUM_THREADS"]="1";env["OPENBLAS_NUM_THREADS"]="1"
        s.update(state="running",started=stamp());save(p/"job.json",s)
        with (p/"stdout.log").open("w") as out,(p/"stderr.log").open("w") as err:
            command=[c["solver"],"input.yaml"]
            if s["mpi_processes"]==2:command=[c["mpirun"],"-np","2"]+command
            proc=subprocess.Popen(command,cwd=p,env=env,stdout=out,stderr=err,stdin=subprocess.DEVNULL,start_new_session=True)
            s.update(solver_pid=proc.pid);save(p/"job.json",s)
            while proc.poll() is None:
                if (p/"cancel.request").exists() or time.monotonic()-started>s["timeout_seconds"]:
                    s["state"]="cancelled" if (p/"cancel.request").exists() else "timed_out"
                    os.killpg(proc.pid,signal.SIGTERM)
                    try:proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
                    break
                time.sleep(0.05)
            s["exit_code"]=proc.returncode
            if s["state"]=="running":s["state"]="completed" if proc.returncode==0 else "failed"
        if s["state"]=="failed":s["error_type"]=diagnose((p/"stdout.log").read_text()+ (p/"stderr.log").read_text())
    except Exception as e:
        s.update(state="failed",error_type="worker",message=str(e))
        if proc and proc.poll() is None:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
    s.update(finished=stamp(),elapsed_seconds=time.monotonic()-started)
    s["outputs"]=[{"name":x.name,"bytes":x.stat().st_size,"sha256":digest(x)} for x in sorted(p.glob("result.e*"))]
    save(p/"job.json",s);event(p,"solver_terminal",job=s)

def diagnose(text):
    for fragment,kind in [("shared libraries","environment"),("Error parsing","input_syntax"),("Node Set","field_or_nodeset"),("fieldId","field_or_nodeset"),("NaN","numerical"),("nan","numerical")]:
        if fragment in text:return kind
    return "solver_failure"

def job_status(run_id: str):
    p=directory(run_id)
    if not (p/"job.json").exists():return result("NOT_STARTED",run_id=run_id)
    s=load(p/"job.json")
    if s["state"] not in TERMINAL and (p/"worker.json").exists():
        try:
            pid=load(p/"worker.json")["pid"];args=Path(f"/proc/{pid}/cmdline").read_bytes().decode().split("\0")
            if run_id not in args:raise ProcessLookupError()
        except (FileNotFoundError,ProcessLookupError):
            # Do not restart: report an absent authoritative worker handle.
            s.update(state="orphaned",error_type="worker_missing");save(p/"job.json",s)
    return result(run_id=run_id,job=s)
def read_log(run_id: str,stream: str="stdout",tail_chars: int=8000):
    p=directory(run_id)
    if stream not in {"stdout","stderr","worker"}:return blocked("input","Unknown log stream")
    f=p/(stream+".log")
    return result(run_id=run_id,stream=stream,text=f.read_text(errors="replace")[-max(1,min(tail_chars,20000)):] if f.exists() else "")
def cancel_job(run_id: str):
    p=directory(run_id);s=job_status(run_id)
    if "job" not in s or s["job"]["state"] in TERMINAL:return blocked("terminal","No active job to cancel")
    save(p/"cancel.request",{"at":stamp()});event(p,"cancel_requested");return result(run_id=run_id)
def collect_results(run_id: str):
    from postprocess import collect
    p=directory(run_id);st=job_status(run_id)
    if "job" not in st or st["job"]["state"]!="completed":return blocked("not_completed","Actual solver completion is required",state=st)
    check=validate_case(run_id)
    if check["status"]!="SUCCEEDED":return check
    job=st["job"]
    if digest(p/"input.yaml")!=job["input_sha256"]:return blocked("physical_semantic","Solved input identity changed")
    if not job.get("outputs") or any(not (p/x["name"]).is_file() or digest(p/x["name"])!=x["sha256"] for x in job["outputs"]):return blocked("output_integrity","Solver outputs changed or are incomplete")
    spec=load(p/'spec.json')
    if spec['template_id']!=PROFILE:
        import fracture
        if digest(p/'points.txt')!=job['mesh_sha256']:return blocked('physical_semantic','Solved mesh identity changed')
        return fracture.collect(p,spec,config(),job)
    return collect(p,spec,config(),job)
def make_report(run_id: str):
    from postprocess import report
    r=collect_results(run_id)
    if r["status"]!="SUCCEEDED":return r
    p=directory(run_id)
    if load(p/'spec.json')['template_id']!=PROFILE:
        import fracture
        fracture.report(p)
    else:report(p)
    return result(run_id=run_id,report=str(p/"report.html"),validation=r["validation"])
