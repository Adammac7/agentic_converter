# 🤖 RTL-to-JSON Agentic Parser

An automated hardware design parsing pipeline that uses a **Dual-Agent Self-Correction Loop** and **Pydantic Validation** to convert SystemVerilog (RTL) into verified, structured JSON netlists.

---

## 🏗️ System Architecture

The pipeline consists of four modular layers designed to ensure data integrity and hardware accuracy:

### 1. Pre-processing Layer (`src/utils/rtl_preprocessor.py`)
* **Token Optimization:** Strips comments (`//`, `/* */`) and excessive whitespace.
* **Accuracy Boost:** Removes "noise" that can lead to AI hallucinations.

### 2. Extraction Layer (`src/agents/extraction_agent.py`)
* **Persona:** Hardware Design Architect.
* **Deterministic Logic:** Uses `temperature=0` to ensure 1:1 mapping of ports and signals.
* **Bit-Width Enforcement:** Calculates bus widths using the $|X-Y| + 1$ rule.

### 3. Validation Layer (`src/utils/json_validator.py`)
* **Schema Enforcement:** Uses **Pydantic** to guarantee the JSON output matches our strict master schema.

### 4. Audit Layer (`src/agents/auditor_agent.py`)
* **Persona:** Verification Engineer.
* **Logic Review:** Flags missing ports or incorrect connections by comparing JSON against the original RTL.

---

## 🔄 The Self-Correction Loop
The system implements a **Reasoning Loop** rather than a "one-shot" prompt:

1.  **Extract:** The Extraction Agent generates a JSON draft.
2.  **Validate:** Pydantic checks structure. If keys are missing, it retries with **Schema Feedback**.
3.  **Audit:** The Auditor checks accuracy. If errors exist, it retries with **Hardware Feedback**.
4.  **Finalize:** Once the Auditor issues a `PASSED` status, the JSON is saved to `data/processed/`.

---

## 📂 Project Structure
```text
.
├── config/
│   └── prompts.yaml          # The "Brain": Modular AI instructions
├── data/
│   ├── raw/                  # Input SystemVerilog (.sv) files
│   └── processed/            # Final, verified JSON netlists
├── src/
│   ├── main.py               # Orchestrator & Self-Correction Logic
│   ├── agents/
│   │   ├── extraction_agent.py
│   │   └── auditor_agent.py
│   └── utils/
│       ├── rtl_preprocessor.py
│       └── json_validator.py
├── .env                      # API Keys & Model Configuration
└── requirements.txt          # Project Dependencies


# 🚀 Quick Start Guide (Windows / Git Bash)

Follow these steps to set up your environment, install dependencies, and run the Agentic Pipeline.

---

## 📦 Step 1: Initialize the Virtual Environment

Keep your project dependencies isolated by using a virtual environment. This prevents conflicts with your global Python installation.

### 🔹 Create and Activate

```bash
# Create the virtual environment
python -m venv venv

# Activate the environment (Git Bash)
source venv/Scripts/activate
```

> ✅ **Tip:** You should see `(venv)` at the start of your terminal once activated.

---

## 📦 Step 2: Install Dependencies

Make sure your virtual environment is active before installing dependencies.

### 🔹 Upgrade pip

```bash
python -m pip install --upgrade pip
```

### 🔹 Install Required Packages

```bash
pip install -r requirements.txt
```

---

## 📦 Step 3: Configure Environment Variables

The AI agents require an OpenAI API key to function or LLM of choice.

### 🔹 Create `.env` File

```bash
touch .env
```

### 🔹 Add Credentials

Open the `.env` file and add:

```env
OPENAI_API_KEY=your_actual_key_here
OPENAI_MODEL=gpt-4o
```

> ⚠️ Never commit your `.env` file to GitHub.

---

## 📦 Step 4: Run the Pipeline

Place your SystemVerilog files in the appropriate directory and start the pipeline.

### 🔹 Add Input Files

```
data/raw/top.sv
```

### 🔹 Execute Workflow

```bash
python src/main.py
```

> 📁 Output will be generated in: `data/processed/`

---

## 🛠️ Requirements File (`requirements.txt`)

Ensure this file exists in your root directory:

```txt
openai (or LLM of choice)
pydantic
pyyaml
python-dotenv
```

### Running the Pipeline
Place your SystemVerilog files in `data/raw/` and execute the orchestrator:
```bash
python src/main.py