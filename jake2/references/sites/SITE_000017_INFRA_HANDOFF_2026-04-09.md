# Site 000017 Infrastructure Handoff

Current read:
- `000017` is an OLT site with live customer presence and active optics alerts.
- NetBox infrastructure in scope: `Digi=1`, `Patch Panel=1`, `OLT=1`, `Router=1`.
- Current top optical work item: `000017.OLT1` `PON 6`.

Field handoff:
- Verify the OLT/router shelf is actually powered and patched before assuming the problem is downstream only.
- Check the local patch panel path for mislabeled, loose, or crossed jumpers.
- Treat Digi reachability as management-only evidence, not proof that the subscriber path is healthy.
- Work the strongest optical concentration first, then validate the local patch path into that PON.

Good Jake follow-ups:
- `what should the field team check physically at 000017?`
- `which PON port is the current top optical work item at 000017?`
- `show the light levels at 000017`

