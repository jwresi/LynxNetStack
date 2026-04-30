# MikroTik Training Corpus

Total scenarios: **40**

## Live Log Parsing Patterns

- **Show DHCP-related events**: `/log print where message~"dhcp"`
- **Show PPPoE-related events**: `/log print where message~"pppoe"`
- **Show interface link changes**: `/log print where message~"link"`
- **Show RADIUS issues**: `/log print where message~"radius"`
- **Show bridge or STP events**: `/log print where message~"bridge|rstp|stp"`
- **Show firewall actions or drops**: `/log print where topics~"firewall" or message~"drop"`
- **Show login/authentication activity**: `/log print where message~"login|logged|authentication|failed"`
- **Show route changes**: `/log print where message~"route|ospf|bgp"`
- **Show only recent warnings and errors**: `/log print where topics~"warning|error|critical"`
- **Show entries from a given interface name**: `/log print where message~"ether1|sfp-sfpplus1|vlan20-cx"`

## Scenarios

### 1. Rogue DHCP Servers / DHCP Leakage
- Problem: Clients receive wrong IP ranges or inconsistent leases due to rogue DHCP and VLAN leakage.
- Symptoms:
  - Clients get unexpected 192.168.x.x addresses
  - DHCP offers appear on customer VLANs
  - Random lease flapping
- Detection commands:
  - `/tool sniffer quick interface=BR-CGNAT port=67,68 ip-protocol=udp`
  - `/ip dhcp-server lease print`
  - `/tool torch interface=BR-CGNAT port=67,68`
- Fix commands:
  - `/ip firewall filter add chain=forward protocol=udp dst-port=67-68 action=drop comment="Block rogue DHCP"`
  - `/ip firewall filter add chain=forward src-address-list=!trusted_dhcp_servers protocol=udp dst-port=67-68 action=drop`
  - `/interface bridge set BR_PPPoE vlan-filtering=yes`
  - `/interface bridge vlan add bridge=BR_PPPoE tagged=bridge,etherX vlan-ids=20`

### 2. DHCP Flapping / Reassigning IPs
- Problem: Clients continuously renew or appear to re-identify due to timing and L2 instability.
- Symptoms:
  - Frequent DHCP deassign/reassign events
  - Discover/offer loops
  - Same client appears with different MACs
- Detection commands:
  - `/interface ethernet monitor ether1`
  - `/log print where message~"dhcp"`
- Fix commands:
  - `/interface ethernet set ether1 eee=no`
  - `/interface bridge set BR_PPPoE protocol-mode=rstp`
  - `/interface bridge port set [find] ingress-filtering=yes`

### 3. Splynx Blocking / Access Issues
- Problem: Users are blocked or lose access due to Splynx address list or firewall chain issues.
- Symptoms:
  - Customer authenticated but no internet
  - Unexpected blocked state
  - Address-list mismatch
- Detection commands:
  - `/ip firewall address-list print where list~"SpLBL"`
  - `/ip firewall filter print where comment~"Splynx"`
  - `/ppp active print`
- Fix commands:
  - `/ip firewall filter move [find comment="SpBlockingRule"] destination=0`
  - `/ip firewall address-list remove [find list="SpLBL_blocked"]`

### 4. PPPoE Discovery Issues / Session Failures
- Problem: Clients fail to establish PPPoE sessions due to binding, MTU, or VLAN problems.
- Symptoms:
  - Discovery visible but no session
  - Intermittent PPPoE login success
  - Clients cannot authenticate
- Detection commands:
  - `/tool sniffer quick interface=vlan20-cx port=pppoe-discovery`
  - `/ppp active print`
  - `/interface bridge port print`
- Fix commands:
  - `/interface pppoe-server server set service-name=SplynxRadius interface=vlan20-cx`
  - `/ppp profile set splynx_pppoe mtu=1480 mru=1480`

### 5. VLAN Misconfiguration / Traffic Bleeding
- Problem: Traffic crosses between mgmt, customer, and security networks due to bad VLAN definitions.
- Symptoms:
  - Management network reachable from customer side
  - Unexpected ARP visibility
  - Cross-network traffic
- Detection commands:
  - `/interface bridge vlan print`
  - `/ip arp print`
- Fix commands:
  - `/interface bridge vlan add bridge=BR_PPPoE vlan-ids=10 tagged=bridge,ether1`
  - `/interface bridge vlan add bridge=BR_PPPoE vlan-ids=20 tagged=bridge,ether1`
  - `/interface bridge vlan add bridge=BR_PPPoE vlan-ids=30 tagged=bridge,ether1`
  - `/interface bridge port set etherX pvid=20`

### 6. Loop / Broadcast Storm Issues
- Problem: Network instability caused by L2 loops and excessive flooding.
- Symptoms:
  - High CPU
  - MAC flapping
  - Instability across bridge domain
- Detection commands:
  - `/interface bridge host print`
  - `/tool torch interface=bridge`
- Fix commands:
  - `/interface bridge set BR_PPPoE protocol-mode=rstp`
  - `/interface bridge port set [find] bpdu-guard=yes`
  - `/interface ethernet set etherX loop-protect=on`

### 7. Wireless Backhaul / Bridge Path Issues
- Problem: Traffic fails across wireless backhaul because the path is treated as L2 when it is actually L3.
- Symptoms:
  - Packet loss across cnWave/Siklu
  - Traffic not flowing as expected
  - Route confusion over wireless mesh
- Detection commands:
  - `/tool traceroute 8.8.8.8`
  - `/ip route print`
- Fix commands:
  - `/ip route add dst-address=X.X.X.X/XX gateway=Y.Y.Y.Y`

### 8. MAC Address Inconsistencies
- Problem: Same client appears under multiple MAC identities due to retry behavior and path instability.
- Symptoms:
  - Different MACs for same client
  - Inconsistent authentication identity
  - Confusing sniffer results
- Detection commands:
  - `/tool sniffer quick`
- Notes: Often not a rogue device. Can be caused by DHCP/PPPoE retry behavior and unstable packet timing.

### 9. LTE Data Usage / ZeroTier Overhead
- Problem: Unexpected cellular usage caused by overlay management traffic.
- Symptoms:
  - LTE consumption high while mostly idle
  - Persistent overhead on OOB link
- Detection commands:
  - `/tool torch interface=lte1`
  - `/ip firewall connection print where dst-port=9993`
  - `/interface monitor-traffic lte1`
- Fix commands:
  - `/queue simple add name=lte-limit target=lte1 max-limit=500k/500k`

### 10. Hardware Offloading Issues
- Problem: CRS or bridge switching falls back to CPU instead of hardware forwarding.
- Symptoms:
  - High CPU on switch
  - Poor throughput
- Detection commands:
  - `/interface bridge port print`
- Fix commands:
  - Confirm the bridge design matches the switch-chip offload model and look for the `H` flag on `/interface bridge port print`
  - Remove offload blockers such as unsupported bridge features, then re-check the affected ports instead of trying to set a generic `hw=yes` knob

### 11. Option 82 / DHCP Architecture Testing
- Problem: Migration from PPPoE to DHCP with relay and Option 82 insertion.
- Symptoms:
  - Need port/site identity in DHCP requests
  - Need DHCP-based subscriber control
- Detection commands:
  - `/ip dhcp-relay print`
- Fix commands:
  - `/interface bridge settings set use-ip-firewall=yes`
  - `/ip dhcp-relay add interface=vlan20 dhcp-server=X.X.X.X add-relay-info=yes`

### 12. Firewall / HTTPS Blocking
- Problem: Need to block HTTPS destinations like YouTube using TLS host matching.
- Symptoms:
  - Need domain-based block for HTTPS
- Detection commands:
  - `/ip firewall filter print`
- Fix commands:
  - `/ip firewall filter add chain=forward tls-host=*.youtube.com action=drop`

### 13. General Debug Toolkit
- Problem: Core diagnostic command set for MikroTik troubleshooting.
- Symptoms:
  - Need quick visibility into live state
- Detection commands:
  - `/tool sniffer quick`
  - `/tool torch`
  - `/ip firewall connection print`
  - `/interface bridge host print`
  - `/ip route print`
  - `/ip arp print`
  - `/log print`
  - `/interface ethernet monitor`

### 14. Interface Flapping / Link Instability
- Problem: Link repeatedly drops and returns due to negotiation problems.
- Symptoms:
  - Interface up/down events
  - Packet loss spikes
- Detection commands:
  - `/interface monitor-traffic ether1`
  - `/log print where message~"link"`
- Fix commands:
  - `/interface ethernet set ether1 auto-negotiation=no speed=1Gbps full-duplex=yes`

### 15. Bridge Misbinding
- Problem: Expected traffic does not pass because an interface is not actually in the bridge.
- Symptoms:
  - No forwarding on expected port
- Detection commands:
  - `/interface bridge port print`
- Fix commands:
  - `/interface bridge port add bridge=BR_PPPoE interface=etherX`

### 16. ARP Table Overflow / Instability
- Problem: Neighbor table limits contribute to instability in larger L2 domains.
- Symptoms:
  - Connectivity drops
  - ARP churn
- Detection commands:
  - `/ip arp print count-only`
- Fix commands:
  - `/ip settings set max-neighbor-entries=8192`

### 17. MTU Blackhole
- Problem: Large packets are silently dropped, breaking some traffic but not all.
- Symptoms:
  - Some websites load, others stall
  - Large packets fail
- Detection commands:
  - `/ping 8.8.8.8 size=1472 do-not-fragment=yes`
- Fix commands:
  - `/interface ethernet set ether1 mtu=1500`
  - `/interface vlan set vlan20 mtu=1500`

### 18. FastTrack Breaking QoS / Visibility
- Problem: FastTrack bypasses queues and hides traffic from normal inspection paths.
- Symptoms:
  - Queue rules appear ineffective
  - Traffic bypasses firewall accounting
- Detection commands:
  - `/ip firewall filter print where action=fasttrack-connection`
- Fix commands:
  - `/ip firewall filter disable [find action=fasttrack-connection]`

### 19. Queue Tree Not Applying
- Problem: Queue tree configuration exists but does not classify traffic as intended.
- Symptoms:
  - Bandwidth limits ignored
- Detection commands:
  - `/queue tree print stats`
- Fix commands:
  - `/queue tree set [find where name="QUEUE_NAME"] parent=global`

### 20. SFP Module Not Recognized
- Problem: Fiber or copper SFP link does not come up as expected.
- Symptoms:
  - SFP port stays down
- Detection commands:
  - `/interface ethernet monitor sfp-sfpplus1`
- Fix commands:
  - `/interface ethernet set sfp-sfpplus1 auto-negotiation=no`

### 21. NAT Not Working
- Problem: Clients have private connectivity but cannot reach the internet due to missing or broken srcnat.
- Symptoms:
  - Clients get IP but no internet
- Detection commands:
  - `/ip firewall nat print`
- Fix commands:
  - `/ip firewall nat add chain=srcnat out-interface=ether1 action=masquerade`

### 22. Connection Tracking Saturation
- Problem: Conntrack table fills and causes performance or session problems.
- Symptoms:
  - High CPU
  - Dropped sessions
  - Large connection count
- Detection commands:
  - `/ip firewall connection print count-only`
- Fix commands:
  - `/ip firewall connection tracking set max-entries=262144`

### 23. Incorrect Default Route
- Problem: No outbound connectivity because default route is missing or wrong.
- Symptoms:
  - No internet
  - Ping to local gateway works but beyond does not
- Detection commands:
  - `/ip route print where dst-address=0.0.0.0/0`
- Fix commands:
  - `/ip route add dst-address=0.0.0.0/0 gateway=X.X.X.X`

### 24. Asymmetric Routing
- Problem: Traffic exits one way and returns another, breaking stateful flows.
- Symptoms:
  - Connection starts but fails
  - No return traffic
- Detection commands:
  - `/tool traceroute`
- Fix commands:
  - `/ip route rule add src-address=SUBNET action=lookup table=main`

### 25. DNS Not Resolving
- Problem: Internet reachable by IP but not by domain due to DNS configuration issues.
- Symptoms:
  - IP connectivity works
  - Names do not resolve
- Detection commands:
  - `/resolve google.com`
- Fix commands:
  - `/ip dns set servers=8.8.8.8,1.1.1.1 allow-remote-requests=yes`

### 26. CPU Spikes from Broadcast Storm
- Problem: Broadcast flooding drives CPU and degrades switching performance.
- Symptoms:
  - High CPU on bridge
  - Flooding behavior
- Detection commands:
  - `/tool profile`
- Fix commands:
  - `/interface bridge port set [find] broadcast-flood=no`

### 27. Management Access Exposed
- Problem: Administrative services are reachable from untrusted networks.
- Symptoms:
  - Router accessible from public internet
- Detection commands:
  - `/ip service print`
- Fix commands:
  - `/ip service set winbox address=192.168.0.0/16`
  - `/ip firewall filter add chain=input in-interface=ether1 action=drop`

### 28. Packet Fragmentation Issues
- Problem: Large TCP sessions break due to MTU/MSS mismatch.
- Symptoms:
  - VPN or HTTPS instability
  - Large transfers fail
- Detection commands:
  - `/ip firewall mangle print`
- Fix commands:
  - `/ip firewall mangle add chain=forward action=change-mss new-mss=clamp-to-pmtu protocol=tcp tcp-flags=syn`

### 29. Duplicate IP Addresses
- Problem: Two devices compete for the same address, causing ARP instability.
- Symptoms:
  - ARP conflicts
  - Intermittent reachability
- Detection commands:
  - `/ip arp print where dynamic=yes`
- Fix commands:
  - `/ip dhcp-server set [find] authoritative=yes`

### 30. Route Flapping
- Problem: Dynamic routes repeatedly appear and disappear, causing path instability.
- Symptoms:
  - Routes flap
  - Intermittent reachability
- Detection commands:
  - `/routing route print`
- Fix commands:
  - `/routing ospf interface-template set [find where interfaces=ether1] cost=10`

### 31. STP Blocking Wrong Port
- Problem: Bridge protocol selects the wrong forwarding path.
- Symptoms:
  - Traffic blackhole
  - Unexpected blocked port
- Detection commands:
  - `/interface bridge port print`
- Fix commands:
  - `/interface bridge port set etherX priority=0x10`

### 32. Wireless Interface Not Passing Traffic
- Problem: Client or AP associates, but data does not bridge correctly.
- Symptoms:
  - Associated but no user traffic
- Detection commands:
  - `/interface wireless registration-table print`
- Fix commands:
  - Verify the active wireless package and datapath/bridge binding for that interface before changing anything; do not assume legacy `bridge-mode` applies on every RouterOS 7.18+ wireless stack

### 33. Firewall Dropping Legit Traffic
- Problem: Rule order or broad match conditions block valid flows.
- Symptoms:
  - Unexpected packet drops
- Detection commands:
  - `/ip firewall filter print stats`
- Fix commands:
  - `/ip firewall filter move [find] destination=0`

### 34. Bridge Horizon Misuse
- Problem: Ports are isolated from each other due to inappropriate bridge horizon settings.
- Symptoms:
  - Ports cannot reach each other when they should
- Detection commands:
  - `/interface bridge port print`
- Fix commands:
  - `/interface bridge port set [find] horizon=none`

### 35. Invalid RADIUS Authentication
- Problem: RADIUS settings prevent PPPoE authentication from succeeding.
- Symptoms:
  - PPPoE login failures
  - RADIUS timeout or reject messages
- Detection commands:
  - `/log print where message~"radius"`
- Fix commands:
  - `/radius set address=X.X.X.X secret=YOUR_SECRET`

### 36. VLAN Not Tagged on Uplink
- Problem: Expected VLAN does not traverse the uplink because it is missing from the bridge VLAN table.
- Symptoms:
  - No upstream connectivity for one VLAN
- Detection commands:
  - `/interface bridge vlan print`
- Fix commands:
  - `/interface bridge vlan add bridge=BR_PPPoE tagged=ether1 vlan-ids=20`

### 37. DHCP Relay Not Working
- Problem: Relay exists but does not pass enough metadata or requests do not reach server correctly.
- Symptoms:
  - No DHCP leases via relay
- Detection commands:
  - `/ip dhcp-relay print`
- Fix commands:
  - `/ip dhcp-relay set [find] add-relay-info=yes`

### 38. Interface Queue Drops
- Problem: Software queues or poor queue configuration cause packet loss under load.
- Symptoms:
  - Drops during high traffic
- Detection commands:
  - `/interface monitor-traffic ether1`
- Fix commands:
  - `/queue interface set ether1 queue=only-hardware-queue`

### 39. Power Issues on PoE Port
- Problem: Connected device does not boot due to PoE delivery settings.
- Symptoms:
  - Device not powering up
- Detection commands:
  - `/interface ethernet poe print`
- Fix commands:
  - `/interface ethernet poe set etherX poe-out=forced-on`

### 40. Neighbor Discovery Noise
- Problem: Discovery protocols create unnecessary traffic or exposure on inappropriate interfaces.
- Symptoms:
  - Excessive discovery chatter
- Detection commands:
  - `/ip neighbor discovery-settings print`
- Fix commands:
  - `/ip neighbor discovery-settings set discover-interface-list=none`
