"""Try every command's example with extreme values and list the answers that are not plain words.

    python tests/fuzz_examples.py [--workers 4] [--values 0,-5,1e6] [--only NAME,...]

Each example in docs/site/command-examples.cmd is run again with one number of its own
command line changed to each of the values (and once with the command given no arguments),
in worker processes, so a crash or a hang loses only that one case: a case that takes more
than a minute is listed as a hang, one that kills its process as a crash. What is printed at
the end is what needs fixing: bare kernel exceptions, bugs, hangs and crashes. It takes about
40 minutes on four cores for the 1530 cases; tests/test_kernel_messages.py keeps what it found.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NUM = re.compile(r"^-?\d+(\.\d+)?$")
RAW = re.compile(r"^(HUNG|CRASHED|RAISED)|\b[A-Z]\w*(Error|Exception|Failure|NotDone)\b|Standard_|StdFail|is a bug|"
                 r"object has no attribute|NoneType|not subscriptable|index out of range|unsupported operand|"
                 r"positional argument|unexpected keyword|invalid literal|could not convert|referenced before")


def split_args(s: str) -> list[str]:
    out, depth, cur, quoted = [], 0, "", False
    for ch in s:
        if ch == '"':
            quoted = not quoted
        if not quoted and ch in "([":
            depth += 1
        if not quoted and ch in ")]":
            depth -= 1
        if ch == "," and depth == 0 and not quoted:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


def cases(values: list[str], only: set[str]) -> list[dict]:
    from modeler import docsite

    out = []
    for name, ex in docsite.read_examples().items():
        if "window" in ex.flags or (only and name not in only):
            continue
        lines = ex.code.splitlines()
        own = [i for i, line in enumerate(lines)
               if re.split(r"[\s,]", line.split("!")[0].strip() + " ", maxsplit=1)[0].upper() == name]
        if not own:
            continue
        i = own[-1]
        parts = split_args(lines[i])
        for k in range(1, len(parts)):
            if NUM.match(parts[k].strip()):
                for v in values:
                    if parts[k].strip() != v:
                        changed = parts[:k] + [" " + v] + parts[k + 1:]
                        out.append({"name": name, "line": ",".join(changed).strip(),
                                    "code": "\n".join(lines[:i] + [",".join(changed)] + lines[i + 1:])})
        out.append({"name": name, "line": name, "code": "\n".join(lines[:i] + [name] + lines[i + 1:])})
    return out


def worker(path: str, lo: int, hi: int, log: str) -> None:
    import signal

    from modeler import docsite

    todo = json.load(open(path, encoding="utf-8"))  # noqa: SIM115
    with open(log, "a", encoding="utf-8") as out:
        for n in range(lo, hi):
            out.write(json.dumps({"n": n, "start": True}) + "\n")
            out.flush()
            if hasattr(signal, "SIGALRM"):
                signal.signal(signal.SIGALRM, lambda *_: os._exit(7))  # a hang: the driver notes it
                signal.alarm(60)
            try:
                res = docsite.run_example(docsite.Example(todo[n]["name"], todo[n]["code"]))
                bad = [r for r in res if not r.ok]
                msg = bad[0].message if bad else "OK"
            except BaseException as exc:  # noqa: BLE001
                msg = f"RAISED {type(exc).__name__}: {exc}"
            if hasattr(signal, "SIGALRM"):
                signal.alarm(0)
            out.write(json.dumps({"n": n, "msg": msg[:400]}) + "\n")
            out.flush()


def drive(todo: list[dict], workers: int) -> dict[int, str]:
    tmp = tempfile.mkdtemp(prefix="m3d-fuzz-")
    path = os.path.join(tmp, "cases.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(todo, f)
    env = dict(os.environ, PYTHONPATH=ROOT, QT_QPA_PLATFORM="offscreen")

    def run(lo: int, hi: int, w: int) -> None:
        log = os.path.join(tmp, f"log{w}.jsonl")
        while lo < hi:
            r = subprocess.run([sys.executable, __file__, "--worker", path, str(lo), str(hi), log], env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            rows = [json.loads(line) for line in open(log, encoding="utf-8")] if os.path.exists(log) else []  # noqa: SIM115
            done = {d["n"] for d in rows if "msg" in d}
            started = [d["n"] for d in rows if d.get("start") and lo <= d["n"] < hi]
            last = max(started) if started else lo
            if started and last not in done:
                with open(log, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"n": last, "msg": "HUNG" if r.returncode == 7 else "CRASHED"}) + "\n")
            lo = last + 1

    step = -(-len(todo) // workers)
    threads = [threading.Thread(target=run, args=(i * step, min(len(todo), (i + 1) * step), i))
               for i in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    out = {}
    for w in range(workers):
        log = os.path.join(tmp, f"log{w}.jsonl")
        if os.path.exists(log):
            for line in open(log, encoding="utf-8"):  # noqa: SIM115
                d = json.loads(line)
                if "msg" in d:
                    out[d["n"]] = d["msg"]
    return out


def main(argv: list[str]) -> int:
    if argv[:1] == ["--worker"]:
        worker(argv[1], int(argv[2]), int(argv[3]), argv[4])
        return 0
    opt = dict(zip(argv[::2], argv[1::2]))
    values = opt.get("--values", "0,-5,1e6").split(",")
    only = {n.strip().upper() for n in opt.get("--only", "").split(",") if n.strip()}
    sys.path.insert(0, ROOT)
    todo = cases(values, only)
    print(f"{len(todo)} cases")
    got = drive(todo, int(opt.get("--workers", "4")))
    # a kernel failure explained in words is fine (its raw words are kept at the end, in brackets)
    bad = [(todo[n]["line"], m) for n, m in sorted(got.items())
           if m != "OK" and RAW.search(re.sub(r"\((kernel|details): .*$", "", m))]
    for line, msg in bad:
        print(f"{line[:90]}\n    -> {msg[:240]}")
    print(f"{len(got)} run, {sum(m == 'OK' for m in got.values())} worked, {len(bad)} need fixing")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
