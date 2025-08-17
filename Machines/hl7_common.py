#!/usr/bin/env python3
import socket, time
from datetime import datetime, timezone

FIELD_SEP = "|"
COMP_SEP = "^"
SB = b"\x0b"
EB = b"\x1c"
CR = b"\x0d"

def ts(dt: datetime | None = None) -> str:
    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt.strftime("%Y%m%d%H%M%S")

def comp(*parts) -> str:
    return COMP_SEP.join("" if p is None else str(p) for p in parts)

def seg(name: str, *fields) -> str:
    return name + FIELD_SEP + FIELD_SEP.join("" if f is None else str(f) for f in fields) + "\r"

class HL7Builder:
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

    def msh(self, message_time: str):
        return seg("MSH",
                   "^~\\&",
                   self.sending_app,
                   self.sending_fac,
                   self.receiving_app,
                   self.receiving_fac,
                   message_time,
                   "",
                   "ORU^R01^ORU_R01",
                   self.next_ctrl_id(),
                   "P",
                   self.version)

    def pid(self, patient_id="123456", patient_name="DOE^JOHN", sex="U"):
        return seg("PID",
                   "1",
                   "",
                   comp(patient_id, "", "", "HOSP^MR"),
                   "",
                   patient_name,
                   "", "", "", "", "", "", "", "", "",
                   sex)

    def obr(self, message_time: str, device_id: str, panel_code=("VITALS","Vital Signs Panel","L","76499-3","Vital signs","LN")):
        from uuid import uuid4
        return seg("OBR",
                   "1",
                   comp(str(uuid4()), "ICU_SIM"),
                   comp(device_id, "DEVICE"),
                   comp(*panel_code),
                   "", "", "", "", "", "", "", "", "",
                   message_time,
                   "", "", "", "", "",
                   "F")

    def obx_numeric(self, set_id: int, loinc_code: str, text: str, coding_system: str, value, units_code: str, units_text: str = "", units_sys: str = "UCUM",
                    observation_time: str | None = None, sub_id: str = ""):
        obs_id = comp(loinc_code, text, coding_system)
        units  = comp(units_code, units_text, units_sys)
        return seg("OBX",
                   str(set_id),
                   "NM",
                   obs_id,
                   sub_id,
                   str(value),
                   units,
                   "",
                   "",
                   "",
                   "",
                   "F",
                   "",
                   (observation_time or ts()))

    def build_message(self, patient_id, patient_name, device_id, obx_segments, message_time=None):
        message_time = message_time or ts()
        return self.msh(message_time) + self.pid(patient_id, patient_name) + self.obr(message_time, device_id) + "".join(obx_segments)

class MLLPClient:
    def __init__(self, host: str, port: int, timeout: float = 10.0, keepalive: bool = True):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.keepalive = keepalive
        self.sock = None

    def connect(self):
        if self.sock is None:
            s = socket.create_connection((self.host, self.port), timeout=self.timeout)
            s.settimeout(self.timeout)
            self.sock = s

    def close(self):
        if self.sock:
            try: self.sock.close()
            finally: self.sock = None

    def send(self, hl7_message: str) -> str | None:
        data = SB + hl7_message.encode("utf-8") + EB + CR
        try:
            self.connect()
            self.sock.sendall(data)
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
