from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, cast

from diagnosis.evidence import RealityModel, UnitEvidence, build_reality_model


Confidence = Literal["high", "medium", "low"]
DispatchPriority = Literal["none", "low", "medium", "high"]
PrimaryStatus = Literal[
    "HEALTHY",
    "NOT_SEEN_ANYWHERE",
    "L2_PRESENT_NO_SERVICE",
    "DEGRADED_LINK_BAD_CABLE_SUSPECTED",
    "CONTROLLER_MAPPING_MISMATCH",
    "INVENTORY_MAC_MISMATCH",
    "DEVICE_SWAPPED_OR_WRONG_UNIT",
    "PPPoE_AUTH_FAILURE",
    "PPPoE_NO_ATTEMPT",
    "DHCP_NO_OFFER",
    "DHCP_ROGUE_OR_WRONG_SERVER",
    "SWITCH_PORT_DISABLED_OR_WRONG_VLAN",
    "CONTROLLER_STALE_DEVICE",
    "NEEDS_MORE_EVIDENCE",
]


@dataclass(slots=True)
class Diagnosis:
    unit: str
    observed_state: str
    primary_status: PrimaryStatus
    secondary_statuses: list[str] = field(default_factory=list)
    confidence: Confidence = "low"
    evidence_used: list[str] = field(default_factory=list)
    evidence_missing: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    likely_causes: list[str] = field(default_factory=list)
    backend_actions: list[str] = field(default_factory=list)
    field_actions: list[str] = field(default_factory=list)
    dispatch_required: bool = False
    dispatch_priority: DispatchPriority = "none"
    explanation: str = ""
    next_best_check: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _truth(reality: RealityModel, layer: str) -> dict[str, Any]:
    return cast(dict[str, Any], getattr(reality, layer))


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_mac(value: Any) -> str:
    return _text(value).lower().replace("-", ":")


def _bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _evidence_used(reality: RealityModel) -> list[str]:
    used: list[str] = []
    for layer_name in (
        "inventory_truth",
        "physical_truth",
        "l2_truth",
        "controller_truth",
        "auth_truth",
        "dhcp_truth",
        "service_truth",
    ):
        for source in list(_truth(reality, layer_name).get("evidence_sources") or []):
            text = _text(source)
            if text and text not in used:
                used.append(text)
    return used


def _evidence_missing(reality: RealityModel) -> list[str]:
    return [item for item in reality.unknowns if _text(item)]


def _contradictions(reality: RealityModel) -> list[str]:
    return [item for item in reality.contradictions if _text(item)]


def _has_hard_contradictions(reality: RealityModel) -> bool:
    soft_markers = {
        "mac is present at l2, but pppoe is expected and no pppoe attempt is visible.",
    }
    contradictions = [item for item in _contradictions(reality) if _text(item)]
    if not contradictions:
        return False
    return any(_text(item).lower() not in soft_markers for item in contradictions)


def _l2_present(reality: RealityModel) -> bool:
    l2 = _truth(reality, "l2_truth")
    if l2.get("live_mac_seen") is True:
        return True
    if l2.get("expected_mac_seen") is True:
        return True
    if _text(l2.get("live_mac")):
        return True
    return bool(l2.get("expected_mac_locations") or [])


def _service_success(reality: RealityModel) -> bool:
    auth = _truth(reality, "auth_truth")
    dhcp = _truth(reality, "dhcp_truth")
    service = _truth(reality, "service_truth")
    if auth.get("pppoe_active") is True:
        return True
    offers_seen = dhcp.get("dhcp_offers_seen")
    if offers_seen is None:
        offers_seen = dhcp.get("offers_seen")
    if _int(offers_seen) > 0:
        return True
    if _text(service.get("service_ip")):
        return True
    if service.get("gateway_reachable") is True:
        return True
    if service.get("customer_traffic_seen") is True:
        return True
    return False


def _global_search_complete(reality: RealityModel) -> bool:
    l2 = _truth(reality, "l2_truth")
    return (
        l2.get("expected_port_checked") is True
        and l2.get("switch_scope_checked") is True
        and l2.get("global_scope_checked") is True
        and l2.get("historical_checked") is True
    )


def _controller_mapping_mismatch(reality: RealityModel) -> bool:
    controller = _truth(reality, "controller_truth")
    return controller.get("controller_seen") is True and controller.get("mapping_matches_inventory") is False


def _controller_stale(reality: RealityModel) -> bool:
    controller = _truth(reality, "controller_truth")
    if controller.get("controller_stale") is True:
        return True
    for item in reality.stale_data_sources:
        if item.startswith("controller_truth."):
            return True
    return False


def _pppoe_active(reality: RealityModel) -> bool:
    return _truth(reality, "auth_truth").get("pppoe_active") is True


def _pppoe_failed(reality: RealityModel) -> bool:
    auth = _truth(reality, "auth_truth")
    if auth.get("pppoe_failed_attempts_seen") is True:
        return True
    if auth.get("pppoe_failures"):
        return True
    return _text(auth.get("pppoe_failure_reason")).lower() in {
        "auth_failed",
        "authentication_failed",
        "radius_reject",
        "auth_reject",
        "timeout",
        "no_response",
    }


def _pppoe_no_attempt(reality: RealityModel) -> bool:
    auth = _truth(reality, "auth_truth")
    return auth.get("pppoe_no_attempt_evidence") is True


def _dhcp_rogue(reality: RealityModel) -> bool:
    dhcp = _truth(reality, "dhcp_truth")
    if dhcp.get("rogue_dhcp_detected") is True or dhcp.get("rogue_dhcp_suspected") is True:
        return True
    offer_source = _text(dhcp.get("dhcp_offer_source")).lower()
    expected_server = _text(dhcp.get("dhcp_expected_server") or dhcp.get("dhcp_server")).lower()
    return bool(offer_source and expected_server and offer_source != expected_server)


def _dhcp_no_offer(reality: RealityModel) -> bool:
    dhcp = _truth(reality, "dhcp_truth")
    if dhcp.get("dhcp_expected") is not True:
        return False
    discovers = dhcp.get("dhcp_discovers_seen")
    if discovers is None:
        discovers = dhcp.get("discovers_seen")
    offers = dhcp.get("dhcp_offers_seen")
    if offers is None:
        offers = dhcp.get("offers_seen")
    return _int(discovers) > 0 and _int(offers) <= 0


def _expected_speed_hint(reality: RealityModel) -> str | None:
    inventory = _truth(reality, "inventory_truth")
    model = _text(inventory.get("expected_model") or inventory.get("expected_make")).lower()
    if any(token in model for token in ("1g", "gig", "hc220", "vilo", "tp-link", "tplink")):
        return "1G"
    return None


def _degraded_link(reality: RealityModel) -> bool:
    auth = _truth(reality, "auth_truth")
    if _pppoe_failed(reality):
        return False
    physical = _truth(reality, "physical_truth")
    speed = _text(physical.get("port_speed")).upper()
    expected_speed = _expected_speed_hint(reality)
    if expected_speed == "1G" and speed == "100M":
        return True
    flap_count = _int(physical.get("link_flaps") or physical.get("port_flaps"))
    if flap_count > 0:
        return True
    error_total = _int(physical.get("rx_errors")) + _int(physical.get("tx_errors")) + _int(physical.get("fcs_errors")) + _int(physical.get("crc_errors"))
    for value in dict(physical.get("port_errors") or {}).values():
        error_total += _int(value)
    if error_total > 0:
        return True
    return bool(list(physical.get("cable_degraded_signal") or [])) and auth.get("pppoe_failed_attempts_seen") is not True


def _live_mac_differs_from_inventory(reality: RealityModel) -> bool:
    inventory = _truth(reality, "inventory_truth")
    l2 = _truth(reality, "l2_truth")
    expected = _normalized_mac(inventory.get("expected_mac"))
    live = _normalized_mac(l2.get("live_mac"))
    return bool(expected and live and expected != live)


def _expected_mac_found_elsewhere(reality: RealityModel) -> str | None:
    inventory = _truth(reality, "inventory_truth")
    l2 = _truth(reality, "l2_truth")
    expected_mac = _normalized_mac(inventory.get("expected_mac"))
    expected_switch = _text(inventory.get("expected_switch"))
    expected_port = _text(inventory.get("expected_port"))
    for location in list(l2.get("expected_mac_locations") or []):
        if _normalized_mac(location.get("mac")) != expected_mac:
            continue
        switch = _text(location.get("switch"))
        port = _text(location.get("port"))
        if expected_port and port and port != expected_port:
            return f"{switch} {port}".strip()
        if expected_switch and switch and switch != expected_switch:
            return f"{switch} {port}".strip()
    return None


def _wrong_mac_on_expected_port(reality: RealityModel) -> bool:
    inventory = _truth(reality, "inventory_truth")
    l2 = _truth(reality, "l2_truth")
    expected_mac = _normalized_mac(inventory.get("expected_mac"))
    live_mac = _normalized_mac(l2.get("live_mac"))
    if not expected_mac or not live_mac or expected_mac == live_mac:
        return False
    if l2.get("any_mac_on_expected_port") is True:
        return True
    expected_port = _text(inventory.get("expected_port"))
    return bool(expected_port and _text(l2.get("live_port")) == expected_port)


def _inventory_mismatch(reality: RealityModel) -> bool:
    return _live_mac_differs_from_inventory(reality)


def _switch_port_or_vlan_issue(reality: RealityModel) -> bool:
    inventory = _truth(reality, "inventory_truth")
    physical = _truth(reality, "physical_truth")
    l2 = _truth(reality, "l2_truth")
    if not _text(inventory.get("expected_port")):
        return False
    if physical.get("port_up") is False:
        return True
    expected_vlan = _text(inventory.get("expected_vlan"))
    live_vlan = _text(l2.get("live_vlan"))
    return bool(expected_vlan and live_vlan and expected_vlan != live_vlan)


def _observed_state(reality: RealityModel) -> str:
    bits: list[str] = []
    bits.append("L2 present" if _l2_present(reality) else "L2 absent")
    physical = _truth(reality, "physical_truth")
    if physical.get("port_up") is True:
        bits.append("port up")
    elif physical.get("port_up") is False:
        bits.append("port down")
    if _pppoe_active(reality):
        bits.append("PPPoE active")
    elif _pppoe_failed(reality):
        bits.append("PPPoE failures seen")
    elif _pppoe_no_attempt(reality):
        bits.append("no PPPoE attempt")
    if _service_success(reality):
        bits.append("service evidence present")
    else:
        bits.append("no service success")
    return ", ".join(bits)


def _confidence(
    reality: RealityModel,
    *,
    strong_signals: int,
    critical_missing: int = 0,
    force_low: bool = False,
) -> Confidence:
    if force_low or _has_hard_contradictions(reality):
        return "low"
    if strong_signals >= 2 and critical_missing == 0 and not reality.stale_data_sources:
        return "high"
    if strong_signals >= 1:
        return "medium"
    return "low"


def _build(
    reality: RealityModel,
    *,
    primary_status: PrimaryStatus,
    likely_causes: list[str],
    backend_actions: list[str],
    field_actions: list[str],
    dispatch_required: bool,
    dispatch_priority: DispatchPriority,
    explanation: str,
    next_best_check: str,
    secondary_statuses: list[str] | None = None,
    strong_signals: int = 1,
    critical_missing: int = 0,
    force_low_confidence: bool = False,
) -> Diagnosis:
    return Diagnosis(
        unit=reality.unit,
        observed_state=_observed_state(reality),
        primary_status=primary_status,
        secondary_statuses=list(secondary_statuses or []),
        confidence=_confidence(
            reality,
            strong_signals=strong_signals,
            critical_missing=critical_missing,
            force_low=force_low_confidence,
        ),
        evidence_used=_evidence_used(reality),
        evidence_missing=_evidence_missing(reality),
        contradictions=_contradictions(reality),
        likely_causes=likely_causes,
        backend_actions=backend_actions,
        field_actions=field_actions,
        dispatch_required=dispatch_required,
        dispatch_priority=dispatch_priority,
        explanation=explanation,
        next_best_check=next_best_check,
    )


def diagnose(reality: RealityModel) -> Diagnosis:
    l2_present = _l2_present(reality)
    service_success = _service_success(reality)
    inventory = _truth(reality, "inventory_truth")
    controller = _truth(reality, "controller_truth")
    auth = _truth(reality, "auth_truth")
    dhcp = _truth(reality, "dhcp_truth")
    physical = _truth(reality, "physical_truth")

    if _has_hard_contradictions(reality):
        return _build(
            reality,
            primary_status="NEEDS_MORE_EVIDENCE",
            likely_causes=["Contradictory evidence prevents a deterministic diagnosis."],
            backend_actions=[],
            field_actions=[],
            dispatch_required=False,
            dispatch_priority="none",
            explanation="The reality model conflicts with itself, so Jake should not choose a root cause yet.",
            next_best_check="Resolve the contradictory controller, L2, auth, or DHCP evidence before diagnosing.",
            strong_signals=0,
            critical_missing=1 if not _global_search_complete(reality) else 0,
            force_low_confidence=True,
        )

    if not l2_present:
        if _switch_port_or_vlan_issue(reality):
            return _build(
                reality,
                primary_status="SWITCH_PORT_DISABLED_OR_WRONG_VLAN",
                likely_causes=["The expected access path is not carrying service because the port is down/disabled or VLAN placement is wrong."],
                backend_actions=["Verify the switch port administrative state and VLAN membership on the expected access path."],
                field_actions=[],
                dispatch_required=False,
                dispatch_priority="none",
                explanation="The expected access port has a backend-configurable state problem that can block service before field dispatch is needed.",
                next_best_check="Confirm the expected port is enabled and in the correct VLAN or service profile.",
                strong_signals=2,
            )
        if not _global_search_complete(reality):
            return _build(
                reality,
                primary_status="NEEDS_MORE_EVIDENCE",
                likely_causes=["The device is not visible at L2, but the global MAC search is incomplete."],
                backend_actions=[],
                field_actions=[],
                dispatch_required=False,
                dispatch_priority="none",
                explanation="Jake cannot classify the device as missing while expected-port, switch-wide, global, or historical MAC searches are incomplete.",
                next_best_check="Complete expected-port, whole-switch, all-switch, and historical MAC searches.",
                strong_signals=0,
                critical_missing=1,
            )
        return _build(
            reality,
            primary_status="NOT_SEEN_ANYWHERE",
            likely_causes=[
                "The expected device is not visible in live MAC, controller, auth, or DHCP evidence after full search.",
                "Possible causes include unplugged device, no power, not installed, dead CPE, or wrong inventory MAC.",
            ],
            backend_actions=["Re-check inventory/controller correctness before dispatch if those records are weak or stale."],
            field_actions=["Verify the device is physically present and powered.", "Check the patch cable, jack, and device label onsite."],
            dispatch_required=True,
            dispatch_priority="medium",
            explanation="The device is not seen anywhere after the required L2 search sequence completed.",
            next_best_check="Confirm the physical device label/MAC onsite and compare it with inventory.",
            strong_signals=2,
            critical_missing=0 if not reality.unknowns else 1,
        )

    secondary: list[str] = []
    if _controller_stale(reality):
        secondary.append("CONTROLLER_STALE_DEVICE")

    if _controller_mapping_mismatch(reality):
        return _build(
            reality,
            primary_status="CONTROLLER_MAPPING_MISMATCH",
            likely_causes=["Controller assignment does not match the expected unit/subscriber mapping."],
            backend_actions=["Correct the controller subscriber/unit mapping before dispatching field work."],
            field_actions=[],
            dispatch_required=False,
            dispatch_priority="none",
            explanation="The controller knows the device, but it is mapped to the wrong unit or subscriber.",
            next_best_check="Verify controller assignment against inventory and service records.",
            secondary_statuses=secondary,
            strong_signals=2,
        )

    if _pppoe_active(reality) and service_success:
        return _build(
            reality,
            primary_status="HEALTHY",
            likely_causes=["Inventory, L2 presence, and service/auth evidence align."],
            backend_actions=[],
            field_actions=[],
            dispatch_required=False,
            dispatch_priority="none",
            explanation="The unit is present at L2 and has active service evidence.",
            next_best_check="No immediate fault check is required.",
            secondary_statuses=secondary,
            strong_signals=3,
        )

    if _pppoe_failed(reality):
        return _build(
            reality,
            primary_status="PPPoE_AUTH_FAILURE",
            likely_causes=["PPPoE attempts are present but authentication is failing."],
            backend_actions=["Check the PPPoE username, password, account state, and RADIUS/Splynx status."],
            field_actions=[],
            dispatch_required=False,
            dispatch_priority="none",
            explanation="The device is present and attempting PPPoE, but the attempts are failing instead of succeeding.",
            next_best_check="Review the most recent PPPoE failure reason and verify the subscriber account state.",
            secondary_statuses=secondary,
            strong_signals=2,
        )

    if _dhcp_rogue(reality):
        return _build(
            reality,
            primary_status="DHCP_ROGUE_OR_WRONG_SERVER",
            likely_causes=["DHCP offers are arriving from an unexpected or rogue server."],
            backend_actions=["Verify the intended DHCP server and VLAN or broadcast-domain boundaries."],
            field_actions=[],
            dispatch_required=False,
            dispatch_priority="none",
            explanation="The device is present, but DHCP behavior shows the wrong server answering.",
            next_best_check="Compare the observed DHCP offer source to the expected DHCP server.",
            secondary_statuses=secondary,
            strong_signals=2,
        )

    if _dhcp_no_offer(reality):
        return _build(
            reality,
            primary_status="DHCP_NO_OFFER",
            likely_causes=["DHCP discovers are visible but no valid offer is being returned."],
            backend_actions=["Check DHCP server reachability, relay policy, and VLAN configuration."],
            field_actions=[],
            dispatch_required=False,
            dispatch_priority="none",
            explanation="The device is active enough to send DHCP discovers, but the expected DHCP response is missing.",
            next_best_check="Verify whether the correct DHCP server or relay is receiving the discover traffic.",
            secondary_statuses=secondary,
            strong_signals=2,
        )

    if _degraded_link(reality):
        likely_causes = ["Physical link evidence suggests a degraded cable or unstable in-unit path."]
        if _text(physical.get("port_speed")).upper() == "100M" and _expected_speed_hint(reality) == "1G":
            likely_causes.append("The link negotiated at 100M where 1G is expected.")
        if _int(physical.get("link_flaps") or physical.get("port_flaps")) > 0:
            likely_causes.append("The link is flapping.")
        if _int(physical.get("rx_errors")) + _int(physical.get("tx_errors")) + _int(physical.get("fcs_errors")) + _int(physical.get("crc_errors")) > 0:
            likely_causes.append("Physical port errors are present.")
        return _build(
            reality,
            primary_status="DEGRADED_LINK_BAD_CABLE_SUSPECTED",
            likely_causes=likely_causes,
            backend_actions=["Verify the port profile and expected speed before dispatching."],
            field_actions=["Check the jack and patch cable.", "Replace or reterminate the cable path if errors or 100M negotiation persist."],
            dispatch_required=True,
            dispatch_priority="high",
            explanation="Physical evidence is stronger than a generic service-layer classification here.",
            next_best_check="Confirm whether the port should negotiate at 1G and inspect the physical path for cable degradation.",
            secondary_statuses=secondary,
            strong_signals=3,
        )

    if _wrong_mac_on_expected_port(reality):
        elsewhere = _expected_mac_found_elsewhere(reality)
        likely_causes = ["A different live MAC is present on the expected path, indicating a swapped device or wrong-unit patch."]
        backend_actions = ["Compare the live MAC against inventory/controller records for nearby units before dispatch."]
        field_actions = ["Verify the physical device label and patch path if backend records cannot prove the swap."]
        explanation = "A different MAC is present on the expected port, so this is an identity/path problem rather than a simple outage."
        if elsewhere:
            likely_causes.append(f"The expected MAC is visible elsewhere at {elsewhere}.")
            explanation += f" The expected MAC was found elsewhere at {elsewhere}."
            backend_actions.append("Correct inventory or patch records if the expected MAC belongs on the alternate live path.")
        return _build(
            reality,
            primary_status="DEVICE_SWAPPED_OR_WRONG_UNIT",
            likely_causes=likely_causes,
            backend_actions=backend_actions,
            field_actions=field_actions,
            dispatch_required=False,
            dispatch_priority="low",
            explanation=explanation,
            next_best_check="Identify which unit currently owns the live MAC and compare that against inventory/controller assignments.",
            secondary_statuses=secondary,
            strong_signals=2,
        )

    if _inventory_mismatch(reality):
        return _build(
            reality,
            primary_status="INVENTORY_MAC_MISMATCH",
            likely_causes=["The live MAC differs from inventory, but there is not enough path evidence to prove a swap."],
            backend_actions=["Review and correct the inventory MAC after comparing controller and historical sightings."],
            field_actions=[],
            dispatch_required=False,
            dispatch_priority="none",
            explanation="The device is present, but the inventory MAC does not match the live MAC.",
            next_best_check="Compare the expected MAC and the live MAC across controller, inventory, and historical switch sightings.",
            secondary_statuses=secondary,
            strong_signals=1,
        )

    if _switch_port_or_vlan_issue(reality):
        likely_causes = ["The expected access path is not carrying service because the port is down/disabled or VLAN placement is wrong."]
        if physical.get("port_up") is False:
            likely_causes.append("The expected access port is down or disabled.")
        expected_vlan = _text(inventory.get("expected_vlan"))
        live_vlan = _text(_truth(reality, "l2_truth").get("live_vlan"))
        if expected_vlan and live_vlan and expected_vlan != live_vlan:
            likely_causes.append(f"The live VLAN does not match expected VLAN {expected_vlan}.")
        return _build(
            reality,
            primary_status="SWITCH_PORT_DISABLED_OR_WRONG_VLAN",
            likely_causes=likely_causes,
            backend_actions=["Verify the switch port administrative state and VLAN membership on the expected access path."],
            field_actions=[],
            dispatch_required=False,
            dispatch_priority="none",
            explanation="The issue appears backend-configurable on the switch path.",
            next_best_check="Confirm the expected port is enabled and in the correct VLAN or service profile.",
            secondary_statuses=secondary,
            strong_signals=2,
        )

    if _text(inventory.get("expected_pppoe")) and _pppoe_no_attempt(reality):
        return _build(
            reality,
            primary_status="PPPoE_NO_ATTEMPT",
            likely_causes=["L2 is present, PPPoE is expected, and no PPPoE attempt evidence exists."],
            backend_actions=["Verify the expected PPPoE service mode and config template for the device."],
            field_actions=[],
            dispatch_required=False,
            dispatch_priority="none",
            explanation="The device is present but not attempting PPPoE, which points more toward config, VLAN, or mode mismatch than auth failure.",
            next_best_check="Confirm the device is configured for PPPoE on the correct VLAN and service profile.",
            secondary_statuses=secondary,
            strong_signals=1,
            critical_missing=1 if reality.unknowns else 0,
        )

    if l2_present and not service_success:
        return _build(
            reality,
            primary_status="L2_PRESENT_NO_SERVICE",
            likely_causes=["The device is visible at L2, but service/auth/DHCP success is absent."],
            backend_actions=["Check VLAN, controller state, PPPoE/DHCP expectations, and service profile alignment."],
            field_actions=[],
            dispatch_required=False,
            dispatch_priority="none",
            explanation="Because the MAC is live on the network, the device is not unplugged; the problem is above simple physical absence.",
            next_best_check="Check whether PPPoE or DHCP should be active for this unit and why that expected service signal is absent.",
            secondary_statuses=secondary,
            strong_signals=2,
            critical_missing=1 if reality.unknowns else 0,
        )

    return _build(
        reality,
        primary_status="NEEDS_MORE_EVIDENCE",
        likely_causes=["No deterministic diagnosis rule had enough support to classify the unit safely."],
        backend_actions=[],
        field_actions=[],
        dispatch_required=False,
        dispatch_priority="none",
        explanation="Reality is still incomplete, so Jake should not guess.",
        next_best_check="Collect the missing L1, controller, auth, and DHCP evidence needed to separate backend from field causes.",
        strong_signals=0,
        critical_missing=1,
        force_low_confidence=bool(reality.contradictions),
    )


def diagnose_unit(evidence: UnitEvidence) -> Diagnosis:
    return diagnose(build_reality_model(evidence))
