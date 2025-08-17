#!/usr/bin/env python3
import argparse, subprocess, sys, time, os

SCRIPTS = [
    ("monitor_sim.py",     ["--interval","1.0","--device-id","MONITOR^BED-01"]),
    ("ventilator_sim.py",  ["--interval","2.0","--device-id","VENT^BED-01"]),
    ("capnograph_sim.py",  ["--interval","3.0","--device-id","CAPNO^BED-01"]),
    ("infusion_pump_sim.py",["--interval","60.0","--device-id","PUMP^BED-01"]),
]

def main():
    ap = argparse.ArgumentParser(description="ICU Simulators Orchestrator")
    ap.add_argument("--mllp-host", required=False)
    ap.add_argument("--mllp-port", required=False, type=int)
    ap.add_argument("--patient-id", default="123456")
    ap.add_argument("--name", default="DOE^JOHN")
    ap.add_argument("--stdout", action="store_true")
    args = ap.parse_args()

    if not args.stdout and not (args.mllp_host and args.mllp_port):
        ap.error("Choose an output: --stdout or --mllp-host/--mllp-port")

    procs = []
    try:
        for script, extra in SCRIPTS:
            cmd = [sys.executable, script]
            if args.stdout:
                cmd.append("--stdout")
            if args.mllp_host and args.mllp_port:
                cmd += ["--mllp-host", args.mllp_host, "--mllp-port", str(args.mllp_port)]
            cmd += ["--patient-id", args.patient_id, "--patient-name", args.name]
            cmd += extra
            print("Starting:", " ".join(cmd), flush=True)
            procs.append(subprocess.Popen(cmd, cwd=os.path.dirname(__file__)))
        print("All simulators running. Ctrl+C to stop.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping...")
        for p in procs:
            try: p.terminate()
            except Exception: pass
        for p in procs:
            try: p.wait(timeout=5)
            except Exception: pass

if __name__ == "__main__":
    main()
