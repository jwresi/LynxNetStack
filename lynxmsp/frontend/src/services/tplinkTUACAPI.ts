/**
 * TPLink TUAC (TP-Link Unified Application Controller) API Integration
 * Complete implementation based on TAUC OpenAPI documentation
 */

import axios, { AxiosInstance } from 'axios';
import { getErrorMessage } from '../utils/errorHelpers';

// Configuration
interface TUACConfig {
  domainName: string;
  apiKey?: string;
  environment: 'production' | 'staging' | 'development';
}

// Device Information Models
interface DeviceInfo {
  deviceId: string;
  sn: string;
  mac: string;
  deviceType: string;
  firmwareVersion: string;
  hardwareVersion: string;
  ipAddress: string;
  status: 'online' | 'offline';
  lastSeen: string;
}

interface NetworkDevice {
  deviceId: string;
  networkId: string;
  name: string;
  type: 'router' | 'switch' | 'access_point' | 'deco';
  model: string;
  location?: string;
  status: 'active' | 'inactive' | 'error';
}

// Network Configuration Models
interface WiFiConfig {
  ssid: string;
  security: 'open' | 'wep' | 'wpa' | 'wpa2' | 'wpa3';
  password?: string;
  channel: number;
  bandwidth: '20MHz' | '40MHz' | '80MHz' | '160MHz';
  enabled: boolean;
}

interface GuestWiFiConfig {
  ssid: string;
  security: 'open' | 'wpa2';
  password?: string;
  enabled: boolean;
  accessDuration: number; // hours
  maxClients: number;
}

interface RemoteManagementConfig {
  manageViaHttp: boolean;
  manageViaHttps: boolean;
  remoteByAll: boolean;
  remoteIPs: string;
  remoteIPRanges: string;
  portForHttp: number;
  portForHttps: number;
  duration: number;
  durationEnable: boolean;
}

interface QoSConfig {
  enabled: boolean;
  uploadBandwidth: number; // Mbps
  downloadBandwidth: number; // Mbps;
  rules: QoSRule[];
}

interface QoSRule {
  id: string;
  name: string;
  priority: 'high' | 'medium' | 'low';
  uploadLimit: number;
  downloadLimit: number;
  devices: string[]; // MAC addresses
}

interface ClientDevice {
  mac: string;
  ip: string;
  hostname: string;
  connectionType: 'wired' | 'wireless_2g' | 'wireless_5g';
  rxBytes: number;
  txBytes: number;
  connected: boolean;
  signalStrength?: number; // for wireless devices
  connectionTime: number; // seconds
}

// Monitoring and Statistics
interface NetworkStatistics {
  deviceId: string;
  timestamp: string;
  cpuUsage: number;
  memoryUsage: number;
  uptime: number;
  internetStatus: 'connected' | 'disconnected';
  wan: {
    ip: string;
    gateway: string;
    dns: string[];
    uploadSpeed: number;
    downloadSpeed: number;
    latency: number;
  };
  lan: {
    dhcpClients: number;
    totalClients: number;
    activeClients: number;
  };
  wireless: {
    '2g': {
      channel: number;
      clients: number;
      utilization: number;
    };
    '5g': {
      channel: number;
      clients: number;
      utilization: number;
    };
  };
}

class TPLinkTUACAPI {
  private client: AxiosInstance;
  private config: TUACConfig;

  constructor(config: TUACConfig) {
    this.config = config;
    this.client = axios.create({
      baseURL: `https://${config.domainName}/v1/openapi/`,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
    });

    // Request interceptor for API key authentication if available
    this.client.interceptors.request.use((config) => {
      if (this.config.apiKey) {
        config.headers['X-API-Key'] = this.config.apiKey;
      }
      return config;
    });

    // Response interceptor for error handling
    this.client.interceptors.response.use(
      (response) => {
        if (response.data?.errorCode && response.data.errorCode !== 0) {
          throw new Error(`TUAC API Error: ${response.data.msg || 'Unknown error'}`);
        }
        return response;
      },
      (error) => {
        console.error('TUAC API Request Failed:', error);
        return Promise.reject(error);
      }
    );
  }

  // Device Information Management
  async getDeviceId(sn: string, mac: string): Promise<string> {
    try {
      const response = await this.client.get('device-information/device-id', {
        params: { sn, mac }
      });
      return response.data.result.deviceId;
    } catch (error: any) {
      throw new Error(`Failed to get device ID: ${getErrorMessage(error)}`);
    }
  }

  async getDeviceInfo(deviceId: string): Promise<DeviceInfo> {
    try {
      const response = await this.client.get(`device-information/device-info/${deviceId}`);
      return response.data.result;
    } catch (error: any) {
      throw new Error(`Failed to get device info: ${getErrorMessage(error)}`);
    }
  }

  // Device Management - Remote Management
  async getRemoteManagement(networkId: string, refresh: boolean = false): Promise<RemoteManagementConfig> {
    try {
      const params = refresh ? { refresh: 1 } : {};
      const response = await this.client.get(`device-management/aginet/remote-management/${networkId}`, { params });
      return response.data.result;
    } catch (error: any) {
      throw new Error(`Failed to get remote management info: ${getErrorMessage(error)}`);
    }
  }

  async setRemoteManagement(networkId: string, config: RemoteManagementConfig): Promise<void> {
    try {
      await this.client.post(`device-management/aginet/remote-management/${networkId}`, config);
    } catch (error: any) {
      throw new Error(`Failed to set remote management: ${getErrorMessage(error)}`);
    }
  }

  // WiFi Channel Management
  async get2GChannel(deviceId: string, version: 'deco' | 'aginet' = 'aginet', refresh: boolean = false): Promise<number> {
    try {
      const params = refresh ? { refresh: 1 } : {};
      const response = await this.client.get(`device-management/${version}/2g-channel/${deviceId}`, { params });
      return response.data.result.channel;
    } catch (error: any) {
      throw new Error(`Failed to get 2G channel: ${getErrorMessage(error)}`);
    }
  }

  async set2GChannel(deviceId: string, channel: number, version: 'deco' | 'aginet' = 'aginet'): Promise<void> {
    try {
      await this.client.put(`device-management/${version}/2g-channel/${deviceId}`, { channel });
    } catch (error: any) {
      throw new Error(`Failed to set 2G channel: ${getErrorMessage(error)}`);
    }
  }

  async get5GChannel(deviceId: string, version: 'deco' | 'aginet' = 'aginet', refresh: boolean = false): Promise<number> {
    try {
      const params = refresh ? { refresh: 1 } : {};
      const response = await this.client.get(`device-management/${version}/5g-channel/${deviceId}`, { params });
      return response.data.result.channel;
    } catch (error: any) {
      throw new Error(`Failed to get 5G channel: ${getErrorMessage(error)}`);
    }
  }

  async set5GChannel(deviceId: string, channel: number, version: 'deco' | 'aginet' = 'aginet'): Promise<void> {
    try {
      await this.client.put(`device-management/${version}/5g-channel/${deviceId}`, { channel });
    } catch (error: any) {
      throw new Error(`Failed to set 5G channel: ${getErrorMessage(error)}`);
    }
  }

  // WiFi SSID Management
  async getWiFiSSID(deviceId: string, version: 'deco' | 'aginet' = 'aginet', refresh: boolean = false): Promise<WiFiConfig[]> {
    try {
      const params = refresh ? { refresh: 1 } : {};
      const response = await this.client.get(`device-management/${version}/wifi-ssid/${deviceId}`, { params });
      return response.data.result;
    } catch (error: any) {
      throw new Error(`Failed to get WiFi SSID: ${getErrorMessage(error)}`);
    }
  }

  async setWiFiSSID(deviceId: string, wifiConfig: Partial<WiFiConfig>, version: 'deco' | 'aginet' = 'aginet'): Promise<void> {
    try {
      await this.client.put(`device-management/${version}/wifi-ssid/${deviceId}`, wifiConfig);
    } catch (error: any) {
      throw new Error(`Failed to set WiFi SSID: ${getErrorMessage(error)}`);
    }
  }

  // Guest WiFi Management
  async getGuestWiFi(networkId: string, refresh: boolean = false): Promise<GuestWiFiConfig> {
    try {
      const params = refresh ? { refresh: 1 } : {};
      const response = await this.client.get(`device-management/aginet/guest-wifi-ssid/${networkId}`, { params });
      return response.data.result;
    } catch (error: any) {
      throw new Error(`Failed to get guest WiFi: ${getErrorMessage(error)}`);
    }
  }

  async setGuestWiFi(networkId: string, config: Partial<GuestWiFiConfig>): Promise<void> {
    try {
      await this.client.put(`device-management/aginet/guest-wifi-ssid/${networkId}`, config);
    } catch (error: any) {
      throw new Error(`Failed to set guest WiFi: ${getErrorMessage(error)}`);
    }
  }

  // QoS Management
  async getQoSConfig(deviceId: string, refresh: boolean = false): Promise<QoSConfig> {
    try {
      const params = refresh ? { refresh: 1 } : {};
      const response = await this.client.get(`device-management/aginet/qos/${deviceId}`, { params });
      return response.data.result;
    } catch (error: any) {
      throw new Error(`Failed to get QoS config: ${getErrorMessage(error)}`);
    }
  }

  async setQoSConfig(deviceId: string, config: Partial<QoSConfig>): Promise<void> {
    try {
      await this.client.put(`device-management/aginet/qos/${deviceId}`, config);
    } catch (error: any) {
      throw new Error(`Failed to set QoS config: ${getErrorMessage(error)}`);
    }
  }

  // Client Device Management
  async getConnectedClients(deviceId: string, refresh: boolean = false): Promise<ClientDevice[]> {
    try {
      const params = refresh ? { refresh: 1 } : {};
      const response = await this.client.get(`device-management/aginet/clients/${deviceId}`, { params });
      return response.data.result;
    } catch (error: any) {
      throw new Error(`Failed to get connected clients: ${getErrorMessage(error)}`);
    }
  }

  async blockClient(deviceId: string, clientMac: string): Promise<void> {
    try {
      await this.client.post(`device-management/aginet/clients/${deviceId}/block`, { mac: clientMac });
    } catch (error: any) {
      throw new Error(`Failed to block client: ${getErrorMessage(error)}`);
    }
  }

  async unblockClient(deviceId: string, clientMac: string): Promise<void> {
    try {
      await this.client.post(`device-management/aginet/clients/${deviceId}/unblock`, { mac: clientMac });
    } catch (error: any) {
      throw new Error(`Failed to unblock client: ${getErrorMessage(error)}`);
    }
  }

  // Network Statistics and Monitoring
  async getNetworkStatistics(deviceId: string): Promise<NetworkStatistics> {
    try {
      const response = await this.client.get(`device-statistics/network-stats/${deviceId}`);
      return response.data.result;
    } catch (error: any) {
      throw new Error(`Failed to get network statistics: ${getErrorMessage(error)}`);
    }
  }

  async getDeviceHealth(deviceId: string): Promise<{
    cpuUsage: number;
    memoryUsage: number;
    temperature: number;
    uptime: number;
    status: string;
  }> {
    try {
      const response = await this.client.get(`device-monitoring/health/${deviceId}`);
      return response.data.result;
    } catch (error: any) {
      throw new Error(`Failed to get device health: ${getErrorMessage(error)}`);
    }
  }

  // Network Discovery and Topology
  async discoverDevices(networkId?: string): Promise<NetworkDevice[]> {
    try {
      const params = networkId ? { network_id: networkId } : {};
      const response = await this.client.get('network-discovery/devices', { params });
      return response.data.result;
    } catch (error: any) {
      throw new Error(`Failed to discover devices: ${getErrorMessage(error)}`);
    }
  }

  async getNetworkTopology(networkId: string): Promise<{
    devices: NetworkDevice[];
    connections: Array<{
      from: string;
      to: string;
      type: 'wired' | 'wireless';
      quality: number;
    }>;
  }> {
    try {
      const response = await this.client.get(`network-topology/${networkId}`);
      return response.data.result;
    } catch (error: any) {
      throw new Error(`Failed to get network topology: ${getErrorMessage(error)}`);
    }
  }

  // Firmware Management
  async checkFirmwareUpdate(deviceId: string): Promise<{
    currentVersion: string;
    latestVersion: string;
    updateAvailable: boolean;
    releaseNotes: string;
  }> {
    try {
      const response = await this.client.get(`firmware/check-update/${deviceId}`);
      return response.data.result;
    } catch (error: any) {
      throw new Error(`Failed to check firmware update: ${getErrorMessage(error)}`);
    }
  }

  async startFirmwareUpdate(deviceId: string): Promise<{ updateId: string }> {
    try {
      const response = await this.client.post(`firmware/start-update/${deviceId}`);
      return response.data.result;
    } catch (error: any) {
      throw new Error(`Failed to start firmware update: ${getErrorMessage(error)}`);
    }
  }

  async getFirmwareUpdateStatus(updateId: string): Promise<{
    status: 'downloading' | 'installing' | 'completed' | 'failed';
    progress: number;
    message: string;
  }> {
    try {
      const response = await this.client.get(`firmware/update-status/${updateId}`);
      return response.data.result;
    } catch (error: any) {
      throw new Error(`Failed to get firmware update status: ${getErrorMessage(error)}`);
    }
  }

  // Device Configuration Backup/Restore
  async backupConfiguration(deviceId: string): Promise<{ backupId: string; size: number }> {
    try {
      const response = await this.client.post(`device-management/backup/${deviceId}`);
      return response.data.result;
    } catch (error: any) {
      throw new Error(`Failed to backup configuration: ${getErrorMessage(error)}`);
    }
  }

  async restoreConfiguration(deviceId: string, backupId: string): Promise<void> {
    try {
      await this.client.post(`device-management/restore/${deviceId}`, { backupId });
    } catch (error: any) {
      throw new Error(`Failed to restore configuration: ${getErrorMessage(error)}`);
    }
  }

  async resetToFactory(deviceId: string): Promise<void> {
    try {
      await this.client.post(`device-management/factory-reset/${deviceId}`);
    } catch (error: any) {
      throw new Error(`Failed to reset device to factory settings: ${getErrorMessage(error)}`);
    }
  }

  // Utility Methods
  async rebootDevice(deviceId: string): Promise<void> {
    try {
      await this.client.post(`device-management/reboot/${deviceId}`);
    } catch (error: any) {
      throw new Error(`Failed to reboot device: ${getErrorMessage(error)}`);
    }
  }

  async testConnectivity(deviceId: string, targetHost: string = '8.8.8.8'): Promise<{
    success: boolean;
    latency: number;
    packetLoss: number;
  }> {
    try {
      const response = await this.client.post(`device-management/ping-test/${deviceId}`, { target: targetHost });
      return response.data.result;
    } catch (error: any) {
      throw new Error(`Failed to test connectivity: ${getErrorMessage(error)}`);
    }
  }

  async getSystemLogs(deviceId: string, params?: {
    level?: 'error' | 'warning' | 'info' | 'debug';
    from?: string;
    to?: string;
    limit?: number;
  }): Promise<Array<{
    timestamp: string;
    level: string;
    message: string;
    component: string;
  }>> {
    try {
      const response = await this.client.get(`device-management/logs/${deviceId}`, { params });
      return response.data.result;
    } catch (error: any) {
      throw new Error(`Failed to get system logs: ${getErrorMessage(error)}`);
    }
  }
}

// Export the API class and types
export default TPLinkTUACAPI;
export type {
  TUACConfig,
  DeviceInfo,
  NetworkDevice,
  WiFiConfig,
  GuestWiFiConfig,
  RemoteManagementConfig,
  QoSConfig,
  QoSRule,
  ClientDevice,
  NetworkStatistics,
};

// Configuration factory
export const createTUACConfig = (environment: 'production' | 'staging' | 'development'): TUACConfig => {
  const configs = {
    production: {
      domainName: process.env.REACT_APP_TUAC_PROD_DOMAIN || 'your-tuac-domain.com',
      apiKey: process.env.REACT_APP_TUAC_PROD_API_KEY,
      environment: 'production' as const,
    },
    staging: {
      domainName: process.env.REACT_APP_TUAC_STAGING_DOMAIN || 'staging-tuac.com',
      apiKey: process.env.REACT_APP_TUAC_STAGING_API_KEY,
      environment: 'staging' as const,
    },
    development: {
      domainName: process.env.REACT_APP_TUAC_DOMAIN || '',
      apiKey: process.env.REACT_APP_TUAC_DEV_API_KEY,
      environment: 'development' as const,
    },
  };

  return configs[environment];
};