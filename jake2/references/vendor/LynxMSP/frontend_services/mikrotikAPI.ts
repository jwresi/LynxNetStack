/**
 * Mikrotik RouterOS API Integration Service
 * Implementation for Mikrotik router management via REST API and RouterOS API
 */

import axios, { AxiosInstance } from 'axios';
import { getErrorMessage } from '../utils/errorHelpers';

// Configuration
interface MikrotikConfig {
  host: string;
  port: number;
  username: string;
  password: string;
  useHttps: boolean;
  apiPort?: number; // For RouterOS API
  environment: 'production' | 'staging' | 'development';
}

// Core RouterOS Models
interface RouterInfo {
  identity: string;
  version: string;
  architecture: string;
  platform: string;
  uptime: string;
  cpuLoad: number;
  freeMemory: number;
  totalMemory: number;
  freeHddSpace: number;
  totalHddSpace: number;
  boardName: string;
  factoryFirmware: string;
  currentFirmware: string;
}

interface Interface {
  id: string;
  name: string;
  type: string;
  macAddress: string;
  mtu: number;
  running: boolean;
  enabled: boolean;
  comment?: string;
  rxBytes: number;
  txBytes: number;
  rxPackets: number;
  txPackets: number;
  rxErrors: number;
  txErrors: number;
  speed?: string;
  fullDuplex?: boolean;
}

interface IPAddress {
  id: string;
  address: string;
  network: string;
  interface: string;
  disabled: boolean;
  dynamic: boolean;
  comment?: string;
}

interface Route {
  id: string;
  dstAddress: string;
  gateway: string;
  gatewayStatus: string;
  distance: number;
  scope: number;
  targetScope: number;
  comment?: string;
  dynamic: boolean;
  active: boolean;
  static: boolean;
  interface?: string;
  routingMark?: string;
}

interface DHCPLease {
  id: string;
  address: string;
  macAddress: string;
  clientId?: string;
  addressLists?: string;
  server: string;
  dhcpOption?: string;
  status: string;
  expiresAfter: string;
  lastSeen: string;
  activeAddress?: string;
  activeClientId?: string;
  activeMacAddress?: string;
  activeServer?: string;
  hostname?: string;
  comment?: string;
  dynamic?: boolean;
}

interface FirewallRule {
  id: string;
  chain: string;
  action: string;
  srcAddress?: string;
  dstAddress?: string;
  srcPort?: string;
  dstPort?: string;
  protocol?: string;
  interface?: string;
  outInterface?: string;
  comment?: string;
  disabled: boolean;
  dynamic: boolean;
  invalid: boolean;
  bytes: number;
  packets: number;
}

interface WirelessInterface {
  id: string;
  name: string;
  radioName: string;
  mode: string;
  ssid: string;
  frequency: number;
  band: string;
  channel: number;
  channelWidth: string;
  countryCode: string;
  antennaGain: number;
  txPower: number;
  security: string;
  wpaPreSharedKey?: string;
  wpa2PreSharedKey?: string;
  disabled: boolean;
  running: boolean;
  clientCount: number;
  noise: number;
  overallCcq: number;
  comment?: string;
}

interface WirelessRegistration {
  id: string;
  interface: string;
  macAddress: string;
  signalStrength: number;
  signalToNoise: number;
  ccq: number;
  txRate: string;
  rxRate: string;
  uptime: string;
  bytes: number;
  packets: number;
  frames: number;
  hwFrames: number;
  framesBytes: number;
  hwFramesBytes: number;
  ackTimeout: number;
  ampdus: number;
  ampduBytes: number;
  distance: number;
  comment?: string;
}

interface PPPSecret {
  id: string;
  name: string;
  password: string;
  service: string;
  callerIdMask?: string;
  profile: string;
  localAddress?: string;
  remoteAddress?: string;
  routes?: string;
  disabled: boolean;
  comment?: string;
}

interface PPPActive {
  id: string;
  name: string;
  service: string;
  callerIdNum?: string;
  address: string;
  uptime: string;
  encoding?: string;
  sessionId?: string;
  limitBytesIn?: number;
  limitBytesOut?: number;
  radius?: boolean;
  comment?: string;
}

interface QueueSimple {
  id: string;
  name: string;
  target: string;
  interface?: string;
  parent?: string;
  maxLimit: string;
  burstLimit?: string;
  burstThreshold?: string;
  burstTime?: string;
  bucketSize?: string;
  priority: number;
  limitAt?: string;
  disabled: boolean;
  invalid: boolean;
  dynamic: boolean;
  bytes: number;
  packets: number;
  queued: number;
  dropped: number;
  rate: string;
  packetRate: string;
  queuedBytes: number;
  droppedBytes: number;
  comment?: string;
}

interface UserManager {
  id: string;
  customer: string;
  username: string;
  password: string;
  sharedUsers: number;
  disabled: boolean;
  wirelessProtocol?: string;
  framed?: boolean;
  comment?: string;
}

interface HotspotUser {
  id: string;
  server: string;
  name: string;
  password: string;
  profile: string;
  disabled: boolean;
  comment?: string;
  bytes: number;
  packets: number;
  uptime: string;
}

class MikrotikAPI {
  private client: AxiosInstance;
  private config: MikrotikConfig;

  constructor(config: MikrotikConfig) {
    this.config = config;
    const protocol = config.useHttps ? 'https' : 'http';
    
    this.client = axios.create({
      baseURL: `${protocol}://${config.host}:${config.port}/rest/`,
      timeout: 30000,
      auth: {
        username: config.username,
        password: config.password,
      },
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
    });

    // Response interceptor for RouterOS API format handling
    this.client.interceptors.response.use(
      (response) => {
        // RouterOS API returns arrays even for single items
        if (Array.isArray(response.data) && response.data.length === 1) {
          return { ...response, data: response.data[0] };
        }
        return response;
      },
      (error) => {
        console.error('Mikrotik API Request Failed:', error);
        return Promise.reject(error);
      }
    );
  }

  // System Information
  async getSystemInfo(): Promise<RouterInfo> {
    try {
      const [resource, routerboard, identity] = await Promise.all([
        this.client.get('system/resource'),
        this.client.get('system/routerboard'),
        this.client.get('system/identity'),
      ]);

      return {
        identity: identity.data.name,
        version: resource.data.version,
        architecture: resource.data.architecture,
        platform: resource.data.platform,
        uptime: resource.data.uptime,
        cpuLoad: parseFloat(resource.data['cpu-load']),
        freeMemory: parseInt(resource.data['free-memory']),
        totalMemory: parseInt(resource.data['total-memory']),
        freeHddSpace: parseInt(resource.data['free-hdd-space']),
        totalHddSpace: parseInt(resource.data['total-hdd-space']),
        boardName: routerboard.data.model,
        factoryFirmware: routerboard.data['factory-firmware'],
        currentFirmware: routerboard.data['current-firmware'],
      };
    } catch (error: any) {
      const message = error instanceof Error ? getErrorMessage(error) : 'Unknown error';
      throw new Error(`Failed to get system info: ${message}`);
    }
  }

  async getSystemHealth(): Promise<{
    temperature: number;
    voltage: number;
    current: number;
    powerConsumption: number;
    fanSpeed: number[];
  }> {
    try {
      const response = await this.client.get('system/health');
      return {
        temperature: parseFloat(response.data.temperature) || 0,
        voltage: parseFloat(response.data.voltage) || 0,
        current: parseFloat(response.data.current) || 0,
        powerConsumption: parseFloat(response.data['power-consumption']) || 0,
        fanSpeed: response.data['fan-speed'] ? [parseFloat(response.data['fan-speed'])] : [],
      };
    } catch (error: any) {
      throw new Error(`Failed to get system health: ${getErrorMessage(error)}`);
    }
  }

  // Interface Management
  async getInterfaces(): Promise<Interface[]> {
    try {
      const response = await this.client.get('interface');
      return Array.isArray(response.data) ? response.data : [response.data];
    } catch (error: any) {
      throw new Error(`Failed to get interfaces: ${getErrorMessage(error)}`);
    }
  }

  async getInterface(id: string): Promise<Interface> {
    try {
      const response = await this.client.get(`interface/${id}`);
      return response.data;
    } catch (error: any) {
      throw new Error(`Failed to get interface: ${getErrorMessage(error)}`);
    }
  }

  async enableInterface(id: string): Promise<void> {
    try {
      await this.client.patch(`interface/${id}`, { disabled: false });
    } catch (error: any) {
      throw new Error(`Failed to enable interface: ${getErrorMessage(error)}`);
    }
  }

  async disableInterface(id: string): Promise<void> {
    try {
      await this.client.patch(`interface/${id}`, { disabled: true });
    } catch (error: any) {
      throw new Error(`Failed to disable interface: ${getErrorMessage(error)}`);
    }
  }

  // IP Address Management
  async getIPAddresses(): Promise<IPAddress[]> {
    try {
      const response = await this.client.get('ip/address');
      return Array.isArray(response.data) ? response.data : [response.data];
    } catch (error: any) {
      throw new Error(`Failed to get IP addresses: ${getErrorMessage(error)}`);
    }
  }

  async addIPAddress(address: string, networkInterface: string, comment?: string): Promise<IPAddress> {
    try {
      const response = await this.client.put('ip/address', {
        address,
        interface: networkInterface,
        comment,
      });
      return response.data;
    } catch (error: any) {
      throw new Error(`Failed to add IP address: ${getErrorMessage(error)}`);
    }
  }

  async removeIPAddress(id: string): Promise<void> {
    try {
      await this.client.delete(`ip/address/${id}`);
    } catch (error: any) {
      throw new Error(`Failed to remove IP address: ${getErrorMessage(error)}`);
    }
  }

  // Routing Management
  async getRoutes(): Promise<Route[]> {
    try {
      const response = await this.client.get('ip/route');
      return Array.isArray(response.data) ? response.data : [response.data];
    } catch (error: any) {
      throw new Error(`Failed to get routes: ${getErrorMessage(error)}`);
    }
  }

  async addRoute(dstAddress: string, gateway: string, comment?: string): Promise<Route> {
    try {
      const response = await this.client.put('ip/route', {
        'dst-address': dstAddress,
        gateway,
        comment,
      });
      return response.data;
    } catch (error: any) {
      throw new Error(`Failed to add route: ${getErrorMessage(error)}`);
    }
  }

  async removeRoute(id: string): Promise<void> {
    try {
      await this.client.delete(`ip/route/${id}`);
    } catch (error: any) {
      throw new Error(`Failed to remove route: ${getErrorMessage(error)}`);
    }
  }

  // DHCP Management
  async getDHCPLeases(): Promise<DHCPLease[]> {
    try {
      const response = await this.client.get('ip/dhcp-server/lease');
      return Array.isArray(response.data) ? response.data : [response.data];
    } catch (error: any) {
      throw new Error(`Failed to get DHCP leases: ${getErrorMessage(error)}`);
    }
  }

  async addDHCPReservation(address: string, macAddress: string, comment?: string): Promise<DHCPLease> {
    try {
      const response = await this.client.put('ip/dhcp-server/lease', {
        address,
        'mac-address': macAddress,
        comment,
      });
      return response.data;
    } catch (error: any) {
      throw new Error(`Failed to add DHCP reservation: ${getErrorMessage(error)}`);
    }
  }

  async removeDHCPLease(id: string): Promise<void> {
    try {
      await this.client.delete(`ip/dhcp-server/lease/${id}`);
    } catch (error: any) {
      throw new Error(`Failed to remove DHCP lease: ${getErrorMessage(error)}`);
    }
  }

  // Firewall Management
  async getFirewallRules(chain?: string): Promise<FirewallRule[]> {
    try {
      const response = await this.client.get('ip/firewall/filter');
      let rules = Array.isArray(response.data) ? response.data : [response.data];
      
      if (chain) {
        rules = rules.filter(rule => rule.chain === chain);
      }
      
      return rules;
    } catch (error: any) {
      throw new Error(`Failed to get firewall rules: ${getErrorMessage(error)}`);
    }
  }

  async addFirewallRule(rule: Partial<FirewallRule>): Promise<FirewallRule> {
    try {
      const response = await this.client.put('ip/firewall/filter', {
        chain: rule.chain,
        action: rule.action,
        'src-address': rule.srcAddress,
        'dst-address': rule.dstAddress,
        'src-port': rule.srcPort,
        'dst-port': rule.dstPort,
        protocol: rule.protocol,
        'in-interface': rule.interface,
        'out-interface': rule.outInterface,
        comment: rule.comment,
      });
      return response.data;
    } catch (error: any) {
      throw new Error(`Failed to add firewall rule: ${getErrorMessage(error)}`);
    }
  }

  async removeFirewallRule(id: string): Promise<void> {
    try {
      await this.client.delete(`ip/firewall/filter/${id}`);
    } catch (error: any) {
      throw new Error(`Failed to remove firewall rule: ${getErrorMessage(error)}`);
    }
  }

  // Wireless Management
  async getWirelessInterfaces(): Promise<WirelessInterface[]> {
    try {
      const response = await this.client.get('interface/wireless');
      return Array.isArray(response.data) ? response.data : [response.data];
    } catch (error: any) {
      throw new Error(`Failed to get wireless interfaces: ${getErrorMessage(error)}`);
    }
  }

  async getWirelessRegistrations(): Promise<WirelessRegistration[]> {
    try {
      const response = await this.client.get('interface/wireless/registration-table');
      return Array.isArray(response.data) ? response.data : [response.data];
    } catch (error: any) {
      throw new Error(`Failed to get wireless registrations: ${getErrorMessage(error)}`);
    }
  }

  async scanWireless(interfaceName: string, duration: number = 5): Promise<any[]> {
    try {
      await this.client.post(`interface/wireless/scan`, {
        interface: interfaceName,
        duration,
      });
      
      // Wait for scan to complete
      await new Promise(resolve => setTimeout(resolve, duration * 1000));
      
      const response = await this.client.get('interface/wireless/scan');
      return Array.isArray(response.data) ? response.data : [response.data];
    } catch (error: any) {
      throw new Error(`Failed to scan wireless: ${getErrorMessage(error)}`);
    }
  }

  // PPP Management (PPPoE, VPN, etc.)
  async getPPPSecrets(): Promise<PPPSecret[]> {
    try {
      const response = await this.client.get('ppp/secret');
      return Array.isArray(response.data) ? response.data : [response.data];
    } catch (error: any) {
      throw new Error(`Failed to get PPP secrets: ${getErrorMessage(error)}`);
    }
  }

  async getPPPActive(): Promise<PPPActive[]> {
    try {
      const response = await this.client.get('ppp/active');
      return Array.isArray(response.data) ? response.data : [response.data];
    } catch (error: any) {
      throw new Error(`Failed to get PPP active sessions: ${getErrorMessage(error)}`);
    }
  }

  async addPPPSecret(secret: Partial<PPPSecret>): Promise<PPPSecret> {
    try {
      const response = await this.client.put('ppp/secret', {
        name: secret.name,
        password: secret.password,
        service: secret.service,
        profile: secret.profile,
        'local-address': secret.localAddress,
        'remote-address': secret.remoteAddress,
        comment: secret.comment,
      });
      return response.data;
    } catch (error: any) {
      throw new Error(`Failed to add PPP secret: ${getErrorMessage(error)}`);
    }
  }

  async removePPPSecret(id: string): Promise<void> {
    try {
      await this.client.delete(`ppp/secret/${id}`);
    } catch (error: any) {
      throw new Error(`Failed to remove PPP secret: ${getErrorMessage(error)}`);
    }
  }

  // Queue Management (QoS)
  async getSimpleQueues(): Promise<QueueSimple[]> {
    try {
      const response = await this.client.get('queue/simple');
      return Array.isArray(response.data) ? response.data : [response.data];
    } catch (error: any) {
      throw new Error(`Failed to get simple queues: ${getErrorMessage(error)}`);
    }
  }

  async addSimpleQueue(queue: Partial<QueueSimple>): Promise<QueueSimple> {
    try {
      const response = await this.client.put('queue/simple', {
        name: queue.name,
        target: queue.target,
        'max-limit': queue.maxLimit,
        'burst-limit': queue.burstLimit,
        'burst-threshold': queue.burstThreshold,
        'burst-time': queue.burstTime,
        priority: queue.priority,
        comment: queue.comment,
      });
      return response.data;
    } catch (error: any) {
      throw new Error(`Failed to add simple queue: ${getErrorMessage(error)}`);
    }
  }

  async removeSimpleQueue(id: string): Promise<void> {
    try {
      await this.client.delete(`queue/simple/${id}`);
    } catch (error: any) {
      throw new Error(`Failed to remove simple queue: ${getErrorMessage(error)}`);
    }
  }

  // User Manager Integration
  async getUserManagerUsers(): Promise<UserManager[]> {
    try {
      const response = await this.client.get('user-manager/user');
      return Array.isArray(response.data) ? response.data : [response.data];
    } catch (error: any) {
      throw new Error(`Failed to get User Manager users: ${getErrorMessage(error)}`);
    }
  }

  async addUserManagerUser(user: Partial<UserManager>): Promise<UserManager> {
    try {
      const response = await this.client.put('user-manager/user', {
        customer: user.customer,
        username: user.username,
        password: user.password,
        'shared-users': user.sharedUsers,
        comment: user.comment,
      });
      return response.data;
    } catch (error: any) {
      throw new Error(`Failed to add User Manager user: ${getErrorMessage(error)}`);
    }
  }

  // Hotspot Management
  async getHotspotUsers(): Promise<HotspotUser[]> {
    try {
      const response = await this.client.get('ip/hotspot/user');
      return Array.isArray(response.data) ? response.data : [response.data];
    } catch (error: any) {
      throw new Error(`Failed to get hotspot users: ${getErrorMessage(error)}`);
    }
  }

  async addHotspotUser(user: Partial<HotspotUser>): Promise<HotspotUser> {
    try {
      const response = await this.client.put('ip/hotspot/user', {
        server: user.server,
        name: user.name,
        password: user.password,
        profile: user.profile,
        comment: user.comment,
      });
      return response.data;
    } catch (error: any) {
      throw new Error(`Failed to add hotspot user: ${getErrorMessage(error)}`);
    }
  }

  // Monitoring and Statistics
  async getInterfaceTraffic(interfaceName?: string): Promise<any[]> {
    try {
      const params = interfaceName ? { interface: interfaceName } : {};
      const response = await this.client.get('interface/monitor-traffic', { params });
      return Array.isArray(response.data) ? response.data : [response.data];
    } catch (error: any) {
      throw new Error(`Failed to get interface traffic: ${getErrorMessage(error)}`);
    }
  }

  async getCPUUsage(): Promise<number> {
    try {
      const response = await this.client.get('system/resource/cpu');
      return parseFloat(response.data.load);
    } catch (error: any) {
      throw new Error(`Failed to get CPU usage: ${getErrorMessage(error)}`);
    }
  }

  // Backup and Configuration
  async exportConfiguration(): Promise<string> {
    try {
      const response = await this.client.post('export');
      return response.data;
    } catch (error: any) {
      throw new Error(`Failed to export configuration: ${getErrorMessage(error)}`);
    }
  }

  async importConfiguration(config: string): Promise<void> {
    try {
      await this.client.post('import', { file: config });
    } catch (error: any) {
      throw new Error(`Failed to import configuration: ${getErrorMessage(error)}`);
    }
  }

  async reboot(): Promise<void> {
    try {
      await this.client.post('system/reboot');
    } catch (error: any) {
      throw new Error(`Failed to reboot: ${getErrorMessage(error)}`);
    }
  }

  async shutdown(): Promise<void> {
    try {
      await this.client.post('system/shutdown');
    } catch (error: any) {
      throw new Error(`Failed to shutdown: ${getErrorMessage(error)}`);
    }
  }

  // Ping and Tools
  async ping(host: string, count: number = 4): Promise<any> {
    try {
      const response = await this.client.post('ping', {
        address: host,
        count,
      });
      return response.data;
    } catch (error: any) {
      throw new Error(`Failed to ping: ${getErrorMessage(error)}`);
    }
  }

  async traceroute(host: string): Promise<any> {
    try {
      const response = await this.client.post('tool/traceroute', {
        address: host,
      });
      return response.data;
    } catch (error: any) {
      throw new Error(`Failed to traceroute: ${getErrorMessage(error)}`);
    }
  }
}

// Export the API class and types
export default MikrotikAPI;
export type {
  MikrotikConfig,
  RouterInfo,
  Interface,
  IPAddress,
  Route,
  DHCPLease,
  FirewallRule,
  WirelessInterface,
  WirelessRegistration,
  PPPSecret,
  PPPActive,
  QueueSimple,
  UserManager,
  HotspotUser,
};

// Configuration factory
export const createMikrotikConfig = (environment: 'production' | 'staging' | 'development'): MikrotikConfig => {
  const configs = {
    production: {
      host: process.env.REACT_APP_MIKROTIK_PROD_HOST || '',
      port: parseInt(process.env.REACT_APP_MIKROTIK_PROD_PORT || '80'),
      username: process.env.REACT_APP_MIKROTIK_PROD_USERNAME || '',
      password: process.env.REACT_APP_MIKROTIK_PROD_PASSWORD || '',
      useHttps: process.env.REACT_APP_MIKROTIK_PROD_HTTPS === 'true',
      apiPort: parseInt(process.env.REACT_APP_MIKROTIK_PROD_API_PORT || '8728'),
      environment: 'production' as const,
    },
    staging: {
      host: process.env.REACT_APP_MIKROTIK_STAGING_HOST || '',
      port: parseInt(process.env.REACT_APP_MIKROTIK_STAGING_PORT || '80'),
      username: process.env.REACT_APP_MIKROTIK_STAGING_USERNAME || '',
      password: process.env.REACT_APP_MIKROTIK_STAGING_PASSWORD || '',
      useHttps: process.env.REACT_APP_MIKROTIK_STAGING_HTTPS === 'true',
      apiPort: parseInt(process.env.REACT_APP_MIKROTIK_STAGING_API_PORT || '8728'),
      environment: 'staging' as const,
    },
    development: {
      host: process.env.REACT_APP_MIKROTIK_HOST || '',
      port: parseInt(process.env.REACT_APP_MIKROTIK_DEV_PORT || '80'),
      username: process.env.REACT_APP_MIKROTIK_DEV_USERNAME || 'admin',
      password: process.env.REACT_APP_MIKROTIK_DEV_PASSWORD || '',
      useHttps: false,
      apiPort: 8728,
      environment: 'development' as const,
    },
  };

  return configs[environment];
};