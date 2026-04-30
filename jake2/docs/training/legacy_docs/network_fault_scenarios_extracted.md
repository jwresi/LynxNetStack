Network Fault Reasoning 
 50 Correlated Training Scenarios 

MikroTik RouterOS · ISP/WISP Fault Diagnosis · AI Model Training Dataset 

How to Use This Dataset 
 Each scenario follows the structured reasoning format required to train a network fault analysis model: 

1. OBSERVATIONS — Raw log and signal data presented as received 
 2. REASONING — Multi-source correlation with timeline reconstruction 
 3. ROOT CAUSE — The first abnormal event, not the loudest symptom 
 4. COMMANDS — Iterative verification queries (broad → narrow → confirm) 
 5. WHY NOT — Explicit elimination of alternative hypotheses 
 6. FIX — Specific remediation commands 
 7. PREVENTION — Systemic changes to prevent recurrence 

Scenario Index 
 Link Flap Cascade (#1–#8) 
 DHCP Failure (#9–#16) 
 VLAN / L2 Issue (#17–#24) 
 Routing / NAT Failure (#25–#32) 
 PPPoE / Session Failure (#33–#40) 
 Security / Advanced (#41–#50) 

Link Flap Cascade 
 Scenario #1 

1. EEE link flap → DHCP churn → PPPoE mass drop 

INPUT — Observed Signals 
 Site down. ~200 customers offline simultaneously. Logs show: 
 - ether1 link down/up cycling every 8–12 seconds 
 - DHCP deassign/assign pairs flooding logs 
 - PPPoE sessions dropping with LCP timeout errors 
 - Multiple MAC addresses seen per client circuit 
 - Upstream switch showing FCS errors on the port 

EXPECTED REASONING 
 Timeline reconstruction: 
 03:14:22 — ether1 first link-down logged 
 03:14:23 — DHCP deassign storm begins (downstream) 
 03:14:28 — PPPoE LCP timeouts start (downstream) 
 03:14:30 — MAC instability observed (downstream, caused by retries) 

Correlation: All events share ether1 as common interface. DHCP and PPPoE instability began AFTER and BECAUSE of the link flap, not independently. 

MAC churn is not a rogue device — it is the same CPE retrying association across flap cycles. 

FCS errors on upstream switch confirm the problem is at the physical/electrical layer, not in MikroTik config. 

ROOT CAUSE 
 Physical link instability on ether1 caused by Energy Efficient Ethernet (EEE) negotiation failure between MikroTik and upstream switch. 

COMMANDS TO VERIFY 
 /log print where message~"ether1" 
 /log print where message~"link" 
 /interface ethernet monitor ether1 
 /interface ethernet print detail where name=ether1 
 /log print where topics~"dhcp" interval=00:00:30 

WHY NOT (Eliminated Hypotheses) 
 NOT a routing issue — local gateway was reachable during flap windows. 
 NOT a rogue DHCP server — all offers came from correct DHCP server IP. 
 NOT a PPPoE config error — sessions were stable before this event. 
 NOT multiple devices — MAC churn matches flap timing exactly. 

FIX 
 /interface ethernet set ether1 eee=no 
 /interface ethernet set ether1 auto-negotiation=no speed=1Gbps full-duplex=yes 

PREVENTION 
 Disable EEE on all uplinks by default in provisioning templates. 
 Add link-flap alerting: alert if interface toggles >3 times in 60 seconds. 
 Document upstream switch port settings and match autoneg state. 

Link Flap Cascade 
 Scenario #2 

2. SFP receive power drop → intermittent L2 → MAC table instability 

INPUT — Observed Signals 
 Intermittent customer complaints, not full outage. Logs show: 
 - sfp-sfpplus1 occasional link-down lasting 200–500ms 
 - MAC table entries for VLAN 100 flapping between two ports 
 - Sporadic ARP failures reported by customers 
 - No errors on copper uplink side 
 - Flaps happen every 3–7 minutes, not continuously 

EXPECTED REASONING 
 Timeline reconstruction: 
 Recurring pattern every 3–7 min: sfp link blink → MAC flush → ARP failure 

The MAC table instability is not an STP issue — there is no topology change notification logged. The MAC flapping between two ports is caused by the brief SFP outage causing a re-learn event on an alternate path. 

ARP failures are purely downstream: MAC table entries disappear during the re-learn window, so ARP replies are dropped or misdirected. 

The intermittency (not continuous) and fiber-only symptoms point to optical layer: dirty connector, marginal receive power, or failing SFP. 

ROOT CAUSE 
 Degraded optical receive power on sfp-sfpplus1 causing sub-second link drops, leading to MAC table invalidation and brief ARP blackholes. 

COMMANDS TO VERIFY 
 /interface ethernet monitor sfp-sfpplus1 
 /interface print stats where name=sfp-sfpplus1 
 /log print where message~"sfp-sfpplus1" 
 /interface bridge host print where on-interface=sfp-sfpplus1 

WHY NOT (Eliminated Hypotheses) 
 NOT an STP loop — no topology change notifications, no port role changes logged. 
 NOT a duplex mismatch — copper side stable, no FCS errors. 
 NOT a rogue device — MAC flapping correlates exactly with SFP blink events. 
 NOT a config issue — behavior began after physical maintenance nearby. 

FIX 
 Clean SFP connector with lint-free swab and IPA. 
 Check and reseat SFP module. If RX power below -3dBm of rated minimum, replace SFP. 
 Check fiber patch cable for tight bends or damage. 

PREVENTION 
 Monitor SFP RX power via SNMP, alert if within 3dBm of minimum threshold. 
 Log optical levels at install. Schedule quarterly fiber inspection. 
 Use dust caps on all unused SFP ports. 

Link Flap Cascade 
 Scenario #3 

3. PoE power budget exceeded → port cycling → downstream switch offline 

INPUT — Observed Signals 
 Entire floor of building offline. Logs show: 
 - ether5 through ether8 link cycling repeatedly 
 - PoE controller log showing overload events 
 - Downstream unmanaged PoE switch unreachable 
 - Three IP cameras were installed same morning by third party 
 - ether1-4 (non-PoE) devices unaffected 

EXPECTED REASONING 
 Timeline reconstruction: 
 09:12 — Third party installs 3 IP cameras 
 09:15 — PoE budget overload events start 
 09:15:03 — ether5–8 begin link cycling 
 09:16 — Downstream switch (powered via PoE) goes offline 
 09:16:10 — All connected clients disconnect 

PoE cycling is not a firmware bug — it is the PoE controller protecting itself. Cameras triggered the overload. 

The downstream switch being PoE-powered means its power interruption = all clients on that switch losing access. This is a single point of failure exposed by the power event. 

ROOT CAUSE 
 Three high-draw PoE IP cameras installed simultaneously exceeded the switch PoE power budget, causing the PoE controller to cycle affected ports including the one powering the downstream switch. 

COMMANDS TO VERIFY 
 /interface ethernet poe print 
 /interface ethernet poe monitor ether5,ether6,ether7,ether8 
 /log print where message~"poe" 
 /log print where message~"overload" 

WHY NOT (Eliminated Hypotheses) 
 NOT a software fault — timing correlation with camera install is decisive. 
 NOT a cable fault — multiple ports affected simultaneously. 
 NOT a PoE device failure — behavior resolved when cameras were removed. 
 NOT a switching loop — ether1-4 unaffected, confirming PoE-specific cause. 

FIX 
 Remove or reduce PoE load. Calculate total draw: new cameras likely 15–25W each. 
 Assign static PoE priority to the downstream switch port (highest priority). 
 If budget insufficient, add dedicated PoE injector for downstream switch. 

PREVENTION 
 Document PoE budget per switch. Set per-port PoE power limits. 
 Never power critical infrastructure (uplink switches) via PoE without backup. 
 Require change notification before new PoE devices are installed. 

Link Flap Cascade 
 Scenario #4 

4. Autoneg mismatch → half-duplex collision → throughput collapse 

INPUT — Observed Signals 
 Customers on one segment reporting very slow speeds but not fully down. Logs show: 
 - No link-down events logged 
 - High collision counters on ether3 
 - Throughput capped at ~5 Mbps on a 100M link 
 - Ping latency to gateway normal (2ms) but under load spikes to 200ms+ 
 - Problem started after ISP replaced their CPE device 

EXPECTED REASONING 
 Timeline reconstruction: 
 ISP replaces CPE → autoneg produces mismatched result → collisions begin → throughput degrades 

Link is UP, so no link-down events. This is a layer 1.5 problem: the link appears healthy but is running half-duplex on one side, full-duplex on the other — causing persistent collisions without triggering a link failure. 

Latency spike under load is the hallmark of collision-based congestion, not routing or firewall. 

The timing (started after CPE replacement) is the decisive correlation anchor. 

ROOT CAUSE 
 Duplex mismatch between MikroTik ether3 (autoneg resolved to full-duplex) and replacement ISP CPE (hardcoded to half-duplex), causing persistent collisions and throughput collapse. 

COMMANDS TO VERIFY 
 /interface ethernet monitor ether3 
 /interface print stats where name=ether3 
 /interface ethernet print detail where name=ether3 

WHY NOT (Eliminated Hypotheses) 
 NOT a bandwidth/QoS issue — speeds degraded uniformly regardless of traffic class. 
 NOT a firewall rule — ping to gateway normal, ruling out policy drops. 
 NOT a cable fault — no link flaps, no FCS errors. 
 NOT a routing issue — default route stable throughout. 

FIX 
 /interface ethernet set ether3 auto-negotiation=no speed=100Mbps full-duplex=yes 
 Coordinate with ISP to match settings on their CPE. 

PREVENTION 
 When ISP replaces CPE, verify duplex match before signing off. 
 Add collision counter monitoring to NOC dashboards. 
 Default all ISP-facing ports to explicit speed/duplex in provisioning. 

Link Flap Cascade 
 Scenario #5 

5. Cable fault → intermittent CRC errors → random client drops 

INPUT — Observed Signals 
 Random customer disconnections, no pattern by time of day. Logs show: 
 - CRC/FCS error counter incrementing on ether6 (not zeroing between checks) 
 - Client sessions dropping without clean LCP terminate 
 - Physical cable runs through conduit shared with power cables 
 - Errors worse during business hours (when AC units run) 
 - No link-down events, speeds appear normal on speed test 

EXPECTED REASONING 
 CRC errors without link-down = data corruption in transit, not physical disconnect. This is a signal integrity problem. 

The correlation with AC unit operation is the key diagnostic clue: electrical interference from high-current equipment inducing noise on unshielded cable. 

Session drops happen when corrupted frames exceed the protocol&apos;s tolerance — PPP/PPPoE will drop the session after too many failed frames, even without a link event. 

No speed test degradation because speed tests use TCP which retransmits — latency goes up but throughput appears adequate until sessions are stressed. 

ROOT CAUSE 
 EMI/RFI interference from AC electrical equipment inducing CRC errors on Cat5e cable running through shared conduit, causing silent session corruption and eventual disconnection. 

COMMANDS TO VERIFY 
 /interface print stats where name=ether6 
 /log print where message~"ether6" 
 /ping 192.168.1.1 count=100 
 /tool bandwidth-test address=<test_server> direction=both 

WHY NOT (Eliminated Hypotheses) 
 NOT a switch fault — errors specific to ether6, other ports clean. 
 NOT a client device fault — problem persists with replacement CPE. 
 NOT a DHCP issue — sessions drop cleanly, not from lease expiry. 
 NOT a load issue — errors present even with minimal traffic. 

FIX 
 Replace Cat5e with shielded STP cable or reroute through separate conduit. 
 If rerouting not possible, use fiber media converter to eliminate EMI susceptibility. 

PREVENTION 
 Never run network cables through conduit shared with power/AC cables. 
 Use STP or fiber for any runs near electrical equipment. 
 Document cable routes at install time. 

Link Flap Cascade 
 Scenario #6 

6. Spanning tree topology change → 30-second traffic blackhole 

INPUT — Observed Signals 
 Periodic 30-second complete outages on one VLAN, every 2–4 hours. Logs show: 
 - STP topology change notifications logged periodically 
 - ether4 briefly shown as alternate/backup role 
 - Customer traffic drops to zero for ~30 seconds then recovers fully 
 - Problem only affects VLAN 200, not VLAN 100 
 - New unmanaged switch was added to the network last week 

EXPECTED REASONING 
 Timeline reconstruction: 
 Periodic: STP TCN received → MAC table flushed for VLAN 200 → 30s blackhole → MAC re-learned → traffic recovers 

The 30-second duration is the STP MAC aging shortcut timer — after a TCN, the bridge flushes the MAC table and traffic is flooded until addresses re-learn. 

The unmanaged switch added last week is the likely TCN source — cheap switches running STP may generate spurious topology changes. 

VLAN 100 unaffected means either: unmanaged switch is only on VLAN 200 ports, or the root bridge differs between VLANs. 

ROOT CAUSE 
 Unmanaged switch generating spurious STP topology change notifications on VLAN 200, causing MAC table flush and 30-second traffic blackhole every time a TCN is received. 

COMMANDS TO VERIFY 
 /interface bridge print 
 /interface bridge monitor bridge1 
 /log print where message~"topology" 
 /log print where message~"stp" 
 /interface bridge port print 

WHY NOT (Eliminated Hypotheses) 
 NOT a hardware failure — full recovery after 30s is too clean. 
 NOT a routing issue — affects L2 VLAN, routing table unchanged. 
 NOT a DHCP problem — clients retain IPs through the outage. 
 NOT a firewall rule — all traffic drops, not just specific flows. 

FIX 
 Enable RSTP PortFast/edge port on all access ports connected to end devices: 
 /interface bridge port set [find interface=ether4] edge=yes auto-edge=yes 
 Replace or remove unmanaged switch. If kept, enable BPDU guard on its uplink port. 

PREVENTION 
 Never introduce unmanaged switches into production networks without assessment. 
 Enable RSTP on all bridges. Set PortFast on all end-device ports. 
 Monitor STP topology change rate — alert if >1 TCN per minute. 

Link Flap Cascade 
 Scenario #7 

7. Upstream ISP link drop → BGP withdrawal → NAT session teardown 

INPUT — Observed Signals 
 Full customer outage, 45 minutes. Logs show: 
 - ether1 (WAN) link down at 14:22:08, up at 15:07:41 
 - BGP session to upstream dropped during outage 
 - After link recovery, many customers still reported being offline 
 - NAT table showed zero entries at 15:09 
 - New DHCP leases being assigned at 15:07 but sessions not establishing 

EXPECTED REASONING 
 Timeline reconstruction: 
 14:22:08 — WAN link down 
 14:22:09 — BGP session drops 
 14:22:10 — Default route withdrawn from routing table 
 14:22:10 — All NAT sessions become invalid (no outbound route) 
 15:07:41 — WAN link restores 
 15:07:42 — BGP session re-establishing (not instant) 
 15:07:45 — DHCP assigning leases (LAN working immediately) 
 15:09:00 — BGP converges, default route restored 
 ~15:09 — Customers must re-initiate sessions (old TCP/PPPoE sessions were torn down) 

Post-recovery complaints are not a new fault — they are session persistence failure. Existing long-lived sessions (gaming, VoIP, video calls) were terminated during the outage and require user re-initiation. 

ROOT CAUSE 
 ISP WAN link failure caused BGP withdrawal and full traffic blackhole. Post-recovery complaints are due to long-lived TCP sessions being terminated during the 45-minute outage, requiring manual reconnection. 

COMMANDS TO VERIFY 
 /log print where message~"bgp" 
 /log print where message~"ether1" 
 /routing bgp session print 
 /ip route print where gateway=<wan_ip> 
 /ip firewall connection print count-only 

WHY NOT (Eliminated Hypotheses) 
 NOT a DHCP failure — new leases assigned immediately after recovery. 
 NOT a DNS failure — resolution worked as soon as BGP converged. 
 NOT a firewall block — NAT table populated correctly post-recovery. 
 NOT a new fault — post-recovery complaints due to expected session teardown. 

FIX 
 Immediate: notify customers that long-lived sessions need re-initiation. 
 For future: configure BGP timers for faster convergence. 
 Implement failover WAN link if SLA requires higher availability. 

PREVENTION 
 Configure BGP keepalive/holddown to detect failure within 30 seconds. 
 Implement dual-WAN with automatic failover for critical sites. 
 Set up automated recovery testing after WAN events. 

Link Flap Cascade 
 Scenario #8 

8. ether channel / LACP negotiation failure → 50% traffic drop 

INPUT — Observed Signals 
 Performance complaints from one customer segment, not full outage. Logs show: 
 - LAG (bond) interface showing one member link down 
 - Throughput halved compared to baseline 
 - bond1 member ether7 showing carrier but LACP PDUs not received 
 - No alarm was triggered because bond1 itself showed as UP 
 - Occurred after scheduled patch window on upstream switch 

EXPECTED REASONING 
 Timeline reconstruction: 
 Patch window completes → upstream switch LACP config reverts/changes → ether7 LACP PDUs stop → bond member goes into individual mode → bond1 operates on ether6 only → 50% capacity 

The bond showing UP is the reason no alert fired — the monitoring system watched the parent interface, not the members. 

The timing (immediately after patch window) is the decisive anchor. LACP config may have been reset to default on the upstream switch, or the port-channel config was not saved before reboot. 

ROOT CAUSE 
 Upstream switch patch window caused LACP configuration loss on one port-channel member, leaving bond1 with one active member and 50% capacity. No alert triggered because parent bond interface remained UP. 

COMMANDS TO VERIFY 
 /interface bonding monitor bond1 
 /interface bonding print detail where name=bond1 
 /log print where message~"bond" 
 /log print where message~"lacp" 
 /interface print stats where name~"ether" 

WHY NOT (Eliminated Hypotheses) 
 NOT a cable fault — ether7 shows carrier, physical link is up. 
 NOT a switch hardware fault — occurred precisely at patch completion. 
 NOT a MikroTik config issue — bond config unchanged on MikroTik side. 
 NOT a traffic spike — utilization halved, consistent with 50% capacity. 

FIX 
 Verify LACP config on upstream switch port-channel. Re-enable LACP on the affected member. 
 On upstream switch: confirm running-config matches startup-config after patch. 

PREVENTION 
 Monitor bond member state, not just parent bond interface. 
 Alert when any bond member goes down, even if bond remains UP. 
 Require config verification (show run vs show start) as step in patch runbook. 

DHCP Failure 
 Scenario #9 

9. DHCP pool exhaustion → new clients fail, existing clients unaffected 

INPUT — Observed Signals 
 New customers cannot get online but existing customers unaffected. Logs show: 
 - DHCP "no free leases" errors in log 
 - DHCP pool shows 0 available addresses 
 - Large number of leases in "waiting" state with MAC addresses not matching active CPEs 
 - Pool was 192.168.1.0/24 (/24 = 254 usable) 
 - Site has 180 active customers 

EXPECTED REASONING 
 Pool has 254 addresses, site has 180 customers — math suggests pool should have 74 free. "Waiting" state leases are the key: these are expired leases not yet purged, holding addresses from devices that have left. 

Not a rogue DHCP server — the MikroTik is responding correctly (error is "no free leases" not "ignored request"). 

Not a misconfiguration of the pool range — the pool was correctly sized at deployment but the site has grown or CPE churn has generated stale leases. 

ROOT CAUSE 
 DHCP pool exhausted by stale &apos;waiting&apos; state leases from CPE devices that were removed/replaced without releasing their leases. Pool is correctly configured but effectively full. 

COMMANDS TO VERIFY 
 /ip dhcp-server lease print count-only 
 /ip dhcp-server lease print where status=waiting 
 /ip dhcp-server lease print where status=expired 
 /ip dhcp-server print 
 /log print where message~"no free" 

WHY NOT (Eliminated Hypotheses) 
 NOT a rogue DHCP server — no foreign DHCP offers seen. 
 NOT a pool range error — range is correctly configured. 
 NOT a client error — multiple new clients failing confirms server-side issue. 
 NOT a network reachability issue — existing clients are online and stable. 

FIX 
 /ip dhcp-server lease remove [find status=waiting] 
 /ip dhcp-server lease remove [find status=expired] 
 Consider expanding pool to /23 if growth expected. 

PREVENTION 
 Set DHCP lease time appropriate to CPE churn rate (shorter = faster reclaim). 
 Monitor pool utilization, alert at 80% full. 
 Schedule weekly stale lease cleanup via script. 

DHCP Failure 
 Scenario #10 

10. Rogue DHCP server on network → clients getting wrong gateway → no internet 

INPUT — Observed Signals 
 Customers on VLAN 50 unable to reach internet. Logs show: 
 - Customers have IP addresses in 10.10.50.x range (correct) 
 - Default gateway set to 10.10.50.200 (NOT the MikroTik gateway IP) 
 - 10.10.50.200 is not responding to pings 
 - DHCP server log shows no leases being issued to these clients 
 - Problem started 2 hours ago, affecting new connections only 

EXPECTED REASONING 
 Timeline reconstruction: 
 2h ago — Rogue DHCP server appears on VLAN 50 
 New clients connect → get offer from rogue server first (faster response or earlier in DORA) 
 Rogue server assigns correct subnet, wrong gateway 
 Clients route to 10.10.50.200 (non-existent) → internet fails 
 Existing clients unaffected → their leases were issued by legitimate server before rogue appeared 

The MikroTik DHCP log showing no leases = rogue server is winning the DORA race. Clients ARE receiving DHCP offers — just not from the right server. 

The gateway 10.10.50.200 is specific: this is either a misconfigured device or a deliberate man-in-the-middle attempt. 

ROOT CAUSE 
 Rogue DHCP server on VLAN 50 winning the DORA race against legitimate MikroTik DHCP server, assigning correct IP subnet but incorrect/non-existent gateway, causing internet failure for all new DHCP clients. 

COMMANDS TO VERIFY 
 /log print where topics~"dhcp" 
 /ip dhcp-server lease print where address~"10.10.50" 
 /tool packet-sniffer sniff interface=vlan50 ip-protocol=udp port=67,68 
 /ip arp print where address~"10.10.50.200" 

WHY NOT (Eliminated Hypotheses) 
 NOT a MikroTik DHCP misconfiguration — gateway in DHCP scope is correct. 
 NOT a routing issue — clients with correct gateway can reach internet. 
 NOT a DNS issue — gateway unreachable before DNS is even consulted. 
 NOT a firewall rule — clients cannot even reach default gateway. 

FIX 
 Identify rogue device: check ARP table for 10.10.50.200, find MAC, trace to switch port. 
 Power off or isolate the rogue device immediately. 
 Implement DHCP snooping on managed switches to block unauthorized DHCP servers. 

PREVENTION 
 Enable DHCP snooping on all managed switches. Trust only uplink/router ports. 
 Implement VLAN isolation to prevent unauthorized devices on infrastructure VLANs. 
 Monitor for unexpected DHCP servers via packet capture or SNMP traps. 

DHCP Failure 
 Scenario #11 

11. DHCP relay broken after VLAN change → new clients get no IP 

INPUT — Observed Signals 
 New building extension customers cannot get online. Existing customers fine. Logs show: 
 - No DHCP discover packets reaching the DHCP server from new VLAN 
 - New customers reporting "limited connectivity" (169.254.x.x address) 
 - DHCP server log shows no requests from the 192.168.30.x subnet 
 - VLAN 30 was extended to the new building yesterday 
 - Customers on VLAN 10 and VLAN 20 unaffected 

EXPECTED REASONING 
 169.254.x.x address = APIPA, meaning DHCP discovery failed entirely — no offer received, not a bad offer. 

DHCP server sees no discovers from VLAN 30. The DHCP server is on a different subnet — so a relay agent must forward the broadcasts. The relay was working before the VLAN extension (VLAN 30 was smaller or on the same L2), but the new building segment requires the relay to be configured on the new L3 interface. 

Existing customers unaffected = VLAN 30 on old segment has relay working. New building is a new L3 segment or the VLAN interface is missing from the relay config. 

ROOT CAUSE 
 DHCP relay agent not configured on the new VLAN 30 interface created for the building extension, so DHCP discovers from new clients are not forwarded to the DHCP server. 

COMMANDS TO VERIFY 
 /ip dhcp-relay print 
 /ip address print where interface~"vlan30" 
 /log print where topics~"dhcp" 
 /ip dhcp-server network print 

WHY NOT (Eliminated Hypotheses) 
 NOT a DHCP pool issue — server never receives the requests. 
 NOT a switch VLAN config error — L2 connectivity confirmed (ARP reaches router). 
 NOT a firewall blocking DHCP — DHCP relay operates before firewall in packet path. 
 NOT a server configuration error — other VLANs with relay working fine. 

FIX 
 /ip dhcp-relay add name=relay-vlan30 interface=vlan30 dhcp-server=<dhcp_server_ip> local-address=<vlan30_gateway> 

PREVENTION 
 Include DHCP relay configuration in the VLAN provisioning checklist. 
 Test DHCP from a client on every new VLAN before customer sign-off. 
 Maintain a VLAN provisioning runbook with all required steps. 

DHCP Failure 
 Scenario #12 

12. DHCP lease time too short → mass simultaneous renewal → server CPU spike 

INPUT — Observed Signals 
 Periodic 2-minute degradation events every 4 hours, then recovery. Logs show: 
 - DHCP server CPU spikes to 100% during degradation 
 - Thousands of simultaneous DHCP renew requests 
 - All leases appear to have been issued at the same time 
 - Problem started after a power outage 2 weeks ago 
 - Lease time is set to 4 hours 

EXPECTED REASONING 
 Periodic events every 4 hours, matching the lease time = all clients renewing simultaneously. This is a "thundering herd" problem caused by synchronized lease issuance. 

During the power outage 2 weeks ago, the router rebooted and re-issued all leases at the same time. All leases now expire/renew simultaneously every 4 hours. 

The 2-minute duration matches DHCP renewal processing time under load. 

This is not a fault in the traditional sense — the DHCP server is functioning correctly, but the synchronized load exceeds its capacity. 

ROOT CAUSE 
 Power outage caused all DHCP leases to be re-issued simultaneously, creating synchronized renewal storms every 4 hours (matching lease time) that overload the DHCP server CPU. 

COMMANDS TO VERIFY 
 /ip dhcp-server lease print 
 /log print where topics~"dhcp" interval=00:01:00 
 /ip dhcp-server print 
 /system resource print 

WHY NOT (Eliminated Hypotheses) 
 NOT a DDoS — requests are all from known legitimate CPE MAC addresses. 
 NOT a hardware failure — CPU normalizes after renewal burst completes. 
 NOT a software bug — behavior is mathematically predictable. 
 NOT a rogue device — all requests are valid DHCP renew packets. 

FIX 
 Increase lease time to 24 hours to reduce renewal frequency. 
 Stagger leases by adding jitter: renew existing leases manually across a 2-hour window. 
 Or: script a staggered lease re-issue to desynchronize the expiry times. 

PREVENTION 
 After any mass outage/reboot, stagger DHCP lease re-issuance. 
 Use longer lease times for stable CPE deployments (24h–7 days). 
 Monitor DHCP server CPU; alert if >50% sustained for >30 seconds. 

DHCP Failure 
 Scenario #13 

13. Static IP conflict with DHCP range → periodic address collision → flapping 

INPUT — Observed Signals 
 One specific customer offline repeatedly. Other customers fine. Logs show: 
 - DHCP lease for 192.168.1.55 assigned to CPE-MAC-A 
 - ARP table shows 192.168.1.55 resolving to CPE-MAC-B at different times 
 - Customer with CPE-MAC-A repeatedly disconnects and reconnects 
 - CPE-MAC-B is a network printer that was manually assigned 192.168.1.55 
 - DHCP pool range starts at 192.168.1.50 

EXPECTED REASONING 
 Two devices have the same IP: CPE-MAC-A via DHCP, network printer CPE-MAC-B via static assignment. The printer&apos;s static IP falls within the DHCP pool range. 

The flapping pattern: DHCP assigns 192.168.1.55 to the CPE → CPE comes online → printer already has that IP → Gratuitous ARP conflict → one device wins the ARP table → other drops offline → eventually printer or CPE re-ARPs and reclaims → repeat. 

The ARP table alternating between two MACs for the same IP is the conclusive evidence. 

ROOT CAUSE 
 IP address conflict between a DHCP-assigned client (192.168.1.55) and a network printer with a static IP within the DHCP pool range, causing ARP table flapping and periodic disconnection for the DHCP client. 

COMMANDS TO VERIFY 
 /ip arp print where address=192.168.1.55 
 /ip dhcp-server lease print where address=192.168.1.55 
 /log print where message~"192.168.1.55" 
 /ping 192.168.1.55 count=5 

WHY NOT (Eliminated Hypotheses) 
 NOT a CPE hardware fault — problem resolves temporarily and recurs predictably. 
 NOT a DHCP server bug — DHCP is correctly assigning the address from its pool. 
 NOT a cable/physical issue — ping to gateway succeeds during up periods. 
 NOT multiple devices claiming to be the customer — MAC-B is the identified printer. 

FIX 
 Change printer static IP to an address outside the DHCP pool range. 
 Or: add DHCP reservation for the printer MAC address. 
 Adjust DHCP pool start address to leave space for static devices: 
 /ip dhcp-server network set [find] gateway=192.168.1.1 
 /ip pool set [find] ranges=192.168.1.100-192.168.1.254 

PREVENTION 
 Reserve first 50 IPs of every subnet for static assignment (/ip pool starting at .50 or higher). 
 Document all static IP assignments. 
 Before assigning a static IP, verify it is outside all DHCP pools. 

DHCP Failure 
 Scenario #14 

14. Firewall blocking DHCP on VLAN interface → clients get APIPA only 

INPUT — Observed Signals 
 New VLAN deployment, no customers can get an IP. Logs show: 
 - DHCP server is running and has pool configured for the new subnet 
 - Client sends discover, no offer received 
 - Packet capture on client side shows discover going out, no reply 
 - Packet capture on server side shows discovers arriving 
 - Server log shows "discover from <MAC>" but no "lease offered" 

EXPECTED REASONING 
 Discovers ARE reaching the server (server log confirms). Server sees them. Server is NOT sending an offer. This eliminates: cable, VLAN config, relay, and client-side issues. 

The server is receiving but not responding. Possible causes: pool exhausted (but pool is new and empty = full of free addresses), firewall on the router input chain blocking UDP 67/68, or a server rule rejecting the request. 

Most common cause in MikroTik after new VLAN creation: an "input" firewall chain rule dropping UDP traffic on the new interface before DHCP processing. 

ROOT CAUSE 
 Firewall input chain rule (likely a &apos;drop all&apos; default rule) blocking DHCP offer packets from leaving the DHCP server on the new VLAN interface, before the server can respond. 

COMMANDS TO VERIFY 
 /ip firewall filter print 
 /ip firewall filter print where chain=input 
 /ip dhcp-server log print 
 /tool packet-sniffer sniff interface=vlan40 ip-protocol=udp port=67,68 

WHY NOT (Eliminated Hypotheses) 
 NOT a DHCP pool error — pool has free addresses. 
 NOT a client fault — multiple clients showing same behavior. 
 NOT a VLAN L2 issue — discovers reaching server confirms L2 working. 
 NOT a DHCP relay issue — client and server are on same device. 

FIX 
 /ip firewall filter add chain=input protocol=udp dst-port=67,68 action=accept place-before=<drop_rule> 
 Or: add VLAN interface to trusted input accept rule. 

PREVENTION 
 Include firewall rule review in VLAN provisioning checklist. 
 Test DHCP on every new VLAN before announcing to customers. 
 Use ordered firewall rules with explicit accept-before-drop structure. 

DHCP Failure 
 Scenario #15 

15. DHCP server clock drift → lease expiry mismatch → mass disconnect at midnight 

INPUT — Observed Signals 
 Mass disconnection event every night at approximately 00:00. Logs show: 
 - Hundreds of leases expiring simultaneously at midnight 
 - Lease duration is set to 12 hours 
 - Customers reconnect within 60 seconds (auto-renewal) 
 - System clock shows correct local time but NTP is not configured 
 - Issue started after DST changeover 

EXPECTED REASONING 
 Leases expiring at midnight, 12h lease time, NTP not configured, and DST changeover = the clock jumped forward 1 hour at DST, but leases were already issued with the old time. 

When leases were issued at noon (12:00) with 12h duration, they expire at midnight (00:00). This is correct math. BUT without NTP, the system clock drifted, and after DST the clock is now 1 hour off. 

The midnight synchronization of expiry is the thundering herd signature — all leases issued around the same time will expire around the same time. After DST the bulk-issue time happened to align with midnight. 

60-second recovery = normal DHCP renewal, not an outage in the traditional sense, but customers notice the interruption. 

ROOT CAUSE 
 NTP not configured causing clock drift; DST changeover without NTP sync shifted bulk lease expiry to align with midnight, causing nightly mass-renewal disruption. 

COMMANDS TO VERIFY 
 /system ntp client print 
 /system clock print 
 /ip dhcp-server lease print 
 /log print where topics~"dhcp" interval=00:01:00 

WHY NOT (Eliminated Hypotheses) 
 NOT a DHCP server fault — expirations are mathematically correct given the clock. 
 NOT a network issue — recovery is clean and fast. 
 NOT a client fault — all clients recover similarly. 
 NOT a security incident — no unexpected MACs or addresses. 

FIX 
 /system ntp client set enabled=yes server-dns-names=pool.ntp.org 
 /system clock set time-zone-name=America/New_York 
 Then stagger lease re-issuance to desynchronize expiry times. 

PREVENTION 
 Configure NTP at deployment on every device. 
 Monitor clock drift; alert if time offset >5 seconds. 
 After DST changes, verify clock accuracy and stagger leases if needed. 

DHCP Failure 
 Scenario #16 

16. DHCP option misconfiguration → wrong DNS → all DNS failures 

INPUT — Observed Signals 
 All customers on a segment unable to browse but can ping IP addresses. Logs show: 
 - Ping to 8.8.8.8 succeeds from all clients 
 - Ping/browse to domain names fails (NXDOMAIN or timeout) 
 - DHCP leases show DNS server as 192.168.1.1 (router) 
 - Router DNS cache working, but clients still fail 
 - Problem started after network team changed DHCP options 

EXPECTED REASONING 
 Pings to IP work, DNS fails = DNS-specific issue. Router IP is set as DNS in leases (correct) but clients still fail. 

The specific trigger (DHCP options change) points to DHCP option 6 (DNS server) being set to wrong value. Options changes would not affect existing leases until renewal — new connections and renewed leases would get the bad option. 

Two sub-scenarios: (a) DNS server IP in option 6 changed to a non-functional address, or (b) option 6 added with a different IP overriding the gateway default. 

Check: what DNS IP are clients actually receiving vs what the server resolves to. 

ROOT CAUSE 
 DHCP option 6 (DNS server) misconfigured during recent change, pointing clients to a non-functional or incorrect DNS server IP, causing all DNS resolution to fail despite correct IP-level connectivity. 

COMMANDS TO VERIFY 
 /ip dhcp-server network print 
 /ip dhcp-server lease print detail where status=bound 
 /ip dns print 
 /tool packet-sniffer sniff ip-protocol=udp port=53 

WHY NOT (Eliminated Hypotheses) 
 NOT a routing issue — IP connectivity works. 
 NOT a firewall blocking DNS — ping to 8.8.8.8 succeeds, DNS port check needed separately. 
 NOT an ISP DNS issue — client DNS server is local router, not ISP. 
 NOT a client OS issue — multiple device types all failing. 

FIX 
 /ip dhcp-server network set [find] dns-server=<correct_dns_ip> 
 Force clients to renew DHCP to get updated DNS. 

PREVENTION 
 Test DNS resolution from a client after any DHCP options change. 
 Change management: document DNS server IPs and verify against DHCP options at deployment. 

VLAN / L2 Issue 
 Scenario #17 

17. VLAN misconfiguration → traffic crossing segment boundary → security incident 

INPUT — Observed Signals 
 Customer reports accessing another customer&apos;s equipment. Logs show: 
 - Customer A (VLAN 10) can ping Customer B (VLAN 20) addresses 
 - ARP table on router shows Customer B MACs learned on VLAN 10 interface 
 - No firewall rules were changed 
 - A new switch was installed and configured by junior technician 
 - Customer isolation was previously working 

EXPECTED REASONING 
 Customers on separate VLANs being able to reach each other without firewall rules = L2 leak. Traffic is bypassing the router entirely. 

MACs from VLAN 20 appearing on VLAN 10 interface = the switch is not properly tagging traffic to the correct VLAN, causing frames to bridge across VLAN boundaries. 

The new switch installation is the event anchor. The junior technician likely misconfigured trunk ports or access port VLAN assignments on the new switch, creating a VLAN leak. 

ROOT CAUSE 
 New switch misconfigured by junior technician with incorrect VLAN assignments, creating an L2 bridge between VLAN 10 and VLAN 20, allowing direct traffic flow between customer segments without routing. 

COMMANDS TO VERIFY 
 /interface bridge host print 
 /interface vlan print 
 /log print where topics~"bridge" 
 /ip arp print 
 /interface bridge port print 

WHY NOT (Eliminated Hypotheses) 
 NOT a firewall rule change — router is not involved in the cross-VLAN traffic. 
 NOT a routing/NAT issue — customers are reaching each other at L2, not L3. 
 NOT a MikroTik config error — problem introduced by new switch. 
 NOT a security attack — consistent with misconfiguration timeline. 

FIX 
 Audit and correct VLAN assignments on new switch port-by-port. 
 Verify trunk ports carry only expected VLANs. 
 Confirm access ports are assigned to correct VLAN only. 
 Test customer isolation from a client on each VLAN. 

PREVENTION 
 Require senior review of switch configs before production cutover. 
 Perform customer isolation test as part of post-installation checklist. 
 Use config templates for switch deployment to minimize manual error. 

VLAN / L2 Issue 
 Scenario #18 

18. Native VLAN mismatch → untagged frames in wrong VLAN → silent L2 leak 

INPUT — Observed Signals 
 Intermittent reports of traffic appearing in wrong VLAN. Not consistent. Logs show: 
 - Some frames from VLAN 1 (management) appearing in VLAN 100 (customer) 
 - Management interface briefly reachable from customer VLAN during events 
 - Trunk port between MikroTik and upstream switch recently reconfigured 
 - MikroTik has native VLAN set to 1, upstream switch native VLAN set to 100 
 - No explicit security breach, but auditors flagged it 

EXPECTED REASONING 
 Native VLAN mismatch = untagged frames on a trunk link are interpreted differently by each end. Frames sent untagged by MikroTik (assuming native VLAN 1) are received by upstream switch as belonging to VLAN 100. 

This is a classic IEEE 802.1Q vulnerability: when two trunk endpoints disagree on native VLAN, untagged management frames can inadvertently appear in the customer VLAN. 

The intermittency is because most management traffic is tagged, but some protocols (LLDP, some STP BPDUs, CDP) send untagged — these are the leaking frames. 

ROOT CAUSE 
 Native VLAN mismatch on trunk port between MikroTik (native VLAN 1) and upstream switch (native VLAN 100), causing untagged management frames to be interpreted as customer VLAN 100 traffic. 

COMMANDS TO VERIFY 
 /interface ethernet print detail where name=<trunk_port> 
 /interface vlan print 
 /interface bridge port print 
 /tool packet-sniffer sniff interface=<trunk_port> 

WHY NOT (Eliminated Hypotheses) 
 NOT a firewall misconfiguration — traffic is leaking at L2, pre-firewall. 
 NOT a DHCP or routing issue — frame injection problem, not address assignment. 
 NOT a deliberate attack — timing matches configuration change, not reconnaissance. 
 NOT a hardware fault — consistent with config mismatch, not packet corruption. 

FIX 
 Align native VLAN on both ends of the trunk, or tag all VLANs explicitly and disable native VLAN: 
 /interface ethernet set <port> pvid=100 (match upstream) 
 Best practice: use a dedicated unused VLAN as native, tag everything else. 

PREVENTION 
 Document native VLAN settings at both ends of every trunk. 
 Use automated config auditing to detect native VLAN mismatches. 
 Default policy: always tag all VLANs, native VLAN should be unused VLAN ID. 

VLAN / L2 Issue 
 Scenario #19 

19. Bridge loop → broadcast storm → full network meltdown 

INPUT — Observed Signals 
 Network completely unusable. All customers offline. Logs show: 
 - CPU at 100% on all switches 
 - Broadcast traffic consuming 100% of bandwidth 
 - Log flooded with MAC table updates 
 - Physical inspection found a cable plugged into two ports of same switch 
 - Problem started immediately after a customer &apos;self-installed&apos; a device 

EXPECTED REASONING 
 100% CPU, 100% broadcast, MAC table flooding = classic broadcast storm from a switching loop. 

Physical inspection finding a cable connecting two ports of the same switch is the definitive root cause. This creates an L2 loop where broadcast frames circulate indefinitely, growing exponentially. 

Customer self-installation is the event anchor. 

Without STP (or with STP disabled/overridden), a single looped cable can take down an entire network in seconds. 

ROOT CAUSE 
 L2 switching loop created by customer plugging a cable between two ports on the same switch during self-installation, causing a broadcast storm that consumed all available bandwidth and CPU across the network. 

COMMANDS TO VERIFY 
 /interface bridge print 
 /log print where message~"loop" 
 /interface print stats (look for broadcast counters) 
 /interface bridge host print (look for same MAC on multiple ports) 

WHY NOT (Eliminated Hypotheses) 
 NOT a virus/DDoS — traffic pattern is broadcast-dominant, not targeted. 
 NOT a DHCP storm — storm started before DHCP traffic analysis possible. 
 NOT a routing issue — L2 problem, routing table irrelevant during storm. 
 NOT a hardware failure — resolved immediately when loop cable removed. 

FIX 
 Immediately: disconnect the looped cable. 
 Enable STP/RSTP on all bridge ports to prevent future loops. 
 Enable BPDU guard and storm control on customer-facing ports. 

PREVENTION 
 Enable STP on all switches. Customer-facing ports: PortFast + BPDU guard. 
 Implement port-based storm control (broadcast rate limit). 
 Never allow customers to self-install switching equipment without approval. 

VLAN / L2 Issue 
 Scenario #20 

20. QinQ double-tag misconfiguration → customer traffic dropped at provider edge 

INPUT — Observed Signals 
 New enterprise customer unable to send traffic. Residential customers unaffected. Logs show: 
 - Enterprise customer frames arriving with double VLAN tags (outer S-tag 200, inner C-tag 100) 
 - Router dropping frames with unrecognized double-tag structure 
 - Upstream provider using 802.1ad (QinQ) for the enterprise circuit 
 - MikroTik config uses standard 802.1Q only 
 - Frames visible in packet capture but discarded 

EXPECTED REASONING 
 Double-tagged frames being visible but dropped = MikroTik is receiving them but not configured to handle 802.1ad (QinQ) Ethertype (0x88a8 vs 0x8100 for standard 802.1Q). 

Residential customers unaffected = single-tagged circuits are working. The enterprise circuit is the only QinQ circuit. 

The mismatch is between the provider&apos;s 802.1ad Ethertype on the outer tag and MikroTik&apos;s expectation of standard 802.1Q frames. 

ROOT CAUSE 
 Provider delivering enterprise circuit with 802.1ad QinQ double-tagging (Ethertype 0x88a8 outer), but MikroTik configured for standard 802.1Q (0x8100) only, causing double-tagged frames to be discarded. 

COMMANDS TO VERIFY 
 /interface vlan print 
 /tool packet-sniffer sniff interface=<enterprise_port> 
 /log print where message~"vlan" 
 /interface bridge port print 

WHY NOT (Eliminated Hypotheses) 
 NOT a cable or physical layer issue — frames are arriving (visible in capture). 
 NOT a DHCP or routing issue — frames are dropped at L2 before L3 processing. 
 NOT a firewall rule — drops occur before firewall for malformed L2 frames. 
 NOT a residential config error — residential circuits are single-tagged and working. 

FIX 
 Configure MikroTik to handle QinQ by creating nested VLAN interfaces: 
 /interface vlan add name=s-vlan200 vlan-id=200 interface=<enterprise_port> 
 /interface vlan add name=c-vlan100 vlan-id=100 interface=s-vlan200 

PREVENTION 
 Clarify encapsulation type (802.1Q vs 802.1ad) with provider before circuit delivery. 
 Include QinQ check in enterprise circuit acceptance testing. 
 Document which circuits use QinQ vs standard tagging. 

VLAN / L2 Issue 
 Scenario #21 

21. MAC address table overflow → switch behaves like hub → traffic interception possible 

INPUT — Observed Signals 
 Security audit finding: traffic from Customer A visible on Customer B&apos;s port. Logs show: 
 - MAC table size at maximum capacity 
 - New MAC addresses not being learned 
 - Flooded unicast frames visible on all ports 
 - Very large number of unique source MAC addresses seen recently 
 - Coincides with a new customer who has commercial routing equipment with many MAC addresses 

EXPECTED REASONING 
 MAC table at maximum + flooded unicast = classic MAC table overflow / CAM table flooding. When the MAC table is full, the switch cannot learn new addresses and must flood unknown unicast traffic to all ports — essentially becoming a hub. 

This allows any customer to receive traffic intended for others, which is the security finding. 

New commercial routing equipment with many MACs is the likely cause: enterprise routers, virtual machines, or bonded interfaces can present hundreds of MAC addresses on a single port. 

This could also be deliberate (MAC flooding attack tool like macof) — but timeline matching customer installation makes accidental cause more likely. 

ROOT CAUSE 
 MAC address table overflow caused by a new customer&apos;s commercial equipment presenting excessive unique MAC addresses, forcing the switch to flood all unknown unicast frames to all ports, creating a traffic interception vulnerability. 

COMMANDS TO VERIFY 
 /interface bridge host print count-only 
 /interface bridge host print 
 /log print where message~"mac" 
 /interface bridge port print 

WHY NOT (Eliminated Hypotheses) 
 NOT a VLAN misconfiguration — frames are flooded to all ports in the same VLAN. 
 NOT a spanning tree issue — no topology changes logged. 
 NOT a deliberate security attack (likely) — timing matches new equipment, not targeted. 
 NOT a firmware bug — consistent behavior when MAC table is full. 

FIX 
 Set MAC address limit per port to prevent table exhaustion: 
 /interface bridge port set [find interface=<customer_port>] learn=yes unknown-unicast-flood=no 
 Implement port security: limit MACs per customer port to 2-4. 
 Identify and address the specific port generating excessive MACs. 

PREVENTION 
 Enable port security with MAC address limits on all customer-facing ports. 
 Monitor MAC table utilization; alert at 80%. 
 Treat MAC flooding as a potential security incident requiring investigation. 

VLAN / L2 Issue 
 Scenario #22 

22. PVID misconfiguration → untagged traffic enters wrong VLAN → wrong subnet assigned 

INPUT — Observed Signals 
 One new customer getting IP from wrong subnet. Other customers on same switch fine. Logs show: 
 - Customer getting 10.20.0.x IP (VLAN 20) instead of expected 10.10.0.x (VLAN 10) 
 - DHCP server correctly has separate pools for each VLAN 
 - Switch port appeared correctly configured in the ticket 
 - Problem specific to this one port (ether9) 
 - VLAN 10 DHCP pool has available leases 

EXPECTED REASONING 
 Customer gets VLAN 20 address instead of VLAN 10 = untagged traffic from this port is entering VLAN 20&apos;s broadcast domain, reaching VLAN 20&apos;s DHCP pool. 

"Switch port appeared correctly configured" means visual inspection missed the error — need to check the actual PVID (Port VLAN ID) value, not just the allowed VLAN list. 

PVID is the VLAN ID assigned to untagged ingress traffic. If PVID is set to 20 instead of 10 on ether9, all untagged CPE traffic enters VLAN 20. 

ROOT CAUSE 
 Port VLAN ID (PVID) on ether9 set to VLAN 20 instead of VLAN 10, causing untagged CPE traffic to enter VLAN 20&apos;s broadcast domain and receive an IP address from the VLAN 20 DHCP pool. 

COMMANDS TO VERIFY 
 /interface bridge port print detail where interface=ether9 
 /interface bridge vlan print 
 /ip dhcp-server lease print where address~"10.20" 
 /log print where message~"ether9" 

WHY NOT (Eliminated Hypotheses) 
 NOT a DHCP pool error — server is correctly issuing from the VLAN it receives traffic on. 
 NOT a CPE issue — CPE sends untagged traffic as expected. 
 NOT a VLAN trunk issue — problem is on access port, not trunk. 
 NOT a routing issue — problem occurs before routing (L2 VLAN assignment). 

FIX 
 /interface bridge port set [find interface=ether9] pvid=10 

PREVENTION 
 Verify PVID explicitly in port configuration review — not just allowed VLANs. 
 Test DHCP and verify correct subnet from a client on every new port before activation. 
 Add PVID to provisioning checklist. 

VLAN / L2 Issue 
 Scenario #23 

23. Hairpin / reflective relay disabled → hosts on same subnet cannot reach each other 

INPUT — Observed Signals 
 Two customers on same subnet (192.168.50.x) cannot reach each other. Both can reach internet. Logs show: 
 - Ping from 192.168.50.10 to 192.168.50.20 fails 
 - Both customers can ping the router gateway (192.168.50.1) 
 - Traffic sent to 192.168.50.20 reaches the router (ARP resolves) but is not forwarded 
 - Both customers are on the same VLAN but connected through the router (L3 routing mode) 
 - Router is performing inter-VLAN routing but also routing within the same subnet 

EXPECTED REASONING 
 Both clients reach the router but not each other. ARP resolves (so L2 is working to the router). Traffic is sent to the router for delivery to .20 but is dropped. 

In L3 routing mode where the router acts as the default gateway for all clients, traffic between clients on the same subnet is routed through the router. This requires hairpin routing (also called proxy ARP or local routing) — the router must forward traffic arriving on an interface back out the same interface. 

By default in many configurations, this "same-interface routing" (hairpin) is disabled for security or efficiency reasons. 

ROOT CAUSE 
 Hairpin/reflective routing not enabled on the router for the 192.168.50.0/24 subnet, preventing traffic between two clients on the same subnet from being forwarded when both route through the router as their default gateway. 

COMMANDS TO VERIFY 
 /ip route print 
 /ip firewall nat print 
 /ip arp print 
 /ip firewall filter print where chain=forward 

WHY NOT (Eliminated Hypotheses) 
 NOT a VLAN issue — both clients are on the same VLAN and can reach the router. 
 NOT a firewall blocking — both can reach internet through same firewall rules. 
 NOT a routing table issue — route to 192.168.50.0/24 exists (it&apos;s the local subnet). 
 NOT a cable/physical issue — both clients independently functional. 

FIX 
 Enable IP proxy-ARP or configure intra-subnet routing: 
 /ip firewall filter add chain=forward src-address=192.168.50.0/24 dst-address=192.168.50.0/24 action=accept place-before=0 

PREVENTION 
 Test intra-subnet client-to-client connectivity during network setup. 
 Document whether hairpin routing is needed in network design. 
 Include client-to-client ping test in customer activation checklist. 

VLAN / L2 Issue 
 Scenario #24 

24. IGMP snooping disabled → multicast flooding → IPTV bandwidth saturation 

INPUT — Observed Signals 
 IPTV customers on one segment reporting choppy video and buffering. Internet speed tests normal. Logs show: 
 - Very high broadcast/multicast traffic on the segment 
 - IPTV multicast streams visible on all ports, not just ports with IPTV subscribers 
 - Non-IPTV customers on same segment experiencing slowdowns 
 - IGMP snooping was disabled during a firmware upgrade maintenance window 
 - Problem started immediately after maintenance 

EXPECTED REASONING 
 IPTV uses IP multicast. IGMP snooping is the mechanism that tells the switch which ports have multicast group subscribers — without it, multicast is flooded to all ports in the VLAN (treated as broadcast). 

When IGMP snooping is disabled, every IPTV stream (potentially 6–10 Mbps per channel) is sent to every port, saturating the segment&apos;s bandwidth regardless of whether subscribers have requested it. 

Non-IPTV customers suffering = collateral damage from multicast flooding consuming shared bandwidth. 

Timing (after firmware upgrade maintenance) = the event anchor. 

ROOT CAUSE 
 IGMP snooping disabled during firmware upgrade maintenance, causing all multicast IPTV streams to be flooded to every port on the VLAN instead of only to subscribing ports, saturating available bandwidth. 

COMMANDS TO VERIFY 
 /interface bridge print detail 
 /interface bridge mdb print 
 /interface bridge port print 
 /interface print stats (check multicast counters) 

WHY NOT (Eliminated Hypotheses) 
 NOT an IPTV server fault — streams are arriving at the switch correctly. 
 NOT a bandwidth capacity issue — problem appeared suddenly at maintenance, not gradually. 
 NOT a CPE issue — problem affects all customers on segment, not one device. 
 NOT a routing issue — multicast flooding is L2, below routing layer. 

FIX 
 /interface bridge set bridge1 igmp-snooping=yes 
 /interface bridge port set [find] multicast-router=auto 

PREVENTION 
 Include IGMP snooping status in post-maintenance verification checklist. 
 Never disable IGMP snooping in production without understanding impact. 
 Monitor multicast traffic rates; alert if unusually high flooding detected. 

Routing / NAT Failure 
 Scenario #25 

25. Default route removed → all internet traffic black-holed → no error to customers 

INPUT — Observed Signals 
 All customers offline but local network working. Logs show: 
 - Customers can ping router gateway 
 - Customers cannot reach any internet IP 
 - Router can ping its WAN IP but cannot reach 8.8.8.8 
 - Routing table shows only local routes, no default route 
 - A script ran 2 hours ago during maintenance to clean up old routes 

EXPECTED REASONING 
 Customers can ping gateway + router has WAN IP = L1/L2 and local routing are fine. Router cannot reach 8.8.8.8 = no route to internet. Routing table has no default route = decisive evidence. 

The maintenance script is the event anchor. Route cleanup scripts that match too broadly can delete the default route if the matching criteria include 0.0.0.0/0. 

This is a pure routing table issue — no hardware fault, no physical problem, no protocol failure. 

ROOT CAUSE 
 Maintenance script accidentally removed the default route (0.0.0.0/0) while cleaning up old routes, causing all internet-destined traffic to be black-holed at the router. 

COMMANDS TO VERIFY 
 /ip route print 
 /ip route print where dst-address=0.0.0.0/0 
 /log print where message~"route" 
 /ping 8.8.8.8 

WHY NOT (Eliminated Hypotheses) 
 NOT a WAN link failure — router has WAN IP and can reach directly connected WAN subnet. 
 NOT a firewall issue — router itself cannot reach internet, confirming routing not firewall. 
 NOT a NAT failure — routing failure precedes NAT processing. 
 NOT a DHCP issue — customers have valid IPs and can reach gateway. 

FIX 
 /ip route add dst-address=0.0.0.0/0 gateway=<wan_gateway_ip> 
 Verify connectivity immediately: 
 /ping 8.8.8.8 

PREVENTION 
 Never run route modification scripts without dry-run verification first. 
 Protect the default route with a comment marker that cleanup scripts check for. 
 After any maintenance, verify default route presence as first post-check step. 

Routing / NAT Failure 
 Scenario #26 

26. NAT masquerade rule deleted → traffic sent unmasked → ISP drops RFC1918 sources 

INPUT — Observed Signals 
 All customers lose internet simultaneously. Logs show: 
 - Customers have valid IPs and gateway 
 - Router has valid WAN IP 
 - Default route exists 
 - Traceroute from customer exits the router but stops at first ISP hop 
 - ISP confirms seeing traffic from 192.168.x.x source IPs (private RFC1918) 
 - A firewall rule cleanup was done earlier today 

EXPECTED REASONING 
 Traffic leaves the router (traceroute shows first hop) but ISP drops it. ISP sees RFC1918 source IPs = NAT masquerade is not being applied. Private source IPs reaching the internet are dropped by ISP border filters (standard practice — RFC 3704). 

The routing is correct (traffic reaches ISP). The WAN IP exists. The default route exists. The only thing missing is NAT. 

Firewall rule cleanup is the event anchor — the masquerade rule was likely deleted as part of cleanup. 

This is subtly different from a routing failure: traffic IS leaving the router, it just isn&apos;t being source-NATted before it does. 

ROOT CAUSE 
 NAT masquerade rule deleted during firewall cleanup, causing customer traffic (with private RFC1918 source IPs) to reach the ISP unmasked, where it is dropped by RFC3704 ingress filtering. 

COMMANDS TO VERIFY 
 /ip firewall nat print 
 /ip firewall nat print where chain=srcnat 
 /log print where message~"nat" 
 /tool packet-sniffer sniff interface=<wan_interface> 

WHY NOT (Eliminated Hypotheses) 
 NOT a routing issue — traceroute shows traffic leaving router correctly. 
 NOT a WAN link failure — ISP is receiving the traffic (they can see it). 
 NOT a DHCP or IP issue — customers have valid addresses. 
 NOT an ISP block — ISP is filtering RFC1918 sources per standard policy, not targeted. 

FIX 
 /ip firewall nat add chain=srcnat action=masquerade out-interface=<wan_interface> 

PREVENTION 
 Protect critical NAT rules with comments marking them as "DO NOT DELETE". 
 Include NAT rule presence check in all post-maintenance verification steps. 
 Use change management: require review of any firewall/NAT modification. 

Routing / NAT Failure 
 Scenario #27 

27. Policy routing loop → CPU spike → network slowdown 

INPUT — Observed Signals 
 Network slowdown, not complete outage. CPU consistently at 80%+. Logs show: 
 - High CPU caused by forwarding process 
 - Traceroute to some destinations showing repeated same hops (routing loop) 
 - Policy routing rules were added yesterday for traffic shaping 
 - Problem affects traffic to specific IP ranges, not all destinations 
 - BGP routes present and correct 

EXPECTED REASONING 
 Routing loop symptoms: traceroute showing repeated hops, CPU high from excessive packet forwarding, affects specific IP ranges (matching policy route criteria). 

Policy routing rules added yesterday = event anchor. A policy routing rule that sends traffic to a gateway which then routes it back through the same policy rule creates a loop. 

BGP routes correct = the main routing table is not the issue. The problem is in the policy routing table (mangle + routing tables interaction). 

High CPU from forwarding process (not protocol/management) = packets circulating, not a control plane issue. 

ROOT CAUSE 
 Policy routing rule misconfiguration creating a routing loop for specific destination IP ranges, causing packets to circulate between two routers and spike CPU on the forwarding process. 

COMMANDS TO VERIFY 
 /ip route print 
 /ip route print table=<policy_table> 
 /ip firewall mangle print 
 /tool traceroute <affected_destination> 
 /system resource print 

WHY NOT (Eliminated Hypotheses) 
 NOT a BGP fault — BGP sessions stable, main routing table correct. 
 NOT a hardware fault — CPU returns to normal if policy rules removed. 
 NOT a firewall dropping — packets are being forwarded (looping), not dropped. 
 NOT an STP loop — this is L3 routing loop, not L2 broadcast storm. 

FIX 
 Identify the looping policy route: 
 /ip route print table=<policy_table> 
 Remove or correct the routing rule that sends traffic back into the loop. 
 Add a &apos;blackhole&apos; or &apos;unreachable&apos; route to terminate the loop during diagnosis. 

PREVENTION 
 Test policy routing rules in a lab before production deployment. 
 When adding policy routes, always verify the next-hop does not route back through the same rule. 
 Use traceroute after any routing change to verify end-to-end path. 

Routing / NAT Failure 
 Scenario #28 

28. Connection tracking table full → new sessions rejected → established sessions unaffected 

INPUT — Observed Signals 
 New connections failing but existing connections working. Logs show: 
 - "conntrack table full" errors in system log 
 - Existing sessions (streaming, downloads in progress) continue normally 
 - New browsing requests failing (TCP SYN sent, no response or RST) 
 - High number of P2P connections from one IP identified 
 - Total connection count at maximum (65536 or configured limit) 

EXPECTED REASONING 
 Existing sessions OK + new sessions fail = state table exhaustion. Connection tracking (conntrack) maintains state for every active connection. When the table is full, new connections cannot be tracked and are rejected or ignored. 

The distinction between existing vs new sessions is the diagnostic key: stateful firewall can continue processing packets for tracked sessions, but cannot create new entries. 

One IP with P2P connections is the cause: P2P clients can maintain thousands of simultaneous connections (torrent seeding), consuming state table entries that should be shared across all customers. 

ROOT CAUSE 
 Connection tracking table exhausted by a single customer running P2P software with thousands of simultaneous connections, preventing new connections from being established for all customers sharing the table. 

COMMANDS TO VERIFY 
 /ip firewall connection print count-only 
 /ip firewall connection print 
 /ip firewall connection tracking print 
 /log print where message~"conntrack" 
 /ip firewall connection print where src-address~"<offending_ip>" 

WHY NOT (Eliminated Hypotheses) 
 NOT a bandwidth issue — existing high-bandwidth sessions continue unaffected. 
 NOT a routing table issue — routes are all present. 
 NOT a NAT failure — NAT sessions for existing connections are intact. 
 NOT a firewall rule block — established sessions would also be blocked if it were a rule. 

FIX 
 Increase conntrack table size (if RAM permits): 
 /ip firewall connection tracking set max-entries=131072 
 Implement per-IP connection limits: 
 /ip firewall filter add chain=forward src-address=<offending_ip> connection-limit=200,32 action=drop 

PREVENTION 
 Implement per-customer connection limits in forward chain. 
 Monitor conntrack table utilization; alert at 80%. 
 Include connection-limit rules in default customer policy templates. 

Routing / NAT Failure 
 Scenario #29 

29. Asymmetric routing → firewall drops return traffic → TCP handshake incomplete 

INPUT — Observed Signals 
 Customers can ping internet IPs but TCP connections fail. UDP works. Logs show: 
 - ICMP (ping) succeeds to all destinations 
 - TCP SYN sent, SYN-ACK received, ACK sent but connection never established 
 - Firewall log shows return traffic dropped with "invalid state" or "not established" 
 - Two WAN links present (load-balanced) 
 - Outbound traffic uses WAN1, return traffic arriving on WAN2 

EXPECTED REASONING 
 Ping works (ICMP stateless) but TCP fails (stateful) = stateful firewall losing track of sessions. 

Firewall "invalid state" on return traffic = firewall has no record of the outbound SYN, so it drops the SYN-ACK. 

Two WAN links + asymmetric path = outbound SYN left via WAN1, return SYN-ACK arrives via WAN2. The firewall saw the SYN on WAN1 and created a connection tracking entry tied to WAN1. The SYN-ACK arriving on WAN2 does not match the tracked entry → dropped as invalid. 

UDP works because UDP is connectionless — ICMP is also stateless. Only stateful TCP is affected. 

ROOT CAUSE 
 Asymmetric routing between two WAN links causing outbound TCP SYN packets to leave via WAN1 while return SYN-ACK arrives via WAN2, mismatching stateful firewall connection tracking entries and causing all TCP connections to fail. 

COMMANDS TO VERIFY 
 /ip route print 
 /ip firewall connection print 
 /ip firewall filter print where chain=input 
 /log print where topics~"firewall" 
 /tool traceroute <destination> 

WHY NOT (Eliminated Hypotheses) 
 NOT a firewall rule error — ICMP and UDP work through same rule set. 
 NOT a DNS issue — IP addresses fail directly. 
 NOT a WAN link failure — both links are up and functional. 
 NOT a NAT misconfiguration — outbound NAT is correct, issue is return path matching. 

FIX 
 Implement connection-tracking-aware routing to ensure return traffic uses same WAN: 
 Use routing marks tied to connection tracking: 
 /ip firewall mangle add chain=prerouting connection-mark=wan1-conn action=mark-routing new-routing-mark=to-wan1 
 /ip route add gateway=<wan1_gateway> routing-mark=to-wan1 

PREVENTION 
 When deploying dual-WAN, always implement connection-based return routing. 
 Test both TCP and UDP connectivity in both WAN failure scenarios before going live. 
 Document asymmetric routing risk in dual-WAN design. 

Routing / NAT Failure 
 Scenario #30 

30. MTU mismatch → large packets silently dropped → some sites load, others don&apos;t 

INPUT — Observed Signals 
 Customers report some websites work fine, others never load. Logs show: 
 - Small pages and DNS work correctly 
 - Large file downloads hang at start 
 - Ping to affected sites works (small ICMP) 
 - Traceroute completes to affected IPs 
 - PPPoE WAN connection present (MTU typically 1492) 
 - No changes made recently 

EXPECTED REASONING 
 Small packets work, large don&apos;t = MTU/fragmentation issue. The "some sites" pattern is because: well-behaved servers that honor ICMP "too big" messages or probe MTU work fine; servers that set DF (Don&apos;t Fragment) bit and ignore ICMP fragmentation-needed messages fail silently. 

PPPoE reduces MTU by 8 bytes (to 1492). If the router LAN interface MTU is still set to 1500, packets between 1493–1500 bytes hit the WAN and cannot be fragmented (DF bit set) → silently dropped → TCP sessions stall waiting for data that never arrives. 

PMTUD (Path MTU Discovery) works by sending ICMP Type 3 Code 4 "fragmentation needed" messages, but firewalls often block these ICMPs, causing "PMTUD black holes." 

ROOT CAUSE 
 MTU mismatch between LAN (1500) and PPPoE WAN (1492) causing large TCP packets with DF bit set to be silently dropped, creating a PMTUD black hole where sites requiring large packet transfers fail to load. 

COMMANDS TO VERIFY 
 /ip dhcp-server network print 
 /interface print detail where name=pppoe-out1 
 /ip firewall mangle print 
 /ping 8.8.8.8 size=1472 do-not-fragment=yes 
 /ping 8.8.8.8 size=1473 do-not-fragment=yes 

WHY NOT (Eliminated Hypotheses) 
 NOT a DNS issue — DNS (small UDP) works fine. 
 NOT a routing issue — traceroute completes to all destinations. 
 NOT an ISP block — affects specific traffic sizes, not specific destinations. 
 NOT a firewall rule — small packets from same sources pass without issue. 

FIX 
 Enable MSS clamping to adjust TCP maximum segment size: 
 /ip firewall mangle add chain=forward protocol=tcp tcp-flags=syn action=change-mss new-mss=clamp-to-pmtu 
 Set PPPoE interface MTU explicitly: 
 /interface pppoe-client set pppoe-out1 max-mru=1492 max-mtu=1492 

PREVENTION 
 Always configure MSS clamping on PPPoE deployments. 
 Test large file downloads as part of PPPoE circuit acceptance testing. 
 Document MTU settings in network configuration records. 

Routing / NAT Failure 
 Scenario #31 

31. IP address conflict on WAN → ARP fights → intermittent WAN loss 

INPUT — Observed Signals 
 Intermittent internet outages, 30–120 seconds each, several times per day. Logs show: 
 - WAN IP (203.0.113.50) appearing in ARP conflicts in log 
 - Duplicate IP detected periodically 
 - ISP has not changed any config 
 - Problem started after a neighboring customer&apos;s router was replaced 
 - No internal network changes 

EXPECTED REASONING 
 WAN IP ARP conflicts = two devices on the same ISP segment think they own the same IP address. This is an ISP-side problem, not an internal one. 

The neighbor&apos;s router replacement is the event anchor. The new router may have been assigned (incorrectly or by misconfiguration) an IP that overlaps, or the old router&apos;s IP may have been released to the pool and reassigned to the neighbor before their old entry expired. 

When the neighbor&apos;s router ARPs for its IP (which happens to be the same), the ISP switch learns the new MAC and traffic destined for 203.0.113.50 is sent to the wrong device for the duration. 

ROOT CAUSE 
 IP address conflict on the ISP&apos;s shared WAN segment between this customer&apos;s WAN IP and a newly installed neighboring router, causing intermittent ARP table overwrites and traffic misdirection. 

COMMANDS TO VERIFY 
 /log print where message~"arp" 
 /ip arp print 
 /interface ethernet monitor <wan_interface> 
 /tool packet-sniffer sniff interface=<wan_interface> ip-protocol=arp 

WHY NOT (Eliminated Hypotheses) 
 NOT an internal misconfiguration — problem is on ISP segment, not inside the network. 
 NOT a WAN link flap — interface stays UP, ARP conflict causes traffic loss. 
 NOT a firewall block — intermittent and self-resolving. 
 NOT a DHCP issue — this is a static WAN IP. 

FIX 
 Report to ISP with evidence: ARP capture showing conflicting MAC addresses. 
 ISP must investigate and correct the neighboring router&apos;s IP assignment. 
 Temporary: use gratuitous ARP to reclaim address (/tool rarp does not exist in ROS, use /ip arp). 

PREVENTION 
 ISPs should implement dynamic ARP inspection and strict IP assignment tracking. 
 When replacing customer equipment, ensure old ARP entries expire before new device comes up. 
 Maintain IP assignment records with current MAC addresses. 

Routing / NAT Failure 
 Scenario #32 

32. Recursive routing via BGP → route flap oscillation → unstable connectivity 

INPUT — Observed Signals 
 Intermittent connectivity, route table changes every few minutes. Logs show: 
 - BGP routes being added and withdrawn repeatedly 
 - Default route flapping in the routing table 
 - BGP peer is a route reflector passing many routes 
 - CPU elevated during flapping events 
 - One specific prefix causing the instability (identified in logs) 

EXPECTED REASONING 
 BGP routes being added and withdrawn in cycles = route oscillation. A single "bad" prefix can cause this if: the prefix&apos;s next-hop becomes unreachable when the prefix itself is withdrawn, which triggers a recursive routing failure. 

Recursive routing loop: BGP prefix X has next-hop Y, next-hop Y is only reachable via prefix X. When prefix X is withdrawn → Y becomes unreachable → BGP session to Y drops → all routes from Y are withdrawn → BGP reconverges → prefix X re-added → Y reachable again → repeat. 

One specific prefix causing the instability confirms this is not a broad BGP issue. 

ROOT CAUSE 
 Recursive BGP routing dependency: a specific BGP prefix&apos;s next-hop is only reachable via the same prefix, creating an oscillation loop where withdrawal of the prefix makes its own next-hop unreachable, triggering reconvergence which re-announces it. 

COMMANDS TO VERIFY 
 /routing bgp session print 
 /ip route print where bgp=yes 
 /routing bgp advertisement print 
 /log print where topics~"bgp" 
 /ip route print where dst-address=<flapping_prefix> 

WHY NOT (Eliminated Hypotheses) 
 NOT a hardware failure on BGP peer — reconvergence pattern is too clean. 
 NOT an ISP transit failure — specific prefix implicated, not all routes. 
 NOT a MikroTik bug — recursive routing issue is a configuration/design problem. 
 NOT a DDoS — CPU spike coincides with BGP reconvergence, not traffic volume. 

FIX 
 Add a static route for the BGP peer&apos;s next-hop IP to break the recursion: 
 /ip route add dst-address=<nexthop_ip>/32 gateway=<directly_connected_gateway> 
 This ensures the peer&apos;s reachability does not depend on a BGP-learned route. 

PREVENTION 
 For BGP peers, always ensure the peer IP is reachable via a static or directly connected route, not via a BGP-learned route. 
 Test BGP failover scenarios before going live. 
 Use BFD for faster peer failure detection. 

PPPoE / Session Failure 
 Scenario #33 

33. PPPoE AC not responding → all new sessions fail → reconnects infinite loop 

INPUT — Observed Signals 
 Mass PPPoE session failure. No new sessions establishing. Logs show: 
 - PPPoE PADI packets being sent but no PADO responses 
 - Existing sessions that did not disconnect are still working 
 - RADIUS server logs show no authentication requests 
 - PPPoE concentrator (AC) process restarted unexpectedly 
 - Happened during peak hour traffic 

EXPECTED REASONING 
 PADI sent, no PADO = Access Concentrator (AC) is not responding. The AC is either crashed, overloaded, or network path to AC is broken. 

Existing sessions still working = PPPoE sessions are maintained in hardware/state tables, they don&apos;t require the AC to stay up. Only new session establishment requires AC. 

RADIUS seeing no requests = the problem is before RADIUS — the AC is not even processing the PADI to the point of sending an authentication request. 

AC process restarted = process crashed (OOM, bug, overload), this is the root cause. 

ROOT CAUSE 
 PPPoE Access Concentrator process crashed (likely OOM or unexpected exception during peak load), preventing new session establishment. Existing sessions maintained in state tables and unaffected. 

COMMANDS TO VERIFY 
 /ppp active print count-only 
 /log print where topics~"pppoe" 
 /log print where message~"padi" 
 /ppp secret print count-only 
 /system resource print 

WHY NOT (Eliminated Hypotheses) 
 NOT a RADIUS authentication failure — RADIUS never receives requests. 
 NOT a network path failure — existing sessions would also drop. 
 NOT a customer CPE issue — all new sessions from all CPEs failing. 
 NOT a bandwidth issue — existing sessions functional at full capacity. 

FIX 
 Restart PPPoE server process: 
 /interface pppoe-server server enable server1 
 Investigate root cause of crash (OOM killer, bug) in system log. 
 /log print where topics~"system" interval=00:01:00 

PREVENTION 
 Monitor PPPoE AC process health, not just session count. 
 Alert when PPPoE new session establishment rate drops to zero while sessions exist. 
 Tune system resources and session limits to prevent OOM crashes. 

PPPoE / Session Failure 
 Scenario #34 

34. RADIUS timeout → PPPoE authentication delay → slow connection establishment 

INPUT — Observed Signals 
 Customers experiencing 30–60 second delays when connecting, but eventual success. Logs show: 
 - PPPoE PADI/PADO exchange immediate 
 - Authentication (CHAP/PAP) phase hangs for 30–60 seconds 
 - RADIUS server IP reachable (ping works) 
 - RADIUS server logs show requests arriving but slowly 
 - Problem started after RADIUS server was moved to new VM host 

EXPECTED REASONING 
 PADI/PADO fast = AC working. Authentication hangs = RADIUS timeout + retry. 

RADIUS default behavior: send request, wait (timeout), retry, wait, retry — eventually succeeds or fails. The 30-60 second delay matches a RADIUS timeout (typically 5-10s) × retry count (3-6) = the first few attempts time out and eventually the server responds. 

RADIUS server "reachable" but "requests arriving slowly" = processing latency on the server side, not network path. VM host migration likely caused CPU/resource contention on the new host. 

The server IS responding eventually (customers succeed) — this is a latency issue not a complete failure. 

ROOT CAUSE 
 RADIUS server experiencing high processing latency after VM host migration (likely CPU/memory contention on new host), causing authentication requests to timeout and retry, adding 30-60 seconds to every PPPoE connection. 

COMMANDS TO VERIFY 
 /log print where topics~"pppoe" interval=00:00:10 
 /radius print 
 /log print where message~"radius" 
 /ping <radius_ip> 
 /tool bandwidth-test address=<radius_ip> 

WHY NOT (Eliminated Hypotheses) 
 NOT a network path issue — ping to RADIUS works, path is clear. 
 NOT an AC configuration error — PADI/PADO phase is immediate. 
 NOT a RADIUS authentication failure — customers succeed eventually. 
 NOT a MikroTik bug — behavior is expected for RADIUS timeout + retry. 

FIX 
 Immediately: tune RADIUS timeout/retry on MikroTik to detect faster: 
 /radius set timeout=3 authentication-port=1812 retransmit=2 
 Long-term: investigate and resolve RADIUS server resource contention on new VM host. 

PREVENTION 
 After RADIUS server migration, run connection timing tests before declaring success. 
 Monitor RADIUS response time as a KPI (target <200ms). 
 Allocate dedicated CPU/memory to RADIUS VM, not shared pool. 

PPPoE / Session Failure 
 Scenario #35 

35. LCP echo failure → PPPoE keeps alive failing → sessions drop every ~60s 

INPUT — Observed Signals 
 PPPoE sessions dropping every 55–65 seconds for specific customers. Others fine. Logs show: 
 - LCP echo-request sent, no echo-reply received 
 - Sessions terminated with "LCP echo timeout" message 
 - Affected customers all on same VLAN segment 
 - Packet capture shows LCP echos going out, replies never arriving back 
 - Physical link stays UP throughout 

EXPECTED REASONING 
 Regular interval drops (~60s) = keepalive timer. LCP echo is the PPPoE keepalive mechanism: the AC sends LCP echo-request, expects echo-reply from the CPE. Timeout = session terminated. 

All affected customers on same VLAN = the problem is somewhere in the L2 path for that VLAN, not in the CPEs themselves (different CPE models would all have to fail the same way). 

LCP echos leaving but replies not arriving = L2 asymmetry or filtering. Possible causes: VLAN config dropping reply traffic, ACL blocking LCP frames, or a managed switch on that segment filtering PPPoE control frames. 

Physical link UP = L1 is fine, L2 path issue. 

ROOT CAUSE 
 L2 path issue on the affected VLAN dropping LCP echo-reply frames (but not echo-request frames), creating asymmetric PPPoE control frame delivery and causing all sessions on that VLAN to terminate on keepalive timeout. 

COMMANDS TO VERIFY 
 /log print where topics~"pppoe" 
 /log print where message~"echo" 
 /tool packet-sniffer sniff interface=<vlan_interface> protocol=pppoe 
 /interface bridge port print 
 /interface vlan print 

WHY NOT (Eliminated Hypotheses) 
 NOT a CPE firmware issue — affects multiple CPE models simultaneously. 
 NOT an LCP configuration error — timer mismatch would cause all sessions to fail, not just this VLAN. 
 NOT a physical cable fault — link stays UP, and other VLANs work on same physical interface. 
 NOT a RADIUS issue — sessions are established successfully then drop later. 

FIX 
 Identify and remove the L2 element dropping LCP reply frames on that VLAN. 
 Check for ACLs on any managed switches in the path. 
 Verify VLAN trunk is passing all frame types bidirectionally. 

PREVENTION 
 Test PPPoE session stability (maintain a session for >300s) on every VLAN after VLAN changes. 
 Log LCP echo failure events and alert if any customer has >2 per hour. 
 When introducing managed switches, verify PPPoE traffic passes bidirectionally. 

PPPoE / Session Failure 
 Scenario #36 

36. PPPoE duplicate session → new session rejected, old stale session held in RADIUS 

INPUT — Observed Signals 
 One specific customer cannot reconnect after power outage. Other customers fine. Logs show: 
 - PPPoE authentication succeeds (RADIUS accepts) 
 - Session rejected with "already logged in" or "maximum sessions reached" 
 - RADIUS shows an active session for this customer from 4 hours ago 
 - Customer had a power outage 30 minutes ago 
 - RADIUS accounting stop was never received for old session 

EXPECTED REASONING 
 RADIUS accepts credentials but rejects session = the session limit check in RADIUS (or the AC) is seeing an existing active session for this user. 

Power outage → CPE lost power → did not send LCP terminate → AC did not send RADIUS accounting-stop → RADIUS still thinks old session is active → rejects new session. 

This is a classic "stale session" problem caused by abrupt disconnection without clean LCP termination. 

The old session is a ghost: the AC may have already removed it internally (after its own timeout), but RADIUS was never notified. 

ROOT CAUSE 
 Stale PPPoE session record in RADIUS caused by power outage preventing clean LCP termination and RADIUS accounting-stop, leaving RADIUS believing the customer is still connected and rejecting new session establishment. 

COMMANDS TO VERIFY 
 /ppp active print where name~"<username>" 
 /log print where message~"<username>" 
 /log print where topics~"pppoe" 

WHY NOT (Eliminated Hypotheses) 
 NOT a wrong password — RADIUS authentication succeeds. 
 NOT an AC failure — other customers connect fine. 
 NOT a hardware fault — problem is specific to this user&apos;s RADIUS state. 
 NOT a network issue — the session is being rejected before any network path matters. 

FIX 
 Clear the stale session from RADIUS server directly. 
 On MikroTik AC side: /ppp active remove [find name="<username>"] 
 Configure RADIUS interim accounting updates so stale sessions auto-expire: 
 /radius set accounting=yes interim-update=00:01:00 

PREVENTION 
 Enable RADIUS interim accounting updates (every 60–120 seconds) to auto-expire stale sessions. 
 Configure session timeout in RADIUS to match expected maximum session duration. 
 Implement automatic stale session cleanup script. 

PPPoE / Session Failure 
 Scenario #37 

37. PPPoE session limit per-VLAN exceeded → overflow customers get no service 

INPUT — Observed Signals 
 New customers unable to connect on VLAN 300. All customers on VLAN 100 and 200 fine. Logs show: 
 - VLAN 300 showing max-sessions reached 
 - Existing customers on VLAN 300 unaffected 
 - PPPoE server configuration shows sessions-max=100 for VLAN 300 interface 
 - VLAN 300 currently has 98 active sessions 
 - Two new customers signed up and cannot connect 

EXPECTED REASONING 
 Sessions-max reached + existing customers fine + new customers fail = hard session limit. The count (98 active, max 100) and two new customers correlates exactly. 

This is not a fault — it is a capacity configuration limit being hit. The session limit is correctly enforced. 

The decision: is this limit intentional (security, resource management) or was it set during initial deployment and not updated as the segment grew? 

A 100-session limit on a VLAN is quite common for resource planning on MikroTik. 

ROOT CAUSE 
 PPPoE server session limit (sessions-max=100) reached on VLAN 300 interface, preventing new session establishment while all existing 98 sessions continue normally. 

COMMANDS TO VERIFY 
 /interface pppoe-server server print 
 /ppp active print count-only where interface~"vlan300" 
 /log print where message~"max-sessions" 
 /interface pppoe-server server print detail 

WHY NOT (Eliminated Hypotheses) 
 NOT a RADIUS failure — RADIUS never even reached (session rejected before auth). 
 NOT a network fault — existing sessions continue normally. 
 NOT a VLAN issue — VLAN 100 and 200 (different limits) unaffected. 
 NOT a CPE problem — multiple new customers all failing. 

FIX 
 /interface pppoe-server server set [find interface=vlan300] max-sessions=200 
 Connect new customers after confirming system resources support the higher limit. 

PREVENTION 
 Monitor active session count per VLAN; alert at 80% of max. 
 Review and update session limits as subscriber counts grow. 
 Include session capacity check in provisioning workflow before activating new customers. 

PPPoE / Session Failure 
 Scenario #38 

38. CHAP secret mismatch → authentication failure loop → customer never connects 

INPUT — Observed Signals 
 One new customer unable to connect, all existing customers fine. Logs show: 
 - PPPoE PADI/PADO exchange successful 
 - CHAP challenge sent by AC 
 - CHAP response received from CPE 
 - RADIUS returns Access-Reject 
 - Customer has triple-checked username and password 

EXPECTED REASONING 
 PADI/PADO success = L2 path and AC are fine. CHAP challenge/response exchange happening = PPPoE session negotiating. RADIUS Access-Reject = credential or attribute mismatch. 

"Customer triple-checked password" — but CHAP authentication is case-sensitive and the issue may not be the password itself. Common causes: (1) username has trailing space, (2) case mismatch in username, (3) RADIUS profile exists but Service-Type attribute mismatch rejects for authorization, not authentication. 

Check RADIUS for the exact reject reason — RADIUS Access-Reject packets contain Reply-Message or Error-Cause attributes. 

ROOT CAUSE 
 CHAP authentication rejected by RADIUS — most likely trailing whitespace in username, case mismatch, or a RADIUS authorization attribute mismatch (correct credentials but rejected profile). RADIUS Access-Reject log will contain the specific reason. 

COMMANDS TO VERIFY 
 /log print where topics~"pppoe" 
 /log print where message~"reject" 
 /log print where message~"<username>" 
 /ppp secret print where name~"<username>" 

WHY NOT (Eliminated Hypotheses) 
 NOT an AC fault — PADI/PADO and challenge exchange are working. 
 NOT a network path issue — RADIUS receives and responds to the request. 
 NOT a CPE hardware fault — authentication is reaching the correct stage. 
 NOT an expired account — RADIUS Active-Reject pattern differs from expiry. 

FIX 
 Check RADIUS user record for exact username (case, spaces). 
 Verify no trailing whitespace in username or password fields. 
 Check RADIUS profile attributes (Service-Type, Framed-Protocol must match PPPoE). 
 Re-provision credentials if mismatch found. 

PREVENTION 
 Trim whitespace from all username/password inputs in provisioning system. 
 Test authentication before customer activation using RADIUS test tool. 
 Log RADIUS reject reasons for diagnostic visibility. 

PPPoE / Session Failure 
 Scenario #39 

39. RADIUS CoA disconnect → sessions terminated by billing system → customers unexpectedly offline 

INPUT — Observed Signals 
 Batch of customers disconnected simultaneously. Billing team ran a collection job. Logs show: 
 - RADIUS Disconnect-Request (CoA) received from billing server 
 - Sessions for customers with overdue accounts terminated 
 - Some customers flagged as overdue were actually paid (payment processing lag) 
 - Mass calls to support 
 - Problem is billing system issue, not network fault 

EXPECTED REASONING 
 RADIUS CoA is a legitimate mechanism for billing-triggered disconnection. The timeline is clear: billing system runs collection job → sends Disconnect-Request to RADIUS → RADIUS sends to AC → AC terminates sessions. 

The network is functioning correctly — it is executing billing instructions. The fault is in the billing system&apos;s data (incorrectly marking paid customers as overdue due to payment processing lag). 

However, network team needs to verify: (1) CoA traffic is legitimate (correct source IP), (2) No unauthorized disconnect requests, (3) Restore sessions for incorrectly disconnected customers. 

ROOT CAUSE 
 RADIUS Change of Authorization (CoA) Disconnect-Requests sent by billing system incorrectly flagging paid customers as overdue due to payment processing lag, resulting in legitimate sessions being terminated by billing-triggered disconnection. 

COMMANDS TO VERIFY 
 /log print where message~"disconnect" 
 /log print where topics~"radius" 
 /ppp active print 
 /log print where message~"coa" 

WHY NOT (Eliminated Hypotheses) 
 NOT a network hardware fault — network functioned correctly, executed valid CoA. 
 NOT a MikroTik bug — CoA processing per RFC 5176. 
 NOT an unauthorized intrusion — source IP matches known billing server. 
 NOT a routing issue — sessions terminated cleanly, not dropped by routing. 

FIX 
 Immediately: restore sessions for incorrectly disconnected customers manually. 
 Notify billing team of data accuracy issue. 
 Implement CoA audit log: before executing disconnect, verify account status via secondary check. 

PREVENTION 
 Add payment-confirmation hold period (15–30 min) between payment processing and CoA action. 
 Implement CoA dry-run mode for collection jobs: log intended disconnections, review before executing. 
 Separate payment-lag grace period from active disconnect threshold. 

PPPoE / Session Failure 
 Scenario #40 

40. LCP MRU negotiation failure → oversized PPPoE frames → silent black hole for large payloads 

INPUT — Observed Signals 
 Customers on a new segment can browse basic sites but video streaming and large file downloads fail silently. Logs show: 
 - PPPoE sessions established successfully 
 - DNS and small HTTP requests work 
 - Large payloads (>1400 bytes) never arrive at destination 
 - LCP negotiation shows MRU mismatch in verbose log 
 - New DSLAM/BRAS equipment was deployed on this segment 

EXPECTED REASONING 
 Sessions establish (LCP negotiation succeeds at session layer) but large payloads fail = MRU (Maximum Receive Unit) negotiation produced mismatched effective limits. 

DNS (small UDP), basic browsing (small HTTP GET/HEAD) work. Video (large continuous TCP segments) fails silently. This is the MTU/MRU signature: the handshake works because SYN/SYN-ACK are small, but data frames exceeding the effective MRU are silently dropped. 

New DSLAM/BRAS equipment = the event anchor. New hardware may negotiate different MRU values or enforce stricter frame size limits. 

LCP verbose log showing MRU mismatch is the confirmatory signal. 

ROOT CAUSE 
 LCP MRU negotiation producing a mismatched effective MTU between the new DSLAM/BRAS equipment and the MikroTik router, causing all PPPoE frames larger than the negotiated MRU to be silently dropped. 

COMMANDS TO VERIFY 
 /interface pppoe-client print detail where name=<pppoe_interface> 
 /interface pppoe-server server print detail 
 /log print where message~"mru" 
 /log print where message~"lcp" 
 /ping <destination> size=1400 do-not-fragment=yes 
 /ping <destination> size=1450 do-not-fragment=yes 

WHY NOT (Eliminated Hypotheses) 
 NOT a RADIUS or authentication issue — sessions are fully established. 
 NOT a routing problem — small packets reach correct destinations. 
 NOT a firewall rule — large packets from all customers on segment fail equally. 
 NOT a customer CPE issue — problem is at the BRAS/router LCP layer. 

FIX 
 Explicitly set MRU/MTU on PPPoE interface to match DSLAM capability: 
 /interface pppoe-server server set <server> mrru=1500 
 /interface pppoe-client set <client> max-mtu=1480 max-mru=1480 
 Add MSS clamping as belt-and-suspenders fix. 

PREVENTION 
 After deploying new BRAS/DSLAM equipment, test large payload transfer (>1400 bytes) as part of acceptance testing. 
 Document MRU settings for each equipment type in the network. 
 Always deploy MSS clamping as standard practice on all PPPoE segments. 

Security / Advanced 
 Scenario #41 

41. ARP spoofing attack → gateway MAC poisoned → traffic intercepted 

INPUT — Observed Signals 
 Customers reporting slow speeds and unusual DNS results. Security alert triggered. Logs show: 
 - ARP table showing gateway IP resolving to an unexpected MAC address 
 - Multiple customers being served ARP replies claiming to be the gateway 
 - Ping to gateway succeeds but certificate warnings on HTTPS sites 
 - Packet capture shows traffic from customers going to an unknown host before reaching internet 
 - One customer&apos;s compromised host identified as source of gratuitous ARPs 

EXPECTED REASONING 
 ARP table: gateway IP → wrong MAC = ARP poisoning/spoofing. An attacker is sending gratuitous ARP replies claiming the gateway IP belongs to their MAC address, redirecting all customer traffic through their machine. 

HTTPS certificate warnings = attacker attempting SSL stripping or serving their own certificate (man-in-the-middle). 

Traffic going to unknown host = traffic is being intercepted (forwarded by attacker, or dropped). 

Source identified as compromised customer host = internal ARP poisoning attack, not external. 

ROOT CAUSE 
 ARP spoofing attack from a compromised customer host, poisoning the ARP tables of neighboring customers to redirect their traffic through the attacker&apos;s machine for interception (man-in-the-middle attack). 

COMMANDS TO VERIFY 
 /ip arp print 
 /log print where topics~"arp" 
 /tool packet-sniffer sniff interface=<segment> arp 
 /interface bridge host print 
 /ip arp print where mac-address=<attacker_mac> 

WHY NOT (Eliminated Hypotheses) 
 NOT a DHCP rogue server — ARP table shows gateway IP poisoned, not wrong DHCP gateway. 
 NOT a routing issue — traffic reaches next hop, just the wrong one. 
 NOT a hardware fault — highly specific and targeted behavior pattern. 
 NOT a DNS attack — certificate warnings confirm HTTPS interception, not DNS only. 

FIX 
 Immediately isolate the compromised host: disable its switch port. 
 Flush poisoned ARP entries: /ip arp flush 
 Add static ARP entry for gateway: 
 /ip arp add address=<gateway_ip> mac-address=<real_gateway_mac> interface=<interface> 
 Enable ARP protection (Dynamic ARP Inspection equivalent) on customer VLANs. 

PREVENTION 
 Enable static ARP entries for all infrastructure gateway IPs. 
 Implement DAI (Dynamic ARP Inspection) on managed switches. 
 Isolate each customer to their own /30 or use private VLANs to prevent ARP between customers. 

Security / Advanced 
 Scenario #42 

42. DNS amplification → outbound UDP port 53 flood → uplink saturation 

INPUT — Observed Signals 
 Severe uplink saturation. ISP threatens null-route. Logs show: 
 - Massive outbound UDP traffic on port 53 from router WAN interface 
 - Source addresses are random internet IPs (spoofed) 
 - DNS response sizes much larger than requests (100-byte query → 4000-byte response) 
 - Router&apos;s DNS resolver is open (accepts queries from any source) 
 - ISP reports router is participating in DDoS amplification attack 

EXPECTED REASONING 
 UDP port 53 + spoofed source IPs + large responses = DNS amplification attack. The router&apos;s open resolver is being abused as an amplifier: attacker sends small DNS queries with spoofed victim IP, router sends large responses to victim. 

The router is not the target — it is an unwilling participant. The attack traffic is outbound (responses), not inbound (the router is the amplifier). 

Logs showing responses much larger than requests (amplification factor) confirm this. 

The fix is to close the open resolver to external queries, not to block DNS traffic entirely. 

ROOT CAUSE 
 Router DNS resolver accepting and responding to queries from external/internet source IPs (open resolver), being exploited as a DNS amplification reflector in a DDoS attack against a third-party victim. 

COMMANDS TO VERIFY 
 /ip dns print 
 /ip firewall filter print 
 /ip firewall connection print where protocol=udp dst-port=53 
 /tool packet-sniffer sniff ip-protocol=udp port=53 

WHY NOT (Eliminated Hypotheses) 
 NOT a customer attacking — spoofed source IPs are internet addresses, not customer subnet. 
 NOT an inbound DDoS against this network — router is the amplifier, not the victim. 
 NOT a malware infection on router — router DNS is functioning as designed, just open to abuse. 
 NOT a routing misconfiguration — traffic routing is correct, policy is wrong. 

FIX 
 Restrict DNS resolver to only serve local customers: 
 /ip dns set allow-remote-requests=no 
 Or restrict via firewall: 
 /ip firewall filter add chain=input protocol=udp dst-port=53 src-address-list=!local-networks action=drop 

PREVENTION 
 Never enable allow-remote-requests=yes on production router DNS resolvers. 
 Include "DNS open resolver check" in new router deployment checklist. 
 Regularly scan for open resolvers from external perspective. 

Security / Advanced 
 Scenario #43 

43. CPE compromised → botnet C2 traffic → customer flagged by ISP abuse team 

INPUT — Observed Signals 
 ISP abuse team contacts about a specific customer IP generating suspicious traffic. Logs show: 
 - Outbound connections from customer IP to multiple international IPs on ports 6667, 4444, 8080 
 - Connection pattern: many short-lived connections, never-ending reconnect cycle 
 - Customer reports no issues with their service (unaware) 
 - Traffic volume small but connection count very high 
 - Pattern matches known botnet IRC/C2 communication 

EXPECTED REASONING 
 Customer unaware + unusual outbound connection pattern + known C2 ports = customer&apos;s device is compromised (malware/botnet). The customer&apos;s CPE or a device behind it has been infected. 

Port 6667 = IRC (historically used by botnets for command and control). Port 4444 = common metasploit/RAT port. Port 8080 = alternative HTTP often used for C2. 

Never-ending reconnect cycle = the malware is attempting to re-establish its C2 connection even when blocked or disconnected. 

The network is functioning normally — the problem is on the customer&apos;s device. 

ROOT CAUSE 
 Customer&apos;s device (CPE or LAN device) compromised by malware participating in a botnet, generating ongoing command-and-control traffic to external servers on known C2 ports. 

COMMANDS TO VERIFY 
 /ip firewall connection print where src-address~"<customer_ip>" 
 /ip firewall connection print where src-address~"<customer_ip>" protocol=tcp 
 /log print where message~"<customer_ip>" 
 /ip flow-tracking print (if configured) 

WHY NOT (Eliminated Hypotheses) 
 NOT a network misconfiguration — traffic is legitimate from network perspective. 
 NOT a DHCP issue — IP assignment is correct. 
 NOT a routing problem — traffic reaches intended (C2) destinations. 
 NOT the customer deliberately attacking — customer unaware, device compromised. 

FIX 
 Notify customer of compromise. Provide remediation guidance. 
 Temporarily block C2 IPs/ports if ISP requires immediate action: 
 /ip firewall filter add chain=forward src-address=<customer_ip> dst-port=6667,4444 protocol=tcp action=drop 
 Document and monitor for recurrence. 

PREVENTION 
 Implement outbound connection rate limiting per customer. 
 Monitor for known botnet port patterns in NetFlow/traffic analysis. 
 Provide customer-facing security notifications for detected abuse patterns. 

Security / Advanced 
 Scenario #44 

44. CPU 100% from excessive log writing → router unresponsive → watchdog reboot 

INPUT — Observed Signals 
 Router became unresponsive and rebooted. After reboot, logs show: 
 - Before reboot: log write rate extremely high (thousands per second) 
 - Before reboot: CPU 100% in logging process 
 - A new firewall rule was added with "log=yes" on a high-traffic chain 
 - The rule matched almost all traffic due to broad match criteria 
 - Router watchdog triggered the reboot 

EXPECTED REASONING 
 CPU 100% in logging + rule with log=yes + broad match = logging-induced CPU overload. Every packet matching the rule generates a log entry. If a broad rule (e.g., log all forward chain traffic) is added to a busy router with thousands of packets per second, the logging subsystem is overwhelmed. 

The watchdog reboot is a self-protection mechanism. It is working as intended. 

The root cause is the logging rule, not a hardware fault or attack. 

After reboot, if the rule persists, the cycle will repeat. The rule must be removed or logging disabled before the router is overloaded again. 

ROOT CAUSE 
 Firewall rule with log=yes added with overly broad match criteria on a high-traffic chain, generating thousands of log entries per second and overloading the router CPU until the watchdog triggered a reboot. 

COMMANDS TO VERIFY 
 /ip firewall filter print 
 /log print where topics~"firewall" 
 /system resource print 
 /system routerboard settings print (check watchdog) 

WHY NOT (Eliminated Hypotheses) 
 NOT a DDoS attack — traffic is normal customer traffic, just being logged. 
 NOT a hardware failure — CPU load directly caused by logging overhead. 
 NOT a firmware bug — logging load is expected behavior for broad rules. 
 NOT a network routing loop — CPU consumer is the log process, not forwarding. 

FIX 
 Immediately remove or disable the broad logging rule: 
 /ip firewall filter disable [find log=yes chain=forward] 
 If logging is needed, narrow the match criteria before re-enabling: 
 /ip firewall filter set [find] src-address=<specific_subnet> log=yes 

PREVENTION 
 Never add log=yes to rules in high-traffic chains without narrow match criteria. 
 Test log rule impact in maintenance window before production. 
 Set syslog to remote server to reduce router CPU load from logging. 

Security / Advanced 
 Scenario #45 

45. BGP hijack attempt → unauthorized prefix announcement → traffic rerouted 

INPUT — Observed Signals 
 Traffic for a customer&apos;s static IP block behaving strangely. Security monitoring alert. Logs show: 
 - BGP routing table shows unexpected route for customer prefix from unknown peer 
 - Traffic destined for customer&apos;s IPs arriving from wrong direction 
 - Customer reports receiving traffic from unknown sources 
 - BGP route has shorter AS path than legitimate route (appears more specific) 
 - ISP&apos;s BGP looking glass shows the prefix being announced from two sources 

EXPECTED REASONING 
 Unauthorized BGP announcement of a customer&apos;s prefix = BGP hijack attempt. An attacker (or misconfigured router) is announcing the customer&apos;s prefix with a shorter/more specific route, causing global traffic to be directed to the attacker. 

The customer receives unexpected traffic because some of it is still arriving via the legitimate path, while other traffic is hijacked. 

BGP hijacks are often identified via: route monitoring services, NOC alerts, or customers reporting unusual traffic patterns. 

This requires coordination with upstream ISPs to filter the unauthorized announcement. 

ROOT CAUSE 
 BGP prefix hijack: an unauthorized AS is announcing the customer&apos;s IP prefix with a more attractive (shorter) AS path, causing traffic to be partially or fully directed to the attacker instead of the legitimate customer. 

COMMANDS TO VERIFY 
 /routing bgp session print 
 /ip route print where bgp=yes 
 /routing bgp advertisement print 
 /log print where topics~"bgp" 

WHY NOT (Eliminated Hypotheses) 
 NOT a MikroTik misconfiguration — the legitimate route is correctly configured. 
 NOT a routing table error — this is a BGP route authority issue. 
 NOT a DNS attack — IP-level routing is being manipulated, not name resolution. 
 NOT a firewall issue — traffic is being redirected before it reaches any firewall. 

FIX 
 Immediately contact upstream ISPs to filter the unauthorized announcement. 
 Implement BGP prefix filtering: only accept customer prefix from legitimate AS. 
 File NOC ticket with relevant ISPs and RIPE/ARIN if needed. 
 Use RPKI to cryptographically sign your legitimate route announcements. 

PREVENTION 
 Implement RPKI (Resource Public Key Infrastructure) for all announced prefixes. 
 Use BGP route monitoring services (RIPE RIS, BGPMon) for real-time alert. 
 Require IRR (Internet Routing Registry) filters on all BGP peers. 

Security / Advanced 
 Scenario #46 

46. Winbox exploit attempt → unauthorized access to router → config backdoor added 

INPUT — Observed Signals 
 Security audit finds unexpected user accounts. Investigation triggered. Logs show: 
 - Unknown admin user &apos;svc_admin&apos; added to router 
 - New firewall rule added allowing Winbox from all IPs 
 - Winbox port (8291) was exposed to internet 
 - Log shows login from unknown external IP two days ago 
 - RouterOS version was not patched for known Winbox vulnerability 

EXPECTED REASONING 
 Unknown user added + firewall rule allowing access from internet + external IP login = successful unauthorized access via a known vulnerability. 

The Winbox exploit (CVE-2018-14847 is the notable example) allowed unauthenticated read of the router&apos;s user database and credentials. If the router was running an unpatched version, the attacker could extract credentials and/or exploit the vulnerability to gain access. 

The backdoor user and firewall rule are the attacker&apos;s persistence mechanisms. 

The network may have been compromised further — traffic may have been logged, NAT rules changed, credentials exfiltrated. 

ROOT CAUSE 
 Unauthorized router access via Winbox vulnerability in unpatched RouterOS version. Attacker created backdoor user account and modified firewall rules to maintain persistent access from the internet. 

COMMANDS TO VERIFY 
 /user print 
 /ip firewall filter print 
 /ip firewall nat print 
 /log print where topics~"account" 
 /system package print (check RouterOS version) 

WHY NOT (Eliminated Hypotheses) 
 NOT a misconfiguration by staff — the specific user and rule pattern indicates external action. 
 NOT a hardware fault — this is a software/security compromise. 
 NOT a routine change — the change log shows external IP, not internal admin. 
 NOT a false positive — combination of backdoor user + access rule confirms intent. 

FIX 
 Immediate: remove unauthorized user, remove backdoor firewall rules. 
 Change all admin credentials. 
 Update RouterOS to latest version. 
 Block Winbox port from internet: 
 /ip firewall filter add chain=input protocol=tcp dst-port=8291 src-address-list=!management-ips action=drop 

PREVENTION 
 Never expose Winbox/SSH/HTTP management to the internet without VPN or IP restriction. 
 Apply RouterOS security updates within 30 days of release. 
 Enable login audit logging and alert on unknown IP logins. 
 Regular user account audit — alert on any new user creation. 

Security / Advanced 
 Scenario #47 

47. NTP amplification from open NTP server → monlist abuse → outbound flood 

INPUT — Observed Signals 
 Uplink saturation event. Source is the router itself. Logs show: 
 - Massive outbound UDP traffic on port 123 from router 
 - Packets are very large (up to 48 responses per query via monlist) 
 - Source IPs are spoofed (random internet IPs) 
 - Router has NTP server enabled and accessible from internet 
 - ISP reports router is amplifying DDoS traffic 

EXPECTED REASONING 
 UDP 123 + large responses + spoofed source IPs = NTP amplification attack using the &apos;monlist&apos; command. Monlist returns up to 600 hosts that recently queried the NTP server, in a single response — amplification factor can reach 556x. 

Similar pattern to DNS amplification: attacker sends tiny request with victim&apos;s spoofed IP, router sends huge response to victim. 

The router is an unwilling amplifier. Fix is to disable the open NTP server or restrict it to local clients only. 

ROOT CAUSE 
 Router NTP server accessible from the internet and responding to monlist requests, being exploited as a high-amplification-factor NTP amplification reflector in a DDoS attack against a third-party victim. 

COMMANDS TO VERIFY 
 /system ntp server print 
 /ip firewall filter print 
 /ip firewall connection print where protocol=udp dst-port=123 

WHY NOT (Eliminated Hypotheses) 
 NOT the router being attacked — router is the amplifier, victim is elsewhere. 
 NOT a customer abuse issue — spoofed IPs are internet addresses. 
 NOT a configuration error in the traditional sense — NTP server is working as designed, just open to abuse. 
 NOT a hardware fault — traffic load is from legitimate (amplified) NTP responses. 

FIX 
 Disable NTP server if not needed: 
 /system ntp server set enabled=no 
 Or restrict to local clients: 
 /ip firewall filter add chain=input protocol=udp dst-port=123 src-address-list=!local-networks action=drop 

PREVENTION 
 Default: disable NTP server on customer-facing routers. 
 If NTP server needed, restrict to internal/management networks only. 
 Include NTP server status in security hardening checklist. 

Security / Advanced 
 Scenario #48 

48. OSPF neighbour injected by attacker → false routes → traffic hijacked internally 

INPUT — Observed Signals 
 Internal traffic behaving strangely after a new device was connected to the management VLAN. Logs show: 
 - Unexpected OSPF Hello packets from unknown device 
 - Routing table showing new routes not previously present 
 - Internal server traffic taking unexpected path (passing through unknown device) 
 - OSPF authentication was not configured 
 - The device is a rogue router connected by an attacker who gained physical access 

EXPECTED REASONING 
 OSPF adjacency formed with unknown device + unexpected routes in table = rogue OSPF router injecting routes. Without OSPF authentication, any device on the same L2 segment can form an OSPF adjacency and inject arbitrary routes. 

Traffic taking unexpected path = the injected routes have lower metric than legitimate routes, causing traffic to be routed through the attacker&apos;s device (man-in-the-middle or traffic blackhole). 

Physical access by attacker → connected a device to management VLAN → OSPF router injecting routes → traffic redirection. 

ROOT CAUSE 
 Rogue OSPF router injected by an attacker with physical access, forming adjacency with legitimate routers (no OSPF authentication configured) and injecting false routes to redirect internal traffic. 

COMMANDS TO VERIFY 
 /routing ospf neighbor print 
 /routing ospf lsa print 
 /ip route print where ospf=yes 
 /log print where topics~"ospf" 

WHY NOT (Eliminated Hypotheses) 
 NOT a misconfiguration by staff — new device not in change log. 
 NOT a software bug — OSPF is functioning as designed (adjacency with any neighbor). 
 NOT a routing table error — routes are correctly installed from OSPF LSAs. 
 NOT a switch issue — the problem is at the OSPF routing protocol layer. 

FIX 
 Immediately disconnect the rogue device. 
 Flush OSPF routes: /routing ospf instance set redistribute-connected=no 
 Enable OSPF MD5 authentication on all interfaces: 
 /routing ospf interface set [find] authentication=md5 authentication-key=<strong_key> 

PREVENTION 
 Enable OSPF authentication on all deployments — always. 
 Restrict physical access to management VLAN connections. 
 Monitor OSPF neighbor table for unexpected adjacencies. 
 Use management VLAN with strict port security and 802.1X. 

Security / Advanced 
 Scenario #49 

49. Firewall bypass via IP fragmentation → blocked content accessible → policy circumvented 

INPUT — Observed Signals 
 Security audit finding: filtered content accessible despite firewall rules. Investigation shows: 
 - Firewall rules explicitly block destination IP 203.0.113.100 
 - Customers can still access content at that IP using specific tools 
 - The tool fragments IP packets so the destination IP field is only in the first fragment 
 - Subsequent fragments are accepted by firewall (no destination IP in header) 
 - Firewall is inspecting individual packets, not reassembling before inspection 

EXPECTED REASONING 
 Firewall blocks IP 203.0.113.100 but fragmented traffic passes = the firewall is doing per-packet inspection without fragment reassembly. 

In IP fragmentation, only the first fragment contains the full IP header with destination IP. Fragments 2+ contain only an IP header with the fragmentation offset and no transport-layer or destination context. 

A firewall that does not reassemble fragments before inspection will: (1) evaluate fragment 0 against rules (block), (2) evaluate fragment 1+ without context (no rule matches → allow). 

The first fragment may also be allowed if the rule only matches on transport port (which is also only in fragment 0). 

ROOT CAUSE 
 Firewall performing stateless per-packet inspection without IP fragment reassembly, allowing subsequent fragments (which lack full IP/transport headers) to bypass rules that matched and blocked the first fragment. 

COMMANDS TO VERIFY 
 /ip firewall filter print 
 /ip firewall connection tracking print 
 /ip settings print 
 /tool packet-sniffer sniff ip-protocol=tcp 

WHY NOT (Eliminated Hypotheses) 
 NOT a rule configuration error — the rule correctly identifies the target IP. 
 NOT a routing bypass — traffic is going through the firewall. 
 NOT a VPN circumvention — fragmentation at IP layer, not tunneling. 
 NOT a firewall hardware fault — this is a known limitation of stateless packet inspection. 

FIX 
 Enable connection tracking and stateful inspection: 
 /ip firewall filter add chain=input connection-state=invalid action=drop 
 /ip firewall filter add chain=forward connection-state=invalid action=drop 
 Alternatively, enforce fragment reassembly at the IP level. 

PREVENTION 
 Always use stateful firewall rules with connection-state matching. 
 Drop all invalid connection-state packets as the first filter rules. 
 Test firewall rules against fragmented traffic in security assessments. 

Security / Advanced 
 Scenario #50 

50. IPv6 traffic bypasses IPv4-only firewall → security policy not applied → unrestricted access 

INPUT — Observed Signals 
 Security audit finding: customers can access blocked content via IPv6. Investigation shows: 
 - Firewall rules are all IPv4 only (/ip firewall filter) 
 - Network provides both IPv4 and IPv6 connectivity 
 - Blocked IPs/domains have IPv6 addresses 
 - Customers use IPv6 to reach blocked destinations, bypassing IPv4 firewall 
 - No IPv6 firewall rules exist (/ipv6 firewall filter is empty) 

EXPECTED REASONING 
 IPv4 firewall rules do not apply to IPv6 traffic. In MikroTik RouterOS, /ip and /ipv6 are completely separate filter chains. A firewall rule in /ip firewall filter is only evaluated for IPv4 packets. 

If the network provides IPv6 (via DHCPv6, SLAAC, or 6to4/Teredo), customers can use IPv6 to reach any IPv6-capable destination, completely bypassing IPv4 filter rules. 

Modern operating systems and many websites prefer IPv6 when available (RFC 6555 Happy Eyeballs). So a customer may not even know they are using IPv6 — their OS selects it automatically. 

ROOT CAUSE 
 IPv6 firewall filter chain empty while network provides IPv6 connectivity, allowing all IPv6 traffic to bypass IPv4-only firewall policies. Customers can reach blocked destinations via IPv6 regardless of IPv4 rules. 

COMMANDS TO VERIFY 
 /ipv6 firewall filter print 
 /ipv6 address print 
 /ip firewall filter print 
 /ipv6 firewall connection print count-only 
 /ipv6 nd print 

WHY NOT (Eliminated Hypotheses) 
 NOT an IPv4 firewall rule error — IPv4 rules are correct and blocking correctly. 
 NOT a routing bypass — IPv6 is a legitimate transport being used intentionally or automatically. 
 NOT a customer tool circumvention — standard OS behavior prefers IPv6 when available. 
 NOT a MikroTik bug — IPv4 and IPv6 firewall chains are by design separate. 

FIX 
 Mirror all policy rules to IPv6 firewall: 
 /ipv6 firewall filter add chain=forward dst-address=<blocked_ipv6_prefix> action=drop 
 Or: disable IPv6 if not intentionally provided: 
 /ipv6 settings set forward=no 
 /ip neighbor discovery-settings set discover-interface-list=none 

PREVENTION 
 Treat IPv6 as equal to IPv4 in all firewall policies — dual-stack means dual filtering. 
 Audit IPv6 firewall rules as part of every IPv4 rule change. 
 Test content filtering from both IPv4 and IPv6 client perspectives after any policy change.
