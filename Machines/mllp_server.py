import socket

HOST = "127.0.0.1"
PORT = 2575

START_BLOCK = b"\x0b"
END_BLOCK = b"\x1c"
CARRIAGE_RETURN = b"\x0d"

def build_ack(msg_control_id="1"):
    return (
        START_BLOCK +
        f"MSH|^~\\&|MLLP_SERVER|TEST_FAC|||20250817153000||ACK^A01|{msg_control_id}|P|2.5\r"
        f"MSA|AA|{msg_control_id}\r".encode() +
        END_BLOCK + CARRIAGE_RETURN
    )

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind((HOST, PORT))
    s.listen(1)
    print(f"MLLP server listening on {HOST}:{PORT}")
    conn, addr = s.accept()
    with conn:
        print(f"Connected by {addr}")
        buffer = b""
        while True:
            data = conn.recv(1024)
            if not data:
                break
            buffer += data
            while START_BLOCK in buffer and END_BLOCK in buffer:
                start = buffer.index(START_BLOCK) + 1
                end = buffer.index(END_BLOCK)
                hl7_msg = buffer[start:end].decode()
                buffer = buffer[end + 2 :]  # skip END_BLOCK + CR
                print("\n--- HL7 message received ---")
                print(hl7_msg)
                print("---------------------------\n")
                conn.sendall(build_ack("1"))
