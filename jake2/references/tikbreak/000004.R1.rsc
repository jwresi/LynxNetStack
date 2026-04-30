# software id = TW4F-N4NK
#
# model = CCR2004-16G-2S+
# serial number = HE908XR51R7
/interface bridge
add ingress-filtering=no name=LAN_Bridge vlan-filtering=yes
add name=Upstairs_Bridge
/interface ethernet
set [ find default-name=ether1 ] name=WAN
set [ find default-name=ether3 ] comment="Garage WiFi"
set [ find default-name=ether7 ] comment="Upstairs Bridge"
set [ find default-name=ether8 ] comment="Upstairs Bridge"
set [ find default-name=ether9 ] comment="Upstairs Bridge"
set [ find default-name=ether10 ] comment=\
    "V2000 - Head End - MAC 30CBC773D593 IP 192.168.111.2"
set [ find default-name=ether11 ] comment="Upstairs Bridge"
set [ find default-name=ether12 ] comment="Upstairs Bridge"
set [ find default-name=ether13 ] comment="Upstairs Bridge"
set [ find default-name=ether14 ] comment="Vilo Config Port - For Now"
/interface wireguard
add listen-port=13231 mtu=1420 name=wireguard1
/interface vlan
add interface=LAN_Bridge name=vlan10 vlan-id=10
add interface=LAN_Bridge name=vlan100 vlan-id=100
/interface ovpn-client
add certificate=splynx cipher=aes192-cbc connect-to=54.243.194.0 mac-address=\
    02:8E:A2:2A:A1:8A name=Splynx user=cambridge
/interface list
add name=LAN
/interface wireless security-profiles
set [ find default=yes ] supplicant-identity=MikroTik
/ip pool
add name=dhcp_pool1 ranges=192.168.10.50-192.168.10.100
add name=dhcp_pool4 ranges=172.16.10.20-172.16.10.30
add name=dhcp_pool6 ranges=10.10.10.2-10.10.10.254
add name=TestPool ranges=192.168.111.80-192.168.111.100
/ip dhcp-server
add address-pool=dhcp_pool1 disabled=yes interface=ether14 lease-time=10m \
    name=dhcp1
add address-pool=TestPool interface=vlan10 lease-time=1d name=dhcp3
add address-pool=dhcp_pool6 interface=Upstairs_Bridge name=dhcp2
add address-pool=TestPool disabled=yes interface=LAN_Bridge name=TestServer
/port
set 0 name=serial0
set 1 name=serial1
/ppp profile
add local-address=10.0.1.1 name=splynx_pppoe only-one=yes
/snmp community
add addresses=::/0 name=resibridge
/system logging action
set 3 bsd-syslog=yes remote=54.221.91.223 syslog-facility=local0
/user group
add name=mktxp_group policy="ssh,read,api,!local,!telnet,!ftp,!reboot,!write,!\
    policy,!test,!winbox,!password,!web,!sniff,!sensitive,!romon,!rest-api"
add name=oxidized policy="ssh,read,password,sensitive,!local,!telnet,!ftp,!reb\
    oot,!write,!policy,!test,!winbox,!web,!sniff,!api,!romon,!rest-api"
/zerotier
set zt1 comment="ZeroTier Central controller - https://my.zerotier.com/" \
    name=zt1 port=9993
/zerotier interface
add instance=zt1 name=zerotier1 network=52b337794fb794fc
#error exporting "/interface/bridge/calea"
/interface bridge port
add bridge=LAN_Bridge interface=ether3
add bridge=LAN_Bridge interface=ether10
add bridge=Upstairs_Bridge interface=ether13
add bridge=Upstairs_Bridge interface=ether12
add bridge=Upstairs_Bridge interface=ether11
add bridge=Upstairs_Bridge interface=ether9
add bridge=Upstairs_Bridge interface=ether8
add bridge=Upstairs_Bridge interface=ether7
add bridge=Upstairs_Bridge interface=ether6
add bridge=Upstairs_Bridge interface=ether5
/interface bridge vlan
add bridge=LAN_Bridge tagged=ether10,ether3,LAN_Bridge vlan-ids=10
add bridge=LAN_Bridge tagged=ether3,ether10 untagged=LAN_Bridge vlan-ids=100
add bridge=LAN_Bridge
/interface detect-internet
set detect-interface-list=all
/interface list member
add interface=WAN
add list=LAN
/interface pppoe-server server
add default-profile=splynx_pppoe disabled=no interface=vlan10 \
    keepalive-timeout=60 one-session-per-host=yes service-name=SplynxRadius
/interface wireguard peers
add allowed-address=192.168.100.4/32,::/0 comment=Graham interface=wireguard1 \
    public-key="07fcBwopOtYSyNXvp74s3iXBr8eDD1hDPlCk0eRr0hw="
add allowed-address=192.168.100.2/32,::/0 comment=Jono interface=wireguard1 \
    public-key="bOas9cEKf9AUHFg4WOIIDPSEYH6lJR5/WZfVp8fU5hY="
add allowed-address=192.168.100.3/32,::/0 comment="Jono New Comp" interface=\
    wireguard1 public-key="WKRj3R/eDIUfwakV6hd0umjDg3z0E9zFasEDuBfMBVg="
add allowed-address=192.168.100.6/32,::/0 comment="Vivek Dell" interface=\
    wireguard1 public-key="4MEZrkTNZ7YwYTLO8Ss4gHw3m9Xp3qGTj268faMIhn0="
add allowed-address=192.168.100.7/32 comment="Vivek OSX" interface=wireguard1 \
    public-key="V6FhC7V/PGVNZ4ciyz6DzzgkRVE2W5MApZQYktDDpHA="
/ip address
add address=66.117.227.10/29 interface=WAN network=66.117.227.8
add address=10.0.1.1/24 interface=vlan10 network=10.0.1.0
add address=169.254.1.25/24 disabled=yes interface=*14 network=169.254.1.0
add address=192.168.100.1/24 comment=Wireguard interface=wireguard1 network=\
    192.168.100.0
add address=192.168.111.1/24 comment="Cambium/Positron Management" interface=\
    LAN_Bridge network=192.168.111.0
add address=192.168.10.2/24 interface=LAN_Bridge network=192.168.10.0
add address=192.168.64.1/24 comment="hotspot network" interface=LAN_Bridge \
    network=192.168.64.0
add address=192.168.112.1/24 comment="GAM Management" interface=vlan100 \
    network=192.168.112.0
add address=10.10.10.1/24 comment="Upstairs Bridge" interface=Upstairs_Bridge \
    network=10.10.10.0
add address=172.16.10.1/24 interface=vlan10 network=172.16.10.0
add address=172.16.10.1/24 disabled=yes interface=LAN_Bridge network=\
    172.16.10.0
/ip dhcp-server lease
add address=192.168.111.58 client-id=1:e8:da:0:f:ab:93 mac-address=\
    E8:DA:00:0F:AB:93 server=dhcp1
add address=192.168.111.55 client-id=1:e8:da:0:f:ce:f1 mac-address=\
    E8:DA:00:0F:CE:F1 server=dhcp1
add address=192.168.111.53 client-id=1:e8:da:0:f:ad:9d mac-address=\
    E8:DA:00:0F:AD:9D server=dhcp1
add address=192.168.111.60 client-id=1:e8:da:0:f:cf:33 mac-address=\
    E8:DA:00:0F:CF:33 server=dhcp1
add address=192.168.111.59 client-id=1:e8:da:0:f:ad:73 mac-address=\
    E8:DA:00:0F:AD:73 server=dhcp1
add address=192.168.111.57 client-id=1:e8:da:0:f:b1:8d mac-address=\
    E8:DA:00:0F:B1:8D server=dhcp1
add address=192.168.111.52 client-id=1:78:8c:b5:10:62:e6 mac-address=\
    78:8C:B5:10:62:E6 server=dhcp1
add address=192.168.111.54 client-id=1:e8:da:0:f:cd:5f mac-address=\
    E8:DA:00:0F:CD:5F server=dhcp1
add address=192.168.111.56 client-id=1:e8:da:0:f:cc:e1 mac-address=\
    E8:DA:00:0F:CC:E1 server=dhcp1
/ip dhcp-server network
add address=10.0.1.0/24 gateway=10.0.1.1
add address=10.10.10.0/24 gateway=10.10.10.1
add address=172.16.10.0/24 dns-server=8.8.8.8 gateway=172.16.10.1 netmask=24
add address=192.168.10.0/24 gateway=192.168.10.1 netmask=24
add address=192.168.64.0/24 comment=CONFIG_DHCP gateway=192.168.64.1
add address=192.168.86.0/24 gateway=192.168.86.1
add address=192.168.88.0/24 gateway=192.168.88.1 netmask=24
add address=192.168.111.0/24 gateway=192.168.111.1
/ip dns
set servers=8.8.8.8
/ip firewall address-list
add address=98.82.104.1 comment=NetBox list=ResiCore
add address=52.0.96.77 comment=Loki_Promtail list=ResiCore
add address=44.207.189.240 comment=JumpA list=ResiCore
add address=52.0.162.201 comment=JumpB list=ResiCore
add address=54.221.91.223 comment=Grafana_Prometheus list=ResiCore
#error exporting "/ip/firewall/calea"
/ip firewall filter
add chain=forward comment="Splynx Blocking Rules - begin" disabled=yes
add action=jump chain=forward comment=SpBlockingRule-2751605989 \
    dst-address-list=!splynx-allowed-resources jump-target=splynx-blocked \
    src-address-list=SpLBL_blocked
add action=jump chain=forward comment=SpBlockingRule-2673675484 \
    dst-address-list=!splynx-allowed-resources jump-target=splynx-blocked \
    src-address-list=SpLBL_new
add action=jump chain=forward comment=SpBlockingRule-3109596403 \
    dst-address-list=!splynx-allowed-resources jump-target=splynx-blocked \
    src-address-list=SpLBL_disabled
add action=jump chain=forward comment=SpBlockingRule-2815368063 \
    dst-address-list=!splynx-allowed-resources jump-target=splynx-blocked \
    src-address-list=Reject_0
add action=jump chain=forward comment=SpBlockingRule-3502779369 \
    dst-address-list=!splynx-allowed-resources jump-target=splynx-blocked \
    src-address-list=Reject_1
add action=jump chain=forward comment=SpBlockingRule-1237416531 \
    dst-address-list=!splynx-allowed-resources jump-target=splynx-blocked \
    src-address-list=Reject_2
add action=jump chain=forward comment=SpBlockingRule-1053182661 \
    dst-address-list=!splynx-allowed-resources jump-target=splynx-blocked \
    src-address-list=Reject_3
add action=jump chain=forward comment=SpBlockingRule-2695028582 \
    dst-address-list=!splynx-allowed-resources jump-target=splynx-blocked \
    src-address-list=Reject_4
add action=accept chain=splynx-blocked comment=SpBlockingRule-3053659851 \
    dst-limit=2,0,src-address/1m40s dst-port=53 protocol=udp
add action=accept chain=splynx-blocked comment=SpBlockingRule-3728159901 \
    dst-address=159.65.88.239 dst-port=80,443,8101,8102,8103,8104 protocol=\
    tcp
add action=reject chain=splynx-blocked comment=SpBlockingRule-3070586937 \
    dst-limit=10,0,src-address/1m40s reject-with=icmp-admin-prohibited
add action=drop chain=splynx-blocked comment=SpBlockingRule-496360353
add chain=forward comment="Splynx Blocking Rules - end" disabled=yes
add action=passthrough chain=unused-hs-chain comment=\
    "place hotspot rules here" disabled=yes
add action=drop chain=forward comment="Drop SSH brute forcers" \
    src-address-list=ssh_blacklist
add action=add-src-to-address-list address-list=ssh_blacklist \
    address-list-timeout=4w2d chain=forward connection-state=new dst-port=\
    22,23 in-interface=WAN protocol=tcp src-address-list=ssh_stage3
add action=add-src-to-address-list address-list=ssh_stage3 \
    address-list-timeout=5m chain=forward connection-state=new dst-port=22,23 \
    in-interface=WAN protocol=tcp src-address-list=ssh_stage2
add action=add-src-to-address-list address-list=ssh_stage2 \
    address-list-timeout=5m chain=forward connection-state=new dst-port=22,23 \
    in-interface=WAN protocol=tcp src-address-list=ssh_stage1
add action=add-src-to-address-list address-list=ssh_stage1 \
    address-list-timeout=5m chain=forward connection-state=new dst-port=22,23 \
    in-interface=WAN protocol=tcp
add action=accept chain=forward comment="Allow ResiBridge Core IPs" \
    src-address-list=ResiCore
/ip firewall nat
add action=passthrough chain=unused-hs-chain comment=\
    "place hotspot rules here" disabled=yes
add action=masquerade chain=srcnat src-address=10.0.1.0/24
add action=masquerade chain=srcnat comment="For Vilo Test" src-address=\
    172.16.10.0/24
add action=masquerade chain=srcnat src-address=192.168.111.0/24
add action=src-nat chain=srcnat disabled=yes src-address=192.168.100.0/24 \
    to-addresses=169.254.1.25
add action=masquerade chain=srcnat src-address=192.168.100.0/24 to-addresses=\
    169.254.1.25
add action=masquerade chain=srcnat src-address=192.168.58.0/24
add action=masquerade chain=srcnat src-address=192.168.10.0/24
add action=masquerade chain=srcnat src-address=10.10.10.0/24
add action=dst-nat chain=dstnat comment="BLOCK keep PPPoE alive Redirect" \
    dst-address-list=BLOCK dst-port=80 protocol=tcp to-addresses=54.243.194.0 \
    to-ports=8102
/ip hotspot user profile
set [ find default=yes ] address-list="" address-pool=*3 shared-users=\
    unlimited
/ip route
add disabled=no dst-address=192.168.10.0/24 gateway=ether14 routing-table=\
    main suppress-hw-offload=no
/ip service
set telnet disabled=yes
set ftp disabled=yes
set www disabled=yes
set ssh address="192.168.100.0/24,10.0.0.0/8,52.0.162.201/32,98.82.104.1/32,44\
    .207.189.240/32,52.0.162.201/32,54.221.91.223/32,172.27.0.0/16"
set api address="192.168.100.0/24,10.0.0.0/8,52.0.162.201/32,98.82.104.1/32,44\
    .207.189.240/32,52.0.162.201/32,54.221.91.223/32,172.27.0.0/16"
set winbox address=10.250.32.1/32,192.168.100.0/24,172.27.0.0/16
set api-ssl address=10.250.32.1/32,10.250.32.0/24
/ipv6 firewall filter
add chain=forward comment="Splynx Blocking Rules - begin" disabled=yes
add chain=forward comment="Splynx Blocking Rules - end" disabled=yes
/ppp aaa
set use-radius=yes
/radius
add address=10.250.32.1 service=ppp,login,dhcp src-address=10.250.32.3
add address=172.27.209.248 service=login
/radius incoming
set accept=yes
/snmp
set enabled=yes trap-community=resibridge trap-version=2
/system clock
set time-zone-name=America/New_York
/system identity
set name=000004.R1
/system logging
set 0 action=remote disabled=yes prefix=:Info topics=wireguard
set 1 action=remote disabled=yes prefix=:Error
set 2 action=remote disabled=yes prefix=:Warning
set 3 action=remote disabled=yes prefix=:Critical topics=interface
add action=remote prefix=:info topics=info
add topics=critical
add action=remote prefix=:Firewall topics=firewall
add action=remote prefix=:Account topics=account
add action=remote prefix=:Caps topics=caps
add action=remote prefix=:Wireles topics=wireless
add action=remote prefix=:warning topics=warning
add action=remote prefix=:pppoe topics=pppoe,info
add action=remote prefix=:interface topics=interface
add action=remote prefix=:pppoe_errors topics=pppoe,error,ppp
add action=remote prefix=:interface_warning topics=interface,warning
add prefix=DHCP topics=dhcp
add action=remote prefix=DHCP topics=dhcp
/system note
set show-at-login=no
/system routerboard settings
set enter-setup-on=delete-key
/tool netwatch
add comment=test disabled=no down-script="" host=1.1.1.1 http-codes="" name=\
    test test-script="" type=icmp up-script=""
add comment="Grafana Instance" disabled=no down-script="" host=54.221.91.223 \
    http-codes="" name="Grafana Instance" test-script="" type=simple \
    up-script=""
add comment="Netbox Instance" disabled=no down-script="" host=98.82.104.1 \
    http-codes="" name="Netbox Instance" test-script="" type=icmp up-script=\
    ""
/tool sniffer
set file-name=sniff filter-ip-address=66.117.227.9/32 filter-stream=yes \
    streaming-enabled=yes
/user aaa
set default-group=full use-radius=yes
