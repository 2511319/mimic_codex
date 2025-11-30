// Minimal stdio wrapper for postgres-mcp on Windows
// Starts MCP server without CLI noise.

const modUrl = new URL('file:///C:/Users/25113/AppData/Roaming/npm/node_modules/postgres-mcp/dist/index.js');
const { startServer } = await import(modUrl.href);

// Redirect noisy log output to stderr to protect MCP stdout
const origLog = console.log;
console.log = (...args) => {
  try {
    process.stderr.write(args.map(v => (typeof v === 'string' ? v : JSON.stringify(v))).join(' ') + '\n');
  } catch {
    origLog(...args);
  }
};

try {
  await startServer();
} catch (err) {
  const msg = err instanceof Error ? err.stack || err.message : String(err);
  console.error(`[postgres-mcp-wrapper] fatal: ${msg}`);
  process.exit(1);
}

process.on('SIGINT', () => process.exit(0));
process.on('SIGTERM', () => process.exit(0));
