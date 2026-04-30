# software id = 4AH9-NH0E
#
# model = CCR2004-16G-2S+
# serial number = HGS0AF78RYM
/interface bridge
add comment="PPPoE Ports2-9" name=PPPoE_Bridge
add name=WAN-Public
/interface ethernet
set [ find default-name=ether1 ] name=WAN
set [ find default-name=ether2 ] comment="1st Floor Switch"
set [ find default-name=ether3 ] comment="2nd Floor Switch"
set [ find default-name=ether4 ] comment="3rd Floor Switch"
set [ find default-name=ether5 ] comment="4th Floor Switch"
set [ find default-name=ether6 ] comment="5th Floor Switch"
set [ find default-name=ether7 ] comment="6th Floor Switch"
set [ find default-name=ether8 ] comment="7th Floor Switch"
set [ find default-name=ether9 ] comment=Lobby
set [ find default-name=ether10 ] comment=ProjectFIND_Public
set [ find default-name=ether11 ] comment=Fairstead_Public
set [ find default-name=ether12 ] comment="HVAC Public"
set [ find default-name=ether13 ] comment="Vilo Test"
/interface ovpn-client
add certificate=jwresibridge.crt_0 cipher=aes192-cbc connect-to=54.243.194.0 \
    mac-address=02:AB:01:62:11:6A name=splynx user=jw
/interface wireguard
add listen-port=13231 mtu=1420 name=wireguard1
/interface list
add name=LAN
/ip pool
add name=PPPoE_Pool ranges=10.0.0.2-10.0.0.200
add name="DHCP Pool" ranges=10.0.0.201-10.0.0.210
/port
set 0 name=serial0
/ppp profile
add local-address=10.0.0.1 name=splynx_pppoe only-one=yes
/queue simple
add max-limit=100M/100M name=WCA_Traffic_Limit target=ether14
add max-limit=300M/300M name=Fairstead_Park79 target=24.39.127.28/32
add max-limit=300M/300M name=ProjectFind_Park79 target=24.39.127.27/32
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
/interface bridge port
add bridge=PPPoE_Bridge interface=ether2
add bridge=PPPoE_Bridge interface=ether3
add bridge=PPPoE_Bridge interface=ether4
add bridge=PPPoE_Bridge interface=ether5
add bridge=PPPoE_Bridge interface=ether6
add bridge=PPPoE_Bridge interface=ether7
add bridge=PPPoE_Bridge interface=ether8
add bridge=PPPoE_Bridge interface=ether9
add bridge=WAN-Public comment="ProjectFind Public" interface=ether10
add bridge=WAN-Public comment=WAN interface=WAN
add bridge=WAN-Public comment="Fairstead Public" interface=ether11
add bridge=PPPoE_Bridge interface=ether13
add bridge=WAN-Public comment="HVAC Public" interface=ether12 trusted=yes
/ip firewall connection tracking
set enabled=yes udp-timeout=10s
/ip neighbor discovery-settings
set discover-interface-list=all
/interface detect-internet
set detect-interface-list=all
/interface l2tp-server server
set use-ipsec=yes
/interface list member
add interface=WAN list=*FFFFFFFF
add interface=PPPoE_Bridge list=LAN
/interface ovpn-server server
set auth=sha1,md5
/interface pppoe-server server
add default-profile=splynx_pppoe disabled=no interface=PPPoE_Bridge \
    keepalive-timeout=60 one-session-per-host=yes service-name=Splynx_Server
/interface wireguard peers
add allowed-address=192.168.100.2/32 comment="Jono Desktop" interface=\
    wireguard1 name=peer1 public-key=\
    "NaxlR90B87O+ifdh36+P3Oui6vy72wZmlG9+q04dLT4="
add allowed-address=192.168.100.3/32 comment="Jono Laptop" interface=\
    wireguard1 name=peer2 private-key=\
    "wNBZReV/QRrQtaf482hKEmGNMSM6YziGzlHBFA5UeHU=" public-key=\
    "WKRj3R/eDIUfwakV6hd0umjDg3z0E9zFasEDuBfMBVg="
add allowed-address=192.168.100.4/32 comment=Graham interface=wireguard1 \
    name=peer3 public-key="07fcBwopOtYSyNXvp74s3iXBr8eDD1hDPlCk0eRr0hw="
add allowed-address=192.168.100.5/32 comment=Phone interface=wireguard1 name=\
    peer4 public-key="Y6fgZuduUYN5f2UeVVJaRftqtRgo3e1bDQgKaPzbhnw="
add allowed-address=192.168.100.6/32 comment=Vivek interface=wireguard1 name=\
    peer5 public-key="4MEZrkTNZ7YwYTLO8Ss4gHw3m9Xp3qGTj268faMIhn0="
add allowed-address=192.168.100.7/32 comment="Vivek OSX" interface=wireguard1 \
    name=peer10 public-key="V6FhC7V/PGVNZ4ciyz6DzzgkRVE2W5MApZQYktDDpHA="
/ip address
add address=24.39.127.26/29 interface=WAN-Public network=24.39.127.24
add address=10.0.0.1/24 interface=PPPoE_Bridge network=10.0.0.0
add address=192.168.88.2/24 interface=PPPoE_Bridge network=192.168.88.0
add address=192.168.100.1/24 interface=wireguard1 network=192.168.100.0
add address=24.39.127.29/29 disabled=yes interface=ether12 network=\
    24.39.127.24
add address=24.39.127.29/29 disabled=yes interface=ether12 network=\
    24.39.127.24
/ip arp
add address=10.0.0.247 interface=WAN mac-address=0C:86:10:A4:73:C9
add address=192.168.88.10 comment=000003.SW01 interface=PPPoE_Bridge \
    mac-address=DC:2C:6E:D4:4E:15
add address=192.168.88.11 comment=000003.SW02 interface=PPPoE_Bridge \
    mac-address=DC:2C:6E:D4:4D:89
add address=192.168.88.12 comment=000003.SW03 interface=PPPoE_Bridge \
    mac-address=DC:2C:6E:D4:40:B1
add address=192.168.88.13 comment=000003.SW04 interface=PPPoE_Bridge \
    mac-address=DC:2C:6E:D4:4D:49
add address=192.168.88.14 comment=000003.SW05 interface=PPPoE_Bridge \
    mac-address=DC:2C:6E:D2:67:D4
add address=192.168.88.15 comment=000003.SW06 interface=PPPoE_Bridge \
    mac-address=DC:2C:6E:D2:49:E0
add address=192.168.88.16 comment=000003.SW07 interface=PPPoE_Bridge \
    mac-address=DC:2C:6E:D2:4A:B2
/ip cloud
set ddns-enabled=yes
/ip dhcp-client
add interface=sfp-sfpplus1
/ip dhcp-server network
add address=10.0.0.0/24 gateway=10.0.0.1
add address=10.90.90.0/24 gateway=10.90.90.1
add address=192.168.1.0/24 gateway=192.168.1.1
add address=192.168.111.0/24 dns-server=24.29.99.35,24.29.99.36 gateway=\
    192.168.111.1
/ip dns
set allow-remote-requests=yes servers=24.29.99.35,24.29.99.36,8.8.8.8
/ip firewall address-list
add address=10.0.0.5 comment=SpLBL_4-143 list=SpLBL_disabled
add address=10.0.0.9 comment=SpLBL_9-147 list=SpLBL_disabled
add address=10.0.0.81 comment=SpLBL_82-235 list=SpLBL_new
add address=98.82.104.1 comment=NetBox list=ResiCore
add address=52.0.96.77 comment=Loki_Promtail list=ResiCore
add address=44.207.189.240 comment=JumpA list=ResiCore
add address=52.0.162.201 comment=JumpB list=ResiCore
add address=54.221.91.223 comment=Grafana_Prometheus list=ResiCore
add address=10.0.0.62 comment=SpLBL_62-5306 list=SpLBL_blocked
/ip firewall filter
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
add action=reject chain=splynx-blocked comment=SpBlockingRule-3070586937 \
    dst-limit=10,0,src-address/1m40s reject-with=icmp-admin-prohibited
add action=jump chain=forward comment=SpBlockingRule-2695028582 \
    dst-address-list=!splynx-allowed-resources jump-target=splynx-blocked \
    src-address-list=Reject_4
add action=drop chain=splynx-blocked comment=SpBlockingRule-496360353
add action=accept chain=splynx-blocked comment=SpBlockingRule-3053659851 \
    dst-limit=2,0,src-address/1m40s dst-port=53 protocol=udp
add action=accept chain=splynx-blocked comment=SpBlockingRule-3728159901 \
    dst-address=159.65.88.239 dst-port=80,443,8101,8102,8103,8104 protocol=\
    tcp
add action=reject chain=splynx-blocked comment=SpBlockingRule-3070586937 \
    dst-limit=10,0,src-address/1m40s reject-with=icmp-admin-prohibited
add action=drop chain=splynx-blocked comment=SpBlockingRule-496360353
add chain=forward comment="Splynx Blocking Rules - begin" disabled=yes
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
add chain=forward comment="Splynx Blocking Rules - end" disabled=yes
add action=accept chain=forward in-interface=zerotier1
add action=accept chain=input in-interface=zerotier1
add action=drop chain=forward src-address-list=BLOCK
add action=accept chain=forward dst-address=54.243.194.0 dst-port=8102 log=\
    yes protocol=tcp src-address-list=BLOCK
add action=accept chain=input disabled=yes src-address=0.0.0.0/0
add action=accept chain=input src-mac-address=70:32:17:4A:A1:F0
add action=drop chain=input comment="drop ssh brute forcers" dst-port=22 \
    protocol=tcp src-address-list=ssh_blacklist
add action=drop chain=forward src-address-list=BLOCK
add action=accept chain=forward dst-address=54.243.194.0 dst-port=8102 log=\
    yes protocol=tcp src-address-list=BLOCK
add action=accept chain=input disabled=yes src-address=0.0.0.0/0
add action=accept chain=input src-mac-address=70:32:17:4A:A1:F0
add action=drop chain=input comment="drop ssh brute forcers" dst-port=22 \
    protocol=tcp src-address-list=ssh_blacklist
add action=add-src-to-address-list address-list=ssh_blacklist \
    address-list-timeout=1w3d chain=input connection-state=new dst-port=22 \
    protocol=tcp src-address-list=ssh_stage3
add action=add-src-to-address-list address-list=ssh_stage3 \
    address-list-timeout=1m chain=input connection-state=new dst-port=22 \
    protocol=tcp src-address-list=ssh_stage2
add action=add-src-to-address-list address-list=ssh_stage2 \
    address-list-timeout=1m chain=input connection-state=new dst-port=22 \
    protocol=tcp src-address-list=ssh_stage1
add action=add-src-to-address-list address-list=ssh_stage1 \
    address-list-timeout=1m chain=input connection-state=new dst-port=22 \
    protocol=tcp
add action=accept chain=forward comment="Allow ResiBridge Core IPs" \
    src-address-list=ResiCore
add action=log chain=input dst-port=6670 log-prefix=WINBOX_INPUT_DEBUG \
    protocol=tcp
/ip firewall nat
add action=masquerade chain=srcnat src-address=10.0.0.0/24
add action=masquerade chain=srcnat src-address=192.168.100.0/24
add action=masquerade chain=srcnat src-address=192.168.200.0/24
add action=dst-nat chain=dstnat comment=SNMP disabled=yes dst-port=110 \
    protocol=udp to-addresses=10.0.0.254 to-ports=161
add action=dst-nat chain=dstnat dst-port=3000 protocol=tcp to-addresses=\
    10.0.0.7 to-ports=80
add action=dst-nat chain=dstnat dst-address-list=BLOCK protocol=tcp \
    to-addresses=54.243.194.0 to-ports=8102
add action=masquerade chain=srcnat disabled=yes dst-address=192.168.200.0/24 \
    out-interface=zerotier1 src-address=10.0.0.0/24
/ip route
add disabled=no distance=1 dst-address=0.0.0.0/0 gateway=24.39.127.25 \
    pref-src="" routing-table=main scope=30 suppress-hw-offload=no \
    target-scope=10
add disabled=no distance=1 dst-address=0.0.0.0/0 gateway=24.39.127.25 \
    pref-src="" routing-table=main scope=30 suppress-hw-offload=no \
    target-scope=10
add disabled=yes distance=1 dst-address=192.168.200.0/24 gateway=zerotier1 \
    routing-table=main scope=30 suppress-hw-offload=no target-scope=10
/ip service
set telnet disabled=yes
set ftp address=10.250.32.1/32,192.168.100.0/24 disabled=yes port=6621
set www address=192.168.100.0/24 disabled=yes
set ssh address="192.168.100.0/24,10.0.0.0/8,52.0.162.201/32,98.82.104.1/32,44\
    .207.189.240/32,52.0.162.201/32,54.221.91.223/32,172.27.0.0/16"
set api address="192.168.100.0/24,10.0.0.0/8,52.0.162.201/32,98.82.104.1/32,44\
    .207.189.240/32,52.0.162.201/32,54.221.91.223/32,172.27.0.0/16"
set winbox address=192.168.100.0/24,172.27.0.0/16
set api-ssl disabled=yes
/ip ssh
set always-allow-password-login=yes
/ipv6 firewall filter
add chain=forward comment="Splynx Blocking Rules - begin" disabled=yes
add chain=forward comment="Splynx Blocking Rules - end" disabled=yes
/ppp aaa
set use-radius=yes
/radius
add address=10.250.32.1 require-message-auth=no service=ppp,login,dhcp \
    src-address=10.250.32.2
add address=172.27.209.248 service=login
/radius incoming
set accept=yes
/snmp
set enabled=yes trap-community=resibridge trap-version=2
/system clock
set time-zone-name=America/New_York
/system identity
set name=000003.R1
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
set default-group=full use-radius=yes
