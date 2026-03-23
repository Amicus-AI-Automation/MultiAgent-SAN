# 🕵️ Autonomous Monitoring Agent

An agentic AI system designed to autonomously monitor, diagnose, and resolve UI errors on web applications using a multi-agent architecture powered by **LLM**, **RAG**, and **Playwright**.

---

## 🌟 Key Features

- **Multi-Agent Orchestration**: Specialized agents for Observation, Diagnosis, and Execution.
- **RAG Intelligence**: Semantic search (FAISS + SentenceTransformers) to match errors with known resolution steps.
- **LLM Grounding**: Uses **Groq (Llama 3 / GPT-OSS)** to map natural language steps to precise CSS selectors.
- **Live Monitoring**: Injects a `MutationObserver` for real-time error detection without page reloads.
- **Self-Healing**: Automatically executes resolution plans and verifies the outcome.

---

## 🏗️ Architecture

The system follows a continuous feedback loop:

1.  **Detect (SnapshotAgent)**: Continuously scours the DOM for new unresolved error entries.
2.  **Diagnose (DiagnosisAgent)**: Retrieves the standard fix via RAG and "grounds" it to the current UI state using the LLM.
3.  **Execute (ExecutionAgent)**: Performs the corrective actions (Click, Fill, Navigate, etc.) via Playwright.
4.  **Verify**: Confirms the error is resolved and logs the history.

---

## 📁 Project Structure

```text
Monitoring_Agent/
├── agents/               # Specialized agent logic (Snapshot, Diagnosis, Execution)
├── core/                 # Infrastructure (Config, Models, Session, Memory)
├── data/                 # Persistent logs, snapshots, and execution history
├── rag_sys/              # RAG components (FAISS index, Knowledge Base)
├── main.py               # Entry point (Browser launch & Login)
├── orchestrator.py       # Pipeline & Lifecycle manager
└── requirements.txt      # Python dependencies
```

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10+
- A [Groq Cloud](https://console.groq.com/) API Key.

### 2. Installation
```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Configuration
Set the following environment variables (or update `core/config.py`):
```bash
export GROQ_API_KEY="your_api_key_here"
export GROQ_MODEL="openai/gpt-oss-20b"
```

### 4. Run the Agent
```bash
python main.py
```
> **Note**: The system will launch a browser and pause for manual login. Once you reach the dashboard, the monitoring system will automatically activate.

---

## 🛠️ Internal Reference
For deep technical details on agent roles and data flow, see [Architecture_Reference.md](./Architecture_Reference.md).

---

