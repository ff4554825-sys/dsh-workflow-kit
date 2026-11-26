#!/usr/bin/env python3
"""verify/v12/test_schema.py — schema-v12 的必红样例（负例优先）

每条测试构造一个坏样例，断言它必须被对应编号判红。
只有「能判红」算验证；全绿的正例放在最后一条做反证。
"""
import json, os, subprocess, sys, tempfile, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
BIN = ROOT / "bin" / "schema-v12"
PY = sys.executable


def base_task(**over):
    t = {
        "record_type": "task", "session_id": "s1", "seq": 1,
        "ts": "2026-11-25T10:00:00+08:00", "executor_id": "ex-1",
        "task": "t", "tier": "std", "tier_rule": "rule:T2", "status": "done",
        "evidence": "e", "arbiter": "pytest", "degraded": False,
        "acceptance": [{"id": "a1", "criterion": "c", "verdict": "PENDING", "pointer": "x.py:1"}],
        "review": "r",
    }
    t.update(over)
    return t


def run(rows):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "log.jsonl")
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    out = subprocess.run([PY, str(BIN), "--file", p], capture_output=True, text=True)
    return out.returncode, out.stdout + out.stderr


def test_full_row_with_gate_and_accept_passes():
    gate = {"record_type": "gate", "session_id": "s1", "seq": 2, "target_seq": 1,
            "ts": "2026-11-25T10:01:00+08:00", "profile": "code",
            "stages": {k: {"exit_code": 0, "duration_ms": 5, "retries": 0, "timed_out": False}
                       for k in ("S", "F1", "F2", "F3")},
            "metrics_auto": {"rounds": 1, "red": 0, "tool_calls": 1, "aborted": 0, "source": "auto"},
            "result": "PASS"}
    acc = {"record_type": "accept", "session_id": "s1", "seq": 3,
           "target": {"session_id": "s1", "seq": 1}, "ts": "2026-11-25T10:02:00+08:00",
           "reviewer": "user", "verdict": "PASS", "pointer": "x.py:1"}
    code, out = run([base_task(), gate, acc])
    assert code == 0, out


def test_model_written_verdict_is_red():
    t = base_task(acceptance=[{"id": "a1", "criterion": "c", "verdict": "PASS", "pointer": "x.py:1"}])
    code, out = run([t])
    assert code == 1 and "V6" in out and "V12" in out, out


def test_full_missing_kill_action_is_red():
    t = base_task(tier="full", tier_rule="rule:T3", improve={
        "id": "i1", "window": 10, "finding": "f", "severity": "P1",
        "action": "a", "due": "2026-12-02", "restore": "r", "closed": False},
        carryover=[])
    code, out = run([t])
    assert code == 1 and "kill_action" in out, out


def test_lite_with_review_is_red():
    t = {"record_type": "task", "session_id": "s1", "seq": 1,
         "ts": "2026-11-25T10:00:00+08:00", "executor_id": "ex-1", "task": "t",
         "tier": "lite", "status": "done", "evidence": "e", "review": "不该出现"}
    code, out = run([t])
    assert code == 1 and "禁用" in out, out


def test_blocked_needs_three_red_attempts():
    t = base_task(status="blocked", red_attempts=[
        {"attempt": 1, "sig": "s", "pointer": "p"}, {"attempt": 2, "sig": "s", "pointer": "p"}])
    code, out = run([t])
    assert code == 1 and "V5" in out, out


def test_gate_timed_out_with_zero_exit_is_red():
    gate = {"record_type": "gate", "session_id": "s1", "seq": 2, "target_seq": 1,
            "ts": "2026-11-25T10:01:00+08:00", "profile": "lite",
            "stages": {"S": {"exit_code": 0, "duration_ms": 1, "retries": 0, "timed_out": True}},
            "metrics_auto": {"rounds": 0, "red": 0, "tool_calls": 0, "aborted": 0, "source": "auto"},
            "result": "PASS"}
    code, out = run([base_task(seq=1), gate])
    assert code == 1 and "V12" in out, out


def test_accept_by_self_is_red():
    acc = {"record_type": "accept", "session_id": "s1", "seq": 2,
           "target": {"session_id": "s1", "seq": 1}, "ts": "2026-11-25T10:02:00+08:00",
           "reviewer": "ex-1", "verdict": "PASS", "pointer": "x.py:1"}
    code, out = run([base_task(), acc])
    assert code == 1 and "自己审自己" in out, out


def test_dangling_corrects_is_red():
    t = base_task(corrects={"session_id": "s1", "seq": 99})
    code, out = run([t])
    assert code == 1 and "V4" in out, out


def test_corrects_cycle_is_red():
    a = base_task(corrects={"session_id": "s1", "seq": 2})
    b = base_task(seq=2, corrects={"session_id": "s1", "seq": 1})
    code, out = run([a, b])
    assert code == 1 and "环" in out, out


def test_long_freetext_is_red():
    t = base_task(evidence="x" * 3000)
    code, out = run([t])
    assert code == 1 and "V11" in out, out


def test_seq_gap_is_red():
    code, out = run([base_task(), base_task(seq=3)])
    assert code == 1 and "V1" in out, out


def _gate(seq=2):
    return {"record_type": "gate", "session_id": "s1", "seq": seq, "target_seq": 1,
            "ts": "2026-11-25T10:01:00+08:00", "profile": "lite",
            "stages": {"S": {"exit_code": 0, "duration_ms": 1, "retries": 0, "timed_out": False}},
            "metrics_auto": {"rounds": 0, "red": 0, "tool_calls": 0, "aborted": 0, "source": "auto"},
            "result": "PASS"}


def _accept(seq, verdict):
    return {"record_type": "accept", "session_id": "s1", "seq": seq,
            "target": {"session_id": "s1", "seq": 1}, "ts": "2026-11-25T10:02:00+08:00",
            "reviewer": "user", "verdict": verdict, "pointer": "x.py:1"}


def _fold(rows):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "log.jsonl")
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    out = subprocess.run([PY, str(BIN), "--fold", "--file", p], capture_output=True, text=True)
    return out.returncode, out.stdout + out.stderr


def _lite_task():
    return {"record_type": "task", "session_id": "s1", "seq": 1,
            "ts": "2026-11-25T10:00:00+08:00", "executor_id": "ex-1", "task": "t",
            "tier": "lite", "status": "done", "evidence": "e",
            "acceptance": [{"id": "a1", "criterion": "c", "verdict": "PENDING", "pointer": "p"}]}


def test_fold_pass_verdict_becomes_accepted():
    code, out = _fold([_lite_task(), _gate(), _accept(3, "PASS")])
    assert code == 0 and "accepted" in out, out


def test_fold_unknown_stays_open():
    code, out = _fold([_lite_task(), _gate(), _accept(3, "UNKNOWN")])
    assert code == 0 and "open" in out and "accepted" not in out, out


def _row(seq, **over):
    return over if seq is None else {"session_id": "s1", "seq": seq, "ts": "2026-11-25T10:0%d:00+08:00" % (seq % 10), **over}


def test_schema_cut_freezes_old_rows():
    """§8：切割点之前的老行只查 V1，不查 V2（即使没有 record_type）。"""
    old = _row(1, task="老行", status="done", result="success")
    cut = _row(2, record_type="schema", spec="1.2", freezes_seq_lte=1)
    new = {"record_type": "task", "session_id": "s1", "seq": 3,
           "ts": "2026-11-25T10:03:00+08:00", "executor_id": "ex-1", "task": "t",
           "tier": "lite", "status": "done", "evidence": "e"}
    code, out = run([old, cut, new])
    assert code == 0, out


def test_schema_cut_wrong_freeze_is_red():
    cut = _row(2, record_type="schema", spec="1.2", freezes_seq_lte=5)
    code, out = run([_row(1, record_type="task"), cut])
    assert code == 1 and "V4" in out and "freezes_seq_lte 应为 1" in out, out


def test_two_schema_events_is_red():
    a = _row(1, record_type="schema", spec="1.2", freezes_seq_lte=0)
    b = _row(2, record_type="schema", spec="1.2", freezes_seq_lte=1)
    code, out = run([a, b])
    assert code == 1 and "只允许一条" in out, out


def test_new_row_with_legacy_key_is_red():
    t = {"record_type": "task", "session_id": "s1", "seq": 1,
         "ts": "2026-11-25T10:00:00+08:00", "executor_id": "ex-1", "task": "t",
         "tier": "lite", "status": "done", "evidence": "e", "legacy": True}
    code, out = run([t])
    assert code == 1 and "禁用该键: legacy" in out, out


def _sealed_log():
    """老行 → schema → seal，返回行列表与封存后的文件内容构造器。"""
    old = {"seq": 1, "ts": "2026-11-25T09:00:00+08:00", "task": "老", "status": "done"}
    cut = {"record_type": "schema", "session_id": "s1", "seq": 2,
           "ts": "2026-11-25T10:00:00+08:00", "spec": "1.2", "freezes_seq_lte": 1}
    return [old, cut]


def _seal_rows(rows):
    """按 log-write 的算法算出 seal 行（测试独立实现，避免自证）。"""
    import hashlib
    canon = lambda r: json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    dg = hashlib.sha256("".join(canon(r) for r in rows).encode()).hexdigest()
    ph = hashlib.sha256(canon(rows[-1]).encode()).hexdigest()
    return {"record_type": "seal", "session_id": "s1", "seq": len(rows) + 1,
            "ts": "2026-11-25T10:01:00+08:00", "through_seq": len(rows),
            "digest": dg, "prev_hash": ph}


def test_seal_valid_chain_passes():
    rows = _sealed_log()
    code, out = run(rows + [_seal_rows(rows)])
    assert code == 0, out


def test_tampering_legacy_row_breaks_digest():
    rows = _sealed_log()
    seal = _seal_rows(rows)
    rows[0]["task"] = "被我改过的历史"
    code, out = run(rows + [seal])
    assert code == 1 and "V14" in out and "摘要不匹配" in out, out


def test_tampering_sealed_row_breaks_chain():
    rows = _sealed_log()
    seal = _seal_rows(rows)
    a = {"record_type": "task", "session_id": "s1", "seq": 4,
         "ts": "2026-11-25T10:02:00+08:00", "executor_id": "ex-1", "task": "t",
         "tier": "lite", "status": "done", "evidence": "e"}
    a["prev_hash"] = _seal_rows(rows)["prev_hash"] if False else None
    import hashlib
    canon = lambda r: json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    a["prev_hash"] = hashlib.sha256(canon(seal).encode()).hexdigest()
    a["task"] = "事后被改"          # 改了内容却不改 prev_hash → 下一行断链
    b = dict(a, seq=5, ts="2026-11-25T10:03:00+08:00")
    b["prev_hash"] = hashlib.sha256(canon(dict(a, task="原内容")).encode()).hexdigest()
    code, out = run(rows + [seal, a, b])
    assert code == 1 and "V14" in out and "断链" in out, out


def test_phone_number_in_evidence_is_red():
    t = base_task(evidence="联系 13812345678 处理")
    code, out = run([t])
    assert code == 1 and "V11" in out, out


def test_hex_hash_with_digits_is_not_red():
    t = base_task(evidence="sha256 4f1e9c2a77b0d3e5f60718293a4b5c6d7e8f9012345678abcdef0123456789ab")
    code, out = run([t])
    assert code == 0, out
