# v1.2 完整性补丁（V14 / seal / prev_hash）

本文件是对 `v1.2-field-matrix.md` 的**增量**补丁，不改动任何既有行、不改 V1–V13 语义。
合并进规范时建议放到 §2.4（新 record_type）与 §7 表尾（V14）。

## 为什么需要

v1.2 解决了「谁能写 verdict」，但没解决「历史能不能被悄悄改」。
实测：直接改写已有行正文，v1.2 校验仍然全绿——整套证据链建立在可改文件上。

## 追加的两种东西

### 1. `record_type: "seal"`（每条分片一条）

| 字段 | 类型 | 写入方 | 约束 |
|---|---|---|---|
| record_type | string | Auto | 固定 `"seal"` |
| session_id / seq / ts | — | Auto | 同其它事件，受 V1 |
| through_seq | int | Auto | 必须等于该行之前的总行数 |
| digest | string | Auto | 前缀 1..through_seq 的规范形 sha256 |
| prev_hash | string | Auto | 上一行规范形的 sha256 |

规范形：`json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))`。
摘要覆盖**原样存储的字节**，因此改写任何一个前缀字段都会让它失配——不需要回写老行。

### 2. `prev_hash`（seal 之后每一行必带）

`prev_hash = sha256(上一行规范形)`。任意一行被改，下一行立刻断链。

## V14 判定

- 每个分片至多一条 seal；`through_seq` 必须等于此前行数，`digest` 必须复算一致。
- seal 之后每一行的 `prev_hash` 必须等于上一行规范形的 sha256。
- 违反 → `GATE: FAIL (V14)`。

## 使用

```sh
~/.dsh/bin/log-write --seal      # 一次性封存现有前缀
```

seal 之前的行仍然靠摘要保护；seal 之后由 `log-write` 自动写入 `prev_hash`。

## 边界（未做到的部分）

- 摘要只防「事后改写」，不防「从某一版备份整片替换」——那需要外部锚点（如把 digest 提交到 git）。
- legacy 前缀没有逐行 hash，只有整片摘要：改动会在 seal 处暴露，但无法定位到具体行。
