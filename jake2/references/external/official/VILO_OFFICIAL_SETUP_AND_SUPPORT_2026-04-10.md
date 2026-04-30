# Vilo Official Setup And Support Notes

- Source URLs:
  - https://support.viloliving.com/hc/en-us/articles/4402320462487-Setting-Up-Your-Vilo-system
  - https://support.viloliving.com/hc/en-us/articles/5903337237399-How-To-Set-Up-Vilo-With-a-Static-IP
  - https://support.viloliving.com/hc/en-us/articles/10628535812375-How-To-Submit-A-Local-Log-From-The-Vilo-App
  - https://support.viloliving.com/hc/en-us/articles/4402479481879-Does-Vilo-support-IPv6
- Source type: official vendor support articles
- Intake date: 2026-04-10
- Use for: Vilo setup behavior, static-IP workflow, support/log workflow, IPv4/IPv6 capability notes

## High-signal points for Jake

1. Vilo setup is app-led first.
- the official setup flow depends on the Vilo App
- the device is linked to the account/network during activation

2. WAN modes matter.
- Vilo setup behavior differs for DHCP, PPPoE, and static IP
- static IP setup and WAN setting changes are explicitly handled in the app flow

3. Local log collection exists.
- Vilo's official support flow includes submitting a local log from the app
- this is useful when the network appears offline in the app

4. IPv6 is model-sensitive.
- Vilo Mesh Wi‑Fi 5 supports IPv4 only
- Vilo 6 supports both IPv4 and IPv6

## Jake operator read

Jake should continue to treat Vilo as:

- primary management truth: Vilo app / cloud / portal surfaces
- useful field truth: local setup SSID/default password, WAN mode, and support-log workflow
- current repo gap: Jake still needs a direct local Vilo adapter instead of relying mostly on controller-side state

## Why this belongs in RAG

This is stable vendor behavior for setup and support. It should shape Jake's explanations and troubleshooting order for Vilo deployments.
