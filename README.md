# Agentic Converter

Convert SystemVerilog RTL into architecture diagrams using a multi-agent LLM pipeline:

**Architect -> Auditor -> Stylist -> DOT Compiler -> QuickChart (SVG)**

---

## What It Does

- Accepts RTL source (`.sv`, `.v`, `.svh`, `.vh`) plus optional style instructions
- Extracts a structured representation of modules/ports/instances
- Audits structure quality with retry-on-failure (up to 3 attempts)
- Applies style intent and compiles Graphviz DOT
- Renders final SVG via QuickChart and serves it through FastAPI
- Supports iterative regeneration with cumulative style edits

---

## Setup

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Set up environment variables:

```bash
cp .env.example .env
```

Then edit `.env`:

```env
GOOGLE_API_KEY="your_key_here"
GOOGLE_MODEL=gemini-2.5-flash
USE_GEMINI=True

# Optional OpenAI fallback when USE_GEMINI=False
OPENAI_API_KEY="your_openai_key_here"
OPENAI_MODEL="gpt-4o-mini"
```

> Note: the template file is currently named `.env.example` in this repository.

---

## Running the App

Run both services from the project root.

Backend (`FastAPI`, port `8000`):

```bash
uv run uvicorn backend.app:app --reload --port 8000
```

Frontend (`Next.js`, port `3000`):

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

---

## API Endpoints

- `POST /upload-rtl`
  - Multipart form: `rtl_file` + optional `customization_text`
  - Runs full pipeline and returns `{ task_id, svg_url }`
- `POST /regenerate/{task_id}`
  - JSON body: `{ "edit_prompt": "..." }`
  - Regenerates diagram from prior task with cumulative style intent
  - Returns a new `{ task_id, svg_url }`
- `GET /task/{task_id}/dot`
  - Returns DOT source for interactive viewer usage
- `GET /static/output/{task_id}.svg`
  - Serves generated SVG assets

---

## Pipeline Flow

```text
Upload RTL + optional style request
              |
              v
Architect: RTL -> RTLStructure JSON
              |
              v
Auditor: validate JSON vs RTL
    | valid                     | invalid
    v                           v
continue                 feedback -> Architect retry (max 3)
              |
              v
Stylist: user prompt -> StyleConfig
              |
              v
DOT Compiler: verified_json + style_map -> DOT
              |
              v
QuickChart Graphviz API: DOT -> SVG
              |
              v
FastAPI returns svg_url + task state
```

---

## Repository Structure

```text
agentic_converter/
├── agents/
│   ├── config.py                 # LLM selection + prompt section loader
│   ├── architect/
│   │   ├── agent.py              # RTL -> RTLStructure
│   │   ├── schema.py
│   │   └── prompt.md
│   ├── auditor/
│   │   ├── agent.py              # JSON audit report (is_valid + feedback)
│   │   ├── schema.py
│   │   └── prompt.md
│   ├── stylist/
│   │   ├── agent.py              # StyleConfig generation
│   │   ├── schema.py
│   │   └── prompt.md
│   └── dot_compiler/
│       ├── agent.py              # verified_json + style_map -> DOT text
│       └── prompt.md
├── orchestrator/
│   └── orchestrator.py           # LangGraph state graph + artifact persistence
├── backend/
│   └── app.py                    # FastAPI routes and in-memory task store
├── tools/
│   └── graphviz_quickchart.py    # DOT -> SVG HTTP client + error handling
├── frontend/
│   ├── app/page.tsx              # Upload workflow
│   ├── app/diagram-review/page.tsx
│   └── public/viewer.html        # Interactive diagram viewer
├── tests/
│   ├── test_json_schema.py
│   ├── test_json_retry_loop.py
│   ├── test_json_llm_self_correction.py
│   ├── test_graphviz_quickchart.py
│   └── README.md
├── requirements.txt
└── uv.lock
```

---

## Testing

Run from project root:

```bash
# Default fast suite
python -m pytest tests/ -v

# Only slow LLM self-correction tests
python -m pytest tests/ -v -s -m slow

# Run all tests including slow
python -m pytest tests/ -v -m ''
```

See `tests/README.md` for detailed guidance and test selection.

---

## Notes

- Prompt sections are loaded from each agent's own `prompt.md` by header name (`# ...`) using `load_prompt(...)`.
- Prompt files use Python `.format(...)`; literal braces in prompt text must be escaped as `{{` and `}}`.
- Runtime artifacts are written under your temp directory (`/tmp/agentic_converter_runtime/...`) to avoid noisy reloads during development.
