import React, { useState, useEffect } from "react";
import {
  Download,
  Upload,
  Plus,
  Trash2,
  FileText,
  RefreshCw,
  Power,
  CheckCircle,
  XCircle,
  Clock,
  Activity,
  ChevronDown,
  ChevronRight,
  Zap,
} from "lucide-react";
import * as Papa from "papaparse";
const getApiBase = () => {
  const env = (process.env.REACT_APP_API_URL || "").trim();
  if (env) return env.replace(/\/$/, "");
  if (typeof window !== "undefined") {
    const { protocol, hostname, port } = window.location;
    const backendPort = port === "3000" || port === "" ? "5001" : port;
    return `${protocol}//${hostname}:${backendPort}`;
  }
  return "";
};
const API_BASE = getApiBase();

const getInitialPage = () => {
  if (typeof window !== 'undefined') {
    const h = window.location.hash.replace('#', '').toLowerCase();
    if (h === 'setup' || h === 'provision') return h;
  }
  return 'provision';
};

const AuditTail = ({ apiBase }) => {
  const [lines, setLines] = React.useState([]);
  React.useEffect(() => {
    const fetchTail = async () => {
      try {
        const r = await fetch(`${apiBase}/api/audit?tail=50`);
        const d = await r.json();
        const parsed = (d.lines || []).map((l) => { try { return JSON.parse(l); } catch { return { raw: l }; } });
        setLines(parsed.reverse());
      } catch {}
    };
    fetchTail();
    const iv = setInterval(fetchTail, 5000);
    return () => clearInterval(iv);
  }, [apiBase]);
  return (
    <div className="space-y-1">
      {lines.map((e, idx) => (
        <div key={idx} className="bg-black/30 border border-white/10 rounded p-2">
          <code className="whitespace-pre-wrap">{JSON.stringify(e)}</code>
        </div>
      ))}
      {lines.length === 0 && <div className="text-blue-300">No recent activity.</div>}
    </div>
  );
};

const RouterOSNetInstaller = () => {
  const [devices, setDevices] = useState([
    {
      id: 1,
      mac: "",
      hostname: "",
      ip: "",
      vlan: "10",
      model: "CRS326-24G-2S+RM",
      portLabels: {},
    },
  ]);
  const [discoveredDevices, setDiscoveredDevices] = useState([]);
  const [provisioningStatus, setProvisioningStatus] = useState({});
  const [isScanning, setIsScanning] = useState(false);
  const [serverStatus, setServerStatus] = useState({
    connected: false,
    backend: "disconnected",
    version: null,
  });
  const [interfaces, setInterfaces] = useState([]);
  const [adminNote, setAdminNote] = useState("");
  const [restarting, setRestarting] = useState(false);
  const [dhcpEnabled, setDhcpEnabled] = useState(false);
  const [toast, setToast] = useState("");
  const [ifaceHealth, setIfaceHealth] = useState({ link: "unknown", ipv4: [] });
  const [hostIfaces, setHostIfaces] = useState([]);
  const [containerIfaces, setContainerIfaces] = useState([]);
  const [preflight, setPreflight] = useState({ checks: [] });
  const [templates, setTemplates] = useState([]);
  const [archMap, setArchMap] = useState({});
  const [selectedTemplate, setSelectedTemplate] = useState("auto");
  const [templatePreview, setTemplatePreview] = useState("");
  const [batchRunning, setBatchRunning] = useState(false);
  const [batchPaused, setBatchPaused] = useState(false);
  const [batchProgress, setBatchProgress] = useState({ total: 0, done: 0 });
  const batchPausedRef = React.useRef(false);
  const batchAbortRef = React.useRef(false);
  const [page, setPage] = useState(getInitialPage());
  const [expandedDevices, setExpandedDevices] = useState({});
  const [editingPortKey, setEditingPortKey] = useState(null);
  const [editingPortValue, setEditingPortValue] = useState("");
  const [showIncompleteOnly, setShowIncompleteOnly] = useState(false);

  // Lightweight custom dropdown for Model to avoid OS dropdown styling issues
  const ModelSelect = ({ value, onChange }) => {
    const [open, setOpen] = React.useState(false);
    const ref = React.useRef(null);
    const options = [
      { value: "CRS326-24G-2S+RM", label: "CRS326-24G-2S+RM (24G)" },
      { value: "CRS418-8P-8G-2S+RM", label: "CRS418-8P-8G-2S+RM (16G, 8 PoE)" },
      { value: "CRS354-48G-4S+2Q+RM", label: "CRS354-48G-4S+2Q+RM (48G)" },
      { value: "CRS354-48P-4S+2Q+RM", label: "CRS354-48P-4S+2Q+RM (48G PoE)" },
    ];
    const current = options.find(o => o.value === value) || options[0];
    React.useEffect(() => {
      const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
      document.addEventListener('click', onDoc);
      return () => document.removeEventListener('click', onDoc);
    }, []);
    return (
      <div className="relative" ref={ref}>
        <button type="button" onClick={() => setOpen(!open)} className="w-full flex items-center justify-between px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white text-sm">
          <span>{current.label}</span>
          <ChevronDown size={16} className="opacity-80" />
        </button>
        {open && (
          <div className="absolute z-20 mt-1 w-full bg-white rounded-lg shadow-lg border border-black/10 max-h-60 overflow-auto">
            {options.map(o => (
              <div key={o.value} onClick={() => { onChange(o.value); setOpen(false); }} className={`px-3 py-2 text-sm cursor-pointer ${o.value === value ? 'bg-blue-50 text-blue-700' : 'hover:bg-gray-100 text-gray-900'}`}>
                {o.label}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  const toggleDeviceAdvanced = (id) =>
    setExpandedDevices((prev) => ({ ...prev, [id]: !prev[id] }));

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(""), 3000);
  };
  const [config, setConfig] = useState({
    gateway: "192.168.44.1",
    subnet: "24",
    baseNetwork: "192.168.44",
    mgmtVlan: "10",
    cxVlan: "20",
    secVlan: "30",
    ntpServer: "time.google.com",
    netinstallInterface: "eth0",
  });

  // Simulate backend connection check
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    checkBackendStatus();
    const interval = setInterval(checkBackendStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  // Listen for hash changes to switch pages
  useEffect(() => {
    const onHash = () => {
      const h = window.location.hash.replace('#', '').toLowerCase();
      if (h === 'setup' || h === 'provision') setPage(h);
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const navigate = (p) => {
    setPage(p);
    if (typeof window !== 'undefined') window.location.hash = p;
  };

  // Auto-refresh discovered devices
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (serverStatus.connected) {
      scanNetwork();
      const interval = setInterval(scanNetwork, 30000);
      return () => clearInterval(interval);
    }
  }, [serverStatus.connected]);

  const checkBackendStatus = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/status`);
      const data = await response.json();
      setServerStatus({
        connected: true,
        backend: data.status || "connected",
        netinstallVersion: data.netinstallVersion,
        interface: data.interface,
        version: data.version || null,
      });
      // Fetch interfaces after we know backend is reachable
      fetchInterfaces();
      // Fetch settings (DHCP toggle)
      fetchSettings();
      // Fetch templates
      fetchTemplates();
      // Fetch arch map for UI badges
      try {
        const m = await fetch(`${API_BASE}/api/arch-map`);
        const mj = await m.json();
        if (mj && mj.map) setArchMap(mj.map);
      } catch {}
    } catch (error) {
      setServerStatus({ connected: false, backend: "disconnected" });
    }
  };

  const fetchInterfaces = async () => {
    try {
      // Prefer host interfaces exported by setup.sh (host view) and fallback to container view
      let res = await fetch(`${API_BASE}/api/host-interfaces`);
      const data = await res.json();
      const hostNames = (data.interfaces || []).map((i) => i.name);
      setHostIfaces(hostNames);

      // Always fetch container interfaces for comparison
      res = await fetch(`${API_BASE}/api/interfaces`);
      const data2 = await res.json();
      const contNames = (data2.interfaces || []).map((i) => i.name);
      setContainerIfaces(contNames);

      // Available choices for the dropdown prefer host view if present
      const names = hostNames.length ? hostNames : contNames;
      setInterfaces(names);
      if (names.length > 0 && !names.includes(config.netinstallInterface)) {
        setConfig({ ...config, netinstallInterface: names[0] });
      }
      // Update interface health for current selection
      fetchInterfaceHealth(config.netinstallInterface || names[0]);
    } catch (e) {
      // Non-fatal; keep manual entry fallback
      setInterfaces([]);
    }
  };

  const restartBackend = async () => {
    try {
      setRestarting(true);
      await fetch(`${API_BASE}/api/admin/restart`, { method: "POST" });
      setAdminNote("Backend restarting…");
      // Poll for backend to come back up
      let up = false;
      for (let i = 0; i < 20; i++) {
        try {
          const r = await fetch(`${API_BASE}/api/status`, { cache: "no-store" });
          if (r.ok) { up = true; break; }
        } catch {}
        await new Promise((res) => setTimeout(res, 1000));
      }
      setRestarting(false);
      checkBackendStatus();
      setAdminNote("");
      if (up) {
        showToast("Backend restarted successfully");
      } else {
        showToast("Backend restart pending… check status");
      }
    } catch (e) {
      setRestarting(false);
      setAdminNote("Failed to request restart");
    }
  };

  const fetchSettings = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/settings`);
      const s = await res.json();
      setDhcpEnabled(Boolean(s.dhcpListener));
    } catch {}
  };

  const setDhcp = async (enabled) => {
    setDhcpEnabled(enabled);
    try {
      const res = await fetch(`${API_BASE}/api/settings/dhcp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
      });
      const data = await res.json();
      if (data.note) setAdminNote(data.note);
    } catch {}
  };

  const fetchInterfaceHealth = async (name) => {
    if (!name) return;
    try {
      const r = await fetch(`${API_BASE}/api/interface/health?name=${encodeURIComponent(name)}`);
      const h = await r.json();
      setIfaceHealth({ link: h.link || "unknown", ipv4: h.ipv4 || [] });
    } catch {}
  };

  const runPreflight = async () => {
    try {
      const r = await fetch(`${API_BASE}/api/preflight`, { cache: "no-store" });
      const data = await r.json();
      setPreflight(data);
      const hasFail = (data.checks || []).some((c) => c.status === "fail");
      const hasWarn = (data.checks || []).some((c) => c.status === "warn");
      if (!hasFail && !hasWarn) showToast("Preflight passed");
    } catch {}
  };

  const fetchTemplates = async () => {
    try {
      const r = await fetch(`${API_BASE}/api/templates`);
      const data = await r.json();
      setTemplates(["auto", ...(data.templates || [])]);
    } catch {}
  };

  const renderTemplate = async (device) => {
    if (selectedTemplate === "auto") {
      setTemplatePreview("");
      return null;
    }
    try {
      // Compute PoE ports per model for template rendering
      const poePortsMap = {
        "CRS418-8P-8G-2S+RM": Array.from({ length: 8 }, (_, i) => `ether${i+1}`),
        "CRS354-48P-4S+2Q+RM": Array.from({ length: 48 }, (_, i) => `ether${i+1}`),
      };
      const payload = {
        template: selectedTemplate,
        variables: {
          hostname: device?.hostname || devices[0]?.hostname || "device",
          ip: device?.ip || devices[0]?.ip || `${config.baseNetwork}.10`,
          mac: device?.mac || devices[0]?.mac || "00:11:22:33:44:55",
          model: device?.model || devices[0]?.model || "CRS326-24G-2S+RM",
          mgmtVlan: config.mgmtVlan,
          cxVlan: config.cxVlan,
          secVlan: config.secVlan,
          subnet: config.subnet,
          gateway: config.gateway,
          ntpServer: config.ntpServer,
          baseNetwork: config.baseNetwork,
          mgmtPort: "ether23",
          secPort: "ether24",
          cxPorts: ["ether1","ether2","ether3"],
          trunkIn: ["sfp-sfpplus1"],
          trunkOut: ["sfp-sfpplus2"],
          now: new Date().toISOString(),
          poePorts: poePortsMap[device?.model || devices[0]?.model] || [],
        },
      };
      const r = await fetch(`${API_BASE}/api/templates/render`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await r.json();
      if (data.rendered) setTemplatePreview(data.rendered);
      return data.rendered || null;
    } catch { return null; }
  };

  const scanNetwork = async () => {
    setIsScanning(true);
    try {
      const response = await fetch(`${API_BASE}/api/discover`);
      const data = await response.json();
      const found = data.devices || [];
      // Merge newly found devices into existing list (append/augment like MikroTik neighbor view)
      setDiscoveredDevices((prev) => {
        const map = new Map((prev || []).map((d) => [(d.mac || '').toLowerCase(), d]));
        for (const dev of found) {
          const mac = (dev.mac || '').toLowerCase();
          if (!mac) continue;
          const existing = map.get(mac);
          if (existing) {
            map.set(mac, {
              ...existing,
              ...dev,
              // Prefer any new identity/model/ip if present; otherwise keep existing
              identity: dev.identity || existing.identity || null,
              model: dev.model || existing.model || null,
              ip: dev.ip || existing.ip || '',
              configured: Boolean(existing.configured || dev.configured),
            });
          } else {
            map.set(mac, dev);
          }
        }
        // Attach a predicted arch/bootfile badge for UI using model→arch map
        const predictArch = (model) => {
          const u = (model || '').toUpperCase();
          // prefix match against server-provided map
          for (const k in archMap) {
            if (!Object.prototype.hasOwnProperty.call(archMap, k)) continue;
            if (u.startsWith(k.toUpperCase())) return archMap[k];
          }
          return null;
        };
        return Array.from(map.values()).map(d => {
          const arch = predictArch(d.model);
          return arch ? { ...d, _arch: arch, _bootfile: `routeros-${arch}.npk` } : d;
        });
      });
      // Do not auto-import discovered devices into the provisioning queue.
      // Users can click "Import" per device to add them explicitly.
    } catch (error) {
      console.error("Network scan failed:", error);
    } finally {
      setIsScanning(false);
    }
  };

  const provisionDevice = async (device) => {
    if (!device.ip) {
      alert("Please enter a static IP address for this device");
      return;
    }

    const targetMAC = device.mac.toLowerCase().replace(/[:-]/g, "");

    setProvisioningStatus((prev) => ({
      ...prev,
      [device.id]: {
        status: "preparing",
        progress: 0,
        message: `Preparing configuration with static IP ${device.ip}...`,
      },
    }));

    try {
      // Step 1: Generate config (template if selected)
      let configContent = null;
      if (selectedTemplate !== "auto") {
        configContent = await renderTemplate(device);
      }
      if (!configContent) {
        configContent = generateConfig(device);
      }
      // Append interface rename commands if port labels present (exec last to avoid breaking references)
      const labels = device.portLabels || {};
      const labelKeys = Object.keys(labels).filter((k) => labels[k]);
      if (labelKeys.length) {
        let rename = "\n/interface ethernet\n";
        labelKeys.forEach((p) => {
          const safe = (labels[p] || '').replace(/[^A-Za-z0-9_+.-]/g, '');
          if (safe) rename += `set [ find name=${p} ] name=${safe}\n`;
        });
        configContent += "\n" + rename;
      }

      setProvisioningStatus((prev) => ({
        ...prev,
        [device.id]: {
          status: "uploading",
          progress: 25,
          message: "Uploading configuration...",
        },
      }));

      // Step 2: Upload config to backend
      const uploadResponse = await fetch(`${API_BASE}/api/config/upload`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mac: targetMAC,
          hostname: device.hostname,
          config: configContent,
        }),
      });

      if (!uploadResponse.ok) throw new Error("Config upload failed");

      setProvisioningStatus((prev) => ({
        ...prev,
        [device.id]: {
          status: "waiting",
          progress: 50,
          message: `Device will boot with static IP ${device.ip}. Put device in netboot mode now!`,
        },
      }));

      // Step 3: Start netinstall process
      const provisionResponse = await fetch(`${API_BASE}/api/provision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mac: targetMAC,
          ip: device.ip,
          hostname: device.hostname,
          configFile: `${device.hostname}.rsc`,
          model: device.model,
        }),
      });

      if (!provisionResponse.ok) throw new Error("Provisioning failed");

      setProvisioningStatus((prev) => ({
        ...prev,
        [device.id]: {
          status: "installing",
          progress: 75,
          message: "Installing RouterOS...",
        },
      }));

      // Step 4: Poll for completion
      const pollStatus = async () => {
        const statusResponse = await fetch(
          `${API_BASE}/api/provision/status/${targetMAC}`,
        );
        const statusData = await statusResponse.json();

        if (statusData.status === "complete") {
          setProvisioningStatus((prev) => ({
            ...prev,
            [device.id]: {
              status: "success",
              progress: 100,
              message: "Device provisioned successfully!",
            },
          }));
          // Post-provision verification
          try {
            const vr = await fetch(`${API_BASE}/api/verify?ip=${encodeURIComponent(device.ip)}`);
            const vd = await vr.json();
            setProvisioningStatus((prev) => ({
              ...prev,
              [device.id]: {
                ...prev[device.id],
                verify: vd,
              },
            }));
          } catch {}
          setTimeout(() => scanNetwork(), 2000);
          setBatchProgress((bp) => ({ ...bp, done: Math.min(bp.done + 1, bp.total) }));
        } else if (statusData.status === "failed") {
          throw new Error(statusData.message || "Provisioning failed");
        } else {
          setProvisioningStatus((prev) => ({
            ...prev,
            [device.id]: {
              status: "installing",
              progress: statusData.progress || 75,
              message: statusData.message || "Installing...",
            },
          }));
          setTimeout(pollStatus, 2000);
        }
      };

      setTimeout(pollStatus, 3000);
    } catch (error) {
      setProvisioningStatus((prev) => ({
        ...prev,
        [device.id]: { status: "failed", progress: 0, message: error.message },
      }));
      setBatchProgress((bp) => ({ ...bp, done: Math.min(bp.done + 1, bp.total) }));
    }
  };

  const addDevice = () => {
    setDevices([
      ...devices,
      {
        id: Date.now(),
        mac: "",
        hostname: "",
        ip: "",
        vlan: "10",
        model: "CRS326-24G-2S+RM",
        portLabels: {},
      },
    ]);
  };

  const removeDevice = (id) => {
    setDevices(devices.filter((d) => d.id !== id));
  };

  const updateDevice = (id, field, value) => {
    setDevices(
      devices.map((d) => (d.id === id ? { ...d, [field]: value } : d)),
    );
  };

  const importFromDiscovered = (discovered) => {
    const mac = (discovered.mac || '').toLowerCase();
    if (!mac) return;
    const idx = devices.findIndex((d) => (d.mac || '').toLowerCase() === mac);
    const candidate = {
      id: Date.now(),
      mac,
      hostname: discovered.identity || `SW-${mac.slice(-8).replace(/:/g, "")}`,
      ip: discovered.ip || "",
      vlan: "10",
      model: discovered.model || "CRS326-24G-2S+RM",
      portLabels: {},
    };
    if (idx >= 0) {
      // Merge details into existing row without creating duplicates
      const next = devices.slice();
      next[idx] = {
        ...next[idx],
        hostname: next[idx].hostname || candidate.hostname,
        ip: next[idx].ip || candidate.ip,
        model: next[idx].model || candidate.model,
      };
      setDevices(next);
    } else {
      setDevices([...devices, candidate]);
    }
  };

  const handleCSVImport = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    Papa.parse(file, {
      header: true,
      dynamicTyping: true,
      skipEmptyLines: true,
      complete: (results) => {
        const imported = results.data.map((row, idx) => ({
          id: Date.now() + idx,
          mac: (row.MAC || row.mac || row["MAC Address"] || "").trim(),
          hostname: (row.Hostname || row.hostname || row.Identity || "").trim(),
          ip: (row.IP || row.ip || row["IP Address"] || "").trim(),
          vlan: (row.VLAN || row.vlan || "10").toString().trim(),
          model: (row.Model || row.model || "CRS326-24G-2S+RM").trim(),
          portLabels: {},
        }));
        const cleaned = imported.filter((d) => d.mac || d.hostname || d.ip);
        const withValidation = cleaned.map((d) => ({ ...d, _errors: validateDeviceRow(d) }));
        setDevices(withValidation);
      },
    });
  };

  const validateDeviceRow = (d) => {
    const errs = [];
    const macRe = /^([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}$/;
    const ipRe = /^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$/;
    if (!d.mac || !macRe.test(d.mac)) errs.push("Invalid MAC");
    if (!d.hostname) errs.push("Missing hostname");
    if (!d.ip || !ipRe.test(d.ip)) errs.push("Invalid IP");
    return errs;
  };

  const hasValidationErrors = () => {
    const rows = devices || [];
    // duplicate check for MAC/hostname/IP
    const dup = (key) => {
      const map = new Map();
      for (const r of rows) {
        const v = (r[key] || '').toLowerCase();
        if (!v) continue;
        if (map.has(v)) return `${key} duplicate: ${v}`;
        map.set(v, true);
      }
      return null;
    };
    for (const r of rows) {
      if ((r._errors || []).length) return true;
    }
    return Boolean(dup('mac') || dup('hostname') || dup('ip'));
  };

  const provisionAll = async () => {
    const rows = devices.filter((d) => (d._errors || []).length === 0);
    const concurrency = 3;
    let index = 0;
    setBatchRunning(true);
    setBatchProgress({ total: rows.length, done: 0 });
    setBatchPaused(false);
    batchPausedRef.current = false;
    batchAbortRef.current = false;
    const runNext = async () => {
      if (index >= rows.length) return;
      // Pause/Abort handling
      while (batchPausedRef.current && !batchAbortRef.current) {
        await new Promise((r) => setTimeout(r, 500));
      }
      if (batchAbortRef.current) return;
      const d = rows[index++];
      await provisionDevice(d);
      await runNext();
    };
    const runners = Array.from({ length: Math.min(concurrency, rows.length) }, () => runNext());
    await Promise.all(runners);
    setBatchRunning(false);
  };

  const downloadSampleCSV = () => {
    const header = ['MAC','Hostname','IP','VLAN','Model'];
    const samples = [
      // Sample rows — replace with real device MACs, hostnames, and IPs for your site
      ['f4:1e:57:89:46:39',`${config.hostname || 'SITE.001.SW01'}`,`${config.baseNetwork}.55`,'10','CRS326-24G-2S+RM'],
      ['f4:1e:57:12:34:56',`${config.hostname || 'SITE.002.SW01'}`,`${config.baseNetwork}.56`,'10','CRS418-8P-8G-2S+RM'],
      ['f4:1e:57:65:43:21',`${config.hostname || 'SITE.003.SW01'}`,`${config.baseNetwork}.57`,'10','CRS354-48P-4S+2Q+RM']
    ];
    const csv = [header.join(','), ...samples.map(r => r.join(','))].join('\n') + '\n';
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'provisioner_sample.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  const copyRenameCommands = (device) => {
    const labels = device.portLabels || {};
    const keys = Object.keys(labels).filter((k) => (labels[k] || '').trim());
    if (!keys.length) { showToast('No port labels set'); return; }
    let out = '/interface ethernet\n';
    keys.forEach((p) => {
      const safe = (labels[p] || '').replace(/[^A-Za-z0-9_+.-]/g, '');
      if (safe) out += `set [ find name=${p} ] name=${safe}\n`;
    });
    try {
      navigator.clipboard.writeText(out);
      showToast('Rename commands copied');
    } catch {
      const ta = document.createElement('textarea');
      ta.value = out; document.body.appendChild(ta); ta.select();
      document.execCommand('copy'); document.body.removeChild(ta);
      showToast('Rename commands copied');
    }
  };

  const toggleBatchPause = () => {
    if (!batchRunning) return;
    const newPaused = !batchPausedRef.current;
    batchPausedRef.current = newPaused;
    setBatchPaused(newPaused);
  };

  const cancelBatch = () => {
    if (!batchRunning) return;
    batchAbortRef.current = true;
    setBatchPaused(false);
    showToast('Batch cancelled');
  };

  const generateConfig = (device) => {
    const { hostname, ip, mac, model } = device;
    const network = `${config.baseNetwork}.0`;

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
    lines.push(`add interface=bridge name=vlan${config.mgmtVlan} vlan-id=${config.mgmtVlan}`);
    lines.push(`add interface=bridge name=vlan${config.cxVlan} vlan-id=${config.cxVlan}`);
    lines.push(`add interface=bridge name=vlan${config.secVlan} vlan-id=${config.secVlan}`);
    lines.push("");
    lines.push(`/interface list`);
    lines.push(`add name=WAN`);
    lines.push(`add name=LAN`);
    lines.push(`add name=CUSTOMER`);
    lines.push("");
    lines.push(`/interface bridge port`);
    // Customer access ports: VLAN ${config.cxVlan}, isolated (horizon=1), edge=yes, admit only untagged/priority-tagged frames
    cxPorts.forEach((p) =>
      lines.push(
        `add bridge=bridge comment=cx pvid=${config.cxVlan} interface=${p} horizon=1 edge=yes frame-types=admit-only-untagged-and-priority-tagged`,
      ),
    );
    lines.push(`add bridge=bridge comment=mgmt pvid=${config.mgmtVlan} interface=${mgmtPort} edge=yes frame-types=admit-only-untagged-and-priority-tagged`);
    lines.push(`add bridge=bridge comment=sec pvid=${config.secVlan} interface=${secPort} edge=yes frame-types=admit-only-untagged-and-priority-tagged`);
    sfpIn.forEach((p) => lines.push(`add bridge=bridge comment=trunk-in frame-types=admit-only-vlan-tagged interface=${p}`));
    sfpOut.forEach((p) => lines.push(`add bridge=bridge comment=trunk-out frame-types=admit-only-vlan-tagged interface=${p}`));
    lines.push("");
    lines.push(`/interface bridge vlan`);
    const taggedAll = [
      ...sfpIn,
      ...sfpOut,
    ].join(",");
    const untaggedCx = cxPorts.join(",");
    lines.push(`add bridge=bridge tagged=${taggedAll} untagged=${untaggedCx} vlan-ids=${config.cxVlan}`);
    lines.push(`add bridge=bridge tagged=${taggedAll} untagged=${mgmtPort} vlan-ids=${config.mgmtVlan}`);
    lines.push(`add bridge=bridge tagged=${taggedAll} untagged=${secPort} vlan-ids=${config.secVlan}`);
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
    // PoE off by default on PoE-capable models
    const poePortsMap = {
      "CRS418-8P-8G-2S+RM": Array.from({ length: 8 }, (_, i) => `ether${i+1}`),
      "CRS354-48P-4S+2Q+RM": Array.from({ length: 48 }, (_, i) => `ether${i+1}`),
    };
    const poePorts = poePortsMap[model] || [];
    if (poePorts.length) {
      lines.push(`/interface ethernet`);
      poePorts.forEach((p) => lines.push(`set [ find name=${p} ] poe-out=off`));
      lines.push("");
    }
    // Drop DHCP on customer access ports (PPPoE access); SEC/mgmt excluded
    lines.push(`/ip firewall filter`);
    lines.push(`add chain=forward in-interface-list=CUSTOMER protocol=udp dst-port=67,68 action=drop comment="Drop DHCP on customer ports"`);
    lines.push("");
    lines.push(`/ip address`);
    lines.push(`add address=${ip}/${config.subnet} comment=defconf interface=vlan${config.mgmtVlan} network=${network}`);
    lines.push("");
    lines.push(`/ip route`);
    lines.push(`add dst-address=0.0.0.0/0 gateway=${config.gateway}`);
    lines.push("");
    lines.push(`/system identity`);
    lines.push(`set name=${hostname}`);
    lines.push("");
    lines.push(`/system note`);
    lines.push(`set show-at-login=no`);
    lines.push("");
    lines.push(`/system ntp client servers`);
    lines.push(`add address=${config.ntpServer}`);
    lines.push("");
    lines.push(`/tool romon`);
    lines.push(`set enabled=yes`);

    return lines.join("\n");
  };

  const downloadConfig = (device) => {
    const used = provisioningStatus?.[device.id]?.config;
    const content = used || (selectedTemplate !== 'auto' ? templatePreview || generateConfig(device) : generateConfig(device));
    const blob = new Blob([content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${device.hostname || "config"}.rsc`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const getStatusIcon = (status) => {
    switch (status?.status) {
      case "success":
        return <CheckCircle className="text-green-400" size={20} />;
      case "failed":
        return <XCircle className="text-red-400" size={20} />;
      case "preparing":
      case "uploading":
      case "waiting":
      case "installing":
        return <Clock className="text-yellow-400 animate-pulse" size={20} />;
      default:
        return null;
    }
  };

  const renderPortMap = (device) => {
    const models = {
      "CRS326-24G-2S+RM": { ether: 24, sfpPlus: 2, qsfpPlus: 0 },
      "CRS418-8P-8G-2S+RM": { ether: 16, sfpPlus: 2, qsfpPlus: 0 },
      "CRS354-48G-4S+2Q+RM": { ether: 48, sfpPlus: 4, qsfpPlus: 2 },
      "CRS354-48P-4S+2Q+RM": { ether: 48, sfpPlus: 4, qsfpPlus: 2 },
    };
    const poeMap = {
      // Best-known defaults; adjust here if needed
      "CRS418-8P-8G-2S+RM": { ports: new Set(Array.from({ length: 8 }, (_, i) => i + 1)), label: "PoE+ (af/at) + Passive 24/48V" },
      "CRS354-48P-4S+2Q+RM": { ports: new Set(Array.from({ length: 48 }, (_, i) => i + 1)), label: "PoE+ (af/at) 54V" },
    };
    const sp = models[device.model] || models["CRS326-24G-2S+RM"];
    const ethers = Array.from({ length: sp.ether }, (_, i) => i + 1);
    const mgmt = sp.ether - 1;
    const sec = sp.ether;
    const portLabels = device.portLabels || {};
    const makeKey = (port) => `${device.id}:${port}`;
    const startEdit = (port) => {
      const current = portLabels[port] || '';
      setEditingPortKey(makeKey(port));
      setEditingPortValue(current);
    };
    const commitEdit = (port) => {
      const safe = (editingPortValue || '').trim();
      updateDevice(device.id, 'portLabels', { ...portLabels, [port]: safe });
      setEditingPortKey(null);
      setEditingPortValue('');
    };
    const cancelEdit = () => { setEditingPortKey(null); setEditingPortValue(''); };
    return (
      <div className="grid grid-cols-8 gap-1 text-xs">
        {ethers.map((n) => {
          const role = n === mgmt ? 'mgmt' : (n === sec ? 'sec' : 'cx');
          const label = `e${n}`;
          const portName = `ether${n}`;
          const key = makeKey(portName);
          const isEditing = editingPortKey === key;
          const poeInfo = poeMap[device.model];
          const isPoe = poeInfo && poeInfo.ports.has(n);
          const baseBg = role === 'mgmt' ? 'bg-amber-500/30' : role === 'sec' ? 'bg-purple-500/30' : 'bg-blue-500/20';
          // Outer shows VLAN color; inner (smaller) shows PoE overlay if applicable
          return (
            <div key={n} className={`px-2 py-1 rounded border border-white/10 ${baseBg} text-blue-100`} onClick={() => !isEditing && startEdit(portName)} title="Click to set a custom label">
              <div className="flex items-center gap-1">
                {!isEditing && (
                  <span className="select-none">{label}{portLabels[portName] ? ` · ${portLabels[portName]}` : ''}</span>
                )}
                {isEditing && (
                  <input
                    autoFocus
                    className="bg-white/10 border border-white/20 rounded px-1 py-0.5 text-[11px] text-white focus:outline-none focus:border-blue-400"
                    value={editingPortValue}
                    onChange={(e) => setEditingPortValue(e.target.value)}
                    onBlur={() => commitEdit(portName)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') commitEdit(portName);
                      if (e.key === 'Escape') cancelEdit();
                    }}
                    placeholder="Label"
                  />
                )}
              </div>
              {isPoe && (
                <div className="mt-0.5 rounded border border-red-400/30 bg-red-500/20 px-1 py-0.5 text-red-100 flex items-center gap-1 text-[10px]">
                  <Zap size={10} /> {poeInfo.label}
                </div>
              )}
            </div>
          );
        })}
        <div className="col-span-8 flex gap-1 mt-1">
          <div className="px-2 py-1 rounded border border-white/10 text-blue-100 bg-green-500/30">sfp+1 (TrunkIn)</div>
          {Array.from({ length: sp.sfpPlus - 1 }, (_, i) => <div key={i} className="px-2 py-1 rounded border border-white/10 text-blue-100 bg-green-500/20">sfp+{i+2} (TrunkOut)</div>)}
          {Array.from({ length: sp.qsfpPlus }, (_, i) => <div key={i} className="px-2 py-1 rounded border border-white/10 text-blue-100 bg-green-500/20">qsfp+{i+1} (TrunkOut)</div>)}
        </div>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-blue-900 to-slate-900 p-6">
      {toast && (
        <div className="fixed top-4 right-4 z-50 bg-green-600 text-white text-sm px-4 py-2 rounded shadow-lg">
          {toast}
        </div>
      )}
      <div className="max-w-7xl mx-auto">
        <div className="bg-white/10 backdrop-blur-lg rounded-2xl shadow-2xl border border-white/20 p-8">
          {/* Header */}
          <div className="flex items-center justify-between mb-8">
            <div>
              <h1 className="text-4xl font-bold text-white mb-2">
                RouterOS NetInstaller
              </h1>
              <p className="text-blue-200">
                MAC-Based Network Provisioning with Static IP Assignment
              </p>
            </div>
            <div className="flex items-center gap-4">
              {page === 'setup' && (
                <button
                  onClick={restartBackend}
                  disabled={restarting}
                  className="flex items-center gap-2 px-3 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-100 rounded-lg border border-red-400/30 text-sm disabled:opacity-50"
                  type="button"
                  title="Restart Backend"
                >
                  <Power size={16} /> {restarting ? "Restarting…" : "Restart"}
                </button>
              )}
              <div
                className={`flex items-center gap-2 px-4 py-2 rounded-lg border ${
                  serverStatus.connected
                    ? "bg-green-500/20 border-green-400/30 text-green-100"
                    : "bg-red-500/20 border-red-400/30 text-red-100"
                }`}
              >
                <div
                  className={`w-2 h-2 rounded-full ${serverStatus.connected ? "bg-green-400" : "bg-red-400"} animate-pulse`}
                />
                <span className="text-sm font-medium">
                  {serverStatus.connected
                    ? "Backend Connected"
                    : "Backend Offline"}
                </span>
              </div>
            </div>
          </div>

          {/* Simple Navigation */}
          <div className="flex items-center gap-2 mb-6">
            <button
              onClick={() => navigate('provision')}
              className={`${page==='provision' ? 'bg-blue-600 text-white' : 'bg-white/10 text-blue-100'} px-3 py-2 rounded border border-white/20`}
            >
              Provision
            </button>
            <button
              onClick={() => navigate('setup')}
              className={`${page==='setup' ? 'bg-blue-600 text-white' : 'bg-white/10 text-blue-100'} px-3 py-2 rounded border border-white/20`}
            >
              Setup
            </button>
          </div>

          {page === 'setup' && (
          /* Preflight Section */
          <div className="bg-white/5 rounded-xl p-4 mb-4 border border-white/10">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-3">
                <Activity className="text-blue-400" size={24} />
                <h2 className="text-lg font-semibold text-white">Preflight Checks</h2>
              </div>
              <button
                onClick={runPreflight}
                className="flex items-center gap-2 px-3 py-1.5 bg-blue-500/20 hover:bg-blue-500/30 text-blue-100 rounded-lg border border-blue-400/30 text-sm"
              >
                <RefreshCw size={18} /> Run Preflight
              </button>
            </div>
            <div className="grid md:grid-cols-2 gap-2 mb-3">
              <div className="bg-white/5 rounded-lg p-2 border border-white/10">
                <div className="text-xs text-blue-100 font-medium mb-1">Host Interfaces</div>
                <div className="text-[11px] text-blue-200 break-words">{hostIfaces.join(', ') || 'n/a'}</div>
              </div>
              <div className="bg-white/5 rounded-lg p-2 border border-white/10">
                <div className="text-xs text-blue-100 font-medium mb-1">Container Interfaces</div>
                <div className="text-[11px] text-blue-200 break-words">{containerIfaces.join(', ') || 'n/a'}</div>
              </div>
            </div>
            {config.netinstallInterface && containerIfaces.length > 0 && !containerIfaces.includes(config.netinstallInterface) && (
              <div className="mb-2 text-xs text-yellow-200">
                Selected interface "{config.netinstallInterface}" is not present in the container. For full L2 provisioning on macOS/Windows, run the backend on the host. On Linux, use host networking (Makefile auto-applies).
              </div>
            )}
            <div className="grid md:grid-cols-2 gap-1">
              {(preflight.checks || []).map((c) => (
                <div key={c.id} className="flex items-center justify-between bg-white/5 rounded-lg p-2 border border-white/10">
                  <div className="text-xs text-blue-100">
                    <div className="font-medium text-white text-sm">{c.name}</div>
                    <div className="opacity-80 text-[11px]">{c.detail}</div>
                    {c.suggestion && <div className="opacity-60 text-[11px]">{c.suggestion}</div>}
                  </div>
                  <div className={`text-[11px] px-2 py-0.5 rounded ${c.status==='pass' ? 'bg-green-500/20 text-green-200' : c.status==='warn' ? 'bg-yellow-500/20 text-yellow-200' : 'bg-red-500/20 text-red-200'}`}>{c.status}</div>
                </div>
              ))}
              {(preflight.checks || []).length === 0 && (
                <div className="text-blue-300 text-sm">Click "Run Preflight" to check environment readiness.</div>
              )}
            </div>
          </div>
          )}

          {page === 'setup' && (
          /* Templates Section */
          <div className="bg-white/5 rounded-xl p-4 mb-4 border border-white/10">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-3">
                <FileText className="text-blue-400" size={20} />
                <h2 className="text-lg font-semibold text-white">Config Templates</h2>
              </div>
              <div className="flex items-center gap-2">
                <select
                  value={selectedTemplate}
                  onChange={(e) => { setSelectedTemplate(e.target.value); if (e.target.value !== 'auto') renderTemplate(); else setTemplatePreview(""); }}
                  className="px-2 py-1.5 bg-white/10 border border-white/20 rounded-lg text-white text-sm focus:outline-none focus:border-blue-400"
                >
                  {templates.map((t) => (
                    <option className="text-gray-900" key={t} value={t}>{t === 'auto' ? 'Auto-Generate' : t}</option>
                  ))}
                </select>
                <button
                  onClick={() => renderTemplate()}
                  disabled={selectedTemplate === 'auto'}
                  className="px-2 py-1.5 bg-blue-500/20 hover:bg-blue-500/30 text-blue-100 rounded-lg border border-blue-400/30 text-sm disabled:opacity-50"
                >
                  Preview
                </button>
              </div>
            </div>
            {templatePreview && (
              <pre className="text-xs text-blue-100 bg-black/40 p-2 rounded border border-white/10 overflow-auto max-h-56 whitespace-pre-wrap">{templatePreview}</pre>
            )}
          </div>
          )}

          {page === 'setup' && (
          /* Audit Log Section */
          <div className="bg-white/5 rounded-xl p-4 mb-4 border border-white/10">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-3">
                <FileText className="text-blue-400" size={20} />
                <h2 className="text-lg font-semibold text-white">Recent Activity</h2>
              </div>
              <button
                onClick={async () => {
                  try {
                    const r = await fetch(`${API_BASE}/api/audit?tail=200`);
                    const data = await r.json();
                    const lines = (data.lines || []).map((l) => {
                      try { return JSON.parse(l); } catch { return { raw: l }; }
                    });
                    const txt = lines.map((e) => JSON.stringify(e, null, 2)).join('\n');
                    const blob = new Blob([txt], { type: 'application/json' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'audit_tail.json';
                    a.click();
                    URL.revokeObjectURL(url);
                  } catch {}
                }}
                className="px-2 py-1.5 bg-blue-500/20 hover:bg-blue-500/30 text-blue-100 rounded-lg border border-blue-400/30 text-xs"
              >
                Export
              </button>
            </div>
            <div className="text-xs text-blue-100 grid gap-1 max-h-48 overflow-auto">
              {/* lightweight live view: fetch last 50 lines on load */}
              <AuditTail apiBase={API_BASE} />
            </div>
          </div>
          )}

          {page === 'provision' && (
          /* Discovered Devices Section */
          <div className="bg-white/5 rounded-xl p-6 mb-6 border border-white/10">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <Activity className="text-blue-400" size={24} />
                <h2 className="text-xl font-semibold text-white">
                  Discovered Devices on L2 Network
                </h2>
              </div>
              <button
                onClick={scanNetwork}
                disabled={isScanning}
                className="flex items-center gap-2 px-4 py-2 bg-blue-500/20 hover:bg-blue-500/30 text-blue-100 rounded-lg border border-blue-400/30 transition-all disabled:opacity-50"
              >
                <RefreshCw
                  size={18}
                  className={isScanning ? "animate-spin" : ""}
                />
                {isScanning ? "Scanning..." : "Scan Network"}
              </button>
            </div>

            {discoveredDevices.length === 0 ? (
              <div className="text-center py-8 text-blue-300">
                {isScanning
                  ? "Scanning network..."
                  : 'No devices discovered. Click "Scan Network" to search for RouterOS devices.'}
              </div>
            ) : (
              <div className="grid gap-3">
                {discoveredDevices.map((dev, idx) => (
                  <div
                    key={idx}
                    className="bg-white/5 rounded-lg p-4 flex items-center justify-between border border-white/10"
                  >
                    <div className="grid grid-cols-4 gap-4 flex-1">
                      <div>
                        <div className="text-xs text-blue-300 mb-1">
                          MAC Address
                        </div>
                        <div className="text-white font-mono text-sm">
                          {dev.mac}
                        </div>
                      </div>
                      <div>
                        <div className="text-xs text-blue-300 mb-1">
                          Identity
                        </div>
                        <div className="text-white text-sm">
                          {dev.identity || "Unknown"}
                        </div>
                      </div>
                      <div>
                        <div className="text-xs text-blue-300 mb-1">Model</div>
                        <div className="text-white text-sm">
                          {dev.model || "Unknown"}
                          {dev._arch && (
                            <span className="ml-2 text-[10px] px-2 py-0.5 rounded bg-white text-gray-900 border border-black/10 align-middle">
                              {dev._arch} · {dev._bootfile}
                            </span>
                          )}
                        </div>
                      </div>
                      <div>
                        <div className="text-xs text-blue-300 mb-1">Status</div>
                        <div
                          className={`text-sm ${dev.configured ? "text-green-400" : "text-yellow-400"}`}
                        >
                          {dev.configured ? "Configured" : "Unconfigured"}
                        </div>
                      </div>
                    </div>
                    <button
                      onClick={() => importFromDiscovered(dev)}
                      className="flex items-center gap-2 px-3 py-1.5 bg-purple-500/20 hover:bg-purple-500/30 text-purple-100 rounded-lg text-sm border border-purple-400/30 transition-all"
                    >
                      <Plus size={16} />
                      Import
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
          )}

          {page === 'setup' && (
          /* Global Settings */
          <div className="bg-white/5 rounded-xl p-4 mb-4 border border-white/10">
            <h2 className="text-lg font-semibold text-white mb-3">
              Global Settings
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div>
                <label className="block text-xs text-blue-200 mb-1">
                  Gateway
                </label>
                <input
                  type="text"
                  value={config.gateway}
                  onChange={(e) =>
                    setConfig({ ...config, gateway: e.target.value })
                  }
                  className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400"
                />
              </div>
              <div>
                <label className="block text-xs text-blue-200 mb-1">
                  Base Network
                </label>
                <input
                  type="text"
                  value={config.baseNetwork}
                  onChange={(e) =>
                    setConfig({ ...config, baseNetwork: e.target.value })
                  }
                  className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400"
                />
              </div>
              <div>
                <label className="block text-xs text-blue-200 mb-1">
                  Subnet
                </label>
                <input
                  type="text"
                  value={config.subnet}
                  onChange={(e) =>
                    setConfig({ ...config, subnet: e.target.value })
                  }
                  className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400"
                />
              </div>
              <div>
                <label className="block text-xs text-blue-200 mb-1">
                  NTP Server
                </label>
                <input
                  type="text"
                  value={config.ntpServer}
                  onChange={(e) =>
                    setConfig({ ...config, ntpServer: e.target.value })
                  }
                  className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400"
                />
              </div>
              <div>
                <label className="block text-xs text-blue-200 mb-1">
                  Interface
                </label>
                {interfaces.length > 0 ? (
                  <select
                    value={config.netinstallInterface}
                    onChange={async (e) => {
                      const val = e.target.value;
                      setConfig({ ...config, netinstallInterface: val });
                      try {
                        const res = await fetch(`${API_BASE}/api/settings/interface`, {
                          method: "POST",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({ interface: val }),
                        });
                        const data = await res.json();
                        if (data.note) setAdminNote(data.note);
                        fetchInterfaceHealth(val);
                      } catch {}
                    }}
                    className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400"
                  >
                    {interfaces.map((name) => (
                      <option className="text-gray-900" key={name} value={name}>
                        {name}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="text"
                    value={config.netinstallInterface}
                    onChange={async (e) => {
                      const val = e.target.value;
                      setConfig({ ...config, netinstallInterface: val });
                      try {
                        const res = await fetch(`${API_BASE}/api/settings/interface`, {
                          method: "POST",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({ interface: val }),
                        });
                        const data = await res.json();
                        if (data.note) setAdminNote(data.note);
                        fetchInterfaceHealth(val);
                      } catch {}
                    }}
                    className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400"
                  />
                )}
                <button
                  onClick={fetchInterfaces}
                  className="mt-1 inline-flex items-center gap-2 px-2 py-1 bg-blue-500/20 hover:bg-blue-500/30 text-blue-100 rounded-lg border border-blue-400/30 text-xs"
                  type="button"
                >
                  <RefreshCw size={14} /> Refresh Interfaces
                </button>
                {adminNote && (
                  <div className="mt-1 text-[11px] text-blue-200">{adminNote}</div>
                )}
                <div className="mt-2 flex items-center gap-3">
                  <label className="flex items-center gap-2 text-xs text-blue-200">
                    <input
                      type="checkbox"
                      checked={dhcpEnabled}
                      onChange={(e) => setDhcp(e.target.checked)}
                      className="accent-blue-400"
                    />
                    Enable DHCP Listener (requires restart)
                  </label>
                </div>
                <div className="mt-1 text-[11px] text-blue-200">
                  Link: <span className={ifaceHealth.link === 'up' ? 'text-green-300' : 'text-red-300'}>{ifaceHealth.link}</span>
                  {" · IPv4: "}
                  {(ifaceHealth.ipv4 || []).join(', ') || 'none'}
                </div>
              </div>
            </div>
          </div>
          )}

          {page === 'provision' && (
          /* Devices to Provision */
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-2xl font-semibold text-white">
              Devices to Provision
            </h2>
            <div className="flex gap-3">
              <label className="flex items-center gap-2 text-blue-100 text-sm">
                <input type="checkbox" className="accent-blue-400" checked={showIncompleteOnly} onChange={(e) => setShowIncompleteOnly(e.target.checked)} />
                Show incomplete only
              </label>
              {batchRunning && (
                <div className="flex items-center gap-2 text-blue-100 text-sm bg-white/10 border border-white/20 px-3 py-2 rounded">
                  <div className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
                  Batch: {batchProgress.done} / {batchProgress.total}
                </div>
              )}
              {batchRunning && (
                <>
                  <button
                    onClick={toggleBatchPause}
                    className="flex items-center gap-2 px-4 py-2 bg-yellow-500/20 hover:bg-yellow-500/30 text-yellow-100 rounded-lg transition-all"
                  >
                    {batchPaused ? 'Resume' : 'Pause'}
                  </button>
                  <button
                    onClick={cancelBatch}
                    className="flex items-center gap-2 px-4 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-100 rounded-lg transition-all"
                  >
                    Cancel
                  </button>
                </>
              )}
              <button
                onClick={provisionAll}
                disabled={hasValidationErrors() || devices.length === 0}
                className="flex items-center gap-2 px-4 py-2 bg-green-500 hover:bg-green-600 text-white rounded-lg transition-all disabled:opacity-50"
                title={hasValidationErrors() ? 'Fix CSV validation errors before provisioning all' : 'Provision all devices'}
              >
                <Power size={18} /> Provision All
              </button>
              <label className="flex items-center gap-2 px-4 py-2 bg-blue-500/20 hover:bg-blue-500/30 text-blue-100 rounded-lg border border-blue-400/30 cursor-pointer transition-all">
                <Upload size={18} />
                Import CSV
                <input
                  type="file"
                  accept=".csv"
                  onChange={handleCSVImport}
                  className="hidden"
                />
              </label>
              <button
                onClick={downloadSampleCSV}
                className="flex items-center gap-2 px-4 py-2 bg-white/10 hover:bg-white/20 text-blue-100 rounded-lg border border-white/20 transition-all"
                title="Download a starter CSV with headers"
              >
                <Download size={18} /> Sample CSV
              </button>
              <button
                onClick={addDevice}
                className="flex items-center gap-2 px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded-lg transition-all"
              >
                <Plus size={18} />
                Add Device
              </button>
            </div>
          </div>
          )}

          {page === 'provision' && (
          <div className="space-y-4">
            {(showIncompleteOnly ? devices.filter(d => !d.mac || !d.hostname || !d.ip) : devices).map((device) => {
              const status = provisioningStatus[device.id];
              return (
                <div
                  key={device.id}
                  className="bg-white/5 rounded-xl p-4 border border-white/10"
                >
                  {(device._errors && device._errors.length > 0) && (
                    <div className="mb-2 text-xs text-red-200">{device._errors.join(' · ')}</div>
                  )}
                  <div className={`grid grid-cols-1 ${expandedDevices[device.id] ? 'md:grid-cols-5' : 'md:grid-cols-4'} gap-4 mb-3`}>
                    <div>
                      <label className="block text-sm text-blue-200 mb-1">
                        MAC Address
                      </label>
                      <input
                        type="text"
                        placeholder="f4:1e:57:89:46:39"
                        value={device.mac}
                        onChange={(e) =>
                          updateDevice(device.id, "mac", e.target.value)
                        }
                        className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white text-sm focus:outline-none focus:border-blue-400"
                      />
                    </div>
                    <div>
                      <label className="block text-sm text-blue-200 mb-1">
                        Hostname
                      </label>
                      <input
                        type="text"
                        placeholder="SITE.002.SW01 — e.g. 000007.002.SW01"
                        value={device.hostname}
                        onChange={(e) =>
                          updateDevice(device.id, "hostname", e.target.value)
                        }
                        className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white text-sm focus:outline-none focus:border-blue-400"
                      />
                    </div>
                    <div>
                      <label className="block text-sm text-blue-200 mb-1">
                        IP Address
                      </label>
                      <input
                        type="text"
                        placeholder="192.168.44.55"
                        value={device.ip}
                        onChange={(e) =>
                          updateDevice(device.id, "ip", e.target.value)
                        }
                        className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white text-sm focus:outline-none focus:border-blue-400"
                      />
                    </div>
                    {/* Always show Model */}
                    <div>
                      <label className="block text-sm text-blue-200 mb-1">Model</label>
                      <ModelSelect
                        value={device.model}
                        onChange={(val) => updateDevice(device.id, "model", val)}
                      />
                    </div>
                    {expandedDevices[device.id] && (
                      <div>
                        <label className="block text-sm text-blue-200 mb-1">MGMT VLAN</label>
                        <input
                          type="text"
                          placeholder="10"
                          value={device.vlan}
                          onChange={(e) => updateDevice(device.id, "vlan", e.target.value)}
                          className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white text-sm focus:outline-none focus:border-blue-400"
                        />
                      </div>
                    )}
                  </div>
                  

                  {status && (
                    <div className="mb-3 bg-white/5 rounded-lg p-3 border border-white/10">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          {getStatusIcon(status)}
                          <span className="text-white text-sm font-medium">
                            {status.message}
                          </span>
                        </div>
                        <span className="text-blue-300 text-sm">
                          {status.progress}%
                        </span>
                      </div>
                      <div className="w-full bg-white/10 rounded-full h-2">
                        <div
                          className={`h-2 rounded-full transition-all duration-500 ${
                            status.status === "success"
                              ? "bg-green-500"
                              : status.status === "failed"
                                ? "bg-red-500"
                                : "bg-blue-500"
                          }`}
                          style={{ width: `${status.progress}%` }}
                        />
                      </div>
                      {status.verify && (
                        <div className="mt-2 text-xs text-blue-200">
                          Verify: {status.verify.ping ? 'Ping OK' : 'Ping FAIL'} · {status.verify.ssh ? 'SSH OPEN' : 'SSH CLOSED'} ({status.verify.ip})
                        </div>
                      )}
                    </div>
                  )}

                  <div className="flex gap-2">
                    <button
                      onClick={() => provisionDevice(device)}
                      disabled={
                        !device.hostname ||
                        !device.ip ||
                        !device.mac ||
                        status?.status === "installing"
                      }
                      className="flex items-center gap-2 px-4 py-2 bg-green-500 hover:bg-green-600 text-white rounded-lg text-sm disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                    >
                      <Power size={16} />
                      Provision Device
                    </button>
                    {status?.status === 'failed' && (
                      <button
                        onClick={() => provisionDevice(device)}
                        className="flex items-center gap-2 px-3 py-2 bg-orange-500/20 hover:bg-orange-500/30 text-orange-100 rounded-lg text-sm border border-orange-400/30 transition-all"
                      >
                        Retry
                      </button>
                    )}
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => downloadConfig(device)}
                        disabled={!device.hostname || !device.ip}
                        className="flex items-center gap-2 px-3 py-2 bg-blue-500/20 hover:bg-blue-500/30 text-blue-100 rounded-lg text-sm border border-blue-400/30 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                      >
                        <Download size={16} />
                        Download
                      </button>
                      <button
                        onClick={() => copyRenameCommands(device)}
                        className="flex items-center gap-1 px-2 py-2 bg-white/5 hover:bg-white/10 text-blue-100 rounded-lg text-xs border border-white/20"
                        type="button"
                        title="Copy interface rename commands"
                      >
                        Copy Renames
                      </button>
                      <button
                        onClick={() => toggleDeviceAdvanced(device.id)}
                        className="flex items-center gap-1 px-2 py-2 bg-white/5 hover:bg-white/10 text-blue-100 rounded-lg text-xs border border-white/20"
                        type="button"
                        title="Show advanced VLAN/Model options"
                      >
                        {expandedDevices[device.id] ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                        Advanced
                      </button>
                    </div>
                    <button
                      onClick={() => removeDevice(device.id)}
                      className="flex items-center gap-2 px-3 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-100 rounded-lg text-sm border border-red-400/30 ml-auto transition-all"
                    >
                      <Trash2 size={16} />
                      Remove
                    </button>
                  </div>
                  {expandedDevices[device.id] && (
                    <div className="mt-3">{renderPortMap(device)}</div>
                  )}
                </div>
              );
            })}
          </div>
          )}

          {devices.length === 0 && (
            <div className="text-center py-12">
              <FileText size={48} className="mx-auto text-blue-300 mb-4" />
              <p className="text-blue-200 mb-4">
                No devices configured for provisioning
              </p>
              <button
                onClick={addDevice}
                className="px-6 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded-lg transition-all"
              >
                Add Your First Device
              </button>
            </div>
          )}
        </div>
        <div className="mt-4 text-xs text-blue-200 flex items-center justify-between">
          <div>
            Backend Version: <span className="text-white">{serverStatus.version || 'dev'}</span>
          </div>
          <a className="text-blue-300 hover:text-blue-200" href="https://github.com/jwresi/Provisioner/releases" target="_blank" rel="noreferrer">Check updates</a>
        </div>
      </div>
    </div>
  );
};

export default RouterOSNetInstaller;
