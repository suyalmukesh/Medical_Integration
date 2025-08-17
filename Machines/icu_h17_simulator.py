#!/usr/bin/env python3
"""
ICU HL7 v2.x Vital Signs Simulator
----------------------------------
Generates HL7 ORU^R01 messages with realistic ICU vital signs and either:
  - prints them to stdout, or
  - sends them to a remote MLLP (Minimal Lower Layer Protocol) listener.

Usage examples:
  # Print 5 messages to stdout, one per second
  python icu_hl7_simulator.py --stdout --count 5 --interval 1

  # Send messages to an MLLP server (e.g., a LIS/engine) at 127.0.0.1:2575
  python icu_hl7_simulator.py --mllp-host 127.0.0.1 --mllp-port 2575 --count 10

  # Infinite stream every 2 seconds
  python icu_hl7_simulator.py --stdout --interval 2

Notes:
- Generates HL7 v2.5 ORU^R01 messages with OBX segments using common LOINC codes.
- No external libraries required.
"""

import argparse
import random
import socket
import sys
import time
from datetime import datetime, timezone
import uuid

FIELD_SEP = "|"
COMP_SEP = "^"
REP_SEP = "~"
ESCAPE = "\\"
SUBCOMP_SEP = "&"

# MLLP framing characters
SB = b"\x0b"       # <VT>  vertical tab, start block
EB = b"\x1c"       # <FS>  file separator, end block
CR = b"\x0d"       # <CR>  carriage return

def ts(dt: datetime | None = None) -> str:
    """HL7 timestamp in YYYYMMDDHHMMSS (ZZZ optional)."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt.strftime("%Y%m%d%H%M%S")

def comp(*parts) -> str:
    return COMP_SEP.join("" if p is None else str(p) for p in parts)

def seg(name: str, *fields) -> str:
    return name + FIELD_SEP + FIELD_SEP.join("" if f is None else str(f) for f in fields) + "\r"

class VitalModel:
    """Random-walk model to generate plausible ICU vitals."""
    def __init__(self, seed=None):
        rnd = random.Random(seed)
        self.hr  = rnd.uniform(70, 95)      # bpm
        self.rr  = rnd.uniform(12, 18)      # breaths/min
        self.spo2= rnd.uniform(95, 99)      # %
        self.temp= rnd.uniform(36.5, 37.3)  # degC
        self.sys = rnd.uniform(110, 130)    # mmHg
        self.dia = rnd.uniform(70, 85)      # mmHg

    def step(self, rnd=None):
        rnd = rnd or random
        def rw(v, lo, hi, step=0.5):
            v += rnd.uniform(-step, step)
            return max(lo, min(hi, v))

        self.hr   = rw(self.hr, 45, 150, 2.0)
        self.rr   = rw(self.rr, 8, 28, 0.6)
        self.spo2 = rw(self.spo2, 80, 100, 0.4)
        self.temp = rw(self.temp, 35.0, 40.0, 0.08)
        self.sys  = rw(self.sys, 80, 200, 2.5)
        self.dia  = rw(self.dia, 40, 120, 2.0)

    @property
    def map(self):
        return self.dia + (self.sys - self.dia) / 3.0

    def snapshot(self) -> dict:
        return {
            "HR": round(self.hr),
            "RR": round(self.rr),
            "SpO2": round(self.spo2, 1),
            "Temp": round(self.temp, 1),
            "Sys": round(self.sys),
            "Dia": round(self.dia),
            "MAP": round(self.map),
        }

class HL7Builder:
    """Builds an ORU^R01 message with vitals as OBX segments (HL7 v2.5)."""

    def __init__(self, sending_app="ICU_SIM", sending_fac="ICU", receiving_app="LIS", receiving_fac="HOSP",
                 version="2.5"):
        self.sending_app = sending_app
        self.sending_fac = sending_fac
        self.receiving_app = receiving_app
        self.receiving_fac = receiving_fac
        self.version = version
        self.ctrl_id = 1

    def next_ctrl_id(self):
        cid = f"MSG{int(time.time())}-{self.ctrl_id}"
        self.ctrl_id += 1
        return cid

    def build(self, patient_id="123456", patient_name="DOE^JOHN", device_id="MONITOR^ICU-01", vitals: dict | None = None,
              observation_dt: datetime | None = None) -> str:
        if vitals is None:
            raise ValueError("vitals dict required")
        if observation_dt is None:
            observation_dt = datetime.now(timezone.utc)

        message_time = ts(observation_dt)

        # MSH
        msh = seg("MSH",
                  "^~\\&",
                  self.sending_app,
                  self.sending_fac,
                  self.receiving_app,
                  self.receiving_fac,
                  message_time,
                  "",                   # Security
                  "ORU^R01^ORU_R01",    # Message Type
                  self.next_ctrl_id(),  # Message Control ID
                  "P",                  # Processing ID
                  self.version          # Version
                  )

        # PID
        pid = seg("PID",
                  "1",                 # Set ID
                  "",                  # Patient ID (External)
                  comp(patient_id, "", "", "HOSP^MR"),  # Patient Identifier List (Cx)
                  "",                  # Alternate ID
                  patient_name,        # Patient Name (XPN)
                  "", "", "", "", "",  # Mother's Maiden, etc.
                  "",                  # Phone
                  "", "", "",          # Address, County, Phone
                  "M"                  # Sex (optional)
                  )

        # OBR
        obr = seg("OBR",
                  "1",                  # Set ID
                  comp(str(uuid.uuid4()), "ICU_SIM"),   # Placer Order Number
                  comp(device_id, "DEVICE"),            # Filler Order Number
                  comp("VITALS", "Vital Signs Panel", "L", "76499-3", "Vital signs", "LN"), # Universal Service ID
                  "", "", "", "", "", "", "", "", "",   # Timing/Quantity etc.
                  message_time,        # Observation Date/Time
                  "", "", "", "", "",
                  "F"                  # Result status: F=Final
                  )

        # OBX segments for each vital
        obx_segments = []
        set_id = 1

        # (identifier, text, system, units, value, ref_range)
        metrics = [
            (("8867-4","Heart rate","LN"), ("/min","{bpm}"), vitals.get("HR")),
            (("9279-1","Respiratory rate","LN"), ("/min","{brpm}"), vitals.get("RR")),
            (("59408-5","Oxygen saturation in Arterial blood by Pulse oximetry","LN"), ("%","{pct}"), vitals.get("SpO2")),
            (("8310-5","Body temperature","LN"), ("Cel","{degC}"), vitals.get("Temp")),
            (("8480-6","Systolic blood pressure","LN"), ("mm[Hg]","{mmHg}"), vitals.get("Sys")),
            (("8462-4","Diastolic blood pressure","LN"), ("mm[Hg]","{mmHg}"), vitals.get("Dia")),
            (("8478-0","Mean blood pressure","LN"), ("mm[Hg]","{mmHg}"), vitals.get("MAP")),
        ]

        for (id_code, id_text, id_sys), (unit_code, _unit_text), value in metrics:
            if value is None:
                continue
            obs_id = comp(id_code, id_text, id_sys)
            units = comp(unit_code, "", "UCUM")
            obx = seg("OBX",
                      str(set_id),       # OBX-1 Set ID
                      "NM",              # OBX-2 Value Type (Numeric)
                      obs_id,            # OBX-3 Identifier (CE)
                      "",                # OBX-4 Sub-ID
                      str(value),        # OBX-5 Observation Value
                      units,             # OBX-6 Units
                      "",                # OBX-7 Reference Range
                      "",                # OBX-8 Abnormal Flags
                      "",                # OBX-9 Probability
                      "",                # OBX-10 Nature of Abnormal Test
                      "F",               # OBX-11 Observation Result Status
                      "",                # OBX-12 Effective Date of Reference Range
                      message_time,      # OBX-14 Date/Time of the Observation
                      "", "", "", "", "", "", "", "", "", "", "", ""
                      )
            obx_segments.append(obx)
            set_id += 1

        return msh + pid + obr + "".join(obx_segments)

class MLLPClient:
    """Minimal MLLP sender. Opens a TCP connection per message unless keepalive=True."""
    def __init__(self, host: str, port: int, timeout: float = 10.0, keepalive: bool = True):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.keepalive = keepalive
        self.sock: socket.socket | None = None

    def connect(self):
        if self.sock is None:
            s = socket.create_connection((self.host, self.port), timeout=self.timeout)
            s.settimeout(self.timeout)
            self.sock = s

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            finally:
                self.sock = None

    def send(self, hl7_message: str) -> str | None:
        data = SB + hl7_message.encode("utf-8") + EB + CR
        try:
            self.connect()
            assert self.sock is not None
            self.sock.sendall(data)

            # Attempt to receive ACK (optional)
            try:
                ack = self.sock.recv(4096)
                if ack:
                    return ack.decode("utf-8", errors="ignore")
            except socket.timeout:
                return None
        finally:
            if not self.keepalive:
                self.close()
        return None

def main():
    parser = argparse.ArgumentParser(description="ICU HL7 v2.x Vital Signs Simulator (ORU^R01)")
    parser.add_argument("--mllp-host", type=str, help="MLLP host to send messages to")
    parser.add_argument("--mllp-port", type=int, help="MLLP port to send messages to")
    parser.add_argument("--stdout", action="store_true", help="Print messages to stdout")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between messages")
    parser.add_argument("--count", type=int, default=0, help="Number of messages to send (0 = infinite)")
    parser.add_argument("--patient-id", type=str, default="123456")
    parser.add_argument("--patient-name", type=str, default="DOE^JOHN", help="HL7 XPN format: LAST^FIRST")
    parser.add_argument("--device-id", type=str, default="MONITOR^ICU-01")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    args = parser.parse_args()

    if not args.stdout and not (args.mllp_host and args.mllp_port):
        parser.error("Choose an output: --stdout or --mllp-host/--mllp-port")

    rnd = random.Random(args.seed)
    vitals = VitalModel(seed=args.seed)
    builder = HL7Builder()

    mllp_client = None
    if args.mllp_host and args.mllp_port:
        mllp_client = MLLPClient(args.mllp_host, args.mllp_port)

    sent = 0
    try:
        while True:
            vitals.step(rnd)
            snapshot = vitals.snapshot()
            msg = builder.build(patient_id=args.patient_id,
                                patient_name=args.patient_name,
                                device_id=args.device_id,
                                vitals=snapshot)

            if args.stdout:
                sys.stdout.write(msg + "\n")
                sys.stdout.flush()

            if mllp_client:
                ack = mllp_client.send(msg)
                if ack and args.stdout:
                    sys.stdout.write(f"MLLP ACK received:\n{ack}\n")
                    sys.stdout.flush()

            sent += 1
            if args.count and sent >= args.count:
                break
            time.sleep(max(0.05, args.interval))
    except KeyboardInterrupt:
        pass
    finally:
        if mllp_client:
            mllp_client.close()

if __name__ == "__main__":
    main()
