#!/usr/bin/env python3
# pyright: reportMissingImports=false, reportMissingModuleSource=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportUnusedCallResult=false
"""
RouterOS NetInstaller Backend Server
Handles device discovery, configuration generation, and provisioning via NetInstall
STATIC IP MODE - Uses MAC-to-IP mapping for targeted provisioning
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess
import os
import time
import threading
from scapy.all import ARP, Ether, srp, sniff, BOOTP, DHCP, IP, UDP
import socket
from typing import Any, Dict, List, Optional
import struct

app = Flask(__name__)
_cors = CORS(app)

# Configuration
CONFIG_DIR = "/app/configs"
NETINSTALL_DIR = "/app/netinstall"
ROUTEROS_NPK = "/app/routeros/routeros.npk"
TEMPLATES_DIR = os.path.join(CONFIG_DIR, "templates")
AUDIT_LOG = os.path.join(CONFIG_DIR, "audit.log")
INTERFACE = os.environ.get("NETINSTALL_INTERFACE", "eth0")
ENABLE_DHCP = os.environ.get("ENABLE_DHCP_LISTENER", "0").lower() in ("1", "true", "yes")
# RouterOS SSH credentials for post-boot config import
ROUTEROS_SSH_USER = os.environ.get("ROUTEROS_SSH_USER", "admin")
ROUTEROS_SSH_PASS = os.environ.get("ROUTEROS_SSH_PASS", "")
BACKEND_VERSION = os.environ.get("BACKEND_VERSION")

# Model to architecture map (best-effort; override by supplying correct files)
MODEL_ARCH_MAP = {
    # CRS (switches)
    "CRS112": "mipsbe",
    "CRS125": "mipsbe",
    "CRS226": "mipsbe",
    "CRS305": "arm",
    "CRS309": "arm",
    "CRS312": "arm",
    "CRS317": "arm",
    "CRS326": "arm",
    "CRS328": "arm",
    "CRS331": "arm",
    "CRS354": "arm64",
    "CRS418": "arm64",

    # CCR (routers)
    "CCR1009": "tile",
    "CCR1016": "tile",
    "CCR1036": "tile",
    "CCR1072": "tile",
    "CCR2004": "arm64",
    "CCR2116": "arm64",
    "CCR2216": "arm64",

    # RB series (branch routers)
    "RB4011": "arm64",
    "RB3011": "arm",
    "RB2011": "mipsbe",
    "RB1100": "powerpc",
    "hEX S": "mmips",
    "hEX": "mmips",
    "hAP ac2": "arm",
    "hAP ac3": "arm",
    "hAP ac": "mipsbe",
    "hAP ax2": "arm64",
    "hAP ax3": "arm64",
}

ARCH_FILENAMES = [
    "routeros-{arch}.npk",  # preferred pattern
    "routeros.{arch}.npk",  # alternate pattern
]

def _resolve_version() -> str:
    if BACKEND_VERSION:
        return BACKEND_VERSION
    try:
        # optional version file installed by packaging
        path = "/opt/provisioner/VERSION"
        if os.path.exists(path):
            with open(path, "r") as f:
                return f.read().strip() or "dev"
    except Exception:
        pass
    return "dev"

def _load_model_arch_map() -> None:
    """Allow overriding/augmenting model→arch mapping via configs/model_arch.json"""
    try:
        path = os.path.join(CONFIG_DIR, "model_arch.json")
        if not os.path.exists(path):
            return
        import json as _json
        with open(path, "r") as f:
            data = _json.load(f)
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(k, str) and isinstance(v, str):
                    MODEL_ARCH_MAP[k] = v
    except Exception as e:
        print(f"[WARN] Failed to load model_arch.json: {e}")

# Persisted settings (override env on startup if present)
SETTINGS_PATH = os.path.join(CONFIG_DIR, "settings.json")

def _load_settings() -> None:
    global INTERFACE, ENABLE_DHCP
    try:
        if os.path.exists(SETTINGS_PATH):
            import json as _json
            with open(SETTINGS_PATH, "r") as f:
                data = _json.load(f)
            if isinstance(data, dict) and data.get("interface"):
                INTERFACE = str(data["interface"]).strip() or INTERFACE
            if isinstance(data, dict) and "dhcpListener" in data:
                ENABLE_DHCP = bool(data.get("dhcpListener"))
    except Exception as e:
        print(f"[WARN] Failed to load settings: {e}")

def _save_settings() -> None:
    try:
        import json as _json
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(SETTINGS_PATH, "w") as f:
            _json.dump({"interface": INTERFACE, "dhcpListener": ENABLE_DHCP}, f)
    except Exception as e:
        print(f"[WARN] Failed to save settings: {e}")

# State management
discovered_devices: Dict[str, Dict[str, Any]] = {}
provision_status: Dict[str, Dict[str, Any]] = {}
active_provisions: Dict[str, Dict[str, Any]] = {}
mac_to_ip_mapping: Dict[str, str] = {}  # MAC -> Static IP mapping
mndp_devices: Dict[str, Dict[str, Any]] = {}  # MAC -> MNDP info (identity, model, version, ip)

try:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(NETINSTALL_DIR, exist_ok=True)
    os.makedirs(TEMPLATES_DIR, exist_ok=True)
    _load_settings()
    _load_model_arch_map()
except OSError:
    # In read-only environments (e.g., local tests), directory creation may fail.
    pass


class StaticIPNetInstaller:
    """Handles RouterOS NetInstall provisioning with static IP assignment"""

    def __init__(self, interface: str):
        self.interface = interface
        self.running = False
        self.dhcp_offers: Dict[str, Any] = {}
        self.netboot_devices: Dict[str, Any] = {}  # Track devices waiting for netboot

    def start_dhcp_listener(self) -> None:
        """Listen for DHCP requests from devices in netboot mode and respond with static IP"""

        def packet_handler(pkt: Any) -> None:
            if pkt.haslayer(DHCP):
                mac = pkt[Ether].src.lower()

                # Check if this is a DHCP Discover
                dhcp_msg_type = None
                for opt in pkt[DHCP].options:
                    if opt[0] == "message-type":
                        dhcp_msg_type = opt[1]
                        break

                if dhcp_msg_type == 1:  # DHCP Discover
                    print(f"[DHCP] Discover from {mac}")

                    # Capture useful hints from DHCP options (vendor class id, hostname)
                    vendor_cls = None
                    host_name = None
                    try:
                        for opt in pkt[DHCP].options:
                            if opt[0] == "vendor_class_id":
                                vendor_cls = opt[1].decode() if isinstance(opt[1], (bytes, bytearray)) else str(opt[1])
                            if opt[0] == "hostname":
                                host_name = opt[1].decode() if isinstance(opt[1], (bytes, bytearray)) else str(opt[1])
                    except Exception:
                        pass

                    # Stash hints for UI/automation
                    self.netboot_devices[mac] = {
                        "mac": mac,
                        "vendorClassId": vendor_cls,
                        "hostname": host_name,
                        "ts": time.time(),
                    }
                    try:
                        log_event({
                            "action": "dhcp.discover",
                            "mac": mac,
                            "vendorClassId": vendor_cls,
                            "hostname": host_name,
                        })
                    except Exception:
                        pass

                    # Check if we have a static IP mapping for this MAC
                    if mac.replace(":", "") in mac_to_ip_mapping:
                        static_ip = mac_to_ip_mapping[mac.replace(":", "")]
                        print(f"[DHCP] Found static mapping: {mac} -> {static_ip}")
                        self.send_dhcp_offer(pkt, static_ip)
                    elif mac in active_provisions:
                        # Use the IP from active provisioning
                        static_ip = active_provisions[mac]["ip"]
                        print(f"[DHCP] Using provisioning IP: {mac} -> {static_ip}")
                        self.send_dhcp_offer(pkt, static_ip)
                    else:
                        print(f"[DHCP] No static mapping found for {mac}")

        print(f"[NetInstall] Starting DHCP listener on {self.interface}")
        enable_listener = ENABLE_DHCP
        if not enable_listener:
            print("[NetInstall] DHCP listener disabled (set ENABLE_DHCP_LISTENER=1 to enable)")
            return

        try:
            sniff(
                iface=self.interface,
                filter="udp and (port 67 or port 68)",
                prn=packet_handler,
                store=0,
            )
        except Exception as e:
            print(f"[ERROR] DHCP listener failed: {e}")

    def send_dhcp_offer(self, discover_pkt: Any, static_ip: str) -> None:
        """Send DHCP offer with static IP assignment"""
        try:
            # Get server IP (interface IP)
            server_ip = self.get_interface_ip()
            if not server_ip:
                print("[ERROR] Could not determine server IP")
                return

            mac = discover_pkt[Ether].src

            # Determine bootfile based on model/arch mapping
            bootfile = self._select_bootfile_for_mac(mac)

            # Build DHCP OFFER packet
            offer = (
                Ether(dst=mac, src=discover_pkt[Ether].dst)
                / IP(src=server_ip, dst="255.255.255.255")
                / UDP(sport=67, dport=68)
                / BOOTP(
                    op=2,  # BOOTREPLY
                    xid=discover_pkt[BOOTP].xid,
                    yiaddr=static_ip,
                    siaddr=server_ip,
                    chaddr=discover_pkt[BOOTP].chaddr,
                    file=bootfile.encode(),
                )
                / DHCP(
                    options=[
                        ("message-type", "offer"),
                        ("server_id", server_ip),
                        ("lease_time", 43200),
                        ("subnet_mask", "255.255.255.0"),
                        ("router", server_ip),
                        ("name_server", server_ip),
                        ("tftp_server_name", server_ip),  # option 66
                        ("bootfile_name", bootfile),  # option 67
                        "end",
                    ]
                )
            )

            # Send the offer
            from scapy.all import sendp

            sendp(offer, iface=self.interface, verbose=False)
            print(f"[DHCP] Sent OFFER: {static_ip} to {mac}")

        except Exception as e:
            print(f"[ERROR] Failed to send DHCP offer: {e}")

    def _select_bootfile_for_mac(self, mac_addr: str) -> str:
        """Choose bootfile name based on provisioned model or MNDP info; fallback to routeros.npk.

        Returns only the filename; TFTP root is /app/routeros.
        """
        name = "routeros.npk"
        try:
            mac_key = mac_addr.lower()
            # Use active_provisions model if available
            meta = active_provisions.get(mac_key) or active_provisions.get(mac_key.replace(":", ""))
            model = None
            if meta and isinstance(meta, dict):
                model = meta.get("model")
            if not model:
                hint = mndp_devices.get(mac_key)
                if hint and isinstance(hint, dict):
                    model = hint.get("model")
            arch = None
            if model:
                for prefix, a in MODEL_ARCH_MAP.items():
                    if str(model).upper().startswith(prefix.upper()):
                        arch = a
                        break
            if arch:
                # Choose first existing arch file
                for fmt in ARCH_FILENAMES:
                    candidate = fmt.format(arch=arch)
                    if os.path.exists(os.path.join("/app/routeros", candidate)):
                        return candidate
        except Exception:
            pass
        # Fallback if specific arch file not found
        return name

    def get_interface_ip(self) -> str:
        """Get IP address of the network interface"""
        try:
            import netifaces

            addrs = netifaces.ifaddresses(self.interface)
            return addrs[netifaces.AF_INET][0]["addr"]
        except:
            # Fallback method
            import socket

            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(("10.255.255.255", 1))
                ip = s.getsockname()[0]
            except Exception:
                ip = "127.0.0.1"
            finally:
                s.close()
            return ip

    def provision_device(self, mac: str, ip: str, hostname: str, config_file: str, model: Optional[str] = None) -> bool:
        """Start provisioning process for a device with static IP"""
        mac_clean = mac.lower().replace(":", "").replace("-", "")
        mac_formatted = mac.lower()

        # Store MAC to IP mapping
        mac_to_ip_mapping[mac_clean] = ip

        provision_status[mac_clean] = {
            "status": "waiting",
            "progress": 0,
            "message": f"Waiting for device to enter netboot mode. Assigned static IP: {ip}",
            "started": time.time(),
            "static_ip": ip,
        }

        active_provisions[mac_formatted] = {
            "ip": ip,
            "hostname": hostname,
            "config_file": config_file,
            "model": model,
        }

        # Start provisioning thread
        thread = threading.Thread(
            target=self._provision_worker, args=(mac, ip, hostname, config_file)
        )
        thread.daemon = True
        thread.start()

        return True

    def _provision_worker(self, mac: str, ip: str, hostname: str, config_file: str) -> None:
        """Background worker for device provisioning with static IP"""
        mac_clean = mac.lower().replace(":", "").replace("-", "")

        try:
            # Step 1: Wait for device to appear on network in netboot mode
            provision_status[mac_clean].update(
                {
                    "status": "detecting",
                    "progress": 10,
                    "message": f"Detecting device on network at {ip}...",
                }
            )

            timeout = 300  # 5 minutes
            start_time = time.time()
            device_found = False

            # Monitor for DHCP requests from this specific MAC
            while time.time() - start_time < timeout:
                if self._check_device_netboot_static(mac, ip):
                    device_found = True
                    break
                time.sleep(2)

            if not device_found:
                raise Exception(
                    f"Device did not enter netboot mode or not reachable at {ip}"
                )

            provision_status[mac_clean].update(
                {
                    "status": "detected",
                    "progress": 20,
                    "message": f"Device detected at {ip}, waiting for netboot...",
                }
            )

            # Step 2: Wait for TFTP transfer to complete
            provision_status[mac_clean].update(
                {
                    "status": "installing",
                    "progress": 30,
                    "message": "RouterOS downloading via TFTP...",
                }
            )

            # Monitor TFTP progress (simulate for now)
            for progress in range(30, 70, 5):
                provision_status[mac_clean]["progress"] = progress
                time.sleep(3)

            provision_status[mac_clean].update(
                {
                    "status": "installing",
                    "progress": 70,
                    "message": "Installing RouterOS to flash...",
                }
            )

            # Wait for installation to complete
            time.sleep(20)

            # Step 3: Wait for device to boot with new RouterOS
            provision_status[mac_clean].update(
                {
                    "status": "booting",
                    "progress": 75,
                    "message": "Device booting with RouterOS...",
                }
            )

            # Wait for device to be accessible via SSH
            if not self._wait_for_ssh(ip, timeout=120):
                raise Exception(f"Device did not respond on SSH at {ip}")

            # Step 4: Upload configuration
            provision_status[mac_clean].update(
                {
                    "status": "configuring",
                    "progress": 85,
                    "message": f"Uploading configuration to {ip}...",
                }
            )

            time.sleep(5)

            if self._upload_config(ip, hostname, config_file):
                provision_status[mac_clean].update(
                    {
                        "status": "complete",
                        "progress": 100,
                        "message": f"Device provisioned successfully at {ip}",
                    }
                )
                # Post-boot verification
                verify = self._post_boot_verify(ip)
                provision_status[mac_clean]["verify"] = verify
            else:
                raise Exception("Configuration upload failed")

        except Exception as e:
            provision_status[mac_clean].update(
                {"status": "failed", "progress": 0, "message": str(e)}
            )
        finally:
            mac_formatted = mac.lower()
            if mac_formatted in active_provisions:
                del active_provisions[mac_formatted]

    def _check_device_netboot_static(self, mac: str, ip: str) -> bool:
        """Check if device is in netboot mode and responding to DHCP with our static IP"""
        mac_clean = mac.lower().replace(":", "").replace("-", "")

        # Check if device has requested DHCP (indicated by our listener)
        if mac_clean in mac_to_ip_mapping:
            # Try to ping the assigned static IP
            try:
                response = subprocess.run(
                    ["ping", "-c", "1", "-W", "1", ip], capture_output=True, timeout=2
                )
                if response.returncode == 0:
                    return True
            except:
                pass

        return False

    def _post_boot_verify(self, ip: str) -> Dict[str, Any]:
        """Run quick verification after import: ping, SSH, identity."""
        result = {"ip": ip, "ping": False, "ssh": False, "identity": None}
        try:
            r = subprocess.run(["ping", "-c", "1", "-W", "1", ip], capture_output=True, timeout=3)
            result["ping"] = (r.returncode == 0)
        except Exception:
            pass
        try:
            import paramiko
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(ip, username=ROUTEROS_SSH_USER or "admin", password=ROUTEROS_SSH_PASS or "", timeout=10, look_for_keys=False, allow_agent=False)
            result["ssh"] = True
            try:
                _in, out, _err = ssh.exec_command("/system identity print", timeout=10)
                txt = out.read().decode(errors="ignore")
                # crude parse
                result["identity"] = (txt or "").strip()
            except Exception:
                pass
            ssh.close()
        except Exception:
            pass
        return result

    def _wait_for_ssh(self, ip: str, timeout: int = 120) -> bool:
        """Wait for SSH port to be available"""
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex((ip, 22))
                sock.close()

                if result == 0:
                    print(f"[SSH] Port 22 open on {ip}")
                    return True
            except:
                pass

            time.sleep(3)

        return False

    def _upload_config(self, ip: str, hostname: str, config_file: str) -> bool:
        """Upload configuration file to device via SSH with static IP"""
        config_path = os.path.join(CONFIG_DIR, config_file)

        if not os.path.exists(config_path):
            print(f"[ERROR] Config file not found: {config_path}")
            return False

        try:
            # Wait a bit for RouterOS to fully boot
            time.sleep(10)

            print(f"[CONFIG] Uploading configuration to {ip} via SSH...")

            import paramiko

            def _connect_candidates() -> tuple:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                # Try env-provided credentials first
                primary_user = ROUTEROS_SSH_USER or "admin"
                primary_pass = ROUTEROS_SSH_PASS or ""
                try:
                    client.connect(
                        ip,
                        username=primary_user,
                        password=primary_pass,
                        timeout=15,
                        banner_timeout=15,
                        auth_timeout=15,
                        look_for_keys=False,
                        allow_agent=False,
                    )
                    return client, primary_user
                except Exception:
                    try:
                        # Fallback to blank admin
                        client.connect(
                            ip,
                            username="admin",
                            password="",
                            timeout=15,
                            banner_timeout=15,
                            auth_timeout=15,
                            look_for_keys=False,
                            allow_agent=False,
                        )
                        return client, "admin"
                    except Exception as e:
                        try:
                            client.close()
                        except Exception:
                            pass
                        raise e

            ssh, used_user = _connect_candidates()
            try:
                sftp = ssh.open_sftp()
                try:
                    remote_path = f"/{config_file}"
                    sftp.put(config_path, remote_path)
                finally:
                    sftp.close()

                # Import configuration; prefer explicit file-name syntax
                cmd = f"/import file-name={config_file}"
                stdin, stdout, stderr = ssh.exec_command(cmd, timeout=30)
                # Read outputs to unblock the channel
                _out = stdout.read().decode(errors="ignore")
                _err = stderr.read().decode(errors="ignore")
                rc = stdout.channel.recv_exit_status() if stdout.channel else 0
                if rc != 0:
                    print(f"[CONFIG] Import returned {rc}: {_err or _out}")
                    return False
                print(f"[CONFIG] Configuration imported on {ip}")

                # Ensure device credentials align with env defaults
                target_user = (ROUTEROS_SSH_USER or "").strip()
                target_pass = ROUTEROS_SSH_PASS or ""
                if target_user:
                    # Escape quotes in password for RouterOS CLI
                    safe_pass = target_pass.replace('"', '\\"')
                    if target_user == "admin":
                        # Set admin password if desired
                        cmd_pw = f"/user set admin password=\"{safe_pass}\""
                        ssh.exec_command(cmd_pw, timeout=15)
                    else:
                        # Create/update desired user, then verify login before disabling default admin
                        ssh.exec_command(f"/user add name=\"{target_user}\" group=full password=\"{safe_pass}\" disabled=no", timeout=15)
                        ssh.exec_command(f"/user set [find name=\"{target_user}\"] password=\"{safe_pass}\"", timeout=15)
                        # Verify we can login with the new user
                        try:
                            import paramiko as _px
                            test = _px.SSHClient()
                            test.set_missing_host_key_policy(_px.AutoAddPolicy())
                            test.connect(ip, username=target_user, password=target_pass, timeout=10, look_for_keys=False, allow_agent=False)
                            test.close()
                            # Only now disable default admin
                            ssh.exec_command("/user set admin disabled=yes", timeout=15)
                        except Exception:
                            print("[CONFIG] Skipping disabling 'admin' because new user login could not be verified")
                return True
            finally:
                ssh.close()

        except Exception as e:
            print(f"[ERROR] Config upload failed to {ip}: {e}")
            return False


# Initialize NetInstall server with static IP support
netinstall = StaticIPNetInstaller(INTERFACE)
_listener_started = False

def _start_dhcp_background():
    global _listener_started
    if _listener_started:
        return
    _listener_started = True
    # Start DHCP listener in background for static IP assignment (honors ENABLE_DHCP)
    dhcp_thread = threading.Thread(target=netinstall.start_dhcp_listener)
    dhcp_thread.daemon = True
    dhcp_thread.start()


class MndpListener:
    """Listens for MikroTik Neighbor Discovery Protocol (MNDP) on UDP/5678 and caches device identity/model."""

    TLV_TYPES = {
        0x01: "mac",
        0x04: "ip",
        0x05: "identity",
        0x07: "version",
        0x08: "platform",
        0x0B: "board",
    }

    def __init__(self):
        self.running = False

    @staticmethod
    def _parse_tlvs(data: bytes) -> Dict[str, Any]:
        # MNDP frames are TLV: type(2) length(2) value(length)
        # Some deployments prefix with 'MNDP' magic which we can skip if present.
        result: Dict[str, Any] = {}
        off = 0
        if len(data) >= 4 and data[:4] == b"MNDP":
            off = 4
        # Scan TLVs defensively
        while off + 4 <= len(data):
            try:
                t, l = struct.unpack_from("!HH", data, off)
            except struct.error:
                break
            off += 4
            if l < 0 or off + l > len(data):
                break
            val = data[off:off + l]
            off += l
            key = MndpListener.TLV_TYPES.get(t, f"tlv_{t}")
            # Decode common fields
            if key == "mac" and len(val) == 6:
                result["mac"] = ":".join(f"{b:02x}" for b in val)
            elif key == "ip" and len(val) == 4:
                result["ip"] = ".".join(str(b) for b in val)
            else:
                try:
                    result[key] = val.decode(errors="ignore").strip("\x00")
                except Exception:
                    result[key] = val
        return result

    def start(self) -> None:
        if self.running:
            return
        self.running = True

        def _worker():
            import socket as _s
            sock = _s.socket(_s.AF_INET, _s.SOCK_DGRAM)
            try:
                sock.setsockopt(_s.SOL_SOCKET, _s.SO_REUSEADDR, 1)
                sock.setsockopt(_s.SOL_SOCKET, _s.SO_BROADCAST, 1)
                sock.bind(("", 5678))
            except Exception as e:
                print(f"[WARN] MNDP listener bind failed: {e}")
                try:
                    sock.close()
                except Exception:
                    pass
                return

            print("[MNDP] Listener started on UDP/5678")
            while self.running:
                try:
                    data, addr = sock.recvfrom(4096)
                    info = self._parse_tlvs(data)
                    if not info:
                        continue
                    mac = str(info.get("mac") or "").lower()
                    if not mac:
                        # Fallback to source address only
                        mac = f"ip:{addr[0]}"
                    entry = {
                        "mac": mac,
                        "ip": info.get("ip") or addr[0],
                        "identity": info.get("identity"),
                        "model": info.get("board") or info.get("platform"),
                        "version": info.get("version"),
                        "ts": time.time(),
                    }
                    mndp_devices[mac] = entry
                except Exception:
                    # Keep listener alive
                    continue

        t = threading.Thread(target=_worker, daemon=True)
        t.start()


_mndp = MndpListener()


def log_event(event: Dict[str, Any]) -> None:
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        event = dict(event)
        event.setdefault("ts", time.time())
        with open(AUDIT_LOG, "a") as f:
            f.write(json.dumps(event) + "\n")
    except Exception:
        pass


def discover_mikrotik_devices() -> List[Dict[str, Any]]:
    """Discover MikroTik devices on L2 network using ARP - works with static IPs"""
    devices = []

    try:
        # Get the network range from environment or use default
        network_range = os.environ.get("NETWORK_RANGE", "192.168.44.0/24")

        print(f"[DISCOVERY] Scanning network {network_range}")

        # Send ARP requests to discover live hosts
        arp = ARP(pdst=network_range)
        ether = Ether(dst="ff:ff:ff:ff:ff:ff")
        packet = ether / arp
        result = srp(packet, timeout=3, iface=INTERFACE, verbose=False)[0]

        for sent, received in result:
            mac = received.hwsrc.lower()
            ip = received.psrc

            # Check if it's a MikroTik device (MAC OUI check)
            if mac.startswith(
                (
                    "00:0c:42",
                    "4c:5e:0c",
                    "48:8f:5a",
                    "d4:ca:6d",
                    "f4:1e:57",
                    "6c:3b:6b",
                    "e6:8d:8c",
                    "18:fd:74",
                    "b8:69:f4",
                    "dc:2c:6e",
                )
            ):
                device = {
                    "mac": mac,
                    "ip": ip,
                    "identity": None,
                    "model": None,
                    "configured": False,
                    "static_ip": True,
                }

                # Enrich from MNDP cache (preferred when available)
                try:
                    hint = mndp_devices.get(mac) or next(
                        (v for k, v in mndp_devices.items() if v.get("ip") == ip),
                        None,
                    )
                    if hint:
                        if hint.get("identity"):
                            device["identity"] = hint.get("identity")
                        if hint.get("model"):
                            device["model"] = hint.get("model")
                        if device.get("identity") or device.get("model"):
                            device["configured"] = True
                except Exception:
                    pass

                devices.append(device)
                discovered_devices[mac] = device

                print(f"[DISCOVERY] Found MikroTik: {mac} at {ip}")

    except Exception as e:
        print(f"[ERROR] Discovery failed: {e}")

    return devices


def get_device_info(ip: str) -> tuple[Optional[str], Optional[str]]:
    """Get device identity and model via RouterOS API or SNMP"""
    try:
        # Try to connect via SSH to get identity (requires RouterOS to be running)
        # In production, implement proper SSH or API connection
        # For now, return None to indicate unconfigured device
        return None, None
    except:
        return None, None


# API Routes


@app.route("/api/status", methods=["GET"])
def get_status():
    """Get backend status"""
    return jsonify(
        {
            "status": "connected",
            "mode": "static-ip",
            "netinstallVersion": "7.16.2",
            "interface": INTERFACE,
            "activeProvisions": len(active_provisions),
            "staticMappings": len(mac_to_ip_mapping),
            "version": _resolve_version(),
        }
    )


@app.route("/api/discover", methods=["GET"])
def discover_devices():
    """Discover devices on L2 network"""
    devices = discover_mikrotik_devices()
    # Merge MNDP hints for any devices we didn't ARP-scan, but only within NETWORK_RANGE
    try:
        import ipaddress as _ip
        network_range = os.environ.get("NETWORK_RANGE", "192.168.44.0/24")
        net = _ip.ip_network(network_range, strict=False)
        known = {d.get("mac") for d in devices}
        for hint in mndp_devices.values():
            mac = (hint.get("mac") or "").lower()
            hip = hint.get("ip")
            if not hip:
                continue
            try:
                if _ip.ip_address(hip) not in net:
                    continue
            except Exception:
                continue
            if mac and mac not in known:
                devices.append({
                    "mac": mac,
                    "ip": hint.get("ip"),
                    "identity": hint.get("identity"),
                    "model": hint.get("model"),
                    "configured": bool(hint.get("identity") or hint.get("model")),
                    "static_ip": False,
                })
                known.add(mac)
    except Exception:
        pass
    return jsonify({"devices": devices, "count": len(devices)})


@app.route("/api/config/upload", methods=["POST"])
def upload_config():
    """Upload device configuration"""
    data = request.json
    mac = data.get("mac", "").lower().replace(":", "").replace("-", "")
    hostname = data.get("hostname")
    config = data.get("config")

    if not all([mac, hostname, config]):
        return jsonify({"error": "Missing required fields"}), 400

    # Ensure config directory exists (tests may override CONFIG_DIR)
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
    except OSError:
        pass

    # Save configuration file
    config_file = f"{hostname}.rsc"
    config_path = os.path.join(CONFIG_DIR, config_file)

    with open(config_path, "w") as f:
        f.write(config)

    print(f"[CONFIG] Saved configuration for {hostname} (MAC: {mac})")
    log_event({
        "action": "config.upload",
        "mac": mac,
        "hostname": hostname,
        "file": config_file,
    })

    return jsonify({"success": True, "configFile": config_file})


@app.route("/api/provision", methods=["POST"])
def provision_device():
    """Start device provisioning with static IP"""
    data = request.json
    mac = data.get("mac", "").lower().replace(":", "").replace("-", "")
    ip = data.get("ip")
    hostname = data.get("hostname")
    config_file = data.get("configFile")
    model = data.get("model")

    if not all([mac, ip, hostname, config_file]):
        return jsonify({"error": "Missing required fields"}), 400

    # Validate IP format
    import ipaddress

    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return jsonify({"error": "Invalid IP address format"}), 400

    print(f"[PROVISION] Starting provisioning for {hostname} (MAC: {mac}, IP: {ip})")
    log_event({
        "action": "provision.start",
        "mac": mac,
        "ip": ip,
        "hostname": hostname,
        "config_file": config_file,
    })

    # Start provisioning with static IP
    success = netinstall.provision_device(mac, ip, hostname, config_file, model)

    if success:
        return jsonify(
            {
                "success": True,
                "message": f"Provisioning started with static IP {ip}",
                "static_ip": ip,
            }
        )
    else:
        return jsonify({"error": "Failed to start provisioning"}), 500


@app.route("/api/provision/status/<mac>", methods=["GET"])
def get_provision_status(mac):
    """Get provisioning status for a device"""
    mac_clean = mac.lower().replace(":", "").replace("-", "")

    if mac_clean in provision_status:
        return jsonify(provision_status[mac_clean])
    else:
        return jsonify(
            {
                "status": "unknown",
                "progress": 0,
                "message": "No provisioning in progress",
            }
        )


@app.route("/api/configs", methods=["GET"])
def list_configs():
    """List all stored configurations"""
    configs = []
    if os.path.isdir(CONFIG_DIR):
        for filename in os.listdir(CONFIG_DIR):
            if filename.endswith(".rsc"):
                configs.append(filename)
    return jsonify({"configs": configs})


@app.route("/api/host-interfaces", methods=["GET"])
def list_host_interfaces():
    """Return interfaces discovered on the host OS (written by setup.sh).

    If unavailable, fall back to container interfaces.
    """
    host_file = os.path.join(CONFIG_DIR, "host_interfaces.json")
    if os.path.exists(host_file):
        try:
            import json as _json

            with open(host_file, "r") as f:
                data = _json.load(f)
            if isinstance(data, dict) and "interfaces" in data:
                return jsonify(data)
        except Exception as e:
            return jsonify({"interfaces": [], "error": str(e)})

    # Fallback to container view
    return list_interfaces()


@app.route("/api/interfaces", methods=["GET"])
def list_interfaces():
    """List available network interfaces inside the backend environment."""
    interfaces: List[Dict[str, Any]] = []
    try:
        import netifaces

        for name in netifaces.interfaces():
            if name in {"lo", "lo0"}:
                continue
            addrs = netifaces.ifaddresses(name)
            ipv4 = [a.get("addr") for a in addrs.get(netifaces.AF_INET, []) if a.get("addr")]
            mac = (addrs.get(netifaces.AF_LINK, [{}])[0].get("addr") or "")
            # Filter to likely-usable interfaces: non-loopback, has IPv4 or looks like physical (eth/en)
            if not ipv4 and not (name.startswith("eth") or name.startswith("en")):
                continue
            if mac and set(mac.replace(":", "")) == {"0"}:
                # Skip all-zero MACs
                continue
            interfaces.append({"name": name, "ipv4": ipv4, "mac": mac or None})
    except Exception as e:
        interfaces.append({"name": INTERFACE, "ipv4": [], "mac": None, "error": str(e)})

    interfaces.sort(key=lambda i: (0 if i.get("name") == INTERFACE else 1, i.get("name")))
    return jsonify({"interfaces": interfaces, "selected": INTERFACE})


@app.route("/api/static-mappings", methods=["GET"])
def get_static_mappings():
    """Get current MAC to Static IP mappings"""
    mappings = [{"mac": mac, "ip": ip} for mac, ip in mac_to_ip_mapping.items()]
    return jsonify({"mappings": mappings})


@app.route("/api/netboot-hints", methods=["GET"])
def netboot_hints():
    """Return recent DHCP discover hints captured by the listener (vendor class, hostname)."""
    try:
        items = list(netinstall.netboot_devices.values())
        # optional TTL filter (seconds)
        ttl = int(request.args.get("ttl", 900))
        now = time.time()
        items = [i for i in items if (now - float(i.get("ts", now))) <= ttl]
        # Sort newest first
        items.sort(key=lambda x: x.get("ts", 0), reverse=True)
        return jsonify({"hints": items})
    except Exception as e:
        return jsonify({"hints": [], "error": str(e)})


@app.route("/api/arch-map", methods=["GET"])
def arch_map():
    """Return current model→arch mapping (prefix-based)."""
    try:
        return jsonify({"map": MODEL_ARCH_MAP})
    except Exception as e:
        return jsonify({"map": {}, "error": str(e)}), 500


@app.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify({
        "interface": INTERFACE,
        "dhcpListener": ENABLE_DHCP,
    })


@app.route("/api/settings/interface", methods=["POST"])
def set_interface():
    global INTERFACE
    data = request.json or {}
    iface = str(data.get("interface", "")).strip()
    if not iface:
        return jsonify({"error": "interface is required"}), 400

    INTERFACE = iface
    try:
        netinstall.interface = iface
    except Exception:
        pass
    _save_settings()

    note = None
    if ENABLE_DHCP:
        note = "DHCP listener change requires backend restart to take effect."

    log_event({"action": "settings.interface", "interface": INTERFACE})
    return jsonify({"ok": True, "interface": INTERFACE, "note": note})


@app.route("/api/settings/dhcp", methods=["POST"])
def set_dhcp_listener():
    global ENABLE_DHCP
    data = request.json or {}
    if "enabled" not in data:
        return jsonify({"error": "enabled is required (true/false)"}), 400
    ENABLE_DHCP = bool(data.get("enabled"))
    _save_settings()
    log_event({"action": "settings.dhcp", "enabled": ENABLE_DHCP})
    return jsonify({
        "ok": True,
        "dhcpListener": ENABLE_DHCP,
        "note": "DHCP listener change requires backend restart to take effect.",
    })


@app.route("/api/admin/restart", methods=["POST"])
def admin_restart():
    """Restart the backend process; container should auto-restart via compose."""
    try:
        def _delayed_exit():
            import time as _t, os as _os
            _t.sleep(0.5)
            _os._exit(0)

        t = threading.Thread(target=_delayed_exit, daemon=True)
        t.start()
        log_event({"action": "admin.restart"})
        return jsonify({"restarting": True}), 202
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/interface/health", methods=["GET"])
def interface_health():
    name = request.args.get("name") or INTERFACE
    info: Dict[str, Any] = {"name": name, "ipv4": [], "link": "unknown"}
    try:
        import netifaces
        addrs = netifaces.ifaddresses(name)
        info["ipv4"] = [a.get("addr") for a in addrs.get(netifaces.AF_INET, []) if a.get("addr")]
    except Exception:
        pass
    # Linux operstate
    try:
        path = f"/sys/class/net/{name}/operstate"
        if os.path.exists(path):
            with open(path) as f:
                state = f.read().strip()
            info["link"] = state
    except Exception:
        pass
    # Heuristic
    if info["link"] == "unknown":
        info["link"] = "up" if info["ipv4"] else "down"
    return jsonify(info)


@app.route("/api/preflight", methods=["GET"])
def preflight():
    checks = []

    def add_check(id, name, status, detail="", suggestion=""):
        checks.append({"id": id, "name": name, "status": status, "detail": detail, "suggestion": suggestion})

    # RouterOS package
    has_npks = False
    try:
        if os.path.exists(ROUTEROS_NPK):
            has_npks = True
        else:
            for fn in os.listdir("/app/routeros"):
                if fn.endswith(".npk"):
                    has_npks = True
                    break
    except Exception:
        pass
    add_check("routeros_pkg", "RouterOS package present", "pass" if has_npks else "fail", detail=ROUTEROS_NPK, suggestion="Place routeros.npk under routeros/")

    # Configs dir writable
    writable = False
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        test_path = os.path.join(CONFIG_DIR, ".write_test")
        with open(test_path, "w") as f:
            f.write("ok")
        os.remove(test_path)
        writable = True
    except Exception as e:
        writable = False
    add_check("configs_writable", "Configs directory writable", "pass" if writable else "fail", detail=CONFIG_DIR)

    # Interface selected
    iface_exists = False
    iface_has_ipv4 = False
    try:
        import netifaces
        if INTERFACE in netifaces.interfaces():
            iface_exists = True
            addrs = netifaces.ifaddresses(INTERFACE)
            iface_has_ipv4 = bool(addrs.get(netifaces.AF_INET))
    except Exception:
        pass
    add_check("iface_exists", f"Interface '{INTERFACE}' exists", "pass" if iface_exists else "fail")
    add_check("iface_ipv4", f"Interface '{INTERFACE}' has IPv4", "pass" if iface_has_ipv4 else "warn", suggestion="Assign IPv4 or select another interface")

    # DHCP listener setting
    add_check("dhcp_listener", "DHCP listener enabled", "pass" if ENABLE_DHCP else "warn", suggestion="Enable if using static IP netboot")

    # TFTP dir readable
    tftp_ok = False
    try:
        files = os.listdir("/app/routeros")
        tftp_ok = any(files)
    except Exception:
        tftp_ok = False
    add_check("tftp_dir", "TFTP directory accessible", "pass" if tftp_ok else "warn", detail="/app/routeros")

    return jsonify({"checks": checks})


@app.route("/api/templates", methods=["GET"])
def list_templates():
    items = []
    try:
        for fn in os.listdir(TEMPLATES_DIR):
            if fn.endswith((".rsc", ".tmpl", ".j2")):
                items.append(fn)
    except Exception:
        pass
    return jsonify({"templates": sorted(items)})


@app.route("/api/templates/render", methods=["POST"])
def render_template():
    data = request.json or {}
    name = data.get("template")
    variables = data.get("variables", {})
    if not name:
        return jsonify({"error": "template is required"}), 400
    path = os.path.normpath(os.path.join(TEMPLATES_DIR, name))
    if not path.startswith(TEMPLATES_DIR):
        return jsonify({"error": "invalid template path"}), 400
    if not os.path.exists(path):
        return jsonify({"error": "template not found"}), 404
    try:
        from jinja2 import Environment, FileSystemLoader, StrictUndefined
        env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), undefined=StrictUndefined, autoescape=False)
        tpl = env.get_template(name)
        output = tpl.render(**variables)
        return jsonify({"rendered": output})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/verify", methods=["GET"])
def verify():
    ip = request.args.get("ip")
    if not ip:
        return jsonify({"error": "ip is required"}), 400
    ping_ok = False
    ssh_ok = False
    try:
        r = subprocess.run(["ping", "-c", "1", "-W", "1", ip], capture_output=True, timeout=3)
        ping_ok = (r.returncode == 0)
    except Exception:
        ping_ok = False
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        ssh_ok = (sock.connect_ex((ip, 22)) == 0)
        sock.close()
    except Exception:
        ssh_ok = False
    result = {"ip": ip, "ping": ping_ok, "ssh": ssh_ok}
    log_event({"action": "verify", **result})
    return jsonify(result)


@app.route("/api/audit", methods=["GET"])
def get_audit():
    tail = int(request.args.get("tail", 200))
    lines = []
    try:
        with open(AUDIT_LOG, "r") as f:
            for line in f.readlines()[-tail:]:
                lines.append(line.strip())
    except Exception:
        pass
    return jsonify({"lines": lines})


if __name__ == "__main__":
    _start_dhcp_background()
    try:
        _mndp.start()
    except Exception as _e:
        print(f"[WARN] MNDP listener not started: {_e}")

    print("=" * 60)
    print("RouterOS NetInstaller - STATIC IP MODE")
    print("=" * 60)
    print(f"Interface: {INTERFACE}")
    print(f"Config Directory: {CONFIG_DIR}")
    print(f"RouterOS NPK: {ROUTEROS_NPK}")
    print("=" * 60)

    # Start Flask server
    import os
    port = int(os.environ.get("API_PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False)
