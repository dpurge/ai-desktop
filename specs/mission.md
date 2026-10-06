---
version: 1
status: approved
updated: 2026-10-06
---

# AI Desktop Mission

## Problem

Chatting with an LLM from a desktop app usually means a cloud-only product or a heavy, hard-to-audit application. AI Desktop is a private, local-first desktop assistant: it connects to Ollama (local or remote) or OpenRouter, keeps session history on the user's machine, and is configured in the app without friction. It is a simplified, more readable take on the desktop AI coworker idea, with a different purpose.

## Users

- A single individual running the app on their own Linux, Windows, or macOS machine
- People who run Ollama locally or on a remote host they control
- People who use OpenRouter with their own API key

## Value proposition

AI Desktop is a small, readable desktop chat app that stores sessions and configuration locally. A user can launch it, enter an Ollama URL or an OpenRouter API key, and start chatting. It grows into an assistant through tools (gmail, gcal, github, shell, ask, propose), skills, an optional NVIDIA OpenShell sandbox, and workflows. Readability of the code is a first-class requirement so the project is easy to audit, modify, and extend.

## Non-goals

- A multi-user server or hosted API; the engine serves only the local GUI
- Copying the full feature set of the reference product
- Mobile applications
