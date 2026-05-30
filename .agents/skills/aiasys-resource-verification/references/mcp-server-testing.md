# MCP Server Testing

Use this reference when the task is specifically about MCP validation, especially Layer 1 / Layer 2 checks that do not require the full AIASys resource panel context.

## Testing layers

### Layer 1: MCP server itself

Confirm:

- server starts
- protocol responds
- `initialize` succeeds
- `list_tools` works
- at least one tool call returns a valid result

### Layer 2: AIASys integration

Confirm:

- backend can save/read MCP config
- session/workspace can load the config
- runtime can call MCP tools successfully

### Layer 3: User-visible E2E

Confirm:

- user configures MCP
- runtime actually uses it
- final result returns through the product path

## Minimal Layer 1 workflow

### Quick protocol probe

```bash
curl -s http://localhost:3001/mcp \
  -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

Note:

- a `Missing session ID` style response can still mean the endpoint exists
- do not treat that as a full pass

### Recommended Python SDK probe

Use an MCP client to verify:

1. `initialize`
2. `list_tools`
3. at least one `call_tool`

The exact script can be small and task-specific; do not hardcode an enormous generic test unless needed.

## Common failure classes

### Connection refused

Likely:

- server not started
- wrong port
- wrong transport endpoint

### Initialize fails

Likely:

- protocol mismatch
- incomplete transport setup
- auth/session handshake missing

### list_tools works but call_tool fails

Likely:

- tool args are wrong
- upstream dependency missing
- server supports listing but not actual execution path

## AIASys-specific rule

Inside AIASys, do not stop at "server responds".

The bar for "usable" is still:

1. mounted/enabled in current task context
2. connectable
3. executable through the real runtime path

This reference was migrated from the old standalone `mcp-testing` skill.
