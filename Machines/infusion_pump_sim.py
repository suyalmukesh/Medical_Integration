#!/usr/bin/env python3
import argparse, random, sys, time
from hl7_common import HL7Builder, MLLPClient, ts, seg, comp

DRUGS = [
    ("NORAD", "Norepinephrine"),
    ("PROP", "Propofol"),
    ("INS", "Insulin"),
    ("DEX", "Dexmedetomidine"),
    ("DOB", "Dobutamine"),
]

class PumpModel:
    def __init__(self, seed=None):
        self.rnd = random.Random(seed)
        self.drug_code, self.drug_name = self.rnd.choice(DRUGS)
        self.rate = self.rnd.uniform(2, 20)     # mL/h
        self.vol  = 0.0

    def step(self):
        r = self.rnd
        self.rate = max(0.0, min(50.0, self.rate + r.uniform(-1.5, 1.5)))
        self.vol  = max(0.0, self.vol + self.rate/60.0)

def main():
    p = argparse.ArgumentParser(description="Infusion Pump Simulator")
    p.add_argument("--mllp-host"); p.add_argument("--mllp-port", type=int)
    p.add_argument("--stdout", action="store_true")
    p.add_argument("--interval", type=float, default=60.0)
    p.add_argument("--count", type=int, default=0)
    p.add_argument("--patient-id", default="123456")
    p.add_argument("--patient-name", default="DOE^JOHN")
    p.add_argument("--device-id", default="PUMP^ICU-01")
    p.add_argument("--seed", type=int, default=None)
    args = p.parse_args()

    if not args.stdout and not (args.mllp_host and args.mllp_port):
        p.error("Choose an output: --stdout or --mllp-host/--mllp-port")

    b = HL7Builder(sending_app="PUMP_SIM")
    client = MLLPClient(args.mllp_host, args.mllp_port) if args.mllp_host and args.mllp_port else None
    model = PumpModel(args.seed)

    sent=0
    try:
        while True:
            model.step()
            now = ts()
            obxs = []
            obxs.append(b.obx_numeric(1, "PUMP_RATE", "Infusion rate", "L", round(model.rate,1), "mL/h", observation_time=now))
            obxs.append(b.obx_numeric(2, "PUMP_VOL", "Volume infused", "L", round(model.vol,1), "mL", observation_time=now))
            obxs.append(seg("OBX","3","TX",comp("PUMP_DRUG","Drug name","L"),"",model.drug_name,"","","","","","F","",now))

            msg = b.build_message(args.patient_id, args.patient_name, args.device_id, obxs, now)
            if args.stdout: sys.stdout.write(msg + "\n"); sys.stdout.flush()
            if client: client.send(msg)
            sent+=1
            if args.count and sent>=args.count: break
            time.sleep(max(0.5, args.interval))
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
