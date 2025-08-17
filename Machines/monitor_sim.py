#!/usr/bin/env python3
import argparse, random, sys, time
from hl7_common import HL7Builder, MLLPClient, ts

class MonitorModel:
    def __init__(self, seed=None):
        self.rnd = random.Random(seed)
        self.hr  = self.rnd.uniform(70, 95)
        self.spo2= self.rnd.uniform(95, 99)
        self.temp= self.rnd.uniform(36.5, 37.3)
        self.sys = self.rnd.uniform(110, 130)
        self.dia = self.rnd.uniform(70, 85)

    def step(self):
        r = self.rnd
        def rw(v, lo, hi, step):
            return max(lo, min(hi, v + r.uniform(-step, step)))
        self.hr   = rw(self.hr,   45, 150, 2.0)
        self.spo2 = rw(self.spo2, 80, 100, 0.4)
        self.temp = rw(self.temp, 35.0, 40.0, 0.08)
        self.sys  = rw(self.sys,  80, 200, 2.5)
        self.dia  = rw(self.dia,  40, 120, 2.0)

    @property
    def map(self):
        return self.dia + (self.sys - self.dia)/3.0

    def snapshot(self):
        return {"HR": round(self.hr), "SpO2": round(self.spo2,1), "Temp": round(self.temp,1),
                "Sys": round(self.sys), "Dia": round(self.dia), "MAP": round(self.map)}

def main():
    p = argparse.ArgumentParser(description="Bedside Monitor Simulator")
    p.add_argument("--mllp-host"); p.add_argument("--mllp-port", type=int)
    p.add_argument("--stdout", action="store_true")
    p.add_argument("--interval", type=float, default=1.0)
    p.add_argument("--count", type=int, default=0)
    p.add_argument("--patient-id", default="123456")
    p.add_argument("--patient-name", default="DOE^JOHN")
    p.add_argument("--device-id", default="MONITOR^ICU-01")
    p.add_argument("--seed", type=int, default=None)
    args = p.parse_args()

    if not args.stdout and not (args.mllp_host and args.mllp_port):
        p.error("Choose an output: --stdout or --mllp-host/--mllp-port")

    model = MonitorModel(args.seed)
    b = HL7Builder(sending_app="MONITOR_SIM")
    client = MLLPClient(args.mllp_host, args.mllp_port) if args.mllp_host and args.mllp_port else None

    metrics = [
        ("8867-4","Heart rate","LN","/min","HR"),
        ("59408-5","Oxygen saturation in Arterial blood by Pulse oximetry","LN","%","SpO2"),
        ("8310-5","Body temperature","LN","Cel","Temp"),
        ("8480-6","Systolic blood pressure","LN","mm[Hg]","Sys"),
        ("8462-4","Diastolic blood pressure","LN","mm[Hg]","Dia"),
        ("8478-0","Mean blood pressure","LN","mm[Hg]","MAP"),
    ]

    sent=0
    try:
        while True:
            model.step()
            snap = model.snapshot()
            now = ts()
            obxs = []
            for i,(code,text,cs,unit,key) in enumerate(metrics, start=1):
                obxs.append(b.obx_numeric(i, code, text, cs, snap[key], unit, observation_time=now))
            msg = b.build_message(args.patient_id, args.patient_name, args.device_id, obxs, now)
            if args.stdout: sys.stdout.write(msg + "\n"); sys.stdout.flush()
            if client: client.send(msg)
            sent+=1
            if args.count and sent>=args.count: break
            time.sleep(max(0.05, args.interval))
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
