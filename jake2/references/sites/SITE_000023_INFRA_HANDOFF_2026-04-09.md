# Site 000023 Infrastructure Handoff

Current read:
- `000023` is a multi-OLT infrastructure site with active alerts but no current local customer-online proof.
- NetBox infrastructure in scope: `OLT=3`, `Power-Distribution=1`, `Router=1`, `Digi=1`, `Power-backup=1`.

Field handoff:
- Start with power distribution, backup power, and the OLT/router shelf.
- Because there are multiple OLTs, isolate whether one shelf/path is dark before assuming whole-site failure.
- Treat Digi reachability as management-only evidence.
- If optics alerts are active, prioritize the strongest OLT/PON concentration first.

Good Jake follow-ups:
- `give me the site infrastructure handoff for 000023`
- `what should the field team check physically at 000023?`
- `which PON port is the current top optical work item at 000023?`

