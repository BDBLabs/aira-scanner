# Changelog

All notable changes to AIRA Scanner will be documented here.

## [Unreleased]

## [v1.3.0] - 2026-07-04

Parity release: the CLI, the web API, and the published Homebrew build now run the same deterministic rules and the same provider/model selection. v1.2.1 installs had drifted from the deployed web scanner while both still reported version 1.2.1.

### Detection changes (deterministic engine)

- Fixed the C11 determinism regex so fractional temperatures such as `temperature=0.9` are detected; v1.2.1 only matched values with a non-zero integer part
- Reworked C05 bypass detection from line-level regex matching to AST-based identifier analysis, removing false positives on plain flag assignments
- Hardened scanner error handling: scanner failures now surface as explicit `SCANNER` findings and dedicated exit codes instead of silently passing

### Provider routing and model selection

- Replaced the Gemini provider with NVIDIA NIM (default model `stepfun-ai/step-3.7-flash`) in both the CLI and the web routing layer
- Web routing now honors an explicit per-request model for NVIDIA, Groq, and OpenRouter (previously only Ollama respected it; other providers silently fell back to the configured default)
- CLI Groq routing now matches the web: `llama-3.1-8b-instant` is the default model and an API key alone is enough to configure the provider
- Auto provider order is now identical in CLI and web (`ollama → nvidia → groq → openrouter`, with the CLI additionally preferring a local OpenAI-compatible endpoint first)

### Packaging and docs

- Moved the scanner package into `CLI/` and refreshed the docs
- Published a dedicated `homebrew-aira-scanner` tap so Homebrew can auto-tap on `brew install BDBLabs/aira-scanner/aira`
- Removed inaccurate PyPI install instructions; AIRA is distributed via Homebrew and source installs only
- Removed the stale Gemini free-tier comment from the web scan route

## [v1.2.1] - 2026-04-21

- Added a documentation pack for scanner history, methodology, and formal check definitions
- Linked the new docs from the repository front door so the scanner's evolution is easier to reconstruct
- Added Supabase research schema v2 with append-only submission streams, normalized submission checks, and FTI-v1 scoring
- Disabled hosted public research writes by default so canonical records stay in internal curated CLI/CI workflows
- Added a manifest-driven `aira collect` workflow for curated public-repo dataset collection
- Switched the Homebrew formula from head-only installs to a stable immutable source archive, while keeping `--HEAD` available for unreleased builds
- Vendored `setuptools` and `wheel` in the Homebrew formula so current Python virtualenv installs can build the CLI package reliably
- Renamed the Homebrew formula from `aira-scanner` to `aira`, enabling `brew install aira` after the tap is installed
- Added a helper script to refresh the Homebrew formula for future release refs

## [v1.2.0] - 2026-03-29

This is the first version where the repository is coherent as a research instrument rather than only a web prototype.

- Formalized the scanner around the AIRA v1.2 check contract
- Added the CLI as a first-class interface for local, CI, and research use
- Added local-first provider routing for OpenAI-compatible endpoints, Ollama, Groq, Gemini, and OpenRouter
- Added provider health checks and Ollama model discovery / validation
- Added aggregate-only research submission from CLI and web
- Added richer research payloads including per-check counts and per-check severity matrices
- Added Airtable health checking and compatibility fallback behavior
- Added Supabase and JSONL research backends, making Supabase the preferred hosted path
- Added parser-backed deterministic static scanning, making static analysis the canonical non-LLM baseline
- Added a deterministic server-side static scan route for the web app

## [Pre-v1.2 Evolution]

### Browser Prototype

- Started as a mostly front-end scanner with a single-page web interface
- Focused on communicating the AIRA thesis and making the 15 checks legible
- Relied heavily on browser-side heuristics

### Server-Side API Connector

- Added an API-backed scan route so the web app could call structured LLM providers
- Preserved the original web experience while making the scanner more useful on real code

### Heuristic Safety Net

- Added a heuristic fallback so the public scanner remained usable under quota, outage, or configuration failure
- Established the principle that AIRA should still produce triage output even when the cloud path is unavailable

### Routed Providers And Health Surfaces

- Added routed cloud failover and provider health endpoints
- Improved visibility into whether the scanner was actually using an LLM or falling back

### CLI And Local-First Operation

- Added the CLI implementation
- Expanded the scanner so it could run on local files, whole repos, and CI targets
- Added support for local OpenAI-compatible endpoints and Ollama, not just hosted providers

### Research Data Collection

- Added aggregate-only research submission and schema documentation
- Started with Airtable compatibility because it was easy to stand up quickly
- Evolved toward richer per-check severity data as the research needs became clearer

### Deterministic Backbone

- Added parser-backed deterministic static scanning for Python and JavaScript
- Shifted the scanner architecture so deterministic analysis became the backbone and LLMs became optional augmentation

### Research Backend Maturation

- Added Supabase and JSONL as serious research sinks
- Repositioned Airtable as a legacy compatibility fallback rather than the preferred destination

### Ollama As A Stable Abstraction Layer

- Added Ollama model discovery and validation
- Clarified that AIRA should integrate with Ollama as an abstraction layer, regardless of whether the selected model is local or cloud-backed
