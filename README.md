# Agents

A collection of AI agents for the Fontys group project.

## Available Agents

| Agent | Description |
|---|---|
| [`privacy_officer/`](./privacy_officer/README.md) | Fully containerized agent that locally anonymizes open-text feedback using a **triple-layer** pipeline (Presidio + EU-PII-Safeguard + local LLM: `aya-expanse:8b`). Includes a Web UI, real-time progress tracking, and dynamic PII selection. Handles Dutch & English without sending any data to the cloud. |

## Getting Started

The recommended way to run the agents is via **Docker**. 

Navigate into the agent's folder (e.g., `cd privacy_officer`) and run:
```bash
docker-compose up --build
```
Please read the specific agent's `README.md` for detailed instructions on the tools used, the architecture, and how to use its Web Interface.
