# Tests

All commands must be run from the **project root** (`agentic_converter/`).

---

## Which test file should I use?

- **`test_json_schema.py`** — schema validation, no LLM, runs instantly
- **`test_json_retry_loop.py`** — retry loop logic, fully mocked, runs instantly
- **`test_graphviz_quickchart.py`** — HTTP client errors, fully mocked, runs instantly
- **`test_json_llm_self_correction.py`** — real LLM calls, requires API key, ~3 min per test

Run the first three by default. Only reach for the LLM file when verifying model behavior or changing agent prompts.

---

## Running tests

### Run everything (fast tests only, default)
```
python -m pytest tests/ -v
```

### Run only LLM tests
```
python -m pytest tests/ -v -s -m slow
```

### Run all tests including slow
```
python -m pytest tests/ -v -m ''
```

### Run a specific file
```
python -m pytest tests/test_json_schema.py -v
python -m pytest tests/test_json_retry_loop.py -v -s
python -m pytest tests/test_json_llm_self_correction.py -v -s -m slow
python -m pytest tests/test_graphviz_quickchart.py -v
```

### Run a specific test class
```
python -m pytest tests/test_json_retry_loop.py::TestRetryOnAuditorRejection -v -s
python -m pytest tests/test_json_llm_self_correction.py::TestLLMSelfCorrectionMissingPorts -v -s -m slow
```

### Run a specific test function
```
python -m pytest tests/test_json_retry_loop.py::TestRetryOnAuditorRejection::test_fails_once_then_passes -v -s
python -m pytest tests/test_json_llm_self_correction.py::TestLLMSelfCorrectionMissingPorts::test_recovers_from_missing_ports -v -s -m slow
```

> **Tip:** add `-s` to any command to print live output from the retry loop (e.g. `[Attempt 1/3]`, `[Auditor] Invalid — retrying.`). Without `-s`, pytest suppresses print statements.

---

## Test file reference

### test_json_schema.py
Tests the Pydantic schemas in `agents/architect/schema.py`.
No LLM, no agents, runs in under a second.

**When to use:** after changing any schema class (`RTLStructure`, `Port`, `LogicBlock`, `InternalWire`), or to verify that bad JSON from the LLM would be correctly rejected.

**What it covers:**
- The golden `tests/test_data/top_structure.json` parses correctly (sanity baseline)
- Missing required fields are rejected
- Wrong types (int, None, string where list expected) are rejected
- `LogicBlock` with no `port_mapping` is rejected (the most common LLM failure)
- `port_mapping` as a list or nested dict is rejected (must be a flat `{str: str}` dict)
- Empty `instances` and `top_level_ports` lists are allowed (schema-valid; auditor catches semantic errors)
- Extra unknown fields on an instance are silently ignored
- `width` as int instead of str is rejected

---

### test_json_retry_loop.py
Tests the Architect → Auditor retry loop in `orchestrator/orchestrator.py`.
Agent responses are mocked — no LLM calls, no API key needed.

**When to use:** after changing the retry loop logic in `orchestrator.py`, or to verify the loop correctly handles failures, passes feedback, and stops at `MAX_ATTEMPTS`.

**What it covers:**
- Auditor rejects JSON once/twice, loop retries and eventually succeeds
- Architect crashes (exception), loop catches it and retries
- All attempts exhausted → pipeline raises `RuntimeError`
- Happy path: passes on first attempt with no retries
- Auditor feedback string is correctly forwarded to the next Architect call

---

### test_json_llm_self_correction.py *(slow — real LLM calls)*
End-to-end tests that verify the LLM can self-correct when given corrupted JSON.
Requires a valid API key in `.env`. Skipped by default (`@pytest.mark.slow`).

**When to use:** when switching LLM models, changing agent prompts, or doing a full integration check before a demo or release. Run one test at a time on the free tier (~3-4 API calls per test).

**How it works:** on attempt 1, the Architect's real output is replaced with programmatically corrupted JSON. The real Auditor (LLM) flags the corruption and generates feedback. On attempt 2+, the real Architect (LLM) runs with that feedback and should self-correct.

**Corruption scenarios (one per test class):**
- `TestLLMSelfCorrectionMissingPorts` — 7 of 8 port mappings removed from u_ctrl
- `TestLLMSelfCorrectionHallucinatedInstance` — fake `u_fake_dma` instance injected
- `TestLLMSelfCorrectionWrongWires` — wire names in u_datapath replaced with wrong values
- `TestLLMSelfCorrectionMissingInstance` — u_fifo removed entirely

---

### test_graphviz_quickchart.py
Tests the QuickChart HTTP client in `tools/graphviz_quickchart.py`.
HTTP calls are mocked — no network required.

**When to use:** after changing `tools/graphviz_quickchart.py`, or to verify that bad DOT input and HTTP errors are handled correctly.
