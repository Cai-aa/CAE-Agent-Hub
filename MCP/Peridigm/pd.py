"""JSON CLI over the same functions exposed by server.py."""
import argparse,json,sys
import core
COMMANDS={"doctor":core.doctor,"templates":core.list_templates,"start":core.start_context,"answer":core.answer_context,"validate":core.validate_case,"repair":core.repair_case,"submit":core.submit_case,"status":core.job_status,"log":core.read_log,"cancel":core.cancel_job,"collect":core.collect_results,"report":core.make_report}
def main():
    if len(sys.argv)==3 and sys.argv[1]=="_worker":core.worker(sys.argv[2]);return
    p=argparse.ArgumentParser();p.add_argument("command",choices=COMMANDS);p.add_argument("--json",default="{}",help="JSON keyword arguments");a=p.parse_args()
    try:r=COMMANDS[a.command](**json.loads(a.json))
    except Exception as e:r=core.blocked("input_or_environment",str(e))
    print(json.dumps(r,indent=2,ensure_ascii=False,allow_nan=False));sys.exit(2 if r["status"]=="BLOCKED" else 0)
if __name__=="__main__":main()
