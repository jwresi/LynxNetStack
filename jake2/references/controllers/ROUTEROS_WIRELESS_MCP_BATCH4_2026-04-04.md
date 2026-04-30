# RouterOS Wireless MCP · Batch 4

`routeros_wireless_mcp` covers MikroTik wireless access and CAPsMAN troubleshooting by operator intent.

## Scope
- driver package capability matrix and decision gate
- wifi-qcom-ac vs wifi-qcom forwarding limitations
- CAPsMAN v1 to v2 migration traps
- CAPsMAN v2 provisioning and VLAN local-forwarding patterns
- iOS and Apple roaming/client compatibility issues
- hotspot MAC-randomization session churn
- community/campus WiFi roaming-domain design

## Included scenarios
- `diagnose_wireless_driver_package_selection`
- `diagnose_wifi_qcom_ac_capsman_forwarding_not_supported`
- `diagnose_wifi_qcom_capsman_forwarding_version_gate`
- `diagnose_ios_cannot_connect_capsman_7_22`
- `diagnose_capsman_v1_to_v2_migration_traps`
- `diagnose_capsman_v2_provisioning_not_applying`
- `diagnose_ft_over_ds_ios_incompatibility`
- `diagnose_capsman_v2_vlan_local_forwarding_pattern`
- `diagnose_capsman_client_flapping`
- `diagnose_hap_ax2_2g_radio_broken_7_18`
- `diagnose_hotspot_mac_randomization_session_conflict`
- `diagnose_legacy_capsman_v1_vlan_config`
- `design_capsman_community_wifi_roaming_domain`
