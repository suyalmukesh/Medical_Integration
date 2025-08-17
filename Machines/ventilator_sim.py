#!/usr/bin/env python3
import argparse, random, sys, time
from hl7_common import HL7Builder, MLLPClient, ts

class VentModel:
    def __init__(self, seed=None):
        self.rnd = random.Random(seed)
        self.rr   = self.rnd.uniform(12, 20)
        self.vte  = self.rnd.uniform(380, 520)
        self.peep = self.rnd.uniform(4, 8)
        self.fio2 = self.rnd.uniform(0.30, 0.5)

    def step(self):
        r = self.rnd
        def rw(v, lo, hi, step):
            return max(lo, min(hi, v + r.uniform(-step, step)))
        self.rr   = rw(self.rr,   8, 35, 0.8)
        self.vte  = rw(self.vte,  200, 800, 15.0)
        self.peep = rw(self.peep, 0, 20, 0.5)
        self.fio2 = rw(self.fio2, 0.21, 1.0, 0.02)

def main():
    p = argparse.ArgumentParser(description="Ventilator Simulator")
    p.add_argument("--mllp-host"); p.add_argument("--mllp-port", type=int)
    p.add_argument("--stdout", action="store_true")
    p.add_argument("--interval", type=float, default=2.0)
    p.add_argument("--count", type=int, default=0)
    p.add_argument("--patient-id", default="123456")
    p.add_argument("--patient-name", default="DOE^JOHN")
    p.add_argument("--device-id", default="VENT^ICU-01")
    p.add_argument("--seed", type=int, default=None)
    args = p.parse_args()

    if not args.stdout and not (args.mllp_host and args.mllp_port):
        p.error("Choose an output: --stdout or --mllp-host/--mllp-port")

    b = HL7Builder(sending_app="VENTILATOR_SIM")
    client = MLLPClient(args.mllp_host, args.mllp_port) if args.mllp_host and args.mllp_port else None
    model = VentModel(args.seed)

    sent=0
    try:
        while True:
            model.step()
            now = ts()
            obxs = []
            obxs.append(b.obx_numeric(1, "9279-1", "Respiratory rate", "LN", round(model.rr), "/min", observation_time=now))
            obxs.append(b.obx_numeric(2, "19868-9", "Tidal volume setting Ventilator", "LN", round(model.vte), "mL", observation_time=now))
            obxs.append(b.obx_numeric(3, "20077-4", "Positive end expiratory pressure setting Ventilator", "LN", round(model.peep,1), "cm[H2O]", observation_time=now))
            obxs.append(b.obx_numeric(4, "3150-0", "Oxygen inhaled concentration", "LN", round(model.fio2*100,1), "%", observation_time=now))

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
