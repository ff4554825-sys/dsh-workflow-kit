#!/usr/bin/env python3
"""verify/v12/test_writer.py — log-write 脚手架的必红样例"""
import json, os, subprocess, sys, tempfile, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
BIN = ROOT / "bin" / "log-write"
PY = sys.executable


def tmpfile(rows=()):
    d = tempfile.mkdtemp()
    p = pathlib.Path(d) / "log.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return p


def run(p, *args):
    env = dict(os.environ, DSH_HOME=str(pathlib.Path.home() / ".dsh"))
    o = subprocess.run([PY, str(BIN), "--file", str(p), *args],
                       capture_output=True, text=True, env=env)
    return o.returncode, o.stdout + o.stderr


def read(p):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").split("\n") if l.strip()]


def test_lite_without_evidence_refuses():
    p = tmpfile()
    code, out = run(p, "--lite", "--task", "t", "--status", "done")
    assert code == 2 and "需要 --task 与 --evidence" in out, out
    assert read(p) == []


def test_new_row_into_uncut_file_is_refused():
    old = {"seq": 1, "ts": "2026-11-25T09:00:00+08:00", "task": "老", "status": "done"}
    p = tmpfile([old])
    code, out = run(p, "--lite", "--task", "t", "--evidence", "e")
    assert code == 1 and "未写入" in out, out
    assert len(read(p)) == 1, "校验失败时不许写任何行"


def test_cut_then_lite_with_gate_writes_two_rows():
    old = {"seq": 1, "ts": "2026-11-25T09:00:00+08:00", "task": "老", "status": "done"}
    p = tmpfile([old])
    code, out = run(p, "--cut")
    assert code == 0 and "freezes_seq_lte=1" in out, out
    code, out = run(p, "--lite", "--task", "t", "--evidence", "e", "--gate", "PASS")
    assert code == 0 and "gate seq=4" in out, out
    rows = read(p)
    assert [r.get("record_type") for r in rows] == [None, "schema", "task", "gate"], rows
    v12 = subprocess.run([PY, str(ROOT / "bin" / "schema-v12"), "--file", str(p)],
                         capture_output=True, text=True)
    assert v12.returncode == 0, v12.stdout + v12.stderr


def test_future_ts_is_extended_not_rejected():
    old = {"seq": 1, "ts": "2099-01-01T00:00:00+08:00", "task": "未来时间戳"}
    p = tmpfile([old])
    code, out = run(p, "--cut")
    assert code == 0, out
    rows = read(p)
    assert rows[-1]["ts"] > old["ts"], rows[-1]["ts"]
