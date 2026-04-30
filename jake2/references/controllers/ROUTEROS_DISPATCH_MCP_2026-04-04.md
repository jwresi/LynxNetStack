# RouterOS Dispatch MCP

`routeros_dispatch_mcp.py` is the confidence-gated routing layer that sits between Jake's front door and the RouterOS/SwOS troubleshooting scenario catalogs.

It does four things:

1. extracts RouterOS-domain signals from a plain-English operator question
2. scores the likely domain
3. asks a short targeted follow-up when the signal is not strong enough
4. renders the top scenario into a normal operator-facing answer

Current domain targets:

- `routeros_access_mcp`
- `routeros_switching_mcp`
- `routeros_routing_mcp`
- `routeros_platform_mcp`
- `routeros_ops_mcp`
- `routeros_wireless_mcp`
- `swos_switching_mcp`

Current thresholds:

- dispatch when confidence is `>= 0.70`
- ask for clarification when confidence is below that threshold

Renderer rules:

- show the scenario summary first
- include applies-to version/hardware only when relevant
- show top likely causes
- show the first safe actions
- show `fixed_in` when present
- only show diagnostic commands if the operator explicitly asked how to check or what to run

The goal is to stop Jake from returning "best fit" metadata dumps when he already has enough signal to give a real answer, while still refusing to guess on weak context.
