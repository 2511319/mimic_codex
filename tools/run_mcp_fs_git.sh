#!/usr/bin/env bash
set -euo pipefail

if ! command -v npx >/dev/null 2>&1; then
  echo "npx not found. Please install Node.js/npm." >&2
  exit 1
fi

if ! command -v uvx >/dev/null 2>&1; then
  echo "uvx not found. Install uv (https://github.com/astral-sh/uv) or use 'pip install mcp-server-git' and 'python -m mcp_server_git'." >&2
fi

: "${MCP_FS_ROOT:=${PWD}}"
: "${MCP_GIT_ROOT:=${PWD}}"

echo "Starting MCP Filesystem with root: $MCP_FS_ROOT" >&2
nohup npx -y @modelcontextprotocol/server-filesystem "$MCP_FS_ROOT" >/dev/null 2>&1 &
FS_PID=$!

echo "Starting MCP Git with workdir: $MCP_GIT_ROOT" >&2
if command -v uvx >/dev/null 2>&1; then
  GIT_WORKDIR="$MCP_GIT_ROOT" nohup uvx mcp-server-git >/dev/null 2>&1 &
else
  echo "uvx not available; ensure 'mcp-server-git' is installed and start it manually." >&2
fi

echo "MCP servers started. Filesystem PID: $FS_PID"

