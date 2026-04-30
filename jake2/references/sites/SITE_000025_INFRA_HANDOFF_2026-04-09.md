# Site 000025 Infrastructure Handoff

Current read:
- `000025` is a compact single-building infrastructure-handoff site.
- NetBox infrastructure in scope: `Digi=1`, `Cable Mgmt=1`, `Power-Distribution=1`, `Patch Panel=1`, `shelf=1`, `Power-backup=1`, `OLT=1`, `Router=1`.

Field handoff:
- Start with power distribution and backup power, then confirm the OLT/router shelf is actually energized.
- Check the patch panel and cable management path for local handoff mistakes before assuming upstream failure.
- Use Digi only as management-plane evidence.
- If customer impact is reported, validate the local optical handoff path into the single OLT first.

Good Jake follow-ups:
- `give me the site infrastructure handoff for 000025`
- `what should the field team check physically at 000025?`
- `what can you tell me about 000025?`

