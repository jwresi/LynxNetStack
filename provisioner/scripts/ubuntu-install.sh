#!/usr/bin/env bash
# Ubuntu installer + setup wizard for RouterOS NetInstaller Provisioner
# - Installs packages (python3-venv, tftpd-hpa, jq)
# - Sets up /opt/provisioner, virtualenv, systemd unit, TFTP root
# - Creates /etc/provisioner.env based on wizard selections
# - Starts backend and TFTP, and runs preflight checks

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
INSTALL_PREFIX="/opt/provisioner"
ENV_FILE="/etc/provisioner.env"
UNIT_SRC="${SCRIPT_DIR}/provisioner-backend.service"
UNIT_DEST="/etc/systemd/system/provisioner-backend.service"
TFTP_DEFAULTS="/etc/default/tftpd-hpa"

require_root() {
  if [[ ${EUID} -ne 0 ]]; then
    echo "[ERROR] Please run as root (e.g., sudo $0)" >&2
    exit 1
  fi
}

apt_install() {
  apt-get update -y
  DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3-venv python3-pip rsync jq curl tftpd-hpa whiptail
}

list_ifaces() {
  ip -br addr | awk '$1!="lo"{print $1"|"$3}' | sed 's@/.*@@' || true
}

calc_cidr() {
  local addr cidr
  addr=$(ip -o -f inet addr show "$1" | awk '{print $4}' | head -n1)
  if [[ -z "$addr" ]]; then
    echo "192.168.88.0/24"
    return
  fi
  cidr="$addr"
  echo "$cidr"
}

cidr_to_network() {
  # input: 192.168.99.1/24 -> 192.168.99.0/24
  python3 - "$1" <<'PY'
import ipaddress, sys
cidr = sys.argv[1]
try:
    net = ipaddress.ip_network(cidr, strict=False)
    print(f"{net.network_address}/{net.prefixlen}")
except Exception:
    print("192.168.88.0/24")
PY
}

wizard() {
  local iface iface_menu iface_cidr net_range dhcp_choice

  echo "[INFO] Running setup wizard..."

  # Interface selection
  mapfile -t items < <(list_ifaces)
  if [[ ${#items[@]} -eq 0 ]]; then
    echo "[WARN] No non-loopback interfaces found. You can fill values manually."
    iface="eth0"
  else
    iface_menu=()
    for line in "${items[@]}"; do
      name="${line%%|*}"
      ip="${line#*|}"
      [[ "$ip" == "UNKNOWN" || -z "$ip" ]] && ip="(no IPv4)"
      iface_menu+=("$name" "$ip")
    done
    if command -v whiptail >/dev/null 2>&1; then
      iface=$(whiptail --title "Provisioner Setup" \
        --menu "Select provisioning NIC (untagged on provisioning VLAN)" 20 70 10 \
        "${iface_menu[@]}" 3>&1 1>&2 2>&3) || true
      if [[ -z "$iface" ]]; then
        echo "[INFO] Wizard cancelled. Exiting."
        exit 1
      fi
    else
      echo "Available interfaces:"
      printf ' - %s\n' "${items[@]}"
      read -rp "Enter interface name to use (e.g., enp0s31f6): " iface
    fi
  fi

  # Network range
  iface_cidr=$(calc_cidr "$iface")
  net_range=$(cidr_to_network "$iface_cidr")
  if command -v whiptail >/dev/null 2>&1; then
    net_range=$(whiptail --title "Provisioner Setup" --inputbox \
      "Discovery range (CIDR) for provisioning network" 10 70 "$net_range" 3>&1 1>&2 2>&3) || true
    [[ -z "$net_range" ]] && net_range="192.168.88.0/24"
  else
    read -rp "Discovery CIDR [$net_range]: " tmp
    net_range=${tmp:-$net_range}
  fi

  # DHCP listener toggle
  if command -v whiptail >/dev/null 2>&1; then
    if whiptail --title "Provisioner Setup" --yesno \
      "Enable backend DHCP listener on $iface? (Only on isolated provisioning VLAN with no other DHCP)" 10 70; then
      dhcp_choice="1"
    else
      dhcp_choice="0"
    fi
  else
    read -rp "Enable backend DHCP listener? [y/N]: " yn
    [[ "${yn,,}" == y* ]] && dhcp_choice="1" || dhcp_choice="0"
  fi

  WZ_IFACE="$iface"
  WZ_RANGE="$net_range"
  WZ_DHCP="$dhcp_choice"
}

write_env() {
  echo "[INFO] Writing ${ENV_FILE}"
  cat >"${ENV_FILE}" <<EOF
NETINSTALL_INTERFACE=${WZ_IFACE}
NETWORK_RANGE=${WZ_RANGE}
API_PORT=5001
ENABLE_DHCP_LISTENER=${WZ_DHCP}
EOF
}

sync_repo() {
  echo "[INFO] Syncing repository to ${INSTALL_PREFIX}"
  mkdir -p "${INSTALL_PREFIX}"
  rsync -a --delete --exclude '.git' --exclude '.venv' "${REPO_ROOT}/" "${INSTALL_PREFIX}/"
}

setup_python() {
  echo "[INFO] Creating virtualenv and installing backend requirements"
  cd "${INSTALL_PREFIX}"
  python3 -m venv .venv
  ./.venv/bin/pip install -U pip
  ./.venv/bin/pip install -r backend/requirements.txt
}

setup_symlink() {
  if [[ ! -e /app ]]; then
    ln -sfn "${INSTALL_PREFIX}" /app
    echo "[INFO] Created symlink /app -> ${INSTALL_PREFIX}"
  else
    echo "[INFO] /app already exists; ensure it points to ${INSTALL_PREFIX}"
  fi
}

setup_tftp() {
  echo "[INFO] Configuring tftpd-hpa"
  mkdir -p "${INSTALL_PREFIX}/routeros"
  chmod -R a+rX "${INSTALL_PREFIX}/routeros"
  tee "${TFTP_DEFAULTS}" >/dev/null <<EOF
RUN_DAEMON="yes"
TFTP_USERNAME="tftp"
TFTP_DIRECTORY="/app/routeros"
TFTP_ADDRESS=":69"
TFTP_OPTIONS="--secure --permissive"
EOF
  systemctl restart tftpd-hpa || true
}

install_unit() {
  echo "[INFO] Installing systemd unit"
  install -m 0644 "${UNIT_SRC}" "${UNIT_DEST}"
  systemctl daemon-reload
  systemctl enable --now provisioner-backend
}

run_preflight() {
  echo "[INFO] Backend status:" || true
  curl -s http://127.0.0.1:5001/api/status || true
  echo
  echo "[INFO] Preflight checks:" || true
  curl -s http://127.0.0.1:5001/api/preflight || true
  echo
}

main() {
  require_root
  apt_install
  wizard
  write_env
  sync_repo
  setup_python
  setup_symlink
  install_unit
  setup_tftp
  echo "[INFO] Restarting backend"
  systemctl restart provisioner-backend || true
  echo "[INFO] Installer complete. Summary:"
  echo " - Interface: ${WZ_IFACE}"
  echo " - Range:     ${WZ_RANGE}"
  echo " - DHCP:      ${WZ_DHCP}"
  echo " - Repo:      ${INSTALL_PREFIX}"
  echo " - Env:       ${ENV_FILE}"
  run_preflight
  echo "[HINT] Place RouterOS package at ${INSTALL_PREFIX}/routeros/routeros.npk"
}

main "$@"

