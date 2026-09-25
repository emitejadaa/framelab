# M2b (part 1) — Every pandas operation from the menu · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Any node offers every allowed pandas method and attribute of its type (DataFrame, Series and its `.str`/`.dt`/`.cat` accessors, GroupBy, windows, Index), searchable and grouped by the API reference categories, each with a form generated from the catalog and live code.

**Architecture:** Python decides what a node offers (`Session.members`: the catalog owners that match the node's value, minus denied and mutating members) and still validates every op. The frontend gets the list once per node (`node.members`), shows it in the node menu search and in a browser dialog, and builds op JSON from a generic form whose controls come from each parameter's `widget`. Window objects (`rolling`, `resample`…) get their own node kind so their members are reachable.

**Tech Stack:** Python 3.11+, pandas 3; React 19 + TypeScript.

**Spec:** `docs/superpowers/specs/2026-09-23-framelab-design.md` (Workbench: "Operar", "Menús y Todos A–Z listan métodos y atributos", formularios auto-generados); catalog from M1b Task 9.

## Global Constraints

- Only members with `allowed` true and `mutates` false are offered; Python re-validates every op (`Op.validate`, policy) — the UI list is a convenience, not a security boundary.
- Unset parameters are never sent: the code shows only what the user set (spec: "solo se emite lo que el usuario fijó").
- Tooltips/summaries stay in English (pandas docstrings); UI chrome is es/en.
- Frontend tests: none new beyond one step in the existing workbench E2E.

## Review Focus

1. **A Series of text vs dates vs categories** — only the matching accessor (`.str`, `.dt`, `.cat`) is offered. Pinned in Task 1.
2. **Window and resampler nodes** (`rolling(3)`, `resample("D")`) — they are nodes with members (`mean`, `sum`…), not dead "Value" nodes. Pinned in Task 1.
3. **Free-text values** (`[1, 2]`, `true`, `3.5`, `None`, text with quotes) — parsed into the right literal, invalid JSON falls back to text. Pinned in Task 2 (TS parser mirrors `parseLiteral` rules) and by Python validation.
4. **Required parameters left empty** — the form says which one and does not apply. Pinned in Task 2.
5. **A member that fails in pandas** — an error node with pandas' message, never a broken UI. Pinned by the existing error-node flow (Task 3 E2E).

---

### Task 1: `Session.members` and window nodes

**Files:** Modify `src/framelab/session/node.py` (`NodeKind.WINDOW`, `classify`), `src/framelab/protocol/schema.py` (`NodeKindName`), `src/framelab/session/core.py` (`members`), `src/framelab/transport/methods.py` (`node.members`); Create `tests/test_members.py`.

**Interfaces:** `Session.members(key) -> list[dict]` (each: catalog `Member.describe()` + `"accessor": list[str]`); protocol `node.members {id}` → `{"members": [...]}`; `NodeKind.WINDOW` (`"Window"`).

```python
# tests/test_members.py (essentials)
def test_dataframe_members(s):
    names = {m["name"] for m in s.members("n1")}
    assert {"sort_values", "head", "T", "nlargest"} <= names
    assert not names & {"to_csv", "insert", "pop", "update", "eval", "query", "plot"}

def test_series_accessors_follow_the_dtype(s):
    text = {(m["accessor"] and m["accessor"][0], m["name"]) for m in s.members(s.apply(getitem("n1", "pais")).id)}
    assert ("str", "upper") in text and not any(a == "dt" for a, _ in text)
    dates = {(m["accessor"] and m["accessor"][0], m["name"]) for m in s.members(s.apply(getitem("n1", "fecha")).id)}
    assert ("dt", "year") in dates and not any(a == "str" for a, _ in dates)

def test_windows_are_nodes_with_members(s):
    rolling = s.apply(call(s.apply(getitem("n1", "monto")).id, "rolling", 2))
    s.wait(rolling.id)
    assert s.node(rolling.id).kind.value == "Window"
    assert "mean" in {m["name"] for m in s.members(rolling.id)}
```

- [ ] Write the tests, see them fail, implement `owners_for(value)` (DataFrame; Series + `str` for string/object-of-text, `dt` for datetime/timedelta/period, `cat` for categorical; DataFrameGroupBy/SeriesGroupBy; Rolling/Expanding/ExponentialMovingWindow/Resampler; Index), `Session.members`, `classify` → `WINDOW` for window and resampler objects, the protocol method; regenerate TS types; run the suite; commit.

### Task 2: Member browser and generated forms (frontend)

**Files:** Create `frontend/src/workbench/members.ts` (types, `useMembers`, `parseLiteral`, `buildMemberOp`), `frontend/src/workbench/MemberBrowser.tsx`, `frontend/src/workbench/MemberForm.tsx`; Modify `state/store.ts` (`browser`, `memberForm`), `workbench/NodeMenu.tsx` (search includes pandas members; "Todas las operaciones de pandas…"), `app/Shell.tsx`, `workbench/format.ts` (`Window` icon), i18n, CSS.

- `parseLiteral(text)`: `""` → unset; `true/false` (any case) → bool; `none/null` → null; a number → number; text starting with `[` or `{` → `JSON.parse` when valid; otherwise the text itself.
- Controls by `widget`: `bool` (default / True / False), `int`/`float` (number, placeholder = default), `choice`/`axis` (select with "(default)"), `columns` (checkboxes of the node's columns → one `colRef` or a list), `column` (select), `frame` (select of other table nodes → node ref), `func` (select of pandas kernels + text), everything else a text box parsed with `parseLiteral`. Required parameters are marked and block "Aplicar" while empty.
- Properties apply at once (`attrOp`); methods open the form (`callOp` with only the set kwargs). Live code via `op.preview`; guard errors offer "Aplicar de todos modos".

### Task 3: E2E step and hunt coverage

- [ ] `frontend/tests/e2e/workbench.e2e.mjs`: from the root menu open "Todas las operaciones de pandas…", search `nlargest`, set `n=2` and `columns=monto`, apply, and check `ventas.nlargest(n=2, columns="monto")` appears in the code panel.
- [ ] Run both E2Es and the hunt script; commit and push.
