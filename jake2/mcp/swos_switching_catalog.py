from __future__ import annotations

from typing import Any


def _tool(
    name: str,
    summary: str,
    impact: str,
    invoke_when: list[str],
    diagnostic_reads: list[str],
    decision_tree: list[str],
    likely_root_cause: list[str],
    safe_fix: list[str],
    rollback: list[str],
    *,
    applies_to: list[str] | None = None,
    avoid_when: list[str] | None = None,
    references: list[str] | None = None,
    confidence: str = "high",
) -> dict[str, Any]:
    return {
        "tool_name": name,
        "intent_group": "switching_l2_swos",
        "summary": summary,
        "impact": impact,
        "applies_to": applies_to or ["CRS1xx/2xx running SwOS"],
        "invoke_when": invoke_when,
        "avoid_when": avoid_when or [],
        "diagnostic_reads": diagnostic_reads,
        "decision_tree": decision_tree,
        "likely_root_cause": likely_root_cause,
        "safe_fix": safe_fix,
        "rollback": rollback,
        "references": references or ["SwOS field observations", "SwitchOS edge access notes"],
        "confidence": confidence,
    }


SWOS_SWITCHING_SCENARIOS: dict[str, dict[str, Any]] = {
    "diagnose_swos_dhcp_snooping_acl_tag_cpu_interaction": _tool(
        name="diagnose_swos_dhcp_snooping_acl_tag_cpu_interaction",
        summary="DHCP snooping and ACL/tag-to-CPU behavior interact badly on SwOS access switches, causing DHCP or control-plane weirdness.",
        impact="high",
        invoke_when=[
            "DHCP behaves inconsistently only on SwOS access edge",
            "ACL or CPU-directed handling is enabled",
            "offers or relayed packets disappear on the switch path",
        ],
        diagnostic_reads=["/sys.b", "/link.b", "/vlan.b", "/!dhost.b"],
        decision_tree=[
            "If the switch is RouterOS, use RouterOS switching tools instead.",
            "If packet loss appears only on SwOS edge with snooping/ACL behavior, treat this as a SwOS interaction first.",
        ],
        likely_root_cause=["SwOS snooping plus ACL/tag-to-CPU interaction on access edge"],
        safe_fix=["Simplify the policy path on the affected switch.", "Disable the conflicting feature combination during validation."],
        rollback=["Restore previous SwOS export/settings if the simplified path is wrong."],
    ),
    "diagnose_swos_tx_flow_control_pause_frames": _tool(
        name="diagnose_swos_tx_flow_control_pause_frames",
        summary="Unexpected pause-frame or flow-control behavior on SwOS causes weird subscriber-edge throughput collapse or bursty stalls.",
        impact="medium",
        invoke_when=[
            "traffic stalls intermittently with link still up",
            "symptom is port-local and not explained by routing/policy",
            "problem tracks SwOS switch path or specific edge port",
        ],
        diagnostic_reads=["/link.b", "/sys.b"],
        decision_tree=[
            "If the issue is site-wide and not edge-port-local, this is a weak fit.",
            "If the failure is bursty and looks physical without total link drop, inspect flow control state.",
        ],
        likely_root_cause=["SwOS port flow-control/pause-frame behavior causing edge stalls"],
        safe_fix=["Disable the problematic flow-control mode on affected edge path if supported and safe.", "Validate one port at a time."],
        rollback=["Restore original flow-control setting if packet loss or contention worsens."],
        confidence="medium",
    ),
    "diagnose_swos_vlan_pvid_access_trunk_mismatch": _tool(
        name="diagnose_swos_vlan_pvid_access_trunk_mismatch",
        summary="Classic SwOS VLAN table or PVID mismatch on access/trunk ports.",
        impact="high",
        invoke_when=[
            "single subscriber port lands on wrong VLAN",
            "port is up but service identity is wrong or absent",
            "switch uses SwOS VLAN tables, not RouterOS bridge VLAN config",
        ],
        diagnostic_reads=["/vlan.b", "/link.b", "/!dhost.b"],
        decision_tree=[
            "If this is RouterOS bridge config, use RouterOS switching MCP instead.",
            "If one SwOS port behaves like a trunk when it should be access, or vice versa, use this tool.",
        ],
        likely_root_cause=["Wrong PVID", "Wrong untagged/tagged membership", "SwOS VLAN table drift"],
        safe_fix=["Correct only the affected port VLAN role first.", "Verify host learning on the corrected port before broader edits."],
        rollback=["Restore original VLAN row or port membership if the wrong edge was modified."],
    ),
    "diagnose_swos_host_table_port_misalignment": _tool(
        name="diagnose_swos_host_table_port_misalignment",
        summary="SwOS host table shows the wrong subscriber or adjacent-unit MAC on a labeled port, pointing to wrong-port field patching or label drift.",
        impact="high",
        invoke_when=[
            "port label and learned MAC identity disagree",
            "adjacent unit appears on labeled port",
            "field patching or comment accuracy is suspect",
        ],
        diagnostic_reads=["/!dhost.b", "/link.b"],
        decision_tree=[
            "If there is no learned MAC and no link, this becomes an offline-port case instead.",
            "If the host table clearly shows the neighbor unit on the labeled port, prefer wrong-port diagnosis over controller guessing.",
        ],
        likely_root_cause=["Wrong customer patch", "Label drift", "Neighbor port used instead of intended edge"],
        safe_fix=["Do not move unrelated ports blindly.", "Mark the port clearly and send field cleanup to the exact edge."],
        rollback=["No config rollback beyond removing temporary label/comment changes."],
    ),
    "diagnose_swos_offline_port_candidate": _tool(
        name="diagnose_swos_offline_port_candidate",
        summary="Port is enabled but no-link, making it a likely offline or power-off customer candidate rather than a duplicate-MAC case.",
        impact="medium",
        invoke_when=[
            "subscriber is missing from controller/router plane",
            "best inferred access port is enabled but no-link",
            "no host-table evidence exists for the target unit",
        ],
        diagnostic_reads=["/link.b", "/!dhost.b"],
        decision_tree=[
            "If another unit is learned on the port, use wrong-port or host-misalignment logic instead.",
            "If the port is simply dark, treat it as offline-field candidate first.",
        ],
        likely_root_cause=["Customer CPE unplugged", "No power", "Dark drop", "Wrong inferred port only if surrounding evidence is weak"],
        safe_fix=["Label the port as no-link candidate.", "Do not move VLANs until link appears unless a recovery workflow explicitly requires it."],
        rollback=["Remove temporary labels if better identity evidence appears later."],
    ),
    "diagnose_swos_duplicate_mac_single_cpe_pattern": _tool(
        name="diagnose_swos_duplicate_mac_single_cpe_pattern",
        summary="Multiple adjacent same-vendor MACs on one SwOS port likely represent one physical CPE with multiple interfaces, not multiple subscribers.",
        impact="medium",
        invoke_when=[
            "same-vendor MACs differ by adjacent or small offset",
            "all sightings are on one edge port",
            "operator is tempted to over-count physical CPEs",
        ],
        diagnostic_reads=["/!dhost.b"],
        decision_tree=[
            "If MACs are mixed unrelated OUIs, use dirty-segment logic instead.",
            "If adjacent same-vendor MACs stay on one edge, classify as likely single CPE first.",
        ],
        likely_root_cause=["Single physical HC220 or similar CPE exposing multiple interface MACs"],
        safe_fix=["Do not disable the port just because two MACs exist.", "Correlate DHCP direction or controller identity before escalating."],
        rollback=["No rollback; this is classification guidance."],
        confidence="medium",
    ),
    "diagnose_swos_dirty_segment_mixed_macs": _tool(
        name="diagnose_swos_dirty_segment_mixed_macs",
        summary="Mixed unrelated MACs on one SwOS access port indicate dirty segment, bridge leakage, or LAN/WAN mispatch.",
        impact="high",
        invoke_when=[
            "multiple unrelated MAC families appear on one customer port",
            "port should be single-subscriber edge",
            "behavior looks like unmanaged switch, wrong-port patching, or leak",
        ],
        diagnostic_reads=["/!dhost.b", "/link.b"],
        decision_tree=[
            "If only adjacent same-vendor MACs are present, use single-CPE duplicate-MAC tool instead.",
            "If many unrelated MACs exist on a supposed access port, prioritize containment and wrong-port suspicion.",
        ],
        likely_root_cause=["Dirty downstream segment", "LAN/WAN mispatch", "Transparent bridge or unmanaged switch behind CPE"],
        safe_fix=["Remove the port from special recovery lanes first.", "Label as wrong-port or dirty-segment candidate once evidence is strong."],
        rollback=["Restore normal VLAN role only after contamination is understood."],
    ),
    "diagnose_swos_ring_rstp_blocking_context": _tool(
        name="diagnose_swos_ring_rstp_blocking_context",
        summary="Understand whether SwOS ring-side port blocking is expected RSTP behavior or a bad edge symptom.",
        impact="medium",
        invoke_when=[
            "operator sees blocked/discarding behavior on ring-side switch path",
            "site uses ring or redundant L2 paths",
            "needs separation of expected protection from real outage",
        ],
        diagnostic_reads=["/link.b", "/sys.b"],
        decision_tree=[
            "If the blocked port is protecting a redundant ring path, that may be normal.",
            "If an access edge is blocked instead of a ring-side path, investigate misconfiguration or topology drift.",
        ],
        likely_root_cause=["Expected RSTP protection in ring", "Unexpected topology drift causing wrong port role"],
        safe_fix=["Do not force-enable blocked ring ports blindly.", "Verify which port should block before changing anything."],
        rollback=["Undo any temporary spanning-tree changes immediately if loop risk increases."],
        confidence="medium",
    ),
}


def scenario_tool_names() -> list[str]:
    return list(SWOS_SWITCHING_SCENARIOS.keys())
