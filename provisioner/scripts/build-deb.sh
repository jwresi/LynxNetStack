#!/usr/bin/env bash
# Build a Debian package for RouterOS NetInstaller Provisioner
# Outputs to dist/ provisioner_<version>_all.deb
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
DIST_DIR="${ROOT_DIR}/dist"
PKG_NAME="provisioner"
VERSION="${1:-1.0.0}"
STAGE_DIR="${DIST_DIR}/${PKG_NAME}_${VERSION}"
DEB_DIR="${STAGE_DIR}/DEBIAN"

echo "[INFO] Building ${PKG_NAME} version ${VERSION}"
rm -rf "${STAGE_DIR}" && mkdir -p "${DEB_DIR}"

# Control file
cat >"${DEB_DIR}/control" <<EOF
Package: ${PKG_NAME}
Version: ${VERSION}
Section: net
Priority: optional
Architecture: all
Maintainer: Local <admin@localhost>
Depends: python3-venv, python3-pip, rsync, jq, curl, tftpd-hpa
Description: RouterOS NetInstaller Provisioner (Flask backend + TFTP helper)
 A provisioning helper for MikroTik RouterOS using NetInstall flows.
 Includes a Flask API backend and TFTP setup. Installs a systemd service
 and a setup helper to configure the provisioning NIC and DHCP listener.
EOF

# Conffiles: keep env file as a user-editable config
cat >"${DEB_DIR}/conffiles" <<EOF
/etc/provisioner.env
EOF

# Maintainer scripts
cat >"${DEB_DIR}/postinst" <<'EOS'
#!/usr/bin/env bash
set -e

ENV_FILE="/etc/provisioner.env"
INSTALL_PREFIX="/opt/provisioner"
SERVICE="provisioner-backend.service"

# Ensure repo is present (installed files)
if [[ ! -d "$INSTALL_PREFIX" ]]; then
  echo "[ERROR] Missing $INSTALL_PREFIX" >&2
  exit 1
fi

# Create /app symlink if missing
if [[ ! -e /app ]]; then
  ln -sfn "$INSTALL_PREFIX" /app || true
fi

# Default env file if not present
if [[ ! -f "$ENV_FILE" ]]; then
  # Try to auto-detect a non-loopback interface
  IFACE=$(ip -br addr | awk '$1!="lo" {print $1; exit}')
  [[ -z "$IFACE" ]] && IFACE="eth0"
  # Compute network range (best-effort)
  CIDR=$(ip -o -f inet addr show "$IFACE" | awk '{print $4}' | head -n1)
  if [[ -z "$CIDR" ]]; then CIDR="192.168.88.0/24"; fi
  python3 - "$CIDR" <<'PY' >"$ENV_FILE"
import ipaddress, sys
cidr=sys.argv[1]
try:
  net=ipaddress.ip_network(cidr, strict=False)
  netstr=f"{net.network_address}/{net.prefixlen}"
except Exception:
  netstr="192.168.88.0/24"
print(f"NETINSTALL_INTERFACE=${IFACE}")
print(f"NETWORK_RANGE={netstr}")
print("API_PORT=5001")
print("ENABLE_DHCP_LISTENER=0")
PY
fi

# Ensure tftpd-hpa serves /app/routeros
mkdir -p "$INSTALL_PREFIX/routeros"
chmod -R a+rX "$INSTALL_PREFIX/routeros"

if [[ -f /etc/default/tftpd-hpa ]]; then
  sed -i 's#^TFTP_DIRECTORY=.*#TFTP_DIRECTORY="/app/routeros"#' /etc/default/tftpd-hpa || true
  sed -i 's#^TFTP_OPTIONS=.*#TFTP_OPTIONS="--secure --permissive"#' /etc/default/tftpd-hpa || true
else
  cat >/etc/default/tftpd-hpa <<EOF
RUN_DAEMON="yes"
TFTP_USERNAME="tftp"
TFTP_DIRECTORY="/app/routeros"
TFTP_ADDRESS=":69"
TFTP_OPTIONS="--secure --permissive"
EOF
fi

systemctl restart tftpd-hpa || true

# Create venv and install requirements
cd "$INSTALL_PREFIX"
python3 -m venv .venv
"$INSTALL_PREFIX/.venv/bin/pip" install -U pip
"$INSTALL_PREFIX/.venv/bin/pip" install -r "$INSTALL_PREFIX/backend/requirements.txt"

# Install service and enable
install -m 0644 "$INSTALL_PREFIX/scripts/provisioner-backend.service" \
  "/etc/systemd/system/$SERVICE"
systemctl daemon-reload
systemctl enable --now "$SERVICE" || true

echo "Provisioner installed. Edit $ENV_FILE if needed, then:"
echo "  sudo systemctl restart $SERVICE"
echo "Place RouterOS package at $INSTALL_PREFIX/routeros/routeros.npk"
exit 0
EOS
chmod 0755 "${DEB_DIR}/postinst"

# Optional maintainer scripts for upgrades/removal
cat >"${DEB_DIR}/prerm" <<'EOS'
#!/usr/bin/env bash
set -e
SERVICE="provisioner-backend.service"
if systemctl is-active --quiet "$SERVICE"; then
  systemctl stop "$SERVICE" || true
fi
exit 0
EOS
chmod 0755 "${DEB_DIR}/prerm"

cat >"${DEB_DIR}/postrm" <<'EOS'
#!/usr/bin/env bash
set -e
if [[ "$1" == "purge" ]]; then
  rm -f /etc/systemd/system/provisioner-backend.service || true
  systemctl daemon-reload || true
fi
exit 0
EOS
chmod 0755 "${DEB_DIR}/postrm"

# Payload files
# Install repo to /opt/provisioner
mkdir -p "${STAGE_DIR}/opt/provisioner"
rsync -a \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude 'routeros/*.npk' \
  --exclude 'routeros/routeros.npk' \
  "${ROOT_DIR}/" "${STAGE_DIR}/opt/provisioner/"

# Install default env as a conffile so dpkg recognizes it
mkdir -p "${STAGE_DIR}/etc"
install -m 0644 "${ROOT_DIR}/scripts/provisioner.env.example" "${STAGE_DIR}/etc/provisioner.env"

# Add helper command to launch the setup wizard
mkdir -p "${STAGE_DIR}/usr/bin"
cat >"${STAGE_DIR}/usr/bin/provisioner-setup" <<'EOF'
#!/usr/bin/env bash
exec sudo /opt/provisioner/scripts/ubuntu-install.sh
EOF
chmod 0755 "${STAGE_DIR}/usr/bin/provisioner-setup"

# Create dist directory and build package
mkdir -p "${DIST_DIR}"
dpkg-deb --build "${STAGE_DIR}" >/dev/null
mv "${STAGE_DIR}.deb" "${DIST_DIR}/${PKG_NAME}_${VERSION}_all.deb"
echo "[OK] Built ${DIST_DIR}/${PKG_NAME}_${VERSION}_all.deb"
