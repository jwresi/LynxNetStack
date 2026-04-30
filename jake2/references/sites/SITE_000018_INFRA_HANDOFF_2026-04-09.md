# Site 000018 Infrastructure Handoff

Current read:
- `000018` is infrastructure-heavy and currently reads as a low-signal / no-customer-visible site from the local customer sources.
- NetBox infrastructure in scope: `Cable Mgmt=2`, `Digi=1`, `OLT=1`, `Power-Distribution=2`, `Patch Panel=1`, `Router=1`.

Field handoff:
- Start with power distribution and confirm the OLT/router shelf is energized.
- Check the patch panel path before assuming upstream fiber or routing failure.
- Inspect cable management for disturbed or cross-connected local handoffs.
- Treat Digi reachability as management-only and not proof of subscriber service.

Good Jake follow-ups:
- `give me the site infrastructure handoff for 000018`
- `which power, patch-panel, or shelf issues could block recovery at 000018?`
- `what can you tell me about 000018?`

