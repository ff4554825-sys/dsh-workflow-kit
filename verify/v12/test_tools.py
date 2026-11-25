#!/usr/bin/env python3
"""verify/v12/test_tools.py — 双口径统计与 accept 写入的必红/必过样例"""
import json, os, pathlib, shutil, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
PY = sys.executable


def sandbox():
    """临时 DSH_HOME：装上 bin/* 与矩阵，模拟真实安装副本。"""
    home = pathlib.Path(tempfile.mkdtemp())
    (home / "bin").mkdir()
    for f in (ROOT / "bin").iterdir():
        if f.is_file():
            shutil.copy2(f, home / "bin" / f.name)
    (home / "docs").mkdir()
    shutil.copy2(ROOT / "docs" / "v12-field-matrix.json", home / "docs" / "v12-field-matrix.json")
    return home


def run(home, *args, cmd="log-write"):
    env = dict(os.environ, DSH_HOME=str(home))
    path = home / "bin" / cmd
    head = path.read_text(encoding="utf-8", errors="replace").split("\n")[0]
    argv = ["sh", str(path)] if head.startswith("#!/bin/sh") else [PY, str(path)]
    o = subprocess.run(argv + list(args), capture_output=True, text=True, env=env)
    return o.returncode, o.stdout + o.stderr


def seed(home, rows):
    p = home / "task-log.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return p


def test_stats_splits_two_sets_and_never_sums():
    home = sandbox()
    seed(home, [{"seq": 1, "ts": "2026-11-25T09:00:00+08:00", "task": "老", "status": "done"}])
    run(home, "--cut")
    run(home, "--lite", "--task", "新", "--evidence", "e", "--gate", "PASS")
    code, out = run(home, cmd="task-stats")
    assert code == 0, out
    assert "[legacy]" in out and "[v1.2]" in out and "不相加" in out, out
    assert "总任务" not in out, out


def test_accept_pass_folds_to_accepted():
    home = sandbox()
    seed(home, [{"seq": 1, "ts": "2026-11-25T09:00:00+08:00", "task": "老", "status": "done"}])
    run(home, "--cut")
    run(home, "--lite", "--task", "新", "--evidence", "e", "--gate", "PASS")
    task_seq = 3
    code, out = run(home, "--accept", "--target-seq", str(task_seq), "--verdict", "PASS",
                    "--reviewer", "user", "--pointer", "review://t")
    assert code == 0, out
    code, out = run(home, cmd="task-stats")
    assert "accepted 1" in out and "open 0" in out, out


def test_accept_by_self_is_refused():
    home = sandbox()
    seed(home, [{"seq": 1, "ts": "2026-11-25T09:00:00+08:00", "task": "老", "status": "done"}])
    run(home, "--cut")
    run(home, "--lite", "--task", "新", "--evidence", "e", "--gate", "PASS")
    me = json.loads((home / "task-log.jsonl").read_text(encoding="utf-8").split("\n")[2])["executor_id"]
    code, out = run(home, "--accept", "--target-seq", "3", "--verdict", "PASS",
                    "--reviewer", me, "--pointer", "x")
    assert code == 1 and "自己审自己" in out, out
    assert len((home / "task-log.jsonl").read_text(encoding="utf-8").strip().split("\n")) == 4
