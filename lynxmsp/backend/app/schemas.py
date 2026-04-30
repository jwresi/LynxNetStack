from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel


class CompanyBase(BaseModel):
    name: str
    domain: str

class CompanyCreate(CompanyBase):
    pass

class Company(CompanyBase):
    id: int
    setup_complete: bool
    created_at: datetime

    class Config:
        from_attributes = True

class UserBase(BaseModel):
    username: str
    email: str

class User(UserBase):
    id: int
    company_id: Optional[int] = None
    is_admin: bool = False
    is_company_admin: bool = False
    created_at: datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str
    user: User

class TokenData(BaseModel):
    username: Optional[str] = None

class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    employee_id: Optional[str] = None
    department: Optional[str] = None
    preferences: Optional[dict] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class CompanySetup(BaseModel):
    company_name: str
    company_domain: str
    admin_username: str
    admin_email: str
    admin_password: str

class ServicePlanBase(BaseModel):
    name: str
    download_speed: int
    upload_speed: int
    monthly_price: float


class ServicePlanCreate(ServicePlanBase):
    description: Optional[str] = None
    setup_fee: Optional[float] = 0.0
    data_cap: Optional[int] = None
    service_type: Optional[str] = "residential"
    technology: Optional[str] = "fiber"
    burst_speed_down: Optional[int] = None
    burst_speed_up: Optional[int] = None
    priority_level: Optional[int] = 5
    billing_cycle: Optional[str] = "monthly"
    contract_length: Optional[int] = 12
    early_termination_fee: Optional[float] = 0.0
    static_ips_included: Optional[int] = 0
    ipv6_enabled: Optional[bool] = True
    cgnat_enabled: Optional[bool] = False
    prorate_first_month: Optional[bool] = True
    auto_renewal: Optional[bool] = True
    equipment_included: Optional[List[str]] = []
    status: Optional[str] = "active"
    available_in_areas: Optional[List[str]] = []


class ServicePlanUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    download_speed: Optional[int] = None
    upload_speed: Optional[int] = None
    monthly_price: Optional[float] = None
    setup_fee: Optional[float] = None
    data_cap: Optional[int] = None
    service_type: Optional[str] = None
    technology: Optional[str] = None
    burst_speed_down: Optional[int] = None
    burst_speed_up: Optional[int] = None
    priority_level: Optional[int] = None
    billing_cycle: Optional[str] = None
    contract_length: Optional[int] = None
    early_termination_fee: Optional[float] = None
    static_ips_included: Optional[int] = None
    ipv6_enabled: Optional[bool] = None
    cgnat_enabled: Optional[bool] = None
    prorate_first_month: Optional[bool] = None
    auto_renewal: Optional[bool] = None
    equipment_included: Optional[List[str]] = None
    status: Optional[str] = None
    available_in_areas: Optional[List[str]] = None

class ServicePlan(ServicePlanBase):
    id: int
    description: Optional[str] = None
    setup_fee: Optional[float] = 0.0
    data_cap: Optional[int] = None
    service_type: Optional[str] = "residential"
    technology: Optional[str] = "fiber"
    burst_speed_down: Optional[int] = None
    burst_speed_up: Optional[int] = None
    priority_level: Optional[int] = 5
    billing_cycle: Optional[str] = "monthly"
    contract_length: Optional[int] = 12
    early_termination_fee: Optional[float] = 0.0
    static_ips_included: Optional[int] = 0
    ipv6_enabled: Optional[bool] = True
    cgnat_enabled: Optional[bool] = False
    prorate_first_month: Optional[bool] = True
    auto_renewal: Optional[bool] = True
    equipment_included: Optional[List[str]] = []
    status: Optional[str] = "active"
    available_in_areas: Optional[List[str]] = []

    class Config:
        from_attributes = True

class CustomerBase(BaseModel):
    name: str
    email: str
    phone: str
    address: str
    service_plan_id: int
    status: Optional[str] = "active"

class CustomerCreate(CustomerBase):
    pass

class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    service_plan_id: Optional[int] = None
    status: Optional[str] = None

class Customer(CustomerBase):
    id: int
    created_at: datetime
    service_plan: Optional[ServicePlan] = None

    class Config:
        from_attributes = True

class InvoiceBase(BaseModel):
    customer_id: int
    amount: float
    due_date: datetime
    status: Optional[str] = "unpaid"

class InvoiceCreate(InvoiceBase):
    pass


class InvoiceUpdate(BaseModel):
    customer_id: Optional[int] = None
    amount: Optional[float] = None
    due_date: Optional[datetime] = None
    status: Optional[str] = None

class Invoice(InvoiceBase):
    id: int
    created_at: datetime
    customer: Optional[Customer] = None

    class Config:
        from_attributes = True

class TicketCommentBase(BaseModel):
    content: str
    author: str

class TicketCommentCreate(TicketCommentBase):
    pass

class TicketComment(TicketCommentBase):
    id: int
    ticket_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class TicketBase(BaseModel):
    customer_id: int
    title: str
    description: str
    status: Optional[str] = "open"
    priority: Optional[str] = "medium"

class TicketCreate(TicketBase):
    pass

class TicketUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None

class Ticket(TicketBase):
    id: int
    created_at: datetime
    customer: Optional[Customer] = None
    comments: List[TicketComment] = []

    class Config:
        from_attributes = True

class DashboardStats(BaseModel):
    total_customers: int
    monthly_revenue: float
    open_tickets: int
    recent_activities: List[dict]

# Network Infrastructure Schemas

class SiteBase(BaseModel):
    name: str
    site_type: str  # 'pop', 'tower', 'headend', 'customer_premise'
    address: str
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None
    elevation: Optional[float] = None
    status: Optional[str] = "active"
    notes: Optional[str] = None

class SiteCreate(SiteBase):
    pass

class SiteUpdate(BaseModel):
    name: Optional[str] = None
    site_type: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None
    elevation: Optional[float] = None
    status: Optional[str] = None
    notes: Optional[str] = None

class Site(SiteBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

class RouterBase(BaseModel):
    name: str
    model: str
    os_version: Optional[str] = None
    management_ip: str
    api_port: Optional[int] = 8728
    username: str
    password: str
    site_id: int
    status: Optional[str] = "active"

class RouterCreate(RouterBase):
    # Router Onboarding Configuration
    customer_subnet: Optional[str] = None
    management_vlan: Optional[int] = 1
    customer_vlan_start: Optional[int] = 100
    dhcp_pool_start: Optional[str] = None
    dhcp_pool_end: Optional[str] = None
    enable_option82: Optional[bool] = True
    bridge_name: Optional[str] = 'bridge-main'
    customer_interface: Optional[str] = 'ether2-ether10'
    uplink_interface: Optional[str] = 'ether1'
    generated_commands: Optional[str] = None

class RouterUpdate(BaseModel):
    name: Optional[str] = None
    model: Optional[str] = None
    os_version: Optional[str] = None
    management_ip: Optional[str] = None
    api_port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    site_id: Optional[int] = None
    status: Optional[str] = None
    customer_subnet: Optional[str] = None
    management_vlan: Optional[int] = None
    customer_vlan_start: Optional[int] = None
    dhcp_pool_start: Optional[str] = None
    dhcp_pool_end: Optional[str] = None
    enable_option82: Optional[bool] = None
    configuration_applied: Optional[bool] = None

class Router(RouterBase):
    id: int
    last_seen: Optional[datetime] = None
    uptime: Optional[int] = None
    customer_subnet: Optional[str] = None
    management_vlan: Optional[int] = None
    customer_vlan_start: Optional[int] = None
    dhcp_pool_start: Optional[str] = None
    dhcp_pool_end: Optional[str] = None
    enable_option82: Optional[bool] = None
    bridge_name: Optional[str] = None
    customer_interface: Optional[str] = None
    uplink_interface: Optional[str] = None
    generated_commands: Optional[str] = None
    configuration_applied: Optional[bool] = None
    created_at: datetime
    site: Optional[Site] = None

    class Config:
        from_attributes = True

class IPSubnetBase(BaseModel):
    name: str
    network: str  # e.g., '192.168.1.0/24'
    gateway: Optional[str] = None
    vlan_id: Optional[int] = None
    subnet_type: str  # 'customer', 'management', 'loopback', 'transit'
    site_id: int
    status: Optional[str] = "active"
    description: Optional[str] = None

class IPSubnetCreate(IPSubnetBase):
    pass

class IPSubnet(IPSubnetBase):
    id: int
    created_at: datetime
    site: Optional[Site] = None

    class Config:
        from_attributes = True

class NetworkInterfaceBase(BaseModel):
    name: str  # e.g., 'ether1', 'wlan1', 'bridge1'
    interface_type: str  # ethernet, wireless, bridge, vlan, tunnel
    router_id: int
    mac_address: Optional[str] = None
    mtu: Optional[int] = 1500
    status: Optional[str] = "enabled"
    speed: Optional[str] = None
    duplex: Optional[str] = None
    description: Optional[str] = None

class NetworkInterfaceCreate(NetworkInterfaceBase):
    pass

class NetworkInterface(NetworkInterfaceBase):
    id: int
    created_at: datetime
    router: Optional[Router] = None

    class Config:
        from_attributes = True

class IPAssignmentBase(BaseModel):
    ip_address: str
    subnet_id: int
    router_id: Optional[int] = None
    interface_id: Optional[int] = None
    customer_id: Optional[int] = None
    assignment_type: str  # 'static', 'dhcp_reservation', 'pool'
    description: Optional[str] = None

class IPAssignmentCreate(IPAssignmentBase):
    pass

class IPAssignment(IPAssignmentBase):
    id: int
    created_at: datetime
    subnet: Optional[IPSubnet] = None
    router: Optional[Router] = None
    interface: Optional[NetworkInterface] = None
    customer: Optional[Customer] = None

    class Config:
        from_attributes = True

class EquipmentBase(BaseModel):
    name: str
    equipment_type: str  # 'router', 'switch', 'radio', 'antenna', 'cable', 'power_supply'
    manufacturer: str
    model: str
    serial_number: str
    purchase_date: Optional[datetime] = None
    warranty_expires: Optional[datetime] = None
    site_id: Optional[int] = None
    customer_id: Optional[int] = None
    status: Optional[str] = "active"
    location_details: Optional[str] = None
    notes: Optional[str] = None

class EquipmentCreate(EquipmentBase):
    pass

class Equipment(EquipmentBase):
    id: int
    created_at: datetime
    site: Optional[Site] = None
    customer: Optional[Customer] = None

    class Config:
        from_attributes = True

class ServiceOrderBase(BaseModel):
    customer_id: int
    order_type: str  # 'new_install', 'upgrade', 'downgrade', 'disconnect', 'maintenance'
    service_plan_id: int
    site_id: Optional[int] = None
    status: Optional[str] = "pending"
    scheduled_date: Optional[datetime] = None
    technician: Optional[str] = None
    installation_address: Optional[str] = None
    equipment_needed: Optional[str] = None
    notes: Optional[str] = None

class ServiceOrderCreate(ServiceOrderBase):
    pass

class ServiceOrder(ServiceOrderBase):
    id: int
    completed_date: Optional[datetime] = None
    created_at: datetime
    customer: Optional[Customer] = None
    service_plan: Optional[ServicePlan] = None
    site: Optional[Site] = None

    class Config:
        from_attributes = True

class NetworkMonitoringBase(BaseModel):
    router_id: int
    metric_type: str  # 'cpu_usage', 'memory_usage', 'interface_traffic', 'uptime'
    metric_value: float
    metric_unit: str  # 'percent', 'bytes', 'seconds'

class NetworkMonitoringCreate(NetworkMonitoringBase):
    pass

class NetworkMonitoring(NetworkMonitoringBase):
    id: int
    timestamp: datetime
    router: Optional[Router] = None

    class Config:
        from_attributes = True

# Customer VLAN Management Schemas

class CustomerVLANBase(BaseModel):
    customer_id: int
    router_id: int
    vlan_id: int
    ip_address: Optional[str] = None
    mac_address: Optional[str] = None
    status: Optional[str] = "active"
    isolation_enabled: Optional[bool] = True
    bandwidth_limit_down: Optional[int] = None
    bandwidth_limit_up: Optional[int] = None

class CustomerVLANCreate(CustomerVLANBase):
    pass

class CustomerVLAN(CustomerVLANBase):
    id: int
    created_at: datetime
    last_seen: Optional[datetime] = None
    customer: Optional[Customer] = None
    router: Optional[Router] = None

    class Config:
        from_attributes = True

class DHCPLeaseBase(BaseModel):
    router_id: int
    customer_id: Optional[int] = None
    ip_address: str
    mac_address: str
    hostname: Optional[str] = None
    lease_time: Optional[datetime] = None
    circuit_id: Optional[str] = None  # DHCP Option 82
    remote_id: Optional[str] = None   # DHCP Option 82
    vlan_id: Optional[int] = None
    status: Optional[str] = "bound"

class DHCPLeaseCreate(DHCPLeaseBase):
    pass

class DHCPLease(DHCPLeaseBase):
    id: int
    created_at: datetime
    router: Optional[Router] = None
    customer: Optional[Customer] = None

    class Config:
        from_attributes = True

# Router Onboarding Wizard Response
class RouterOnboardingResponse(BaseModel):
    success: bool
    router_id: int
    message: str
    configuration_commands: str
    next_steps: List[str]

# TPLink TAUC Device Schemas
class TPLinkDeviceBase(BaseModel):
    device_id: str
    sn: str
    mac: str
    name: str
    model: str
    device_type: str
    firmware_version: Optional[str] = None
    ip_address: Optional[str] = None
    management_domain: str
    status: Optional[str] = "unknown"
    site_id: Optional[int] = None
    customer_id: Optional[int] = None
    parent_device_id: Optional[int] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    network_id: Optional[str] = None

class TPLinkDeviceCreate(TPLinkDeviceBase):
    pass

class TPLinkDeviceUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    site_id: Optional[int] = None
    customer_id: Optional[int] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    network_id: Optional[str] = None

class TPLinkDevice(TPLinkDeviceBase):
    id: int
    temperature: Optional[float] = None
    power_consumption: Optional[float] = None
    uptime: Optional[int] = None
    alarm_count: Optional[int] = 0
    last_seen: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class TPLinkInterfaceBase(BaseModel):
    device_id: int
    interface_name: str
    alias: Optional[str] = None
    interface_type: str
    status: Optional[str] = "unknown"
    admin_status: Optional[str] = "enabled"
    speed: Optional[str] = None
    duplex: Optional[str] = None
    mtu: Optional[int] = 1500
    mac_address: Optional[str] = None
    vlan_id: Optional[int] = None
    vlan_mode: Optional[str] = None
    description: Optional[str] = None

class TPLinkInterfaceCreate(TPLinkInterfaceBase):
    pass

class TPLinkInterfaceUpdate(BaseModel):
    alias: Optional[str] = None
    status: Optional[str] = None
    admin_status: Optional[str] = None
    speed: Optional[str] = None
    duplex: Optional[str] = None
    mtu: Optional[int] = None
    vlan_id: Optional[int] = None
    vlan_mode: Optional[str] = None
    description: Optional[str] = None

class TPLinkInterface(TPLinkInterfaceBase):
    id: int
    rx_bytes: Optional[int] = 0
    tx_bytes: Optional[int] = 0
    rx_packets: Optional[int] = 0
    tx_packets: Optional[int] = 0
    rx_errors: Optional[int] = 0
    tx_errors: Optional[int] = 0
    pon_port_number: Optional[int] = None
    optical_power_tx: Optional[float] = None
    optical_power_rx: Optional[float] = None
    connected_onts: Optional[int] = 0
    ssid: Optional[str] = None
    security_mode: Optional[str] = None
    channel: Optional[int] = None
    signal_strength: Optional[float] = None
    last_updated: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class TPLinkONTProvisionBase(BaseModel):
    olt_device_id: int
    customer_id: int
    pon_port: str
    ont_id: int
    serial_number: str
    service_profile: Optional[str] = "default"
    bandwidth_profile: Optional[str] = None
    notes: Optional[str] = None

class TPLinkONTProvisionCreate(TPLinkONTProvisionBase):
    vlan_config: Optional[dict] = None
    wifi_config: Optional[dict] = None

class TPLinkONTProvisionUpdate(BaseModel):
    service_profile: Optional[str] = None
    bandwidth_profile: Optional[str] = None
    vlan_config: Optional[dict] = None
    wifi_config: Optional[dict] = None
    notes: Optional[str] = None

class TPLinkONTProvision(TPLinkONTProvisionBase):
    id: int
    ont_device_id: Optional[int] = None
    provision_status: str
    provision_date: Optional[datetime] = None
    last_online: Optional[datetime] = None
    vlan_config: Optional[dict] = None
    wifi_config: Optional[dict] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

class TPLinkAlarmBase(BaseModel):
    device_id: int
    alarm_type: str
    severity: str
    alarm_code: str
    message: str
    source_interface: Optional[str] = None

class TPLinkAlarm(TPLinkAlarmBase):
    id: int
    status: str
    raised_at: datetime
    cleared_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    
    class Config:
        from_attributes = True

class TPLinkPerformanceMetricBase(BaseModel):
    device_id: int
    interface_name: Optional[str] = None
    metric_type: str
    metric_value: float
    metric_unit: str

class TPLinkPerformanceMetric(TPLinkPerformanceMetricBase):
    id: int
    timestamp: datetime
    
    class Config:
        from_attributes = True

# Port Control Schemas
class PortControlRequest(BaseModel):
    action: str  # enable, disable, configure
    interface_name: str
    speed: Optional[str] = None
    duplex: Optional[str] = None
    vlan_id: Optional[int] = None
    description: Optional[str] = None

class BulkPortControlRequest(BaseModel):
    operations: List[dict]  # List of port operations

class DeviceStatusResponse(BaseModel):
    device_id: str
    status: str
    uptime: Optional[int] = None
    temperature: Optional[float] = None
    power_consumption: Optional[float] = None
    alarm_count: int
    interface_count: int
    last_updated: datetime

class OLTStatusResponse(BaseModel):
    device_id: str
    pon_ports: List[dict]
    ethernet_ports: List[dict]
    connected_onts: int
    total_capacity: dict
    performance_metrics: dict

class ONTStatusResponse(BaseModel):
    device_id: str
    pon_status: str
    optical_power_rx: Optional[float] = None
    optical_power_tx: Optional[float] = None
    ethernet_ports: List[dict]
    wifi_status: Optional[dict] = None

# Company Settings Schemas
class CompanySettingBase(BaseModel):
    setting_key: str
    setting_value: str
    setting_type: str  # 'string', 'password', 'url', 'number', 'boolean'
    category: str  # 'api', 'network', 'notifications', 'general'
    description: Optional[str] = None
    is_encrypted: Optional[bool] = False

class CompanySettingCreate(CompanySettingBase):
    pass

class CompanySettingUpdate(BaseModel):
    setting_value: Optional[str] = None
    description: Optional[str] = None

class CompanySetting(CompanySettingBase):
    id: int
    company_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class CompanySettingsResponse(BaseModel):
    settings: List[CompanySetting]
    categories: List[str]

class SettingsBulkUpdate(BaseModel):
    settings: List[dict]  # List of {setting_key, setting_value}

# User Invitation Schemas
class UserInvitationBase(BaseModel):
    email: str
    role: str = "user"

class UserInvitationCreate(UserInvitationBase):
    pass

class UserInvitation(UserInvitationBase):
    id: int
    company_id: int
    invitation_token: str
    invited_by_user_id: int
    status: str
    created_at: datetime
    expires_at: datetime
    accepted_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class InvitationAccept(BaseModel):
    invitation_token: str
    username: str
    password: str

class NotificationTest(BaseModel):
    notification_type: str  # 'email' or 'slack'

class InvitationResponse(BaseModel):
    success: bool
    message: str
    invitation_token: Optional[str] = None
    expires_at: Optional[str] = None
    email_sent: bool = False
    slack_sent: bool = False