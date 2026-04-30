// Config generator for RouterOS CRS3xx switches with defaults and hardening

export function generateConfig(device, cfg) {
  const { hostname, ip, mac, model, portLabels = {} } = device;
  const network = `${cfg.baseNetwork}.0`;

  const specs = {
    "CRS326-24G-2S+RM": { ether: 24, sfpPlus: 2, qsfpPlus: 0 },
    "CRS418-8P-8G-2S+RM": { ether: 16, sfpPlus: 2, qsfpPlus: 0 },
    "CRS354-48G-4S+2Q+RM": { ether: 48, sfpPlus: 4, qsfpPlus: 2 },
    "CRS354-48P-4S+2Q+RM": { ether: 48, sfpPlus: 4, qsfpPlus: 2 },
  };
  const sp = specs[model] || specs["CRS326-24G-2S+RM"];
  const ethers = Array.from({ length: sp.ether }, (_, i) => `ether${i + 1}`);
  const cxPorts = sp.ether >= 2 ? ethers.slice(0, sp.ether - 2) : [];
  const mgmtPort = sp.ether >= 2 ? ethers[sp.ether - 2] : ethers[0];
  const secPort = sp.ether >= 1 ? ethers[sp.ether - 1] : ethers[0];
  const sfpIn = ["sfp-sfpplus1"];
  const sfpOut = [];
  for (let i = 2; i <= sp.sfpPlus; i++) sfpOut.push(`sfp-sfpplus${i}`);
  for (let i = 1; i <= sp.qsfpPlus; i++) sfpOut.push(`qsfpplus-${i}`);

  const lines = [];
  lines.push(`# RouterOS Configuration for ${hostname}`);
  lines.push(`# Generated: ${new Date().toISOString()}`);
  lines.push(`# MAC: ${mac}`);
  lines.push(`# Model: ${model}`);
  lines.push("");
  lines.push(`/interface bridge`);
  lines.push(`add admin-mac=${mac} auto-mac=no comment=defconf name=bridge vlan-filtering=yes`);
  lines.push(`set [ find name=bridge ] protocol-mode=rstp`);
  lines.push("");
  lines.push(`/interface vlan`);
  lines.push(`add interface=bridge name=vlan${cfg.mgmtVlan} vlan-id=${cfg.mgmtVlan}`);
  lines.push(`add interface=bridge name=vlan${cfg.cxVlan} vlan-id=${cfg.cxVlan}`);
  lines.push(`add interface=bridge name=vlan${cfg.secVlan} vlan-id=${cfg.secVlan}`);
  lines.push("");
  lines.push(`/interface list`);
  lines.push(`add name=WAN`);
  lines.push(`add name=LAN`);
  lines.push(`add name=CUSTOMER`);
  lines.push("");
  lines.push(`/interface bridge port`);
  // Customer ports: isolation + hygiene
  cxPorts.forEach((p) =>
    lines.push(
      `add bridge=bridge comment=cx pvid=${cfg.cxVlan} interface=${p} horizon=1 edge=yes frame-types=admit-only-untagged-and-priority-tagged`,
    ),
  );
  lines.push(`add bridge=bridge comment=mgmt pvid=${cfg.mgmtVlan} interface=${mgmtPort} edge=yes frame-types=admit-only-untagged-and-priority-tagged`);
  lines.push(`add bridge=bridge comment=sec pvid=${cfg.secVlan} interface=${secPort} edge=yes frame-types=admit-only-untagged-and-priority-tagged`);
  sfpIn.forEach((p) => lines.push(`add bridge=bridge comment=trunk-in frame-types=admit-only-vlan-tagged interface=${p}`));
  sfpOut.forEach((p) => lines.push(`add bridge=bridge comment=trunk-out frame-types=admit-only-vlan-tagged interface=${p}`));
  lines.push("");
  lines.push(`/interface bridge vlan`);
  const taggedAll = [...sfpIn, ...sfpOut].join(",");
  const untaggedCx = cxPorts.join(",");
  lines.push(`add bridge=bridge tagged=${taggedAll} untagged=${untaggedCx} vlan-ids=${cfg.cxVlan}`);
  lines.push(`add bridge=bridge tagged=${taggedAll} untagged=${mgmtPort} vlan-ids=${cfg.mgmtVlan}`);
  lines.push(`add bridge=bridge tagged=${taggedAll} untagged=${secPort} vlan-ids=${cfg.secVlan}`);
  lines.push("");
  lines.push(`/interface list member`);
  cxPorts.forEach((p) => lines.push(`add interface=${p} list=LAN`));
  cxPorts.forEach((p) => lines.push(`add interface=${p} list=CUSTOMER`));
  lines.push(`add interface=${mgmtPort} list=LAN`);
  lines.push(`add interface=${secPort} list=LAN`);
  sfpIn.forEach((p) => lines.push(`add interface=${p} list=WAN`));
  sfpOut.forEach((p) => lines.push(`add interface=${p} list=LAN`));
  lines.push("");
  // Harden access ports: BPDU-Guard and Loop-Protect
  lines.push(`/interface bridge port`);
  cxPorts.forEach((p) => lines.push(`set [ find where interface=${p} ] bpdu-guard=yes`));
  lines.push("");
  lines.push(`/interface ethernet`);
  cxPorts.forEach((p) => lines.push(`set [ find name=${p} ] loop-protect=on loop-protect-disable-time=5m loop-protect-send-interval=5s`));
  lines.push("");
  // PoE off by default on PoE models
  const poePortsMap = {
    "CRS418-8P-8G-2S+RM": Array.from({ length: 8 }, (_, i) => `ether${i + 1}`),
    "CRS354-48P-4S+2Q+RM": Array.from({ length: 48 }, (_, i) => `ether${i + 1}`),
  };
  const poePorts = poePortsMap[model] || [];
  if (poePorts.length) {
    lines.push(`/interface ethernet`);
    poePorts.forEach((p) => lines.push(`set [ find name=${p} ] poe-out=off`));
    lines.push("");
  }
  // Drop DHCP on access ports
  lines.push(`/ip firewall filter`);
  lines.push(`add chain=forward in-interface-list=CUSTOMER protocol=udp dst-port=67,68 action=drop comment="Drop DHCP on customer ports"`);
  lines.push("");
  lines.push(`/ip address`);
  lines.push(`add address=${ip}/${cfg.subnet} comment=defconf interface=vlan${cfg.mgmtVlan} network=${network}`);
  lines.push("");
  lines.push(`/ip route`);
  lines.push(`add dst-address=0.0.0.0/0 gateway=${cfg.gateway}`);
  lines.push("");
  lines.push(`/system identity`);
  lines.push(`set name=${hostname}`);
  lines.push("");
  lines.push(`/system note`);
  lines.push(`set show-at-login=no`);
  lines.push("");
  lines.push(`/system ntp client servers`);
  lines.push(`add address=${cfg.ntpServer}`);
  lines.push("");
  lines.push(`/tool romon`);
  lines.push(`set enabled=yes`);

  // Append interface rename commands if provided
  const labelKeys = Object.keys(portLabels).filter((k) => portLabels[k]);
  if (labelKeys.length) {
    lines.push("");
    lines.push(`/interface ethernet`);
    labelKeys.forEach((p) => {
      const safe = (portLabels[p] || '').replace(/[^A-Za-z0-9_\-\+\.]/g, '');
      if (safe) lines.push(`set [ find name=${p} ] name=${safe}`);
    });
  }

  return lines.join("\n");
}

