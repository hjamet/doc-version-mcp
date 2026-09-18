# 📄 doc-version-mcp

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastMCP](https://img.shields.io/badge/FastMCP-0.4.0+-brightgreen.svg)](https://github.com/jlowin/fastmcp)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **FastMCP Server for Document Versioning, Content-Addressable Storage (CAS), AST Diffs, and AI-Compliance Auditing.**

`doc-version-mcp` provides a robust, local-first document versioning engine built on top of the Model Context Protocol (MCP). It brings Git-like precision to LLM agents and human authors without cluttering Git commit histories, offering deterministic snapshots, word-level differential AST projections, and collaborative safety rails.

---

## ⚡ Quick Start (Windows PowerShell One-Liner)

Install and configure `doc-version-mcp` automatically with a single command in PowerShell:

```powershell
irm https://raw.githubusercontent.com/hjamet/doc-version-mcp/main/install.ps1 | iex
```

The installer automatically:
1. Detects or creates the target directory (`~/Documents/code/doc-version-mcp`).
2. Configures a dedicated Python virtual environment (`.venv`) with all dependencies.
3. Initializes the Content-Addressable Storage (CAS) hierarchy at `~/.gemini/antigravity/cas_commits/`.
4. Registers the server into your Antigravity MCP configuration (`mcp_config.json`).
5. Copies metadata schemas and installs command-line wrappers (`doc-version.cmd`, `doc-version.ps1`).

---

## 🏛️ Architecture & Key Features

```
┌─────────────────────────────────────────────────────────────┐
│                       LLM Agent / User                      │
└──────────────────────────────┬──────────────────────────────┘
                               │  FastMCP Stdio Transport
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                      doc-version-mcp                        │
│  ┌───────────────────────────┐ ┌──────────────────────────┐ │
│  │   CAS Storage Engine      │ │   AST & Diff Generator   │ │
│  │   - SHA-256 Addressing    │ │   - LaTeX & KaTeX Diffs  │ │
│  │   - zlib Level 9 Compress │ │   - Mode 'paper' & 'draft'││
│  │   - Isolated Commit Trees │ │   - AI Compliance Auditing││
│  └───────────────────────────┘ └──────────────────────────┘ │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│             Local Storage & Workspace Integrity             │
│   ~/.gemini/antigravity/cas_commits/{commits,objects}/       │
└─────────────────────────────────────────────────────────────┘
```

- **Content-Addressable Storage (CAS)**: Documents are stored as immutable, content-addressed blobs compressed via `zlib` (level 9) and indexed by SHA-256 hashes, keeping disk overhead minimal.
- **Dual Operational Modes**:
  - **`paper` Mode**: Tailored for scientific manuscripts (LaTeX and Markdown). Analyzes mathematical environments, AST sections, and evaluates AI-stylometry metrics ($P(\text{AI}) < 0.10$).
  - **`draft` Mode**: Dedicated to precision editing of drafts. Audits `<XXX>` uncertainty placeholders and enforces a strict text retention threshold ($\ge 90\%$).
- **Deterministic Collaboration**:
  - Seamless upstream synchronization (`record_git_pull_event`) with automatic stashing (`--autostash`).
  - Strict preservation of co-author contributions with blocking conflict detection.
  - Zero uncontrolled global rewrites: changes are validated block-by-block.
- **Local-First & Portable**: Pure local Python package, independent of cloud services and fully compatible with multi-machine setups.

---

## 🛠️ MCP Tools Reference

`doc-version-mcp` exposes 6 declarative MCP tools:

| Tool Name | Description | Key Parameters |
|---|---|---|
| `commit_document` | Creates a timestamped CAS snapshot of a document on disk or in virtual memory. | `target` (str, req), `message` (str, req), `author` (str, default `"agent"`), `content` (str, opt), `is_pinned` (bool, default `False`), `mode` (str, default `"paper"`) |
| `get_diff_artifact` | Computes surgical word-level diffs and generates an interactive Markdown artifact in Antigravity Brain. | `target` (str, req), `diff_explanation` (str, opt), `brain_dir` (str, opt), `artifact_name` (str, opt), `mode` (str, default `"paper"`), `from_commit_id` (str, opt), `to_commit_id` (str, opt) |
| `restore_commit` | Restores a document from a historical CAS commit ID. Supports dry-run preview. | `commit_id` (str, req), `target` (str, opt), `dry_run` (bool, default `False`) |
| `list_commits` | Lists stored CAS commits with timestamps, authors, and metadata. | `target` (str, opt), `limit` (int, default `10`), `mode` (str, opt) |
| `prune_commits` | Purges expired snapshots based on TTL and disk quota, protecting pinned baselines. | `ttl_days` (int, default `14`), `max_size_mb` (int, default `500`), `keep_baselines` (bool, default `True`) |
| `record_git_pull_event` | Synchronizes a Git repository via `git pull --rebase` with autostash and creates an upstream snapshot. | `repo_path` (str, req), `autostash` (bool, default `True`) |

---

## 🔧 Client Configuration Guide

### 1. Google Antigravity

Add the server to `~/.gemini/antigravity/mcp_config.json`:

```json
{
  "mcpServers": {
    "doc-version": {
      "command": "C:\\Users\\<USER>\\Documents\\code\\doc-version-mcp\\.venv\\Scripts\\doc-version.exe",
      "args": [],
      "env": {
        "SystemRoot": "C:\\Windows",
        "PATH": "%PATH%"
      }
    }
  }
}
```

### 2. Claude Desktop

Add to `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "doc-version": {
      "command": "C:\\Users\\<USER>\\Documents\\code\\doc-version-mcp\\.venv\\Scripts\\doc-version.exe",
      "args": []
    }
  }
}
```

### 3. Cursor

Configure in `.cursor/mcp.json` or Global Settings:

```json
{
  "mcpServers": {
    "doc-version": {
      "command": "C:\\Users\\<USER>\\Documents\\code\\doc-version-mcp\\.venv\\Scripts\\doc-version.exe",
      "args": []
    }
  }
}
```

### 4. Claude Code CLI

```bash
claude mcp add doc-version -- C:\Users\<USER>\Documents\code\doc-version-mcp\.venv\Scripts\doc-version.exe
```

---

## 💻 Local Development & Testing

### Installation from Source

```powershell
# Clone the repository
git clone https://github.com/hjamet/doc-version-mcp.git
cd doc-version-mcp

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install in editable mode with development dependencies
pip install --upgrade pip
pip install -e ".[dev]"
```

### Running Test Suite

```powershell
pytest tests/ -v
```

### Manual Inspection & CLI Run

```powershell
# Verify FastMCP server entry point
doc-version --help
```

---

## 📄 License

This project is licensed under the terms of the [MIT License](LICENSE).
