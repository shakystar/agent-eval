#!/usr/bin/env python3
"""Record app-server turn starts at the downstream stdio boundary."""
import fcntl
import hashlib
import json
import os
import re
import select
import signal
import subprocess
import sys

LIMIT = 16 * 1024 * 1024
FIELDS = ("ordinal", "assignment", "run", "attempt", "thread", "rpc_id", "request_sha256")
stopping = False


class Fault(Exception):
    pass


def stop(_signum, _frame):
    global stopping
    stopping = True


def require(condition):
    if not condition:
        raise Fault()


def unique(pairs):
    obj = {}
    for key, value in pairs:
        require(key not in obj)
        obj[key] = value
    return obj


def reject_constant(_value):
    raise Fault()


def decode(row):
    require(row.endswith(b"\n") and len(row) <= LIMIT)
    value = json.loads(row.decode("utf-8"), object_pairs_hook=unique,
                       parse_constant=reject_constant)
    require(isinstance(value, dict))
    return value


def label(value):
    return isinstance(value, str) and bool(value) and not any(
        0xD800 <= ord(char) <= 0xDFFF for char in value)


def write_row(ledger, row):
    data = memoryview((json.dumps(row, separators=(",", ":")) + "\n").encode("ascii"))
    require(len(data) <= LIMIT)
    while data:
        count = os.write(ledger.fileno(), data)
        require(count > 0)
        data = data[count:]
    os.fsync(ledger.fileno())


def recover(ledger, assignment):
    ledger.seek(0)
    starts, acked = [], set()
    while True:
        raw = ledger.readline(LIMIT + 1)
        if not raw:
            return len(starts)
        row = decode(raw)
        kind = row.get("kind")
        require(kind in ("start", "ack"))
        require(set(row) == set(FIELDS) | ({"kind", "turn"} if kind == "ack" else {"kind"}))
        number = row["ordinal"]
        require(type(number) is int and number > 0 and row["assignment"] == assignment)
        require(all(label(row[key]) for key in ("run", "attempt", "thread")))
        require(row["rpc_id"] == "" or label(row["rpc_id"]))
        digest = row["request_sha256"]
        require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest))
        link = tuple(row[key] for key in FIELDS)
        if kind == "start":
            require(number == len(starts) + 1)
            starts.append(link)
        else:
            require(number <= len(starts) and number not in acked)
            require(link == starts[number - 1] and label(row["turn"]))
            acked.add(number)


def route(raw, upstream, pending, ledger, identity, ordinal):
    msg = decode(raw)
    require("jsonrpc" not in msg or msg["jsonrpc"] == "2.0")
    has_id = "id" in msg
    rpc_id = msg.get("id")
    require(rpc_id is None or type(rpc_id) in (str, int))
    require(not isinstance(rpc_id, str) or rpc_id == "" or label(rpc_id))
    if "method" in msg:
        require(label(msg["method"]) and "result" not in msg and "error" not in msg)
        if upstream:
            start = None
            if msg["method"] == "turn/start":
                params = msg.get("params")
                require(has_id and rpc_id is not None and isinstance(params, dict))
                require(label(params.get("threadId")))
                ordinal += 1
                start = dict(identity, ordinal=ordinal, thread=params["threadId"],
                             rpc_id=str(rpc_id), request_sha256=hashlib.sha256(raw).hexdigest())
                write_row(ledger, dict(start, kind="start"))
            if has_id:
                require(rpc_id not in pending)
                pending[rpc_id] = start
    else:
        require(has_id and (("result" in msg) != ("error" in msg)))
        if "error" in msg:
            error = msg["error"]
            require(isinstance(error, dict) and type(error.get("code")) is int and
                    isinstance(error.get("message"), str))
        if not upstream:
            start = pending.pop(rpc_id, None)
            if start is not None and "result" in msg:
                result = msg["result"]
                turn = result.get("turn") if isinstance(result, dict) else None
                require(isinstance(turn, dict) and label(turn.get("id")))
                write_row(ledger, dict(start, kind="ack", turn=turn["id"]))
    return ordinal


def relay(proc, ledger, identity, ordinal):
    readers = (0, proc.stdout.fileno())
    writers = (proc.stdin.fileno(), 1)
    buffers = [bytearray(), bytearray()]
    queues = [bytearray(), bytearray()]
    opened = [True, True]
    pending = {}
    for fd in (*readers, *writers):
        os.set_blocking(fd, False)
    while opened[1] or queues[1]:
        require(not stopping)
        if not opened[0] and not queues[0] and not proc.stdin.closed:
            proc.stdin.close()
        poll = select.poll()
        for i in range(2):
            if opened[1] and opened[i] and len(queues[i]) < LIMIT:
                poll.register(readers[i], select.POLLIN)
            if queues[i] and (i == 1 or opened[1]):
                poll.register(writers[i], select.POLLOUT)
        ready = dict(poll.poll(100))
        # Process client EOF before backend EOF if both were reported.
        for i in range(2):
            if readers[i] not in ready:
                continue
            try:
                data = os.read(readers[i], 65536)
            except BlockingIOError:
                continue
            if not data:
                require(not buffers[i])
                opened[i] = False
                continue
            buffers[i].extend(data)
            lines = buffers[i].split(b"\n")
            buffers[i] = lines.pop()
            require(len(buffers[i]) < LIMIT)
            for line in lines:
                raw = bytes(line) + b"\n"
                ordinal = route(raw, i == 0, pending, ledger, identity, ordinal)
                queues[i].extend(raw)
        for i in range(2):
            if writers[i] in ready and (i == 1 or opened[1]):
                try:
                    count = os.write(writers[i], queues[i][:65536])
                except BlockingIOError:
                    continue
                require(count > 0)
                del queues[i][:count]
        if opened[1] and len(queues[1]) < LIMIT and readers[1] not in ready:
            # An exited backend must not leave us waiting on an inherited pipe.
            if proc.poll() is not None:
                check = select.poll()
                check.register(readers[1], select.POLLIN)
                require(check.poll(0))
    require(not opened[0] and not queues[0] and not stopping)
    if not proc.stdin.closed:
        proc.stdin.close()
    require(proc.wait(timeout=5) == 0 and not stopping)


def main():
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, stop)
    path, backend = (os.environ[key] for key in ("M3_LEDGER", "M3_BACKEND"))
    require(os.path.isabs(path) and os.path.isabs(backend))
    identity = {name: os.environ["M3_" + name.upper()]
                for name in ("assignment", "run", "attempt")}
    require(all(label(value) for value in identity.values()))
    flags = os.O_RDWR | os.O_CREAT
    lock_fd = os.open(path + ".lock", flags, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd = os.open(path, flags | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a+b") as ledger:
            ordinal = recover(ledger, identity["assignment"])
            proc = None
            blocking = {fd: os.get_blocking(fd) for fd in (0, 1)}
            try:
                directory = os.open(os.path.dirname(path), os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
                require(not stopping)
                proc = subprocess.Popen([backend, *sys.argv[1:]], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, bufsize=0)
                relay(proc, ledger, identity, ordinal)
            except Exception:
                # A fault after an ack must not look like a clean ledger to the gate.
                write_row(ledger, {"kind": "invalid"})
                raise
            finally:
                if proc is not None:
                    with proc:
                        if proc.poll() is None:
                            try:
                                proc.kill()
                            except ProcessLookupError:
                                pass
                for fd, mode in blocking.items():
                    os.set_blocking(fd, mode)
    finally:
        os.close(lock_fd)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit("m3_recorder: failed closed")
