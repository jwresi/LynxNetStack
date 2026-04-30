# cnWave cnMaestro And E2E Management Notes

- Source URLs:
  - https://docs.cloud.cambiumnetworks.com/help/5.2.0/Content/UG_files/Onboarding%20Devices/E2E%20Controller.htm
  - https://docs.cloud.cambiumnetworks.com/help/3.1.1/Content/UG_files/Onboarding%20Devices/E2E%20Controller.htm
- Source type: official documentation
- Intake date: 2026-04-10
- Use for: cnWave onboarding, cnMaestro vs E2E controller roles, management-plane expectations

## High-signal points for Jake

1. cnMaestro management for cnWave depends on E2E controller onboarding.
- cnWave devices are managed through an onboard or external E2E controller
- after onboarding succeeds, the network is managed through cnMaestro

2. The official UI path for onboarding is:
- `Monitor and Manage > Network > select 60 GHz cnWave E2E Network`

3. Onboard E2E controller can run directly on a cnWave device.
- useful for smaller deployments
- the PoP node can host the onboard E2E controller

4. Operational implication:
- cnMaestro is not the same thing as the E2E controller
- when Jake reasons about cnWave management reachability, he should distinguish:
  - exporter metrics
  - cnMaestro management plane
  - E2E controller communication path

5. What this officially proves:
- the controller and onboarding relationship
- the management path for cnWave networks through cnMaestro after onboarding

6. What this does not officially prove:
- the exact remote-command inventory like `Show IPv4 Neighbors`
- per-radio neighbor-table visibility details

## Jake operator read

Jake should use this doc to explain:

- why cnWave management depends on successful E2E onboarding
- why cnMaestro visibility and radio-local visibility are not the same thing
- why controller-side commands may fail even when exporter metrics still exist

## Why this belongs in RAG

This is stable vendor management-plane doctrine and should shape Jake's cnWave controller explanations.
