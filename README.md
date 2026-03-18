# 🤖 RTL-to-JSON Agentic Parser

An automated hardware design parsing pipeline that uses a **Dual-Agent Self-Correction Loop** and **Pydantic Validation** to convert SystemVerilog (RTL) into verified, structured JSON netlists.

## 🚀 Overview
 This project converts RTL to JSON code that by using an **Agentic Workflow**:
1.  **The Architect (Extractor):** Analyzes the RTL and generates a JSON draft.
2.  **The Inspector (Validator):** Ensures the JSON matches a strict structural schema.
3.  **The Auditor (Critic):** Cross-checks the JSON against the source RTL for hardware logic errors.
4.  **Self-Correction:** If errors are found, the system automatically triggers a "Revision Loop" until the design passes verification.

---

## 🏗️ System Architecture

The pipeline consists of four modular layers:

### 1. Pre-processing Layer (`utils/rtl_preprocessor.py`)
* **Token Optimization:** Strips comments (`//`, `/* */`) and excessive whitespace.
* **Accuracy Boost:** Removes "noise" like TODOs or commented-out code that can lead to AI hallucinations.

### 2. Extraction Layer (`agents/extraction_agent.py`)
* **Persona:** Hardware Design Architect.
* **Deterministic Logic:** Uses `temperature=0` to ensure 1:1 mapping of ports and signals.
* **Bit-Width Enforcement:** Calculates bus widths using the $|X-Y| + 1$ rule (e.g., `[7:0]` = 8).

### 3. Validation Layer (`utils/json_validator.py`)
* **Schema Enforcement:** Uses **Pydantic** to guarantee the JSON output matches our data model.
* **Type Safety:** Ensures widths are integers and directions are valid (`input`/`output`) before saving.

### 4. Audit Layer (`agents/auditor_agent.py`)
* **Persona:** Verification Engineer.
* **Logic Review:** Flags missing ports, incorrect connections, or module name mismatches.

---

## 🔄 The Self-Correction Loop
The system implements a "Reasoning Loop" rather than a one-shot prompt:

1.  **Attempt 1:** Agent generates a JSON netlist.
2.  **Schema Check:** Pydantic validates keys. If the AI renamed a key, it is told to fix the structure.
3.  **Hardware Audit:** The Auditor compares the JSON to the RTL. If a port is missing, the specific error is sent back to the Extractor.
4.  **Revision:** The Extractor receives the feedback and generates a corrected version.
5.  **Finalize:** Once the Auditor issues a `PASSED` status, the JSON is saved to `data/processed/`.

---

## 🛠️ Setup & Usage

### Prerequisites
* Python 3.9+
* OpenAI API Key (configured for `gpt-4o` for best results)

### Installation
1.  **Install dependencies:**
    ```bash
    pip install openai pydantic pyyaml python-dotenv
    ```
2.  **Configure Environment:**
    Create a `.env` file in the root directory:
    ```env
    OPENAI_API_KEY=your_actual_key_here
    OPENAI_MODEL=gpt-4o
    ```

### Running the Pipeline
Place your SystemVerilog files in `data/raw/` and execute the orchestrator:
```bash
python src/main.py