# software id = SDQR-739Y
#
# model = CCR2004-16G-2S+
# serial number = HES09F91PS7
/interface bridge
add dhcp-snooping=yes name=main-office
add name=test
/interface ethernet
set [ find default-name=ether1 ] comment=WAN
set [ find default-name=ether3 ] comment="Router Provision"
set [ find default-name=ether10 ] comment=CGNAT-NETWORK
set [ find default-name=ether11 ] comment=CGNAT-NETWORK
set [ find default-name=ether14 ] comment="OLT GE"
set [ find default-name=ether16 ] comment="Mikrotik Hallway"
set [ find default-name=sfp-sfpplus1 ] comment=Switch
set [ find default-name=sfp-sfpplus2 ] comment="OLT for Building"
/interface wireguard
add listen-port=13231 mtu=1420 name=wireguard1
/interface wireless security-profiles
set [ find default=yes ] supplicant-identity=MikroTik
/iot lora servers
add address=eu1.cloud.thethings.industries name="TTS Cloud (eu1)" protocol=\
    UDP
add address=nam1.cloud.thethings.industries name="TTS Cloud (nam1)" protocol=\
    UDP
add address=au1.cloud.thethings.industries name="TTS Cloud (au1)" protocol=\
    UDP
add address=eu1.cloud.thethings.network name="TTN V3 (eu1)" protocol=UDP
add address=nam1.cloud.thethings.network name="TTN V3 (nam1)" protocol=UDP
add address=au1.cloud.thethings.network name="TTN V3 (au1)" protocol=UDP
/ip pool
add name="dhcp_pool1 - main" ranges=192.168.10.2-192.168.10.254
add comment="for AP" name=pool-ether7 ranges=172.16.0.2-172.16.0.254
add name=tplink-dhcp-ether2 ranges=192.168.1.2-192.168.1.6
add name=tplink-dhcp-ether3 ranges=10.0.0.2-10.0.0.6
add name=tplink-dhcp-ether4 ranges=172.16.0.2-172.16.0.6
/ip dhcp-server
add address-pool="dhcp_pool1 - main" interface=main-office name=\
    "dhcp1 - main"
/ip smb users
set [ find default=yes ] disabled=yes
/port
set 0 name=serial0
set 1 name=serial1
/ppp profile
add local-address=100.64.2.1 name=splynx_pppoe_ipv6 remote-address=\
    tplink-dhcp-ether2
/snmp community
set [ find default=yes ] name=resibridge
/system logging action
set 3 remote=54.221.91.223 remote-log-format=syslog syslog-facility=local0
/user group
add name=mktxp_group policy="ssh,read,api,!local,!telnet,!ftp,!reboot,!write,!\
    policy,!test,!winbox,!password,!web,!sniff,!sensitive,!romon,!rest-api"
add name=oxidized policy="ssh,read,password,sensitive,!local,!telnet,!ftp,!reb\
    oot,!write,!policy,!test,!winbox,!web,!sniff,!api,!romon,!rest-api"
/zerotier
set zt1 disabled=no disabled=no
/zerotier interface
add instance=zt1 name=zerotier1 network=52b337794fb794fc
/interface bridge port
add bridge=*17 interface=ether7
add bridge=main-office comment="test OLT" interface=ether8
add bridge=main-office interface=ether10
add bridge=main-office interface=ether11
add bridge=main-office interface=sfp-sfpplus1
add bridge=main-office interface=ether6
add bridge=main-office interface=ether9
add bridge=main-office interface=ether12
add bridge=main-office interface=ether13
add bridge=main-office interface=ether14
add bridge=main-office interface=ether16
add bridge=main-office interface=sfp-sfpplus2
add bridge=main-office interface=ether2
/ip firewall connection tracking
set enabled=yes
/ipv6 settings
set max-neighbor-entries=8192 soft-max-neighbor-entries=8191
/interface ovpn-server server
add mac-address=FE:07:13:46:B4:D2 name=ovpn-server1
/interface wireguard peers
add allowed-address=192.168.100.4/32 comment=Jono interface=wireguard1 name=\
    peer2 private-key="0DHoJAnjd0lUtsdyNZ+dbVn/+H71pi4pdZYpFBt52nk=" \
    public-key="YzBvCelxSMz0x8HgcYqdI1g8eVgDphBqH/STBGiuQyA="
add allowed-address=192.168.100.3/32 comment=Graham interface=wireguard1 \
    name=peer3 public-key="Jtilau1XOR5hKz0/F1y98JZ10EVwlmAlWbSvOTH8JRI="
add allowed-address=192.168.100.2/32 comment="Jono New Laptop" interface=\
    wireguard1 name=peer5 private-key=\
    "wNBZReV/QRrQtaf482hKEmGNMSM6YziGzlHBFA5UeHU=" public-key=\
    "WKRj3R/eDIUfwakV6hd0umjDg3z0E9zFasEDuBfMBVg="
add allowed-address=192.168.100.6/32 comment="Vivek Dell" interface=\
    wireguard1 name=peer6 public-key=\
    "4MEZrkTNZ7YwYTLO8Ss4gHw3m9Xp3qGTj268faMIhn0="
add allowed-address=192.168.100.7/32 comment="Vivek OSX" interface=wireguard1 \
    name=peer7 public-key="V6FhC7V/PGVNZ4ciyz6DzzgkRVE2W5MApZQYktDDpHA="
/iot lora traffic options
set crc-errors=no
set crc-errors=no
/ip address
add address=192.168.10.1/24 interface=sfp-sfpplus1 network=192.168.10.0
add address=38.89.155.34/29 interface=ether1 network=38.89.155.32
add address=192.168.100.1/24 interface=wireguard1 network=192.168.100.0
add address=172.16.0.1/24 interface=*17 network=172.16.0.0
add address=192.168.0.2/24 comment="OLT Default" interface=sfp-sfpplus1 \
    network=192.168.0.0
add address=100.64.2.1/24 interface=*19 network=100.64.2.0
add address=192.168.44.1/24 interface=sfp-sfpplus1 network=192.168.44.0
add address=192.168.1.1/29 interface=test network=192.168.1.0
add address=10.0.0.1/29 interface=*1E network=10.0.0.0
add address=172.16.0.1/29 interface=*1F network=172.16.0.0
add address=192.168.0.254 comment="Rescue source IP for 192.168.0.1" \
    interface=main-office network=192.168.0.254
add address=192.168.10.254 comment="Alias -> stranded device" interface=\
    sfp-sfpplus1 network=192.168.10.254
/ip arp
add address=192.168.10.199 comment="calix OLT test" interface=sfp-sfpplus1 \
    mac-address=84:D3:43:D2:B3:7B
/ip dhcp-client
# Interface not active
add interface=ether15
/ip dhcp-server lease
add address=192.168.10.249 client-id=1:48:a9:8a:ae:44:51 mac-address=\
    48:A9:8A:AE:44:51 server="dhcp1 - main"
add address=192.168.10.72 client-id=1:6:a2:38:9d:82:c4 mac-address=\
    06:A2:38:9D:82:C4 server="dhcp1 - main"
add address=192.168.10.201 mac-address=5C:E9:31:C6:75:2C
add address=192.168.10.162 client-id=1:f4:6b:8c:c3:c2:c7 comment=\
    "linux  server in mikrotik harlem rack" mac-address=F4:6B:8C:C3:C2:C7 \
    server="dhcp1 - main"
add address=192.168.10.51 client-id=1:38:f7:cd:c6:bc:e3 comment=smxmin01 \
    mac-address=38:F7:CD:C6:BC:E3 server="dhcp1 - main"
add address=192.168.10.61 client-id=1:b4:63:6f:90:f3:81 mac-address=\
    B4:63:6F:90:F3:81
add address=192.168.10.16 client-id=1:52:54:0:ae:3c:93 mac-address=\
    52:54:00:AE:3C:93 server="dhcp1 - main"
add address=192.168.10.115 mac-address=00:27:04:3E:86:14 server=\
    "dhcp1 - main"
add address=192.168.10.116 mac-address=00:27:04:3E:86:20 server=\
    "dhcp1 - main"
add address=192.168.10.118 mac-address=00:27:04:3E:84:A7 server=\
    "dhcp1 - main"
add address=192.168.10.119 mac-address=00:27:04:3E:86:12 server=\
    "dhcp1 - main"
add address=192.168.10.120 mac-address=00:27:04:3E:86:13 server=\
    "dhcp1 - main"
add address=192.168.10.121 mac-address=00:27:04:3E:86:11 server=\
    "dhcp1 - main"
add address=192.168.10.122 mac-address=00:27:04:3E:86:1D server=\
    "dhcp1 - main"
add address=192.168.10.123 mac-address=00:27:04:3E:86:18 server=\
    "dhcp1 - main"
add address=192.168.10.124 mac-address=00:27:04:3E:86:1C server=\
    "dhcp1 - main"
add address=192.168.10.117 mac-address=00:27:04:3E:86:19 server=\
    "dhcp1 - main"
/ip dhcp-server network
add address=10.0.0.0/29 dns-server=8.8.8.8,8.8.4.4 gateway=10.0.0.1 netmask=\
    29
add address=100.64.2.0/24 dns-server=8.8.8.8 gateway=100.64.2.1 netmask=24
add address=172.16.0.0/24 comment="for AP" dns-server=8.8.8.8,8.8.4.4 \
    gateway=172.16.0.1 netmask=24
add address=192.168.1.0/29 dns-server=8.8.8.8,8.8.4.4 gateway=192.168.1.1 \
    netmask=29
add address=192.168.10.0/24 comment=main dns-server=8.8.8.8,8.8.4.4 gateway=\
    192.168.10.1 netmask=24
add address=192.168.44.0/24 dns-server=8.8.8.8,8.8.4.4 gateway=192.168.44.1 \
    netmask=24
/ip dns
set allow-remote-requests=yes servers=\
    2606:4700:4700::1111,2606:4700:4700::1001
/ip firewall address-list
add address=98.82.104.1 comment=NetBox list=ResiCore
add address=52.0.96.77 comment=Loki_Promtail list=ResiCore
add address=44.207.189.240 comment=JumpA list=ResiCore
add address=52.0.162.201 comment=JumpB list=ResiCore
add address=54.221.91.223 comment=Grafana_Prometheus list=ResiCore
/ip firewall filter
add action=accept chain=forward in-interface=zerotier1
add action=accept chain=input in-interface=zerotier1
add action=accept chain=input comment="Allow UDP 19810 for device management" \
    dst-port=19810 protocol=udp
add action=accept chain=input comment="Allow UDP 29810 for device management" \
    dst-port=29810 protocol=udp
add action=accept chain=input comment="Allow TCP 29811 for device management" \
    dst-port=29811 protocol=tcp
add action=accept chain=input comment="Allow TCP 29812 for device management" \
    dst-port=29812 protocol=tcp
add action=accept chain=input comment="Allow TCP 29813 for device management" \
    dst-port=29813 protocol=tcp
add action=accept chain=input comment="Allow TCP 29814 for device management" \
    dst-port=29814 protocol=tcp
add action=accept chain=input comment="Allow TCP 29815 for device management" \
    dst-port=29815 protocol=tcp
add action=accept chain=input comment="Allow TCP 29816 for device management" \
    dst-port=29816 protocol=tcp
add action=accept chain=forward comment="Allow ResiBridge Core IPs" \
    src-address-list=ResiCore
add action=drop chain=input disabled=yes src-address=100.64.0.0/10
add action=accept chain=forward dst-address=!100.64.0.0/10 src-address=\
    100.64.0.0/10
add action=drop chain=input disabled=yes protocol=icmp
/ip firewall nat
add action=dst-nat chain=dstnat comment="Alias web -> 192.168.0.1" \
    dst-address=192.168.10.254 dst-port=80,443 protocol=tcp to-addresses=\
    192.168.0.1
add action=src-nat chain=srcnat comment="ZT  stranded device reply fix" \
    dst-address=192.168.0.1 dst-port=80,443 in-interface=zerotier1 protocol=\
    tcp to-addresses=192.168.0.254
add action=masquerade chain=srcnat out-interface=ether1
add action=dst-nat chain=dstnat dst-address=38.89.155.34 dst-port=7443 \
    protocol=tcp to-addresses=192.168.10.196 to-ports=8443
add action=dst-nat chain=dstnat comment="Testing GNS3 Public" dst-address=\
    38.89.155.34 dst-port=3333 protocol=tcp to-addresses=192.168.10.162 \
    to-ports=3080
add action=dst-nat chain=dstnat comment="Office_Server_SSH forward" \
    dst-address=38.89.155.34 dst-port=6626 protocol=tcp to-addresses=\
    192.168.10.162 to-ports=22
add action=dst-nat chain=dstnat comment=GNS3_Winbox dst-address=38.89.155.34 \
    dst-port=5902 protocol=tcp to-addresses=192.168.10.162 to-ports=5902
add action=dst-nat chain=dstnat comment=Office_Server_Essex_TPLink \
    dst-address=38.89.155.34 dst-port=8998 protocol=tcp to-addresses=\
    192.168.10.162 to-ports=5000
add action=dst-nat chain=dstnat dst-address=38.89.155.34 dst-port=6622 \
    protocol=tcp to-addresses=192.168.10.200 to-ports=22
add action=dst-nat chain=dstnat dst-address=38.89.155.34 dst-port=6621 \
    protocol=tcp to-addresses=192.168.10.197 to-ports=6622
add action=dst-nat chain=dstnat dst-address=38.89.155.34 dst-port=5551 \
    protocol=tcp to-addresses=192.168.10.201 to-ports=80
add action=dst-nat chain=dstnat dst-address=38.89.155.34 dst-port=6623 \
    protocol=tcp to-addresses=192.168.10.197 to-ports=3000
add action=dst-nat chain=dstnat dst-address=38.89.155.34 dst-port=6624 \
    protocol=tcp to-addresses=192.168.10.197 to-ports=9090
add action=dst-nat chain=dstnat dst-address=38.89.155.34 dst-port=6625 \
    protocol=tcp to-addresses=192.168.10.197 to-ports=9116
add action=dst-nat chain=dstnat dst-address=38.89.155.34 dst-port=6627 \
    protocol=tcp to-addresses=192.168.10.197 to-ports=9273
add action=dst-nat chain=dstnat comment=Minecraft dst-address=38.89.155.34 \
    dst-port=6633 protocol=tcp to-addresses=192.168.10.197 to-ports=25565
add action=dst-nat chain=dstnat comment=DefaultAginet dst-address=\
    38.89.155.34 dst-port=8888 protocol=tcp to-addresses=192.168.88.1 \
    to-ports=80
add action=dst-nat chain=dstnat comment=GenieACS_GUI dst-address=38.89.155.34 \
    dst-port=6628 protocol=tcp to-addresses=192.168.10.197 to-ports=3001
add action=dst-nat chain=dstnat comment=GenieACS_ACS_PORT dst-address=\
    38.89.155.34 dst-port=6629 protocol=tcp to-addresses=192.168.10.197 \
    to-ports=7547
add action=dst-nat chain=dstnat comment=GenieACS_API dst-address=38.89.155.34 \
    dst-port=6630 protocol=tcp to-addresses=192.168.10.197 to-ports=7557
add action=dst-nat chain=dstnat comment="NYCHA Config" dst-address=\
    38.89.155.34 dst-port=6670 protocol=tcp to-addresses=192.168.10.19 \
    to-ports=6670
add action=dst-nat chain=dstnat dst-address=38.89.155.34 dst-port=3354 \
    protocol=tcp to-addresses=192.168.10.197 to-ports=3354
add action=masquerade chain=srcnat out-interface=ether1
add chain=srcnat src-address=100.64.0.0/10 to-addresses=38.89.155.34
add action=masquerade chain=srcnat src-address=192.168.44.19
add action=src-nat chain=srcnat comment="NAT mgmt access to stranded device" \
    dst-address=192.168.0.1 to-addresses=192.168.0.254
add action=src-nat chain=srcnat comment="ZT to stranded device via rescue IP" \
    dst-address=192.168.0.1 src-address=172.27.0.0/16 to-addresses=\
    192.168.0.254
add action=src-nat chain=srcnat dst-address=192.168.0.1 src-address=\
    172.27.0.0/16 to-addresses=192.168.0.254
/ip ipsec profile
set [ find default=yes ] dpd-interval=2m dpd-maximum-failures=5
/ip route
add disabled=no distance=1 dst-address=0.0.0.0/0 gateway=38.89.155.33 \
    pref-src="" routing-table=main scope=30 suppress-hw-offload=no \
    target-scope=10
/ip service
set telnet disabled=yes
set ftp disabled=yes
set www disabled=yes
set ssh address="192.168.100.0/24,192.168.110.49/32,10.0.0.0/8,52.0.162.201/32\
    ,98.82.104.1/32,44.207.189.240/32,52.0.162.201/32,54.221.91.223/32,172.27.\
    0.0/16"
set api address="192.168.100.0/24,10.0.0.0/8,52.0.162.201/32,98.82.104.1/32,44\
    .207.189.240/32,52.0.162.201/32,54.221.91.223/32,68.173.179.95/32,67.254.1\
    44.100/32,72.14.201.207/32,172.27.0.0/16"
set winbox address=192.168.100.0/24,192.168.10.0/24,172.27.0.0/16
/ip smb shares
set [ find default=yes ] directory=/pub
/radius
add address=172.27.209.248 service=login
/snmp
set contact=support@resibridge.com enabled=yes trap-generators=\
    interfaces,start-trap,temp-exception trap-version=2
/system identity
set name=000001.R1
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
add topics=dhcp
/system note
set show-at-login=no
/system routerboard settings
set enter-setup-on=delete-key
/tool graphing interface
add disabled=yes
/tool netwatch
add comment=test disabled=no down-script="" host=1.1.1.1 http-codes="" name=\
    test test-script="" type=icmp up-script=""
add comment="Grafana Instance" disabled=no down-script="" host=54.221.91.223 \
    http-codes="" name="Grafana Instance" test-script="" type=simple \
    up-script=""
add comment="Netbox Instance" disabled=no down-script="" host=98.82.104.1 \
    http-codes="" name="Netbox Instance" test-script="" type=icmp up-script=\
    ""
/tool romon
set enabled=yes
/user aaa
set use-radius=yes
