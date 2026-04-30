/**
 * Unified Network Management API
 * Integrates Splynx, Mikrotik, and TPLink TUAC APIs into a single interface
 */

import SplynxAPI, { SplynxConfig, Customer, Service, RouterDevice as SplynxRouter } from './splynxAPI';
import MikrotikAPI, { MikrotikConfig, RouterInfo, Interface as MikrotikInterface } from './mikrotikAPI';
import TPLinkTUACAPI, { TUACConfig, DeviceInfo, NetworkDevice, WiFiConfig } from './tplinkTUACAPI';
import { getErrorMessage } from '../utils/errorHelpers';

// Unified Models
interface UnifiedDevice {
  id: string;
  name: string;
  type: 'mikrotik' | 'tplink' | 'splynx_managed';
  status: 'online' | 'offline' | 'warning' | 'error';
  ipAddress: string;
  location?: string;
  model?: string;
  firmwareVersion?: string;
  lastSeen: Date;
  capabilities: DeviceCapability[];
  managementInterface: 'mikrotik' | 'tuac' | 'splynx';
}

interface DeviceCapability {
  type: 'routing' | 'switching' | 'wireless' | 'firewall' | 'vpn' | 'hotspot' | 'dhcp' | 'qos';
  enabled: boolean;
  configuration?: any;
}

interface UnifiedCustomer {
  id: string;
  name: string;
  email: string;
  phone: string;
  address: string;
  status: 'active' | 'inactive' | 'suspended' | 'blocked';
  services: UnifiedService[];
  devices: CustomerDevice[];
  billingInfo: {
    balance: number;
    lastPayment?: Date;
    nextBilling?: Date;
    plan: string;
  };
  networkInfo: {
    ipAddress?: string;
    macAddress?: string;
    onlineStatus: boolean;
    lastSeen?: Date;
    bandwidth: {
      download: number;
      upload: number;
      usage: {
        current: number;
        limit?: number;
      };
    };
  };
}

interface UnifiedService {
  id: string;
  type: 'internet' | 'voice' | 'tv' | 'hosting' | 'domain';
  name: string;
  status: 'active' | 'suspended' | 'stopped';
  plan: string;
  price: number;
  startDate: Date;
  endDate?: Date;
  configuration: any;
}

interface CustomerDevice {
  macAddress: string;
  ipAddress?: string;
  hostname?: string;
  deviceType: 'computer' | 'phone' | 'tablet' | 'router' | 'other';
  connectionType: 'wired' | 'wireless';
  online: boolean;
  signalStrength?: number;
  bandwidth: {
    download: number;
    upload: number;
  };
  restrictions?: {
    blocked: boolean;
    timeRestrictions?: string[];
    bandwidthLimit?: number;
  };
}

interface NetworkTopology {
  devices: UnifiedDevice[];
  connections: NetworkConnection[];
  subnets: NetworkSubnet[];
  overview: {
    totalDevices: number;
    onlineDevices: number;
    totalCustomers: number;
    onlineCustomers: number;
    bandwidthUtilization: number;
  };
}

interface NetworkConnection {
  from: string;
  to: string;
  type: 'wired' | 'wireless' | 'vpn';
  quality: number;
  bandwidth: number;
  latency: number;
}

interface NetworkSubnet {
  network: string;
  mask: string;
  gateway: string;
  vlan?: number;
  description?: string;
  assignedIPs: number;
  totalIPs: number;
}

interface MonitoringData {
  timestamp: Date;
  metrics: {
    device: {
      id: string;
      cpuUsage: number;
      memoryUsage: number;
      temperature?: number;
      uptime: number;
    };
    network: {
      interfaces: Array<{
        name: string;
        rxBytes: number;
        txBytes: number;
        errors: number;
        utilization: number;
      }>;
      bandwidth: {
        download: number;
        upload: number;
        peak: number;
      };
    };
    customers: {
      total: number;
      online: number;
      topUsage: Array<{
        customerId: string;
        usage: number;
      }>;
    };
  };
}

class UnifiedNetworkAPI {
  private splynxAPI: SplynxAPI;
  private mikrotikAPIs: Map<string, MikrotikAPI> = new Map();
  private tuacAPIs: Map<string, TPLinkTUACAPI> = new Map();
  private deviceRegistry: Map<string, UnifiedDevice> = new Map();

  constructor(
    splynxConfig: SplynxConfig,
    mikrotikConfigs: MikrotikConfig[] = [],
    tuacConfigs: TUACConfig[] = []
  ) {
    this.splynxAPI = new SplynxAPI(splynxConfig);

    // Initialize Mikrotik API instances
    mikrotikConfigs.forEach((config, index) => {
      const api = new MikrotikAPI(config);
      this.mikrotikAPIs.set(`mikrotik_${index}`, api);
    });

    // Initialize TUAC API instances
    tuacConfigs.forEach((config, index) => {
      const api = new TPLinkTUACAPI(config);
      this.tuacAPIs.set(`tuac_${index}`, api);
    });
  }

  // Device Discovery and Registration
  async discoverAllDevices(): Promise<UnifiedDevice[]> {
    const devices: UnifiedDevice[] = [];

    try {
      // Discover Splynx-managed routers
      const splynxRouters = await this.splynxAPI.getRouters();
      for (const router of splynxRouters) {
        devices.push({
          id: `splynx_${router.id}`,
          name: router.title,
          type: 'splynx_managed',
          status: router.enabled ? 'online' : 'offline',
          ipAddress: router.ip,
          managementInterface: 'splynx',
          capabilities: this.inferCapabilities(router.type),
          lastSeen: new Date(),
        });
      }

      // Discover Mikrotik devices
      for (const [key, mikrotikAPI] of Array.from(this.mikrotikAPIs)) {
        try {
          const systemInfo = await mikrotikAPI.getSystemInfo();
          devices.push({
            id: `mikrotik_${key}`,
            name: systemInfo.identity,
            type: 'mikrotik',
            status: 'online',
            ipAddress: '', // Will be filled from configuration
            model: systemInfo.platform,
            firmwareVersion: systemInfo.version,
            managementInterface: 'mikrotik',
            capabilities: [
              { type: 'routing', enabled: true },
              { type: 'firewall', enabled: true },
              { type: 'dhcp', enabled: true },
              { type: 'wireless', enabled: true },
              { type: 'vpn', enabled: true },
              { type: 'hotspot', enabled: true },
              { type: 'qos', enabled: true },
            ],
            lastSeen: new Date(),
          });
        } catch (error: any) {
          console.warn(`Failed to discover Mikrotik device ${key}:`, error);
        }
      }

      // Discover TPLink TUAC devices
      for (const [key, tuacAPI] of Array.from(this.tuacAPIs)) {
        try {
          const discoveredDevices = await tuacAPI.discoverDevices();
          for (const device of discoveredDevices) {
            devices.push({
              id: `tuac_${device.deviceId}`,
              name: device.name,
              type: 'tplink',
              status: device.status === 'active' ? 'online' : 'offline',
              ipAddress: '', // May need to be retrieved separately
              model: device.model,
              location: device.location,
              managementInterface: 'tuac',
              capabilities: this.inferTUACCapabilities(device.type),
              lastSeen: new Date(),
            });
          }
        } catch (error: any) {
          console.warn(`Failed to discover TUAC devices ${key}:`, error);
        }
      }

      // Update device registry
      devices.forEach(device => {
        this.deviceRegistry.set(device.id, device);
      });

      return devices;
    } catch (error: any) {
      throw new Error(`Failed to discover devices: ${getErrorMessage(error)}`);
    }
  }

  // Customer Management
  async getUnifiedCustomers(params?: {
    search?: string;
    status?: string;
    limit?: number;
    offset?: number;
  }): Promise<UnifiedCustomer[]> {
    try {
      const splynxCustomers = await this.splynxAPI.getCustomers(params);
      const unifiedCustomers: UnifiedCustomer[] = [];

      for (const customer of splynxCustomers.data) {
        const services = await this.splynxAPI.getCustomerServices(customer.id!);
        const statistics = await this.splynxAPI.getCustomerStatistics(customer.id!);

        unifiedCustomers.push({
          id: customer.id!.toString(),
          name: customer.name,
          email: customer.email,
          phone: customer.phone,
          address: `${customer.street_1}, ${customer.city}, ${customer.zip_code}`,
          status: customer.status as any,
          services: services.map(service => ({
            id: service.id!.toString(),
            type: 'internet', // Infer from service data
            name: service.description || 'Internet Service',
            status: service.status as any,
            plan: service.tariff_price_id.toString(),
            price: 0, // Would need to fetch from tariff data
            startDate: new Date(service.start_date),
            endDate: service.end_date ? new Date(service.end_date) : undefined,
            configuration: {},
          })),
          devices: [], // Would need to correlate with network device data
          billingInfo: {
            balance: 0, // Would need to fetch from billing data
            plan: 'Unknown',
          },
          networkInfo: {
            onlineStatus: false, // Would need to check against active sessions
            bandwidth: {
              download: 0,
              upload: 0,
              usage: {
                current: 0,
              },
            },
          },
        });
      }

      return unifiedCustomers;
    } catch (error: any) {
      throw new Error(`Failed to get unified customers: ${getErrorMessage(error)}`);
    }
  }

  // Network Topology
  async getNetworkTopology(): Promise<NetworkTopology> {
    try {
      const devices = await this.discoverAllDevices();
      const connections: NetworkConnection[] = [];
      const subnets: NetworkSubnet[] = [];

      // Analyze connections between devices
      for (const device of devices) {
        if (device.managementInterface === 'mikrotik') {
          const mikrotikAPI = this.getMikrotikAPI(device.id);
          if (mikrotikAPI) {
            try {
              const routes = await mikrotikAPI.getRoutes();
              // Analyze routes to determine connections
              // This would require more sophisticated topology discovery
            } catch (error: any) {
              console.warn(`Failed to get routes from ${device.id}:`, error);
            }
          }
        }
      }

      return {
        devices,
        connections,
        subnets,
        overview: {
          totalDevices: devices.length,
          onlineDevices: devices.filter(d => d.status === 'online').length,
          totalCustomers: 0, // Would need to count from customer data
          onlineCustomers: 0, // Would need to count from active sessions
          bandwidthUtilization: 0, // Would need to calculate from monitoring data
        },
      };
    } catch (error: any) {
      throw new Error(`Failed to get network topology: ${getErrorMessage(error)}`);
    }
  }

  // Monitoring and Statistics
  async getMonitoringData(deviceId?: string): Promise<MonitoringData[]> {
    try {
      const monitoringData: MonitoringData[] = [];
      const devices = deviceId ? [this.deviceRegistry.get(deviceId)!] : Array.from(this.deviceRegistry.values());

      for (const device of devices) {
        if (!device) continue;

        let metrics: any = {
          device: {
            id: device.id,
            cpuUsage: 0,
            memoryUsage: 0,
            uptime: 0,
          },
          network: {
            interfaces: [],
            bandwidth: { download: 0, upload: 0, peak: 0 },
          },
          customers: {
            total: 0,
            online: 0,
            topUsage: [],
          },
        };

        if (device.managementInterface === 'mikrotik') {
          const mikrotikAPI = this.getMikrotikAPI(device.id);
          if (mikrotikAPI) {
            try {
              const systemInfo = await mikrotikAPI.getSystemInfo();
              const interfaces = await mikrotikAPI.getInterfaces();
              
              metrics.device = {
                id: device.id,
                cpuUsage: systemInfo.cpuLoad,
                memoryUsage: (1 - systemInfo.freeMemory / systemInfo.totalMemory) * 100,
                uptime: parseInt(systemInfo.uptime) || 0,
              };

              metrics.network.interfaces = interfaces.map(iface => ({
                name: iface.name,
                rxBytes: iface.rxBytes,
                txBytes: iface.txBytes,
                errors: iface.rxErrors + iface.txErrors,
                utilization: 0, // Would need to calculate based on interface speed
              }));
            } catch (error: any) {
              console.warn(`Failed to get Mikrotik monitoring data for ${device.id}:`, error);
            }
          }
        } else if (device.managementInterface === 'tuac') {
          const tuacAPI = this.getTUACAPI(device.id);
          if (tuacAPI) {
            try {
              const health = await tuacAPI.getDeviceHealth(device.id.replace('tuac_', ''));
              const stats = await tuacAPI.getNetworkStatistics(device.id.replace('tuac_', ''));
              
              metrics.device = {
                id: device.id,
                cpuUsage: health.cpuUsage,
                memoryUsage: health.memoryUsage,
                temperature: health.temperature,
                uptime: health.uptime,
              };

              metrics.network = {
                interfaces: [], // Would need to map from TUAC statistics
                bandwidth: {
                  download: stats.wan.downloadSpeed,
                  upload: stats.wan.uploadSpeed,
                  peak: Math.max(stats.wan.downloadSpeed, stats.wan.uploadSpeed),
                },
              };
            } catch (error: any) {
              console.warn(`Failed to get TUAC monitoring data for ${device.id}:`, error);
            }
          }
        }

        monitoringData.push({
          timestamp: new Date(),
          metrics,
        });
      }

      return monitoringData;
    } catch (error: any) {
      throw new Error(`Failed to get monitoring data: ${getErrorMessage(error)}`);
    }
  }

  // Service Provisioning
  async provisionInternetService(customerId: string, serviceConfig: {
    bandwidth: { download: number; upload: number };
    ipAddress?: string;
    vlan?: number;
    restrictions?: any;
  }): Promise<void> {
    try {
      // Start service in Splynx
      await this.splynxAPI.startInternetService(parseInt(customerId));

      // Configure bandwidth limits on relevant devices
      for (const [key, mikrotikAPI] of Array.from(this.mikrotikAPIs)) {
        try {
          // Add queue for bandwidth limiting
          await mikrotikAPI.addSimpleQueue({
            name: `customer_${customerId}`,
            target: serviceConfig.ipAddress || '',
            maxLimit: `${serviceConfig.bandwidth.upload}M/${serviceConfig.bandwidth.download}M`,
            comment: `Customer ${customerId} bandwidth limit`,
          });
        } catch (error: any) {
          console.warn(`Failed to configure bandwidth on ${key}:`, error);
        }
      }
    } catch (error: any) {
      throw new Error(`Failed to provision internet service: ${getErrorMessage(error)}`);
    }
  }

  async suspendCustomerService(customerId: string): Promise<void> {
    try {
      // Stop service in Splynx
      await this.splynxAPI.stopInternetService(parseInt(customerId));

      // Block customer traffic on network devices
      for (const [key, mikrotikAPI] of Array.from(this.mikrotikAPIs)) {
        try {
          await mikrotikAPI.addFirewallRule({
            chain: 'forward',
            action: 'drop',
            srcAddress: '', // Would need customer IP
            comment: `Suspended customer ${customerId}`,
          });
        } catch (error: any) {
          console.warn(`Failed to block customer on ${key}:`, error);
        }
      }
    } catch (error: any) {
      throw new Error(`Failed to suspend customer service: ${getErrorMessage(error)}`);
    }
  }

  // Helper Methods
  private inferCapabilities(deviceType: string): DeviceCapability[] {
    const capabilities: DeviceCapability[] = [
      { type: 'routing', enabled: true },
    ];

    if (deviceType.toLowerCase().includes('mikrotik')) {
      capabilities.push(
        { type: 'firewall', enabled: true },
        { type: 'dhcp', enabled: true },
        { type: 'wireless', enabled: true },
        { type: 'vpn', enabled: true },
        { type: 'hotspot', enabled: true },
        { type: 'qos', enabled: true }
      );
    }

    return capabilities;
  }

  private inferTUACCapabilities(deviceType: string): DeviceCapability[] {
    const capabilities: DeviceCapability[] = [];

    if (deviceType === 'router' || deviceType === 'access_point') {
      capabilities.push(
        { type: 'routing', enabled: true },
        { type: 'wireless', enabled: true },
        { type: 'dhcp', enabled: true },
        { type: 'firewall', enabled: true },
        { type: 'qos', enabled: true }
      );
    }

    return capabilities;
  }

  private getMikrotikAPI(deviceId: string): MikrotikAPI | undefined {
    // Extract the key from device ID and return corresponding API instance
    const key = deviceId.replace('mikrotik_', '');
    return this.mikrotikAPIs.get(`mikrotik_${key}`);
  }

  private getTUACAPI(deviceId: string): TPLinkTUACAPI | undefined {
    // Extract the key from device ID and return corresponding API instance
    const key = deviceId.replace('tuac_', '');
    return this.tuacAPIs.get(`tuac_${key}`);
  }

  // Configuration Management
  async getDeviceConfiguration(deviceId: string): Promise<any> {
    const device = this.deviceRegistry.get(deviceId);
    if (!device) {
      throw new Error(`Device ${deviceId} not found`);
    }

    switch (device.managementInterface) {
      case 'mikrotik':
        const mikrotikAPI = this.getMikrotikAPI(deviceId);
        if (mikrotikAPI) {
          return await mikrotikAPI.exportConfiguration();
        }
        break;
      case 'tuac':
        // TUAC doesn't have a direct export function, would need to gather various settings
        break;
      case 'splynx':
        // Configuration is managed through Splynx
        break;
    }

    throw new Error(`Configuration export not supported for ${device.managementInterface}`);
  }

  async backupDeviceConfiguration(deviceId: string): Promise<string> {
    const device = this.deviceRegistry.get(deviceId);
    if (!device) {
      throw new Error(`Device ${deviceId} not found`);
    }

    switch (device.managementInterface) {
      case 'mikrotik':
        const mikrotikAPI = this.getMikrotikAPI(deviceId);
        if (mikrotikAPI) {
          return await mikrotikAPI.exportConfiguration();
        }
        break;
      case 'tuac':
        const tuacAPI = this.getTUACAPI(deviceId);
        if (tuacAPI) {
          const backup = await tuacAPI.backupConfiguration(deviceId.replace('tuac_', ''));
          return backup.backupId;
        }
        break;
    }

    throw new Error(`Backup not supported for ${device.managementInterface}`);
  }
}

// Export the unified API and types
export default UnifiedNetworkAPI;
export type {
  UnifiedDevice,
  UnifiedCustomer,
  UnifiedService,
  CustomerDevice,
  NetworkTopology,
  NetworkConnection,
  NetworkSubnet,
  MonitoringData,
  DeviceCapability,
};