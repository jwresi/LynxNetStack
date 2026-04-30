# TP-Link HC220-G5 Official Notes

- Source URLs:
  - https://www.tp-link.com/us/service-provider/managed-wifi-for-isp/hc220-g5/
  - https://www.tp-link.com/us/support/download/hc220-g5/
  - https://static.tp-link.com/upload/manual/2022/202203/20220308/UG_HC220-G5_%28V1%29.pdf
- Source type: official product page, support page, and user guide
- Intake date: 2026-04-10
- Use for: HC220 capability framing, local management expectations, TAUC/cloud management expectations

## High-signal points for Jake

1. HC220-G5 is an ISP-managed mesh/AP platform.

2. The official product/support material explicitly points to:
- TP-Link Aginet Unified Cloud (TAUC)
- app-based and web-interface setup
- router mode and access point mode
- EasyMesh / unified SSID behavior

3. Operationally important management facts:
- the product is meant to be remotely managed through the TP-Link ISP/Aginet stack
- official support/download material exists for manual, firmware, app, and emulators
- this supports Jake's current model that HC220 is controller-first, not purely local-first

4. Local behavior that matters for field work:
- HC220 can operate in router mode or AP mode
- seamless mesh / unified SSID behavior can make unit identity confusing in the field if the wrong node is being validated
- local web interface exists in the official user-guide framing, but Jake still needs a direct local on-box adapter in this repo to use it operationally

## Jake operator read

Jake should continue to model HC220 like this:

- primary management truth: TAUC / provider management plane
- useful local truth: local WAN IP, local setup state, edge switch or OLT correlation
- current repo gap: a read-only direct local HC220 adapter is still needed for on-box inspection

## Why this belongs in RAG

This is stable vendor/product behavior and should inform how Jake explains HC220 management and setup.
