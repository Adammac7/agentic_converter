# Agentic Converter

RTL → Diagram pipeline powered by an agentic LLM system (Architect → Auditor → Stylist → DOT Compiler).

---

## Setup

```
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and add your API key:
```
GOOGLE_API_KEY="your_key_here"
GOOGLE_MODEL=gemini-2.5-flash
USE_GEMINI=True
```

---

## Running the app

Run both servers from the **project root**.

**Backend** (FastAPI on port 8000):
```
uvicorn backend.app:app --reload --port 8000
```

**Frontend** (Next.js on port 3000):
```
cd frontend
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## Running the pipeline directly

```
python -m orchestrator.orchestrator
```

Reads `agents/converter_agent/data/raw/top.sv` and writes `output.svg` to the project root.

---

## Tests

```
python -m pytest tests/ -v              # fast tests (default)
python -m pytest tests/ -v -s -m slow  # LLM self-correction tests (requires API key)
```

See [tests/README.md](tests/README.md) for the full test guide.

---

## Architecture

```
agentic_converter/
├── backend/
│   └── app.py                  — FastAPI server (POST /upload-rtl, POST /regenerate/{id})
├── frontend/
│   └── app/
│       ├── page.tsx            — Upload page (RTL file input + style prompt)
│       └── diagram-review/
│           └── page.tsx        — Diagram viewer (SVG output + re-style input)
├── orchestrator/
│   └── orchestrator.py         — LangGraph pipeline: wires agents together and runs the retry loop
├── agents/
│   └── converter_agent/
│       ├── config.py           — LLM setup (Gemini/OpenAI switch, prompt loader)
│       ├── rtl_to_json_agent.py    — Architect: RTL → structured JSON
│       ├── rtl_and_json_auditor_agent.py — Auditor: verifies JSON matches RTL
│       ├── stylist_agent.py        — Stylist: maps user style requests to components
│       ├── dot_compiler_agent.py   — DOT Compiler: JSON + styles → Graphviz DOT
│       ├── prompts.md          — Architect, Auditor, Stylist prompts
│       ├── diagram_spec.md     — DOT Compiler prompt + rendering rules
│       └── tools/
│           ├── json_schema.py      — RTLStructure Pydantic schema (Architect output)
│           ├── auditor_schema.py   — AuditReport Pydantic schema (Auditor output)
│           ├── style_schema.py     — StyleConfig Pydantic schema (Stylist output)
│           └── rtl_extractor.py    — RTL parsing utilities
├── tools/
│   └── graphviz_quickchart.py  — HTTP client: sends DOT to QuickChart, returns SVG
├── tests/                      — See tests/README.md
├── core/                       — Shared base classes (base_agent, state)
├── requirements.txt
└── pyproject.toml              — Pytest config (registers 'slow' marker)
```

### Pipeline flow

```
User uploads RTL + style prompt
        ↓
[Architect] RTL → JSON (RTLStructure)
        ↓
[Auditor]  JSON valid? ──No──→ feedback → retry Architect (up to 3x)
        ↓ Yes
[Stylist]  style prompt → StyleConfig
        ↓
[DOT Compiler] JSON + StyleConfig → DOT source
        ↓
[QuickChart]   DOT → SVG
        ↓
SVG returned to frontend / saved to backend/static/output/
```
