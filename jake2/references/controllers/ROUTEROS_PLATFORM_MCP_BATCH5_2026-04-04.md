# RouterOS Platform MCP · Batch 5

Platform and upgrade-risk scenarios for RouterOS hardware roles.

Included in this batch:

- `diagnose_ccr2004_upgrade_nand_disk_space_failure`
- `diagnose_device_mode_blocking_features_7_17`
- `diagnose_rb5009_l2mtu_change_7_21`
- `diagnose_poe_firmware_update_power_interruption_7_22`
- `diagnose_arm64_unbalanced_cpu_load_rps`
- `diagnose_routerboard_firmware_upgrade_required`
- `diagnose_local_package_mirror_upgrade`
- `diagnose_l009_arm64_migration_path`
- `diagnose_crs3xx_switch_marvell_firmware_7_22`
- `diagnose_upgrade_channel_strategy_wisp`
- `diagnose_protected_routerboot_flagging`

Intent:

- answer upgrade-risk questions without dumping a raw site summary
- catch hardware-specific traps before maintenance windows
- give Jake a clean place for CCR2004/RB5009/L009/RouterBOARD lifecycle reasoning
