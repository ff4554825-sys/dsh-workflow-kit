"""log-check 判死测试：7 个坏样例必须报出指定编号，1 个好样例必须全绿。
裁决者 = pytest，不是执行者自评。"""
import json, subprocess, pathlib, tempfile, pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
BIN = str(ROOT / "bin" / "log-check")

def rec(**kw):
    base = {
        "seq": 1, "corrects": None, "ts": "2026-11-25T10:00:00+08:00",
        "task": "t", "tier": "full", "tier_rule": "rule:T3", "degraded": False,
        "evidence": "e", "kill_action": "k", "arbiter": "pytest", "review": "r",
        "improve": {"window": 10, "finding": "no-new-pattern", "action": None,
                    "due": None, "restore": None},
        "carryover": [],
        "gate": {"F1": "pass",
                 "F2": {"result": "pass", "coverage": "tests/test_x.py::test_y"},
                 "F3_task": "m=1",
                 "F3_proc": {"rounds": 3, "red": 0, "source": "auto"}},
        "red_attempts": [], "status": "done",
        "acceptance": [{"criterion": "c", "verdict": "PASS", "pointer": "tests/test_x.py::test_y"}],
    }
    base.update(kw)
    return base

def run(rows):
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
        f.write("\n".join(json.dumps(r, ensure_ascii=False) for r in rows))
        path = f.name
    return subprocess.run([BIN, "--file", path], capture_output=True, text=True)

BAD = {
    "S2": [rec(seq=1), rec(seq=3)],                                     # 跳号
    "S3": [rec(seq=1, ts="2026-11-25T10:05:00+08:00"),
           rec(seq=2, ts="2026-11-25T10:01:00+08:00")],                 # 时间倒退
    "S5": [rec(acceptance=[{"criterion": "c", "verdict": "PASS", "pointer": ""}])],
    "S4": [rec(corrects=99)],                                           # 指向不存在
    "S8": [rec(status="blocked", red_attempts=[{"sig": "a"}, {"sig": "a"}])],
    "S9": [rec(gate={"F1": "pass", "F2": {"coverage": "c"}, "F3_task": "m",
                     "F3_proc": {"rounds": 3, "red": 0, "source": "manual"}})],
    "S10": [rec(degraded=True)],                                        # 无 improve.restore
}

@pytest.mark.parametrize("code", list(BAD))
def test_bad_reports_expected_code(code):
    r = run(BAD[code])
    assert r.returncode == 1, "%s 应失败但通过:\n%s" % (code, r.stdout)
    assert code in r.stdout, "%s 期望报 %s，实际:\n%s" % (code, code, r.stdout)

def test_good_passes():
    r = run([rec(seq=1), rec(seq=2, corrects=1)])
    assert r.returncode == 0, "合法样例被误判:\n%s" % r.stdout
    assert "SCHEMA: OK" in r.stdout

def test_legacy_exempt():
    """legacy=true 只受 S2/S3 约束，不该因缺字段报红。"""
    r = run([{"seq": 1, "ts": "2026-11-25T10:00:00+08:00", "legacy": True}])
    assert r.returncode == 0, r.stdout

def test_legacy_still_checks_seq_gap():
    r = run([{"seq": 1, "ts": "2026-11-25T10:00:00+08:00", "legacy": True},
             {"seq": 3, "ts": "2026-11-25T10:01:00+08:00", "legacy": True}])
    assert r.returncode == 1 and "S2" in r.stdout, r.stdout
