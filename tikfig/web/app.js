const state = {
  deviceName: "",
  template: "switch",
  device: null,
  rendered: "",
};

const steps = document.querySelectorAll(".step");
const panels = document.querySelectorAll(".panel");

function setStep(step) {
  steps.forEach((button) => button.classList.toggle("active", button.dataset.step === step));
  panels.forEach((panel) => panel.classList.toggle("hidden", panel.dataset.panel !== step));
}

steps.forEach((button) => {
  button.addEventListener("click", () => setStep(button.dataset.step));
});

const discoveryStatus = document.getElementById("discovery-status");
const discoveryMeta = document.getElementById("discovery-meta");
const calloutBody = document.getElementById("callout-body");
const refreshDiscovery = document.getElementById("refresh-discovery");

async function checkDiscovery() {
  try {
    const response = await fetch("/api/discovery");
    const data = await response.json();
    discoveryStatus.textContent = data.status === "online" ? "Device online" : "Device not found";
    discoveryStatus.className = `status ${data.status}`;
    discoveryMeta.textContent = `${data.ip}:${data.port} • ${data.latency_ms}ms`;
    calloutBody.textContent = data.status === "online"
      ? "Device detected. You can proceed to NetBox lookup."
      : "Waiting for device on default API address.";
  } catch (error) {
    discoveryStatus.textContent = "Error";
    discoveryMeta.textContent = "Discovery failed.";
    calloutBody.textContent = "Unable to reach local discovery service.";
  }
}

refreshDiscovery.addEventListener("click", checkDiscovery);
setInterval(checkDiscovery, 2500);
checkDiscovery();

const deviceNameInput = document.getElementById("device-name");
const deviceRoleSelect = document.getElementById("device-role");
const lookupButton = document.getElementById("lookup-device");
const deviceNote = document.getElementById("device-note");
const deviceSummary = document.getElementById("device-summary");

lookupButton.addEventListener("click", async () => {
  const name = deviceNameInput.value.trim();
  if (!name) {
    deviceNote.textContent = "Enter a device name.";
    return;
  }

  deviceNote.textContent = "Looking up NetBox...";
  try {
    const response = await fetch(`/api/netbox/device?name=${encodeURIComponent(name)}`);
    const data = await response.json();
    if (!response.ok) {
      deviceNote.textContent = data.error || "NetBox lookup failed.";
      return;
    }

    state.deviceName = name;
    state.device = data.raw;
    state.template = deviceRoleSelect.value;

    deviceSummary.innerHTML = `
      <strong>${data.device.name}</strong>
      <span>Model: ${data.device.model || "Unknown"}</span>
      <span>Site: ${data.device.site || "Unknown"}</span>
      <span>Primary IP: ${data.device.primary_ip4 || "None"}</span>
    `;
    deviceNote.textContent = "Loaded device from NetBox.";
    setStep("3");
  } catch (error) {
    deviceNote.textContent = "NetBox lookup failed.";
  }
});

const generateButton = document.getElementById("generate-config");
const renderNote = document.getElementById("render-note");
const output = document.getElementById("rendered-output");
const downloadButton = document.getElementById("download-config");
const downloadNote = document.getElementById("download-note");

function buildOverrides() {
  const overrides = {
    cgnat_prefix_str: document.getElementById("cgnat-prefix").value.trim() || null,
    cgnat_gateway: document.getElementById("cgnat-gateway").value.trim() || null,
    digi_prefix_str: document.getElementById("digi-prefix").value.trim() || null,
    digi_gateway: document.getElementById("digi-gateway").value.trim() || null,
    digi_prefix_length: document.getElementById("digi-prefix-length").value.trim() || null,
    model: document.getElementById("model-override").value.trim() || null,
  };

  Object.keys(overrides).forEach((key) => {
    if (!overrides[key]) {
      delete overrides[key];
    }
  });

  return overrides;
}

generateButton.addEventListener("click", async () => {
  if (!state.deviceName) {
    renderNote.textContent = "Load a NetBox device first.";
    return;
  }

  renderNote.textContent = "Rendering template...";
  try {
    const response = await fetch("/api/render", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        device_name: state.deviceName,
        template: deviceRoleSelect.value,
        overrides: buildOverrides(),
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      renderNote.textContent = data.error || "Render failed.";
      return;
    }
    state.rendered = data.rendered;
    output.textContent = data.rendered;
    renderNote.textContent = "Rendered successfully.";
    downloadNote.textContent = "Ready to download.";
    setStep("4");
  } catch (error) {
    renderNote.textContent = "Render failed.";
  }
});

downloadButton.addEventListener("click", () => {
  if (!state.rendered) {
    downloadNote.textContent = "Generate a config first.";
    return;
  }

  const blob = new Blob([state.rendered], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${state.deviceName || "device"}.rsc`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  downloadNote.textContent = "Downloaded.";
});
