import os
from datetime import datetime

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, Numeric, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./lynxcrm.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class Company(Base):
    __tablename__ = "companies"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    domain = Column(String, unique=True, index=True)  # Company subdomain/identifier
    setup_complete = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    users = relationship("User", back_populates="company")


class OrganizationInfo(Base):
    __tablename__ = "organization_info"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, default="Your Organization")
    logo_url = Column(String, nullable=True)
    icon_url = Column(String, nullable=True)
    tagline = Column(String, nullable=True)
    primary_color = Column(String, default="#1976d2")
    secondary_color = Column(String, default="#1565c0")
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    email = Column(String, index=True)
    password_hash = Column(String)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)  # Nullable for admin/demo user
    is_admin = Column(Boolean, default=False)
    is_company_admin = Column(Boolean, default=False)  # Admin for their company
    created_at = Column(DateTime, default=datetime.utcnow)
    
    company = relationship("Company", back_populates="users")

class ServicePlan(Base):
    __tablename__ = "service_plans"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(Text, nullable=True)
    download_speed = Column(Integer)
    upload_speed = Column(Integer)
    monthly_price = Column(Float)
    setup_fee = Column(Float, default=0.0)
    data_cap = Column(Integer, nullable=True)  # GB, null means unlimited
    service_type = Column(String, default="residential")  # residential, business, enterprise
    technology = Column(String, default="fiber")  # fiber, wireless, cable, dsl, satellite
    burst_speed_down = Column(Integer, nullable=True)
    burst_speed_up = Column(Integer, nullable=True)
    priority_level = Column(Integer, default=5)  # 1-10
    billing_cycle = Column(String, default="monthly")  # monthly, quarterly, annually
    contract_length = Column(Integer, default=12)  # months
    early_termination_fee = Column(Float, default=0.0)
    static_ips_included = Column(Integer, default=0)
    ipv6_enabled = Column(Boolean, default=True)
    cgnat_enabled = Column(Boolean, default=False)
    prorate_first_month = Column(Boolean, default=True)
    auto_renewal = Column(Boolean, default=True)
    equipment_included = Column(JSON, default=list)  # List of equipment
    status = Column(String, default="active")  # active, inactive, deprecated
    available_in_areas = Column(JSON, default=list)  # List of areas
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    customers = relationship("Customer", back_populates="service_plan")

class Customer(Base):
    __tablename__ = "customers"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, index=True)
    phone = Column(String)
    address = Column(Text)
    service_plan_id = Column(Integer, ForeignKey("service_plans.id"))
    status = Column(String, default="active")  # active, suspended, disconnected
    connection_type = Column(String)  # fiber, wireless, ethernet
    installation_date = Column(DateTime)
    coordinates = Column(String)  # lat,lng for mapping
    site_id = Column(Integer, ForeignKey("sites.id"))
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    service_plan = relationship("ServicePlan", back_populates="customers")
    invoices = relationship("Invoice", back_populates="customer")
    tickets = relationship("Ticket", back_populates="customer")
    site = relationship("Site", back_populates="customers")
    equipment = relationship("Equipment", back_populates="customer")
    ip_assignments = relationship("IPAssignment", back_populates="customer")
    vlans = relationship("CustomerVLAN", back_populates="customer")

class Invoice(Base):
    __tablename__ = "invoices"
    
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    amount = Column(Float)
    due_date = Column(DateTime)
    status = Column(String, default="unpaid")
    created_at = Column(DateTime, default=datetime.utcnow)
    
    customer = relationship("Customer", back_populates="invoices")

class Ticket(Base):
    __tablename__ = "tickets"
    
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    title = Column(String)
    description = Column(Text)
    status = Column(String, default="open")
    priority = Column(String, default="medium")
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    customer = relationship("Customer", back_populates="tickets")
    comments = relationship("TicketComment", back_populates="ticket")

class TicketComment(Base):
    __tablename__ = "ticket_comments"
    
    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id"))
    content = Column(Text)
    author = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    ticket = relationship("Ticket", back_populates="comments")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class Site(Base):
    __tablename__ = "sites"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    site_type = Column(String)  # 'pop', 'tower', 'headend', 'customer_premise'
    address = Column(Text)
    latitude = Column(Numeric(10, 7))
    longitude = Column(Numeric(10, 7))
    elevation = Column(Float)  # meters above sea level
    status = Column(String, default="active")  # active, inactive, planned, decommissioned
    notes = Column(Text)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    routers = relationship("Router", back_populates="site")
    equipment = relationship("Equipment", back_populates="site")
    customers = relationship("Customer", back_populates="site")

class Router(Base):
    __tablename__ = "routers"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    model = Column(String)  # e.g., 'RB5009UG+S+IN', 'CCR2004-1G-12S+2XS'
    os_version = Column(String)  # RouterOS version
    management_ip = Column(String, index=True)
    api_port = Column(Integer, default=8728)
    username = Column(String)
    password = Column(String)  # Encrypted in production
    site_id = Column(Integer, ForeignKey("sites.id"))
    status = Column(String, default="active")  # active, inactive, maintenance, failed
    last_seen = Column(DateTime)
    uptime = Column(Integer)  # seconds
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    
    # Router Onboarding Configuration
    customer_subnet = Column(String)  # e.g., '192.168.100.1/24'
    management_vlan = Column(Integer, default=1)
    customer_vlan_start = Column(Integer, default=100)
    dhcp_pool_start = Column(String)
    dhcp_pool_end = Column(String)
    enable_option82 = Column(Boolean, default=True)
    bridge_name = Column(String, default='bridge-main')
    customer_interface = Column(String, default='ether2-ether10')
    uplink_interface = Column(String, default='ether1')
    generated_commands = Column(Text)  # Store the RouterOS configuration
    configuration_applied = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    site = relationship("Site", back_populates="routers")
    interfaces = relationship("NetworkInterface", back_populates="router")
    ip_assignments = relationship("IPAssignment", back_populates="router")
    customer_vlans = relationship("CustomerVLAN", back_populates="router")

class IPSubnet(Base):
    __tablename__ = "ip_subnets"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    network = Column(String, index=True)  # e.g., '192.168.1.0/24'
    gateway = Column(String)
    vlan_id = Column(Integer)
    subnet_type = Column(String)  # 'customer', 'management', 'loopback', 'transit'
    site_id = Column(Integer, ForeignKey("sites.id"))
    status = Column(String, default="active")
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    site = relationship("Site")
    ip_assignments = relationship("IPAssignment", back_populates="subnet")

class NetworkInterface(Base):
    __tablename__ = "network_interfaces"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)  # e.g., 'ether1', 'wlan1', 'bridge1'
    interface_type = Column(String)  # ethernet, wireless, bridge, vlan, tunnel
    router_id = Column(Integer, ForeignKey("routers.id"))
    mac_address = Column(String)
    mtu = Column(Integer, default=1500)
    status = Column(String, default="enabled")  # enabled, disabled, error
    speed = Column(String)  # e.g., '1Gbps', '100Mbps'
    duplex = Column(String)  # full, half
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    router = relationship("Router", back_populates="interfaces")
    ip_assignments = relationship("IPAssignment", back_populates="interface")

class IPAssignment(Base):
    __tablename__ = "ip_assignments"
    
    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String, index=True)
    subnet_id = Column(Integer, ForeignKey("ip_subnets.id"))
    router_id = Column(Integer, ForeignKey("routers.id"), nullable=True)
    interface_id = Column(Integer, ForeignKey("network_interfaces.id"), nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    assignment_type = Column(String)  # 'static', 'dhcp_reservation', 'pool'
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    subnet = relationship("IPSubnet", back_populates="ip_assignments")
    router = relationship("Router", back_populates="ip_assignments")
    interface = relationship("NetworkInterface", back_populates="ip_assignments")
    customer = relationship("Customer")

class Equipment(Base):
    __tablename__ = "equipment"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    equipment_type = Column(String)  # 'router', 'switch', 'radio', 'antenna', 'cable', 'power_supply'
    manufacturer = Column(String)
    model = Column(String)
    serial_number = Column(String, unique=True)
    purchase_date = Column(DateTime)
    warranty_expires = Column(DateTime)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    status = Column(String, default="active")  # active, spare, maintenance, failed, disposed
    location_details = Column(Text)  # Rack position, etc.
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    site = relationship("Site", back_populates="equipment")
    customer = relationship("Customer")

class ServiceOrder(Base):
    __tablename__ = "service_orders"
    
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    order_type = Column(String)  # 'new_install', 'upgrade', 'downgrade', 'disconnect', 'maintenance'
    service_plan_id = Column(Integer, ForeignKey("service_plans.id"))
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=True)
    status = Column(String, default="pending")  # pending, scheduled, in_progress, completed, cancelled
    scheduled_date = Column(DateTime)
    completed_date = Column(DateTime)
    technician = Column(String)
    installation_address = Column(Text)
    equipment_needed = Column(Text)
    notes = Column(Text)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    customer = relationship("Customer")
    service_plan = relationship("ServicePlan")
    site = relationship("Site")

class NetworkMonitoring(Base):
    __tablename__ = "network_monitoring"
    
    id = Column(Integer, primary_key=True, index=True)
    router_id = Column(Integer, ForeignKey("routers.id"))
    metric_type = Column(String)  # 'cpu_usage', 'memory_usage', 'interface_traffic', 'uptime'
    metric_value = Column(Float)
    metric_unit = Column(String)  # 'percent', 'bytes', 'seconds'
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    router = relationship("Router")

class NetworkDiscoveryJob(Base):
    __tablename__ = "network_discovery_jobs"
    
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    name = Column(String, index=True)
    target_range = Column(String)
    discovery_type = Column(String)  # lldp, snmp, both
    status = Column(String, default="pending")  # pending, running, completed, failed
    progress = Column(Integer, default=0)
    devices_found = Column(Integer, default=0)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    company = relationship("Company")

class LLDPNeighborRecord(Base):
    __tablename__ = "lldp_neighbors"
    
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    router_id = Column(Integer, ForeignKey("routers.id"), nullable=True)
    device_ip = Column(String, index=True)
    chassis_id = Column(String)
    port_id = Column(String)
    port_description = Column(String)
    system_name = Column(String)
    system_description = Column(Text)
    management_address = Column(String)
    capabilities = Column(JSON, default=list)
    discovered_at = Column(DateTime, default=datetime.utcnow)
    ttl = Column(Integer, default=0)
    
    router = relationship("Router")
    company = relationship("Company")

class CustomerVLAN(Base):
    __tablename__ = "customer_vlans"
    
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    router_id = Column(Integer, ForeignKey("routers.id"))
    vlan_id = Column(Integer, index=True)
    ip_address = Column(String)  # Assigned customer IP
    mac_address = Column(String)  # Customer device MAC
    status = Column(String, default="active")  # active, suspended, terminated
    isolation_enabled = Column(Boolean, default=True)
    bandwidth_limit_down = Column(Integer)  # Mbps
    bandwidth_limit_up = Column(Integer)  # Mbps
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime)
    
    customer = relationship("Customer")
    router = relationship("Router", back_populates="customer_vlans")

class DHCPLease(Base):
    __tablename__ = "dhcp_leases"
    
    id = Column(Integer, primary_key=True, index=True)
    router_id = Column(Integer, ForeignKey("routers.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    ip_address = Column(String, index=True)
    mac_address = Column(String, index=True)
    hostname = Column(String)
    lease_time = Column(DateTime)
    circuit_id = Column(String)  # DHCP Option 82
    remote_id = Column(String)  # DHCP Option 82
    vlan_id = Column(Integer)
    status = Column(String, default="bound")  # bound, expired, released
    created_at = Column(DateTime, default=datetime.utcnow)
    
    router = relationship("Router")
    customer = relationship("Customer")

# CGNAT Models
class CGNATPool(Base):
    __tablename__ = "cgnat_pools"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    public_ip_range = Column(String)  # e.g., "203.0.113.0/24"
    port_range_start = Column(Integer, default=1024)
    port_range_end = Column(Integer, default=65535)
    ports_per_user = Column(Integer, default=1000)
    max_users = Column(Integer)
    current_users = Column(Integer, default=0)
    router_id = Column(Integer, ForeignKey("routers.id"))
    status = Column(String, default="active")  # active, inactive, full
    created_at = Column(DateTime, default=datetime.utcnow)
    
    router = relationship("Router")
    allocations = relationship("CGNATAllocation", back_populates="pool")

class CGNATAllocation(Base):
    __tablename__ = "cgnat_allocations"
    
    id = Column(Integer, primary_key=True, index=True)
    pool_id = Column(Integer, ForeignKey("cgnat_pools.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"))
    private_ip = Column(String)  # Customer's private IP
    public_ip = Column(String)  # Assigned public IP
    port_range_start = Column(Integer)
    port_range_end = Column(Integer)
    allocated_at = Column(DateTime, default=datetime.utcnow)
    last_activity = Column(DateTime)
    status = Column(String, default="active")  # active, inactive, expired
    
    pool = relationship("CGNATPool", back_populates="allocations")
    customer = relationship("Customer")
    sessions = relationship("CGNATSession", back_populates="allocation")

class CGNATSession(Base):
    __tablename__ = "cgnat_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    allocation_id = Column(Integer, ForeignKey("cgnat_allocations.id"))
    private_ip = Column(String)
    private_port = Column(Integer)
    public_ip = Column(String)
    public_port = Column(Integer)
    destination_ip = Column(String)
    destination_port = Column(Integer)
    protocol = Column(String)  # tcp, udp, icmp
    created_at = Column(DateTime, default=datetime.utcnow)
    last_packet = Column(DateTime, default=datetime.utcnow)
    packet_count = Column(Integer, default=0)
    byte_count = Column(Integer, default=0)
    status = Column(String, default="active")  # active, closed, timeout
    
    allocation = relationship("CGNATAllocation", back_populates="sessions")

# IPv6 Models
class IPv6Pool(Base):
    __tablename__ = "ipv6_pools"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    prefix = Column(String)  # e.g., "2001:db8::/32"
    prefix_length = Column(Integer)
    delegation_size = Column(Integer, default=64)  # Size of delegated prefixes
    router_id = Column(Integer, ForeignKey("routers.id"))
    status = Column(String, default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    
    router = relationship("Router")
    delegations = relationship("IPv6Delegation", back_populates="pool")

class IPv6Delegation(Base):
    __tablename__ = "ipv6_delegations"
    
    id = Column(Integer, primary_key=True, index=True)
    pool_id = Column(Integer, ForeignKey("ipv6_pools.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"))
    delegated_prefix = Column(String)  # e.g., "2001:db8:1::/64"
    prefix_length = Column(Integer)
    allocated_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="active")  # active, inactive, expired
    
    pool = relationship("IPv6Pool", back_populates="delegations")
    customer = relationship("Customer")

# TPLink TAUC Device Models
class TPLinkDevice(Base):
    __tablename__ = "tplink_devices"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, unique=True, index=True)  # TAUC device ID
    sn = Column(String, unique=True, index=True)  # Serial number
    mac = Column(String, unique=True, index=True)  # MAC address
    name = Column(String, index=True)
    model = Column(String)  # PizzaBox OLT 4/8 port, XZ000-G7 ONT, etc.
    device_type = Column(String)  # olt_pizzabox_4, olt_pizzabox_8, ont_xz000_g7
    firmware_version = Column(String)
    ip_address = Column(String)
    management_domain = Column(String)  # TAUC domain
    status = Column(String, default="unknown")  # online, offline, maintenance, error
    last_seen = Column(DateTime)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)  # For ONTs
    parent_device_id = Column(Integer, ForeignKey("tplink_devices.id"), nullable=True)  # For ONTs linked to OLTs
    
    # TAUC API Configuration
    client_id = Column(String)
    client_secret = Column(String)
    network_id = Column(String)  # TAUC network ID
    
    # Device specific data
    temperature = Column(Float)
    power_consumption = Column(Float)
    uptime = Column(Integer)  # seconds
    alarm_count = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    site = relationship("Site")
    customer = relationship("Customer")
    parent_device = relationship("TPLinkDevice", remote_side=[id], back_populates="child_devices")
    child_devices = relationship("TPLinkDevice", back_populates="parent_device")
    interfaces = relationship("TPLinkInterface", back_populates="device")
    alarms = relationship("TPLinkAlarm", back_populates="device")
    performance_metrics = relationship("TPLinkPerformanceMetric", back_populates="device")

class TPLinkInterface(Base):
    __tablename__ = "tplink_interfaces"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("tplink_devices.id"))
    interface_name = Column(String, index=True)  # eth1, pon1, wifi2.4g, etc.
    alias = Column(String)
    interface_type = Column(String)  # ethernet, pon, wifi, optical
    status = Column(String)  # up, down, disabled, error
    admin_status = Column(String)  # enabled, disabled
    
    # Physical properties
    speed = Column(String)  # 1Gbps, 100Mbps, etc.
    duplex = Column(String)  # full, half
    mtu = Column(Integer, default=1500)
    mac_address = Column(String)
    
    # Statistics
    rx_bytes = Column(Integer, default=0)
    tx_bytes = Column(Integer, default=0)
    rx_packets = Column(Integer, default=0)
    tx_packets = Column(Integer, default=0)
    rx_errors = Column(Integer, default=0)
    tx_errors = Column(Integer, default=0)
    
    # VLAN Configuration
    vlan_id = Column(Integer)
    vlan_mode = Column(String)  # access, trunk
    
    # PON specific (for OLT PON ports)
    pon_port_number = Column(Integer)
    optical_power_tx = Column(Float)  # dBm
    optical_power_rx = Column(Float)  # dBm
    connected_onts = Column(Integer, default=0)
    
    # WiFi specific (for ONT WiFi)
    ssid = Column(String)
    security_mode = Column(String)
    channel = Column(Integer)
    signal_strength = Column(Float)
    
    description = Column(Text)
    last_updated = Column(DateTime, default=datetime.utcnow)
    
    device = relationship("TPLinkDevice", back_populates="interfaces")

class TPLinkONTProvision(Base):
    __tablename__ = "tplink_ont_provisions"
    
    id = Column(Integer, primary_key=True, index=True)
    olt_device_id = Column(Integer, ForeignKey("tplink_devices.id"))
    ont_device_id = Column(Integer, ForeignKey("tplink_devices.id"), nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    
    pon_port = Column(String)  # pon1, pon2, etc.
    ont_id = Column(Integer)  # ONT ID on the PON port
    serial_number = Column(String, unique=True)
    service_profile = Column(String, default="default")
    
    # Provisioning status
    provision_status = Column(String, default="pending")  # pending, provisioned, failed, deprovisioned
    provision_date = Column(DateTime)
    last_online = Column(DateTime)
    
    # Service configuration
    bandwidth_profile = Column(String)
    vlan_config = Column(JSON)  # Store VLAN configuration as JSON
    wifi_config = Column(JSON)  # Store WiFi configuration as JSON
    
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    olt_device = relationship("TPLinkDevice", foreign_keys=[olt_device_id])
    ont_device = relationship("TPLinkDevice", foreign_keys=[ont_device_id])
    customer = relationship("Customer")

class TPLinkAlarm(Base):
    __tablename__ = "tplink_alarms"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("tplink_devices.id"))
    alarm_type = Column(String)  # temperature, power, interface, optical
    severity = Column(String)  # critical, major, minor, warning, info
    alarm_code = Column(String)
    message = Column(Text)
    source_interface = Column(String, nullable=True)
    
    status = Column(String, default="active")  # active, cleared, acknowledged
    raised_at = Column(DateTime, default=datetime.utcnow)
    cleared_at = Column(DateTime, nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    acknowledged_by = Column(String, nullable=True)
    
    device = relationship("TPLinkDevice", back_populates="alarms")

class TPLinkPerformanceMetric(Base):
    __tablename__ = "tplink_performance_metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("tplink_devices.id"))
    interface_name = Column(String, nullable=True)
    metric_type = Column(String)  # cpu_usage, memory_usage, temperature, optical_power, bandwidth
    metric_value = Column(Float)
    metric_unit = Column(String)  # percent, celsius, dbm, mbps, bytes
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    device = relationship("TPLinkDevice", back_populates="performance_metrics")

class TPLinkConfiguration(Base):
    __tablename__ = "tplink_configurations"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("tplink_devices.id"))
    config_type = Column(String)  # system, interface, wifi, vlan, qos
    config_name = Column(String)
    config_data = Column(JSON)  # Store configuration as JSON
    applied_at = Column(DateTime)
    applied_by = Column(String)
    status = Column(String, default="pending")  # pending, applied, failed, rolled_back
    
    device = relationship("TPLinkDevice")

class CompanySetting(Base):
    __tablename__ = "company_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"))
    setting_key = Column(String, index=True)  # 'splynx_api_url', 'snmp_community', etc.
    setting_value = Column(Text)  # Encrypted for sensitive values
    setting_type = Column(String)  # 'string', 'password', 'url', 'number', 'boolean'
    category = Column(String)  # 'api', 'network', 'notifications', 'general'
    description = Column(String)
    is_encrypted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    company = relationship("Company")

class UserInvitation(Base):
    __tablename__ = "user_invitations"
    
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"))
    email = Column(String, index=True)
    invitation_token = Column(String, unique=True, index=True)
    role = Column(String, default="user")  # 'user', 'admin', 'company_admin'
    invited_by_user_id = Column(Integer, ForeignKey("users.id"))
    status = Column(String, default="pending")  # 'pending', 'accepted', 'expired', 'cancelled'
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    accepted_at = Column(DateTime, nullable=True)
    
    company = relationship("Company")
    invited_by = relationship("User")

def init_db():
    Base.metadata.create_all(bind=engine)
