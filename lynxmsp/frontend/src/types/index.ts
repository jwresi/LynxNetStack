export interface User {
  id: number;
  username: string;
  email?: string;
}

export interface ServicePlan {
  id: number;
  name: string;
  speed_down: number;
  speed_up: number;
  price: number;
}

export interface Customer {
  id: number;
  name: string;
  email: string;
  phone?: string;
  address?: string;
  service_plan_id: number;
  service_plan?: ServicePlan;
  status: 'active' | 'suspended' | 'inactive';
  created_at: string;
}

export interface Invoice {
  id: number;
  customer_id: number;
  customer?: Customer;
  amount: number;
  due_date: string;
  payment_status: 'pending' | 'paid' | 'overdue';
  created_at: string;
}

export interface Ticket {
  id: number;
  customer_id: number;
  customer?: Customer;
  title: string;
  description: string;
  status: 'open' | 'in_progress' | 'resolved' | 'closed';
  priority: 'low' | 'medium' | 'high' | 'urgent';
  availability_status?: 'available' | 'busy' | 'offline';
  created_at: string;
  updated_at: string;
}

export interface TicketComment {
  id: number;
  ticket_id: number;
  author: string;
  content: string;
  created_at: string;
}

export interface DashboardStats {
  total_customers: number;
  active_customers: number;
  total_revenue: number;
  pending_invoices: number;
  open_tickets: number;
}

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}