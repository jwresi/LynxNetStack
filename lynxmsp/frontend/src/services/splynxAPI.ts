/**
 * Splynx API Integration Service
 * Complete implementation based on Splynx API v2.0 documentation
 */

import axios, { AxiosInstance, AxiosResponse } from 'axios';
import { getErrorMessage } from '../utils/errorHelpers';

// Base Configuration
interface SplynxConfig {
  baseUrl: string;
  apiKey: string;
  apiSecret: string;
  environment: 'production' | 'staging' | 'development';
}

// Authentication Types
interface AuthCredentials {
  login: string;
  password: string;
  code?: string; // 2FA code
  fingerprint?: string; // Trusted device fingerprint
}

interface AccessToken {
  access_token: string;
  access_token_expiration: number;
  refresh_token: string;
  refresh_token_expiration: number;
  permissions: string[];
}

// Core Data Models
interface Customer {
  id?: number;
  partner_id: number;
  location_id: number;
  login: string;
  category: 'person' | 'company';
  name: string;
  email: string;
  billing_email?: string;
  phone: string;
  street_1: string;
  zip_code: string;
  city: string;
  country: string;
  date_add?: string;
  status: 'new' | 'active' | 'inactive' | 'blocked';
  billing_type: 'prepaid' | 'recurring';
  additional_attributes?: Record<string, any>;
}

interface Service {
  id?: number;
  customer_id: number;
  tariff_price_id: number;
  status: 'active' | 'stopped' | 'disabled';
  quantity: number;
  unit: string;
  start_date: string;
  end_date?: string;
  description?: string;
}

interface Invoice {
  id?: number;
  customer_id: number;
  number: string;
  date: string;
  date_till: string;
  total: number;
  to_pay: number;
  status: 'unpaid' | 'paid' | 'partial';
  note?: string;
}

interface Payment {
  id?: number;
  customer_id: number;
  receipt_number: string;
  date: string;
  amount: number;
  comment?: string;
  payment_type: 'cash' | 'bank_transfer' | 'credit_card' | 'paypal';
  field_1?: string;
  field_2?: string;
  field_3?: string;
  field_4?: string;
  field_5?: string;
}

interface RouterDevice {
  id?: number;
  title: string;
  ip: string;
  login: string;
  password: string;
  type: 'mikrotik' | 'cisco' | 'juniper' | 'other';
  nas_type: string;
  secret: string;
  enabled: boolean;
  api_url?: string;
}

// API Response Types
interface ApiResponse<T> {
  data?: T;
  error?: {
    message: string;
    code: number;
    internal_code: string;
  };
}

interface ListResponse<T> {
  data: T[];
  meta: {
    total: number;
    count: number;
    per_page: number;
    current_page: number;
    total_pages: number;
  };
}

class SplynxAPI {
  private client: AxiosInstance;
  private config: SplynxConfig;
  private accessToken: string | null = null;
  private tokenExpiration: number = 0;
  private refreshToken: string | null = null;

  constructor(config: SplynxConfig) {
    this.config = config;
    this.client = axios.create({
      baseURL: `${config.baseUrl}/api/2.0/`,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
    });

    // Request interceptor for authentication
    this.client.interceptors.request.use(async (config) => {
      await this.ensureValidToken();
      if (this.accessToken) {
        config.headers.Authorization = `Splynx-EA (access_token=${this.accessToken})`;
      }
      return config;
    });

    // Response interceptor for error handling
    this.client.interceptors.response.use(
      (response) => response,
      async (error) => {
        if (error.response?.status === 401 && this.refreshToken) {
          await this.renewToken();
          return this.client.request(error.config);
        }
        return Promise.reject(error);
      }
    );
  }

  // Authentication Methods
  async authenticate(credentials: AuthCredentials): Promise<AccessToken> {
    try {
      const response = await axios.post(`${this.config.baseUrl}/api/2.0/admin/auth/tokens`, {
        auth_type: 'admin',
        ...credentials,
      });

      const tokenData = response.data;
      this.accessToken = tokenData.access_token;
      this.tokenExpiration = tokenData.access_token_expiration;
      this.refreshToken = tokenData.refresh_token;

      return tokenData;
    } catch (error: any) {
      throw new Error(`Authentication failed: ${error.response?.data?.error?.message || getErrorMessage(error)}`);
    }
  }

  async authenticateWithApiKey(): Promise<AccessToken> {
    const nonce = Math.floor(Date.now() / 1000);
    const signature = await this.generateSignature(nonce);

    try {
      const response = await axios.post(`${this.config.baseUrl}/api/2.0/admin/auth/tokens`, {
        auth_type: 'api_key',
        key: this.config.apiKey,
        signature,
        nonce,
      });

      const tokenData = response.data;
      this.accessToken = tokenData.access_token;
      this.tokenExpiration = tokenData.access_token_expiration;
      this.refreshToken = tokenData.refresh_token;

      return tokenData;
    } catch (error: any) {
      throw new Error(`API key authentication failed: ${error.response?.data?.error?.message || getErrorMessage(error)}`);
    }
  }

  private async generateSignature(nonce: number): Promise<string> {
    // Use Web Crypto API for browser compatibility
    const encoder = new TextEncoder();
    const data = encoder.encode(nonce + this.config.apiKey);
    const keyData = encoder.encode(this.config.apiSecret);
    
    const cryptoKey = await crypto.subtle.importKey(
      'raw',
      keyData,
      { name: 'HMAC', hash: 'SHA-256' },
      false,
      ['sign']
    );
    
    const signature = await crypto.subtle.sign('HMAC', cryptoKey, data);
    const hashArray = Array.from(new Uint8Array(signature));
    const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
    return hashHex.toUpperCase();
  }

  private async ensureValidToken(): Promise<void> {
    if (!this.accessToken || Date.now() / 1000 + 5 > this.tokenExpiration) {
      if (this.refreshToken) {
        await this.renewToken();
      } else {
        await this.authenticateWithApiKey();
      }
    }
  }

  private async renewToken(): Promise<void> {
    if (!this.refreshToken) {
      throw new Error('No refresh token available');
    }

    try {
      const response = await axios.get(
        `${this.config.baseUrl}/api/2.0/admin/auth/tokens/${this.refreshToken}`
      );

      const tokenData = response.data;
      this.accessToken = tokenData.access_token;
      this.tokenExpiration = tokenData.access_token_expiration;
      this.refreshToken = tokenData.refresh_token;
    } catch (error: any) {
      throw new Error(`Token renewal failed: ${error.response?.data?.error?.message || getErrorMessage(error)}`);
    }
  }

  // Customer Management
  async getCustomers(params?: {
    search?: string;
    status?: string;
    limit?: number;
    offset?: number;
  }): Promise<ListResponse<Customer>> {
    const queryParams = new URLSearchParams();
    
    if (params?.search) {
      queryParams.append('main_attributes[name]', `LIKE,${params.search}`);
    }
    if (params?.status) {
      queryParams.append('main_attributes[status]', params.status);
    }
    if (params?.limit) {
      queryParams.append('limit', params.limit.toString());
    }
    if (params?.offset) {
      queryParams.append('offset', params.offset.toString());
    }

    const response = await this.client.get(`admin/customers/customer?${queryParams}`);
    return response.data;
  }

  async getCustomer(id: number): Promise<Customer> {
    const response = await this.client.get(`admin/customers/customer/${id}`);
    return response.data;
  }

  async createCustomer(customer: Omit<Customer, 'id'>): Promise<Customer> {
    const response = await this.client.post('admin/customers/customer', customer);
    return response.data;
  }

  async updateCustomer(id: number, customer: Partial<Customer>): Promise<Customer> {
    const response = await this.client.put(`admin/customers/customer/${id}`, customer);
    return response.data;
  }

  async deleteCustomer(id: number): Promise<void> {
    await this.client.delete(`admin/customers/customer/${id}`);
  }

  // Service Management
  async getCustomerServices(customerId: number): Promise<Service[]> {
    const response = await this.client.get(`admin/customers/customer/${customerId}/services`);
    return response.data;
  }

  async createService(service: Omit<Service, 'id'>): Promise<Service> {
    const response = await this.client.post('admin/tariff-plans/services', service);
    return response.data;
  }

  async updateService(id: number, service: Partial<Service>): Promise<Service> {
    const response = await this.client.put(`admin/tariff-plans/services/${id}`, service);
    return response.data;
  }

  async startInternetService(customerId: number): Promise<void> {
    await this.client.post(`admin/customers/customer/${customerId}/start-internet`);
  }

  async stopInternetService(customerId: number): Promise<void> {
    await this.client.post(`admin/customers/customer/${customerId}/stop-internet`);
  }

  // Billing Management
  async getInvoices(params?: {
    customer_id?: number;
    status?: string;
    date_from?: string;
    date_to?: string;
    limit?: number;
    offset?: number;
  }): Promise<ListResponse<Invoice>> {
    const queryParams = new URLSearchParams();
    
    if (params?.customer_id) {
      queryParams.append('main_attributes[customer_id]', params.customer_id.toString());
    }
    if (params?.status) {
      queryParams.append('main_attributes[status]', params.status);
    }
    if (params?.date_from) {
      queryParams.append('main_attributes[date]', `>=,${params.date_from}`);
    }
    if (params?.date_to) {
      queryParams.append('main_attributes[date]', `<=,${params.date_to}`);
    }
    if (params?.limit) {
      queryParams.append('limit', params.limit.toString());
    }
    if (params?.offset) {
      queryParams.append('offset', params.offset.toString());
    }

    const response = await this.client.get(`admin/finance/invoices?${queryParams}`);
    return response.data;
  }

  async createInvoice(invoice: Omit<Invoice, 'id'>): Promise<Invoice> {
    const response = await this.client.post('admin/finance/invoices', invoice);
    return response.data;
  }

  async payInvoice(invoiceId: number, payment: Omit<Payment, 'id'>): Promise<Payment> {
    const response = await this.client.post(`admin/finance/invoices/${invoiceId}/pay`, payment);
    return response.data;
  }

  // Payment Management
  async getPayments(params?: {
    customer_id?: number;
    date_from?: string;
    date_to?: string;
    limit?: number;
    offset?: number;
  }): Promise<ListResponse<Payment>> {
    const queryParams = new URLSearchParams();
    
    if (params?.customer_id) {
      queryParams.append('main_attributes[customer_id]', params.customer_id.toString());
    }
    if (params?.date_from) {
      queryParams.append('main_attributes[date]', `>=,${params.date_from}`);
    }
    if (params?.date_to) {
      queryParams.append('main_attributes[date]', `<=,${params.date_to}`);
    }
    if (params?.limit) {
      queryParams.append('limit', params.limit.toString());
    }
    if (params?.offset) {
      queryParams.append('offset', params.offset.toString());
    }

    const response = await this.client.get(`admin/finance/payments?${queryParams}`);
    return response.data;
  }

  async createPayment(payment: Omit<Payment, 'id'>): Promise<Payment> {
    const response = await this.client.post('admin/finance/payments', payment);
    return response.data;
  }

  // Network Management
  async getRouters(): Promise<RouterDevice[]> {
    const response = await this.client.get('admin/networking/routers');
    return response.data;
  }

  async createRouter(router: Omit<RouterDevice, 'id'>): Promise<RouterDevice> {
    const response = await this.client.post('admin/networking/routers', router);
    return response.data;
  }

  async updateRouter(id: number, router: Partial<RouterDevice>): Promise<RouterDevice> {
    const response = await this.client.put(`admin/networking/routers/${id}`, router);
    return response.data;
  }

  async testRouterConnection(id: number): Promise<{ success: boolean; message: string }> {
    const response = await this.client.post(`admin/networking/routers/${id}/test`);
    return response.data;
  }

  // Statistics and Monitoring
  async getCustomerStatistics(customerId: number, params?: {
    date_from?: string;
    date_to?: string;
  }): Promise<any> {
    const queryParams = new URLSearchParams();
    queryParams.append('main_attributes[customer_id]', customerId.toString());
    
    if (params?.date_from) {
      queryParams.append('main_attributes[date]', `>=,${params.date_from}`);
    }
    if (params?.date_to) {
      queryParams.append('main_attributes[date]', `<=,${params.date_to}`);
    }

    const response = await this.client.get(`admin/customers/customer-statistics?${queryParams}`);
    return response.data;
  }

  async getOnlineCustomers(): Promise<any[]> {
    const response = await this.client.get('admin/customers/customers-online');
    return response.data;
  }

  // Dashboard and Reporting
  async getDashboardData(): Promise<any> {
    const response = await this.client.get('admin/dashboard');
    return response.data;
  }

  async getFinanceStatistics(params?: {
    date_from?: string;
    date_to?: string;
  }): Promise<any> {
    const queryParams = new URLSearchParams();
    
    if (params?.date_from) {
      queryParams.append('date_from', params.date_from);
    }
    if (params?.date_to) {
      queryParams.append('date_to', params.date_to);
    }

    const response = await this.client.get(`admin/finance/statistics?${queryParams}`);
    return response.data;
  }

  // Error Handling Utility
  private handleApiError(error: any): never {
    if (error.response?.data?.error) {
      const apiError = error.response.data.error;
      throw new Error(`Splynx API Error: ${apiError.message} (${apiError.internal_code})`);
    }
    throw new Error(`Splynx API Request Failed: ${getErrorMessage(error)}`);
  }
}

// Export the API class and types
export default SplynxAPI;
export type {
  SplynxConfig,
  Customer,
  Service,
  Invoice,
  Payment,
  RouterDevice,
  AccessToken,
  AuthCredentials,
  ApiResponse,
  ListResponse,
};

// Default configuration for different environments
export const createSplynxConfig = (environment: 'production' | 'staging' | 'development'): SplynxConfig => {
  const configs = {
    production: {
      baseUrl: process.env.REACT_APP_SPLYNX_PROD_URL || 'https://your-splynx-server.com',
      apiKey: process.env.REACT_APP_SPLYNX_PROD_API_KEY || '',
      apiSecret: process.env.REACT_APP_SPLYNX_PROD_API_SECRET || '',
      environment: 'production' as const,
    },
    staging: {
      baseUrl: process.env.REACT_APP_SPLYNX_STAGING_URL || 'https://staging.splynx.com',
      apiKey: process.env.REACT_APP_SPLYNX_STAGING_API_KEY || '',
      apiSecret: process.env.REACT_APP_SPLYNX_STAGING_API_SECRET || '',
      environment: 'staging' as const,
    },
    development: {
      baseUrl: process.env.REACT_APP_SPLYNX_URL || '',
      apiKey: process.env.REACT_APP_SPLYNX_DEV_API_KEY || '',
      apiSecret: process.env.REACT_APP_SPLYNX_DEV_API_SECRET || '',
      environment: 'development' as const,
    },
  };

  return configs[environment];
};