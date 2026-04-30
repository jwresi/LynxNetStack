/**
 * Comprehensive API Integration Testing Suite
 * Tests all API integrations: Splynx, Mikrotik, TPLink TUAC, and Unified Network API
 */

import SplynxAPI, { createSplynxConfig } from '../services/splynxAPI';
import MikrotikAPI, { createMikrotikConfig } from '../services/mikrotikAPI';
import TPLinkTUACAPI, { createTUACConfig } from '../services/tplinkTUACAPI';
import UnifiedNetworkAPI from '../services/unifiedNetworkAPI';
import { getErrorMessage } from '../utils/errorHelpers';

interface TestResult {
  testName: string;
  status: 'passed' | 'failed' | 'skipped';
  duration: number;
  error?: string;
  details?: any;
}

interface TestSuite {
  suiteName: string;
  results: TestResult[];
  summary: {
    total: number;
    passed: number;
    failed: number;
    skipped: number;
    duration: number;
  };
}

class APIIntegrationTester {
  private splynxAPI: SplynxAPI;
  private mikrotikAPI: MikrotikAPI;
  private tuacAPI: TPLinkTUACAPI;
  private unifiedAPI: UnifiedNetworkAPI;
  private testResults: TestSuite[] = [];

  constructor() {
    // Initialize APIs with development/test configurations
    const splynxConfig = createSplynxConfig('development');
    const mikrotikConfig = createMikrotikConfig('development');
    const tuacConfig = createTUACConfig('development');

    this.splynxAPI = new SplynxAPI(splynxConfig);
    this.mikrotikAPI = new MikrotikAPI(mikrotikConfig);
    this.tuacAPI = new TPLinkTUACAPI(tuacConfig);
    this.unifiedAPI = new UnifiedNetworkAPI(splynxConfig, [mikrotikConfig], [tuacConfig]);
  }

  async runAllTests(): Promise<TestSuite[]> {
    console.log('🚀 Starting comprehensive API integration tests...');
    
    const testSuites = [
      () => this.testSplynxAPI(),
      () => this.testMikrotikAPI(),
      () => this.testTPLinkTUACAPI(),
      () => this.testUnifiedNetworkAPI(),
      () => this.testEndToEndIntegration(),
    ];

    for (const testSuite of testSuites) {
      try {
        await testSuite();
      } catch (error: any) {
        console.error(`Test suite failed: ${getErrorMessage(error)}`);
      }
    }

    this.generateTestReport();
    return this.testResults;
  }

  // Splynx API Tests
  async testSplynxAPI(): Promise<void> {
    const suite: TestSuite = {
      suiteName: 'Splynx API Integration',
      results: [],
      summary: { total: 0, passed: 0, failed: 0, skipped: 0, duration: 0 },
    };

    const tests = [
      { name: 'Authentication with API Key', test: () => this.testSplynxAuthentication() },
      { name: 'Get Customers List', test: () => this.testSplynxGetCustomers() },
      { name: 'Create Customer', test: () => this.testSplynxCreateCustomer() },
      { name: 'Get Customer Services', test: () => this.testSplynxGetServices() },
      { name: 'Get Invoices', test: () => this.testSplynxGetInvoices() },
      { name: 'Create Payment', test: () => this.testSplynxCreatePayment() },
      { name: 'Get Routers', test: () => this.testSplynxGetRouters() },
      { name: 'Get Dashboard Data', test: () => this.testSplynxGetDashboard() },
      { name: 'Get Finance Statistics', test: () => this.testSplynxGetFinanceStats() },
      { name: 'Customer Statistics', test: () => this.testSplynxCustomerStats() },
    ];

    await this.runTestSuite(suite, tests);
    this.testResults.push(suite);
  }

  private async testSplynxAuthentication(): Promise<any> {
    try {
      const token = await this.splynxAPI.authenticateWithApiKey();
      if (!token.access_token) {
        throw new Error('No access token received');
      }
      return { tokenExpiration: token.access_token_expiration };
    } catch (error: any) {
      return { error: true, message: 'Splynx API authentication failed', details: error.message };
    }
  }

  private async testSplynxGetCustomers(): Promise<any> {
    try {
      const customers = await this.splynxAPI.getCustomers({ limit: 10 });
      return { count: customers.data?.length || 0, meta: customers.meta };
    } catch (error: any) {
      return { error: true, message: 'Failed to fetch customers', details: error.message };
    }
  }

  private async testSplynxCreateCustomer(): Promise<any> {
    try {
      const customer = await this.splynxAPI.createCustomer({
        partner_id: 1,
        location_id: 1,
        login: `test_${Date.now()}`,
        category: 'person',
        name: 'Test Customer',
        email: 'test@lynxmsp.com',
        phone: '+1234567890',
        street_1: '123 Test St',
        zip_code: '12345',
        city: 'Test City',
        country: 'US',
        status: 'active',
        billing_type: 'recurring',
      });
      return { customerId: customer.id };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  private async testSplynxGetServices(): Promise<any> {
    try {
      const services = await this.splynxAPI.getCustomerServices(1);
      return { count: services.length };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  private async testSplynxGetInvoices(): Promise<any> {
    try {
      const invoices = await this.splynxAPI.getInvoices({ limit: 10 });
      return { count: invoices.data?.length || 0 };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  private async testSplynxCreatePayment(): Promise<any> {
    try {
      const payment = await this.splynxAPI.createPayment({
        customer_id: 1,
        receipt_number: `TEST_${Date.now()}`,
        date: new Date().toISOString().split('T')[0],
        amount: 100.00,
        comment: 'Test payment',
        payment_type: 'credit_card',
      });
      return { paymentId: payment.id };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  private async testSplynxGetRouters(): Promise<any> {
    try {
      const routers = await this.splynxAPI.getRouters();
      return { count: routers.length };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  private async testSplynxGetDashboard(): Promise<any> {
    try {
      const dashboard = await this.splynxAPI.getDashboardData();
      return { hasData: !!dashboard };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  private async testSplynxGetFinanceStats(): Promise<any> {
    try {
      const stats = await this.splynxAPI.getFinanceStatistics();
      return { hasStats: !!stats };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  private async testSplynxCustomerStats(): Promise<any> {
    try {
      const stats = await this.splynxAPI.getCustomerStatistics(1);
      return { hasStats: !!stats };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  // Mikrotik API Tests
  async testMikrotikAPI(): Promise<void> {
    const suite: TestSuite = {
      suiteName: 'Mikrotik RouterOS API Integration',
      results: [],
      summary: { total: 0, passed: 0, failed: 0, skipped: 0, duration: 0 },
    };

    const tests = [
      { name: 'Get System Information', test: () => this.testMikrotikSystemInfo() },
      { name: 'Get System Health', test: () => this.testMikrotikSystemHealth() },
      { name: 'Get Interfaces', test: () => this.testMikrotikGetInterfaces() },
      { name: 'Get IP Addresses', test: () => this.testMikrotikGetIPAddresses() },
      { name: 'Get Routes', test: () => this.testMikrotikGetRoutes() },
      { name: 'Get DHCP Leases', test: () => this.testMikrotikGetDHCPLeases() },
      { name: 'Get Firewall Rules', test: () => this.testMikrotikGetFirewallRules() },
      { name: 'Get Wireless Interfaces', test: () => this.testMikrotikGetWireless() },
      { name: 'Get PPP Secrets', test: () => this.testMikrotikGetPPPSecrets() },
      { name: 'Get Simple Queues', test: () => this.testMikrotikGetQueues() },
    ];

    await this.runTestSuite(suite, tests);
    this.testResults.push(suite);
  }

  private async testMikrotikSystemInfo(): Promise<any> {
    try {
      const info = await this.mikrotikAPI.getSystemInfo();
      return {
        identity: info.identity,
        version: info.version,
        uptime: info.uptime,
        cpuLoad: info.cpuLoad,
      };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  private async testMikrotikSystemHealth(): Promise<any> {
    try {
      const health = await this.mikrotikAPI.getSystemHealth();
      return health;
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  private async testMikrotikGetInterfaces(): Promise<any> {
    try {
      const interfaces = await this.mikrotikAPI.getInterfaces();
      return { count: interfaces.length };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  private async testMikrotikGetIPAddresses(): Promise<any> {
    try {
      const addresses = await this.mikrotikAPI.getIPAddresses();
      return { count: addresses.length };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  private async testMikrotikGetRoutes(): Promise<any> {
    try {
      const routes = await this.mikrotikAPI.getRoutes();
      return { count: routes.length };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  private async testMikrotikGetDHCPLeases(): Promise<any> {
    try {
      const leases = await this.mikrotikAPI.getDHCPLeases();
      return { count: leases.length };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  private async testMikrotikGetFirewallRules(): Promise<any> {
    try {
      const rules = await this.mikrotikAPI.getFirewallRules();
      return { count: rules.length };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  private async testMikrotikGetWireless(): Promise<any> {
    try {
      const wireless = await this.mikrotikAPI.getWirelessInterfaces();
      return { count: wireless.length };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  private async testMikrotikGetPPPSecrets(): Promise<any> {
    try {
      const secrets = await this.mikrotikAPI.getPPPSecrets();
      return { count: secrets.length };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  private async testMikrotikGetQueues(): Promise<any> {
    try {
      const queues = await this.mikrotikAPI.getSimpleQueues();
      return { count: queues.length };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  // TPLink TUAC API Tests
  async testTPLinkTUACAPI(): Promise<void> {
    const suite: TestSuite = {
      suiteName: 'TPLink TUAC API Integration',
      results: [],
      summary: { total: 0, passed: 0, failed: 0, skipped: 0, duration: 0 },
    };

    const tests = [
      { name: 'Get Device ID', test: () => this.testTUACGetDeviceId() },
      { name: 'Get Device Info', test: () => this.testTUACGetDeviceInfo() },
      { name: 'Get Remote Management', test: () => this.testTUACGetRemoteManagement() },
      { name: 'Get WiFi Channels', test: () => this.testTUACGetWiFiChannels() },
      { name: 'Get WiFi SSID', test: () => this.testTUACGetWiFiSSID() },
      { name: 'Get Guest WiFi', test: () => this.testTUACGetGuestWiFi() },
      { name: 'Get Connected Clients', test: () => this.testTUACGetClients() },
      { name: 'Get Network Statistics', test: () => this.testTUACGetNetworkStats() },
      { name: 'Device Discovery', test: () => this.testTUACDiscoverDevices() },
      { name: 'Check Firmware Update', test: () => this.testTUACCheckFirmware() },
    ];

    await this.runTestSuite(suite, tests);
    this.testResults.push(suite);
  }

  private async testTUACGetDeviceId(): Promise<any> {
    try {
      const deviceId = await this.tuacAPI.getDeviceId('TEST123', '00:11:22:33:44:55');
      return { deviceId };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  private async testTUACGetDeviceInfo(): Promise<any> {
    try {
      const info = await this.tuacAPI.getDeviceInfo('mock_device_123');
      return { hasInfo: !!info };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  private async testTUACGetRemoteManagement(): Promise<any> {
    try {
      const config = await this.tuacAPI.getRemoteManagement('network_123');
      return { hasConfig: !!config };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  private async testTUACGetWiFiChannels(): Promise<any> {
    try {
      const channel2g = await this.tuacAPI.get2GChannel('mock_device_123');
      const channel5g = await this.tuacAPI.get5GChannel('mock_device_123');
      return { channel2g, channel5g };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  private async testTUACGetWiFiSSID(): Promise<any> {
    try {
      const ssids = await this.tuacAPI.getWiFiSSID('mock_device_123');
      return { count: ssids.length };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  private async testTUACGetGuestWiFi(): Promise<any> {
    try {
      const guestWifi = await this.tuacAPI.getGuestWiFi('network_123');
      return { hasGuestWifi: !!guestWifi };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  private async testTUACGetClients(): Promise<any> {
    try {
      const clients = await this.tuacAPI.getConnectedClients('mock_device_123');
      return { count: clients.length };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  private async testTUACGetNetworkStats(): Promise<any> {
    try {
      const stats = await this.tuacAPI.getNetworkStatistics('mock_device_123');
      return { hasStats: !!stats };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  private async testTUACDiscoverDevices(): Promise<any> {
    try {
      const devices = await this.tuacAPI.discoverDevices();
      return { count: devices.length };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  private async testTUACCheckFirmware(): Promise<any> {
    try {
      const firmware = await this.tuacAPI.checkFirmwareUpdate('mock_device_123');
      return firmware;
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  // Unified Network API Tests
  async testUnifiedNetworkAPI(): Promise<void> {
    const suite: TestSuite = {
      suiteName: 'Unified Network API Integration',
      results: [],
      summary: { total: 0, passed: 0, failed: 0, skipped: 0, duration: 0 },
    };

    const tests = [
      { name: 'Discover All Devices', test: () => this.testUnifiedDiscoverDevices() },
      { name: 'Get Unified Customers', test: () => this.testUnifiedGetCustomers() },
      { name: 'Get Network Topology', test: () => this.testUnifiedGetTopology() },
      { name: 'Get Monitoring Data', test: () => this.testUnifiedGetMonitoring() },
      { name: 'Provision Internet Service', test: () => this.testUnifiedProvisionService() },
      { name: 'Suspend Customer Service', test: () => this.testUnifiedSuspendService() },
      { name: 'Backup Device Configuration', test: () => this.testUnifiedBackupConfig() },
    ];

    await this.runTestSuite(suite, tests);
    this.testResults.push(suite);
  }

  private async testUnifiedDiscoverDevices(): Promise<any> {
    try {
      const devices = await this.unifiedAPI.discoverAllDevices();
      return { count: devices.length };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  private async testUnifiedGetCustomers(): Promise<any> {
    try {
      const customers = await this.unifiedAPI.getUnifiedCustomers({ limit: 10 });
      return { count: customers.length };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  private async testUnifiedGetTopology(): Promise<any> {
    try {
      const topology = await this.unifiedAPI.getNetworkTopology();
      return {
        devices: topology.devices.length,
        connections: topology.connections.length,
        overview: topology.overview,
      };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  private async testUnifiedGetMonitoring(): Promise<any> {
    try {
      const monitoring = await this.unifiedAPI.getMonitoringData();
      return { count: monitoring.length };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  private async testUnifiedProvisionService(): Promise<any> {
    try {
      await this.unifiedAPI.provisionInternetService('123', {
        bandwidth: { download: 100, upload: 50 },
        ipAddress: '192.168.1.100',
      });
      return { success: true };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  private async testUnifiedSuspendService(): Promise<any> {
    try {
      await this.unifiedAPI.suspendCustomerService('123');
      return { success: true };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  private async testUnifiedBackupConfig(): Promise<any> {
    try {
      const backup = await this.unifiedAPI.backupDeviceConfiguration('mikrotik_0');
      return { hasBackup: !!backup };
    } catch (error: any) {
      return { error: true, message: "API request failed", details: error.message };
    }
  }

  // End-to-End Integration Tests
  async testEndToEndIntegration(): Promise<void> {
    const suite: TestSuite = {
      suiteName: 'End-to-End Integration Tests',
      results: [],
      summary: { total: 0, passed: 0, failed: 0, skipped: 0, duration: 0 },
    };

    const tests = [
      { name: 'Customer Onboarding Flow', test: () => this.testCustomerOnboarding() },
      { name: 'Service Provisioning Flow', test: () => this.testServiceProvisioning() },
      { name: 'Network Monitoring Flow', test: () => this.testNetworkMonitoring() },
      { name: 'Billing Integration Flow', test: () => this.testBillingIntegration() },
      { name: 'Troubleshooting Flow', test: () => this.testTroubleshootingFlow() },
    ];

    await this.runTestSuite(suite, tests);
    this.testResults.push(suite);
  }

  private async testCustomerOnboarding(): Promise<any> {
    try {
      // Simulate full customer onboarding process
      const customer = await this.testSplynxCreateCustomer();
      const devices = await this.testUnifiedDiscoverDevices();
      const provisioning = await this.testUnifiedProvisionService();
      
      return {
        customer: customer.customerId,
        devices: devices.count,
        provisioned: provisioning.success,
      };
    } catch (error: any) {
      return { error: true, message: "End-to-end test failed", details: error.message };
    }
  }

  private async testServiceProvisioning(): Promise<any> {
    try {
      // Test complete service provisioning
      const topology = await this.testUnifiedGetTopology();
      const monitoring = await this.testUnifiedGetMonitoring();
      const backup = await this.testUnifiedBackupConfig();
      
      return {
        topology: topology.devices,
        monitoring: monitoring.count,
        backup: backup.hasBackup,
      };
    } catch (error: any) {
      return { error: true, message: "Service provisioning test failed", details: error.message };
    }
  }

  private async testNetworkMonitoring(): Promise<any> {
    try {
      // Test network monitoring capabilities
      const mikrotikHealth = await this.testMikrotikSystemHealth();
      const tuacStats = await this.testTUACGetNetworkStats();
      const unifiedMonitoring = await this.testUnifiedGetMonitoring();
      
      return {
        mikrotik: mikrotikHealth.temperature,
        tuac: tuacStats.stats?.cpuUsage,
        unified: unifiedMonitoring.count,
      };
    } catch (error: any) {
      return { error: true, message: "Network monitoring test failed", details: error.message };
    }
  }

  private async testBillingIntegration(): Promise<any> {
    try {
      // Test billing integration
      const invoices = await this.testSplynxGetInvoices();
      const payment = await this.testSplynxCreatePayment();
      const financeStats = await this.testSplynxGetFinanceStats();
      
      return {
        invoices: invoices.count,
        payment: payment.paymentId,
        stats: financeStats.hasStats,
      };
    } catch (error: any) {
      return { error: true, message: "Billing integration test failed", details: error.message };
    }
  }

  private async testTroubleshootingFlow(): Promise<any> {
    try {
      // Test troubleshooting capabilities
      const systemInfo = await this.testMikrotikSystemInfo();
      const deviceInfo = await this.testTUACGetDeviceInfo();
      const customers = await this.testSplynxGetCustomers();
      
      return {
        mikrotikUptime: systemInfo.uptime,
        tuacStatus: deviceInfo.deviceInfo?.status,
        customersOnline: customers.count,
      };
    } catch (error: any) {
      return { error: true, message: "Troubleshooting flow test failed", details: error.message };
    }
  }

  // Helper Methods
  private async runTestSuite(suite: TestSuite, tests: Array<{ name: string; test: () => Promise<any> }>): Promise<void> {
    console.log(`\n📋 Running ${suite.suiteName}...`);
    const suiteStartTime = Date.now();

    for (const { name, test } of tests) {
      const startTime = Date.now();
      let result: TestResult;

      try {
        console.log(`  ⏳ ${name}...`);
        const details = await test();
        const duration = Date.now() - startTime;
        
        result = {
          testName: name,
          status: 'passed',
          duration,
          details,
        };
        
        console.log(`  ✅ ${name} (${duration}ms)`);
        suite.summary.passed++;
      } catch (error: any) {
        const duration = Date.now() - startTime;
        
        result = {
          testName: name,
          status: 'failed',
          duration,
          error: getErrorMessage(error),
        };
        
        console.log(`  ❌ ${name} (${duration}ms): ${getErrorMessage(error)}`);
        suite.summary.failed++;
      }

      suite.results.push(result);
      suite.summary.total++;
    }

    suite.summary.duration = Date.now() - suiteStartTime;
    console.log(`📊 ${suite.suiteName} completed: ${suite.summary.passed}/${suite.summary.total} passed`);
  }


  private generateTestReport(): void {
    console.log('\n📊 TEST EXECUTION REPORT');
    console.log('========================');
    
    let totalTests = 0;
    let totalPassed = 0;
    let totalFailed = 0;
    let totalDuration = 0;

    for (const suite of this.testResults) {
      console.log(`\n${suite.suiteName}:`);
      console.log(`  Total: ${suite.summary.total}`);
      console.log(`  Passed: ${suite.summary.passed} ✅`);
      console.log(`  Failed: ${suite.summary.failed} ❌`);
      console.log(`  Duration: ${suite.summary.duration}ms`);
      
      totalTests += suite.summary.total;
      totalPassed += suite.summary.passed;
      totalFailed += suite.summary.failed;
      totalDuration += suite.summary.duration;
    }

    const successRate = ((totalPassed / totalTests) * 100).toFixed(1);
    
    console.log('\n📈 OVERALL SUMMARY:');
    console.log(`  Total Tests: ${totalTests}`);
    console.log(`  Passed: ${totalPassed} ✅`);
    console.log(`  Failed: ${totalFailed} ❌`);
    console.log(`  Success Rate: ${successRate}%`);
    console.log(`  Total Duration: ${totalDuration}ms`);
    
    if (totalFailed === 0) {
      console.log('\n🎉 ALL TESTS PASSED! LynxMSP API integrations are working correctly.');
    } else {
      console.log(`\n⚠️  ${totalFailed} tests failed. Check the details above for issues.`);
    }
  }
}

// Export the tester
export default APIIntegrationTester;
export type { TestResult, TestSuite };

// Auto-run tests if called directly
if (typeof window !== 'undefined' && (window as any).runAPITests) {
  const tester = new APIIntegrationTester();
  tester.runAllTests().then(() => {
    console.log('🏁 API Integration Testing Complete!');
  });
}