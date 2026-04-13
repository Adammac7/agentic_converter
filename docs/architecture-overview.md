# Architecture Overview

This project is organized so the orchestration framework stays stable while agent implementations can change over time.

## Root-Level Files and Folders

- `main.py`
  - Entry point for running the app.
  - Later, this should parse input and call the orchestrator.

- `archive/`
  - Legacy files moved out of the active root layout.
  - Keep old code here while migrating into the new structure.

- `core/`
  - Framework runtime and shared contracts.
  - This folder should not contain domain-specific conversion logic.

- `agents/`
  - Plug-in style agent implementations.
  - Each agent has its own folder, config, and prompts/tooling surface.

- `pipelines/`
  - Pipeline definitions (which agents run and in what order).
  - Lets you change orchestration flow without changing Python code.

- `tools/`
  - Shared utilities callable by the orchestrator (e.g. Graphviz / diagram rendering).

## `core/` File Responsibilities

- `core/contracts.py`
  - Defines shared interfaces/types:
    - agent contract (what methods an agent must expose)
    - shared run context shape
    - result/event/error structures

- `core/orchestrator.py`
  - Executes agents in order based on pipeline config.
  - Handles flow control and error policy.

- `core/registry.py`
  - Maps agent names to concrete implementations.
  - Used by the orchestrator to instantiate pipeline steps.

- `core/__init__.py`
  - Package marker for clean imports.

## `agents/` Layout

Each agent folder follows the same pattern:

- `agent.py`
  - Agent implementation class/function.
  - Reads context, performs one responsibility, returns updates.

- `config.toml`
  - Agent-specific settings (timeouts, defaults, flags).

- `prompt.md`
  - Optional prompt/instructions if the agent uses LLM behavior.

- `__init__.py`
  - Package marker.

Current scaffold:

- `agents/architect/`
- `agents/auditor/`
- `agents/stylist/`
- `agents/dot_compiler/`

## `pipelines/default.toml`

Defines default execution order (example):

1. converter agent
2. validator agent

This should be treated as orchestration data, not code.

## How Execution Should Flow

1. `main.py` loads runtime config and selected pipeline.
2. Orchestrator reads step names from `pipelines/default.toml`.
3. Registry resolves each step name to an agent implementation.
4. Orchestrator runs each agent with shared context.
5. Final context and status are returned to the caller.

## Why This Structure

- Keeps orchestration logic separate from domain logic.
- Makes agents replaceable and independently testable.
- Reduces root-level clutter.
- Supports adding future agents without large refactors.
