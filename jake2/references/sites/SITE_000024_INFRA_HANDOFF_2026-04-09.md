# Site 000024 Infrastructure Handoff

Current read:
- `000024` is the heaviest infrastructure-handoff site in the current thin-coverage group.
- NetBox infrastructure in scope: `Cable Mgmt=1`, `OLT=3`, `Power-Distribution=1`, `Patch Panel=1`, `Power-backup=4`, `Router=1`, `shelf=1`, `Digi=1`.
- Building split in NetBox:
  - Building A carries the main patch/power/router/shelf footprint.
  - Buildings B and C each carry an OLT plus backup power.

Field handoff:
- Verify Building A power, patch panel, router, and shelf first because that is the densest shared infrastructure.
- Then confirm Buildings B and C are individually powered and that each OLT/UPS pair is live.
- Check the patch-panel path before escalating to upstream fiber theory.
- Inspect cable management and shelf layout for disturbed local handoffs.

Good Jake follow-ups:
- `which power, patch-panel, or shelf issues could block recovery at 000024?`
- `give me the site infrastructure handoff for 000024`
- `what can you tell me about 000024?`

