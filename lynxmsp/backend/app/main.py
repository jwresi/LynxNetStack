from datetime import timedelta, datetime
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, status, Form
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import schemas
from .auth import authenticate_user, create_access_token, get_current_user
from .database import (User, Customer, ServicePlan, Invoice, Ticket, TicketComment,
                       Site, Router, IPSubnet, NetworkInterface, IPAssignment, Equipment,
                       ServiceOrder, NetworkMonitoring, CustomerVLAN, DHCPLease,
                       CGNATPool, CGNATAllocation, CGNATSession, IPv6Pool, IPv6Delegation,
                       TPLinkDevice, TPLinkInterface, TPLinkONTProvision, TPLinkAlarm,
                       TPLinkPerformanceMetric, Company, CompanySetting,
                       UserInvitation, OrganizationInfo, LLDPNeighborRecord,
                       NetworkDiscoveryJob)
from .database import get_db, init_db

app = FastAPI(title="LynxCRM API", version="1.0.0", description="Comprehensive ISP/MSP/WISP Management Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    init_db()

# ============================================================================
# AUTHENTICATION ENDPOINTS
# ============================================================================

@app.post("/auth/login", response_model=schemas.Token)
async def login(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = authenticate_user(db, username, password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "user": user}

@app.get("/auth/me", response_model=schemas.User)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user


@app.get("/auth/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.put("/auth/profile", response_model=schemas.User)
async def update_profile(
        profile_data: schemas.UserUpdate,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    # Update user profile fields
    for field, value in profile_data.dict(exclude_unset=True).items():
        if hasattr(current_user, field):
            setattr(current_user, field, value)

    db.commit()
    db.refresh(current_user)
    return current_user


@app.put("/auth/change-password")
async def change_password(
        password_data: schemas.PasswordChange,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    from .auth import verify_password, get_password_hash

    # Verify current password
    if not verify_password(password_data.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    # Update password
    current_user.password_hash = get_password_hash(password_data.new_password)
    db.commit()

    return {"message": "Password updated successfully"}

# ============================================================================
# ORGANIZATION BRANDING ENDPOINTS
# ============================================================================

@app.get("/api/v1/organization/info")
async def get_organization_info(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    # Get organization info for the user's company or global if admin
    org_info = db.query(OrganizationInfo).first()
    if not org_info:
        # Create default organization info if none exists
        org_info = OrganizationInfo(
            name="Your Organization",
            tagline="Customer Relationship Management",
            primary_color="#1976d2",
            secondary_color="#1565c0"
        )
        db.add(org_info)
        db.commit()
        db.refresh(org_info)

    return org_info


# ============================================================================
# API V1 COMPATIBILITY ENDPOINTS
# ============================================================================

@app.get("/api/v1/auth/users")
async def get_users_v1(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Compatibility route for v1 user listing."""
    users = db.query(User).all()
    return [
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": getattr(user, 'full_name', ''),
            "role": getattr(user, 'role', 'user'),
            "is_active": getattr(user, 'is_active', True),
            "created_at": user.created_at
        }
        for user in users
    ]

@app.get("/api/v1/ipv6/subnets")
async def get_ipv6_subnets_v1(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Compatibility route for IPv6 subnet listings."""
    subnets = db.query(IPSubnet).all()
    return [
        subnet for subnet in subnets
        if subnet.subnet_type == "ipv6" or ":" in (subnet.network or "")
    ]

@app.get("/api/v1/network/lldp/neighbors")
async def get_lldp_neighbors_v1(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Compatibility route for LLDP neighbors."""
    query = db.query(LLDPNeighborRecord)
    if current_user.company_id:
        query = query.filter(LLDPNeighborRecord.company_id == current_user.company_id)
    neighbors = query.order_by(LLDPNeighborRecord.discovered_at.desc()).all()
    return [
        {
            "id": neighbor.id,
            "local_device_id": neighbor.device_ip or neighbor.chassis_id,
            "local_port": neighbor.port_id,
            "remote_device_id": neighbor.chassis_id,
            "remote_port": neighbor.port_id,
            "remote_device_name": neighbor.system_name,
            "remote_system_description": neighbor.system_description,
            "remote_management_ip": neighbor.management_address,
            "ttl": neighbor.ttl,
            "capabilities": neighbor.capabilities or [],
            "discovered_at": neighbor.discovered_at,
            "last_seen": neighbor.discovered_at
        }
        for neighbor in neighbors
    ]

@app.post("/api/v1/network/lldp/discover")
async def start_lldp_discovery_v1(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Compatibility route to start discovery using default ranges."""
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="User must be associated with a company")

    settings = db.query(CompanySetting).filter(
        CompanySetting.company_id == current_user.company_id,
        CompanySetting.category == 'network'
    ).all()
    settings_dict = {s.setting_key: s.setting_value for s in settings}
    ranges_value = settings_dict.get("network_discovery_ranges", "192.168.1.0/24")
    network_ranges = [r.strip() for r in ranges_value.split(",") if r.strip()]

    from .services.network_discovery import NetworkDiscoveryService
    discovery_service = NetworkDiscoveryService(db, current_user.company_id)
    results = await discovery_service.full_network_discovery(network_ranges)
    discovery_service.save_discovery_results(results)

    return {
        "message": "Network discovery completed",
        "active_hosts_count": len(results.get("active_hosts", [])),
        "snmp_devices_count": len(results.get("snmp_devices", [])),
        "lldp_neighbors_count": len(results.get("lldp_neighbors", [])),
        "errors": results.get("errors", [])
    }

@app.get("/api/v1/network/snmp/devices")
async def get_snmp_devices_v1(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Compatibility route for SNMP device listings."""
    query = db.query(Router)
    if current_user.company_id:
        query = query.filter(Router.company_id == current_user.company_id)
    routers = query.all()
    devices = []
    for router in routers:
        devices.append({
            "id": router.id,
            "ip_address": router.management_ip,
            "hostname": router.name,
            "system_description": router.os_version or "",
            "system_uptime": router.uptime or 0,
            "snmp_version": "2c",
            "community_string": None,
            "contact": None,
            "location": None,
            "interfaces": [],
            "status": "online" if router.status == "active" else "offline",
            "last_polled": router.last_seen or router.created_at,
            "response_time_ms": 0
        })
    return devices

@app.post("/api/v1/network/snmp/devices/{device_id}/poll")
async def poll_snmp_device_v1(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Compatibility route to mark a device as polled."""
    query = db.query(Router).filter(Router.id == device_id)
    if current_user.company_id:
        query = query.filter(Router.company_id == current_user.company_id)
    router = query.first()
    if not router:
        raise HTTPException(status_code=404, detail="Device not found")

    router.last_seen = datetime.now()
    db.commit()
    return {"message": "Device polled", "device_id": router.id}

@app.get("/api/v1/network/discovery/jobs")
async def get_discovery_jobs_v1(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Compatibility route for discovery job listings."""
    query = db.query(NetworkDiscoveryJob)
    if current_user.company_id:
        query = query.filter(NetworkDiscoveryJob.company_id == current_user.company_id)
    jobs = query.order_by(NetworkDiscoveryJob.created_at.desc()).all()
    return [
        {
            "id": job.id,
            "name": job.name,
            "target_range": job.target_range,
            "discovery_type": job.discovery_type,
            "status": job.status,
            "progress": job.progress,
            "devices_found": job.devices_found,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "error_message": job.error_message
        }
        for job in jobs
    ]

@app.post("/api/v1/network/discovery/jobs")
async def start_discovery_job_v1(
    job_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Compatibility route to create and run a discovery job."""
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="User must be associated with a company")

    target_range = job_data.get("target_range") or "192.168.1.0/24"
    discovery_type = job_data.get("discovery_type") or "both"

    job = NetworkDiscoveryJob(
        company_id=current_user.company_id,
        name=job_data.get("name", "Discovery Job"),
        target_range=target_range,
        discovery_type=discovery_type,
        status="running",
        progress=0,
        started_at=datetime.now()
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        from .services.network_discovery import NetworkDiscoveryService
        discovery_service = NetworkDiscoveryService(db, current_user.company_id)
        results = await discovery_service.full_network_discovery([target_range])
        discovery_service.save_discovery_results(results)

        job.status = "completed"
        job.progress = 100
        job.devices_found = len(results.get("snmp_devices", []))
        job.completed_at = datetime.now()
        db.commit()
    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)
        job.completed_at = datetime.now()
        db.commit()

    return {
        "id": job.id,
        "name": job.name,
        "target_range": job.target_range,
        "discovery_type": job.discovery_type,
        "status": job.status,
        "progress": job.progress,
        "devices_found": job.devices_found,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "error_message": job.error_message
    }

@app.post("/api/v1/organization/info")
async def update_organization_info(
        name: str = Form(...),
        tagline: str = Form(""),
        primary_color: str = Form("#1976d2"),
        secondary_color: str = Form("#1565c0"),
        logo: Optional[str] = None,  # File upload handling would go here
        icon: Optional[str] = None,  # File upload handling would go here
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    # Check if user has permission to update organization info
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    # Get or create organization info
    org_info = db.query(OrganizationInfo).first()
    if not org_info:
        org_info = OrganizationInfo()
        db.add(org_info)

    # Update fields
    org_info.name = name
    org_info.tagline = tagline
    org_info.primary_color = primary_color
    org_info.secondary_color = secondary_color
    org_info.updated_at = datetime.now()

    # TODO: Handle file uploads for logo and icon
    # if logo:
    #     org_info.logo_url = save_uploaded_file(logo, 'logos')
    # if icon:
    #     org_info.icon_url = save_uploaded_file(icon, 'icons')

    db.commit()
    db.refresh(org_info)
    return org_info


# ============================================================================
# COMPANY SETUP ENDPOINTS
# ============================================================================

@app.post("/setup/company", response_model=schemas.Token)
async def setup_company(setup_data: schemas.CompanySetup, db: Session = Depends(get_db)):
    # Check if company domain already exists
    existing_company = db.query(Company).filter(Company.domain == setup_data.company_domain).first()
    if existing_company:
        raise HTTPException(status_code=400, detail="Company domain already exists")
    
    # Check if user already exists
    existing_user = db.query(User).filter(User.username == setup_data.admin_username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    # Create company
    company = Company(
        name=setup_data.company_name,
        domain=setup_data.company_domain,
        setup_complete=True
    )
    db.add(company)
    db.flush()  # To get the company ID
    
    # Create admin user
    from .auth import get_password_hash
    admin_user = User(
        username=setup_data.admin_username,
        email=setup_data.admin_email,
        password_hash=get_password_hash(setup_data.admin_password),
        company_id=company.id,
        is_company_admin=True
    )
    db.add(admin_user)
    db.commit()
    
    # Return login token
    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": admin_user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "user": admin_user}


@app.get("/setup/company-required")
async def check_company_setup_required(db: Session = Depends(get_db)):
    # Check if system needs initial company setup
    companies_count = db.query(Company).count()
    return {"setup_required": companies_count == 0}

# ============================================================================
# DASHBOARD ENDPOINTS
# ============================================================================

def get_company_filter(query, model, current_user: User):
    """Apply company-based filtering to queries for data isolation"""
    if current_user.is_admin and current_user.company_id is None:
        # Global admin can see all data across companies
        return query
    elif current_user.company_id:
        # Company users only see their company's data
        return query.filter(model.company_id == current_user.company_id)
    else:
        # No company association, return empty
        return query.filter(False)

@app.get("/dashboard/stats")
async def get_dashboard_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Apply company filtering to all queries
    customers_query = get_company_filter(db.query(Customer), Customer, current_user)
    sites_query = get_company_filter(db.query(Site), Site, current_user)
    routers_query = get_company_filter(db.query(Router), Router, current_user)
    orders_query = get_company_filter(db.query(ServiceOrder), ServiceOrder, current_user)
    tickets_query = get_company_filter(db.query(Ticket), Ticket, current_user)
    
    total_customers = customers_query.count()
    active_customers = customers_query.filter(Customer.status == "active").count()
    total_sites = sites_query.count()
    active_routers = routers_query.filter(Router.status == "active").count()
    pending_orders = orders_query.filter(ServiceOrder.status == "pending").count()
    open_tickets = tickets_query.filter(Ticket.status == "open").count()
    
    # Revenue calculation
    monthly_revenue = db.query(ServicePlan.monthly_price).join(Customer).filter(Customer.status == "active").all()
    total_revenue = sum([price[0] for price in monthly_revenue if price[0]])

    # Calculate real network utilization from router interfaces
    network_utilization = 0.0
    try:
        # Get average utilization from all active router interfaces
        routers = get_company_filter(db.query(Router), Router, current_user).filter(Router.status == "active").all()
        if routers:
            total_utilization = 0
            interface_count = 0
            for router in routers:
                # Get latest monitoring data for interface traffic
                latest_metrics = db.query(NetworkMonitoring).filter(
                    NetworkMonitoring.router_id == router.id,
                    NetworkMonitoring.metric_type == "interface_traffic"
                ).order_by(NetworkMonitoring.timestamp.desc()).limit(5).all()

                if latest_metrics:
                    avg_traffic = sum(m.metric_value for m in latest_metrics) / len(latest_metrics)
                    # Convert to utilization percentage (assuming 1Gbps = 100% for simplicity)
                    utilization = min((avg_traffic / 125000000) * 100, 100)  # 1Gbps in bytes/sec
                    total_utilization += utilization
                    interface_count += 1

            if interface_count > 0:
                network_utilization = total_utilization / interface_count
    except Exception:
        # Fallback to 0 if calculation fails
        network_utilization = 0.0
    
    # CGNAT usage
    total_cgnat_pools = db.query(CGNATPool).count()
    active_cgnat_allocations = db.query(CGNATAllocation).filter(CGNATAllocation.status == "active").count()
    
    # IPv6 delegation stats
    total_ipv6_pools = db.query(IPv6Pool).count()
    active_ipv6_delegations = db.query(IPv6Delegation).filter(IPv6Delegation.status == "active").count()
    
    return {
        "total_customers": total_customers,
        "active_customers": active_customers,
        "total_sites": total_sites,
        "active_routers": active_routers,
        "pending_orders": pending_orders,
        "open_tickets": open_tickets,
        "monthly_revenue": round(total_revenue, 2),
        "network_utilization": network_utilization,
        "cgnat_pools": total_cgnat_pools,
        "cgnat_allocations": active_cgnat_allocations,
        "ipv6_pools": total_ipv6_pools,
        "ipv6_delegations": active_ipv6_delegations
    }

@app.get("/dashboard/network-overview")
async def get_network_overview(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Advanced network overview for dashboard"""
    sites = db.query(Site).all()
    site_data = []
    
    for site in sites:
        routers = db.query(Router).filter(Router.site_id == site.id).all()
        customers_at_site = db.query(Customer).filter(Customer.site_id == site.id).count()
        
        site_data.append({
            "id": site.id,
            "name": site.name,
            "location": site.address,
            "type": site.site_type,
            "routers": len(routers),
            "customers": customers_at_site,
            "status": "active" if routers else "inactive"
        })
    
    return {"sites": site_data}

# ============================================================================
# COMPANY SETTINGS ENDPOINTS
# ============================================================================

@app.get("/settings", response_model=schemas.CompanySettingsResponse)
async def get_company_settings(
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="User must be associated with a company")
    
    query = db.query(CompanySetting).filter(CompanySetting.company_id == current_user.company_id)
    
    if category:
        query = query.filter(CompanySetting.category == category)
    
    settings = query.all()
    categories = db.query(CompanySetting.category).filter(
        CompanySetting.company_id == current_user.company_id
    ).distinct().all()
    
    return {
        "settings": settings,
        "categories": [cat[0] for cat in categories]
    }

@app.post("/settings", response_model=schemas.CompanySetting)
async def create_company_setting(
    setting: schemas.CompanySettingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="User must be associated with a company")
    
    # Check if setting already exists
    existing = db.query(CompanySetting).filter(
        CompanySetting.company_id == current_user.company_id,
        CompanySetting.setting_key == setting.setting_key
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Setting already exists")
    
    db_setting = CompanySetting(
        company_id=current_user.company_id,
        **setting.dict()
    )
    db.add(db_setting)
    db.commit()
    db.refresh(db_setting)
    return db_setting

@app.put("/settings/{setting_key}", response_model=schemas.CompanySetting)
async def update_company_setting(
    setting_key: str,
    setting_update: schemas.CompanySettingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="User must be associated with a company")
    
    db_setting = db.query(CompanySetting).filter(
        CompanySetting.company_id == current_user.company_id,
        CompanySetting.setting_key == setting_key
    ).first()
    
    if not db_setting:
        raise HTTPException(status_code=404, detail="Setting not found")
    
    for key, value in setting_update.dict(exclude_unset=True).items():
        setattr(db_setting, key, value)
    
    db.commit()
    db.refresh(db_setting)
    return db_setting

@app.delete("/settings/{setting_key}")
async def delete_company_setting(
    setting_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="User must be associated with a company")
    
    db_setting = db.query(CompanySetting).filter(
        CompanySetting.company_id == current_user.company_id,
        CompanySetting.setting_key == setting_key
    ).first()
    
    if not db_setting:
        raise HTTPException(status_code=404, detail="Setting not found")
    
    db.delete(db_setting)
    db.commit()
    return {"message": "Setting deleted successfully"}

@app.post("/settings/bulk")
async def bulk_update_settings(
    settings_update: schemas.SettingsBulkUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="User must be associated with a company")
    
    updated_settings = []
    
    for setting_data in settings_update.settings:
        setting_key = setting_data.get("setting_key")
        setting_value = setting_data.get("setting_value")
        
        if not setting_key or setting_value is None:
            continue
        
        db_setting = db.query(CompanySetting).filter(
            CompanySetting.company_id == current_user.company_id,
            CompanySetting.setting_key == setting_key
        ).first()
        
        if db_setting:
            db_setting.setting_value = setting_value
            updated_settings.append(db_setting)
    
    db.commit()
    return {"message": f"Updated {len(updated_settings)} settings"}

@app.post("/settings/initialize")
async def initialize_default_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="User must be associated with a company")
    
    # Default settings for a new company
    default_settings = [
        # API Settings
        {"setting_key": "splynx_api_url", "setting_value": "", "setting_type": "url", "category": "api", "description": "Splynx API Base URL"},
        {"setting_key": "splynx_api_key", "setting_value": "", "setting_type": "password", "category": "api", "description": "Splynx API Key", "is_encrypted": True},
        {"setting_key": "splynx_api_secret", "setting_value": "", "setting_type": "password", "category": "api", "description": "Splynx API Secret", "is_encrypted": True},
        
        # Network Settings
        {"setting_key": "snmp_community", "setting_value": "public", "setting_type": "string", "category": "network", "description": "Default SNMP Community String"},
        {"setting_key": "snmp_version", "setting_value": "2c", "setting_type": "string", "category": "network", "description": "SNMP Version (1, 2c, 3)"},
        {"setting_key": "lldp_enabled", "setting_value": "true", "setting_type": "boolean", "category": "network", "description": "Enable LLDP Discovery"},
        {"setting_key": "network_discovery_interval", "setting_value": "300", "setting_type": "number", "category": "network", "description": "Network Discovery Interval (seconds)"},
        
        # TP-Link TAUC Settings
        {"setting_key": "tplink_tauc_url", "setting_value": "", "setting_type": "url", "category": "api", "description": "TP-Link TAUC Controller URL"},
        {"setting_key": "tplink_client_id", "setting_value": "", "setting_type": "string", "category": "api", "description": "TP-Link TAUC Client ID"},
        {"setting_key": "tplink_client_secret", "setting_value": "", "setting_type": "password", "category": "api", "description": "TP-Link TAUC Client Secret", "is_encrypted": True},
        
        # Notification Settings
        {"setting_key": "email_smtp_server", "setting_value": "", "setting_type": "string", "category": "notifications", "description": "SMTP Server for Email Notifications"},
        {"setting_key": "email_smtp_port", "setting_value": "587", "setting_type": "number", "category": "notifications", "description": "SMTP Port"},
        {"setting_key": "email_username", "setting_value": "", "setting_type": "string", "category": "notifications", "description": "Email Username"},
        {"setting_key": "email_password", "setting_value": "", "setting_type": "password", "category": "notifications", "description": "Email Password", "is_encrypted": True},
        {"setting_key": "slack_webhook_url", "setting_value": "", "setting_type": "url", "category": "notifications", "description": "Slack Webhook URL for Notifications"},
        
        # General Settings
        {"setting_key": "company_timezone", "setting_value": "UTC", "setting_type": "string", "category": "general", "description": "Company Timezone"},
        {"setting_key": "monitoring_enabled", "setting_value": "true", "setting_type": "boolean", "category": "general", "description": "Enable Network Monitoring"},
        {"setting_key": "auto_provisioning", "setting_value": "false", "setting_type": "boolean", "category": "general", "description": "Enable Auto-Provisioning"}
    ]
    
    created_count = 0
    for setting_data in default_settings:
        # Check if setting already exists
        existing = db.query(CompanySetting).filter(
            CompanySetting.company_id == current_user.company_id,
            CompanySetting.setting_key == setting_data["setting_key"]
        ).first()
        
        if not existing:
            db_setting = CompanySetting(
                company_id=current_user.company_id,
                **setting_data
            )
            db.add(db_setting)
            created_count += 1
    
    db.commit()
    return {"message": f"Initialized {created_count} default settings"}

# ============================================================================
# CUSTOMER MANAGEMENT ENDPOINTS
# ============================================================================

@app.get("/customers", response_model=List[schemas.Customer])
async def get_customers(
    search: Optional[str] = None,
    status: Optional[str] = None,
    connection_type: Optional[str] = None,
    site_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = get_company_filter(db.query(Customer), Customer, current_user)
    if search:
        query = query.filter(Customer.name.contains(search) | Customer.email.contains(search))
    if status:
        query = query.filter(Customer.status == status)
    if connection_type:
        query = query.filter(Customer.connection_type == connection_type)
    if site_id:
        query = query.filter(Customer.site_id == site_id)
    return query.all()

@app.post("/customers", response_model=schemas.Customer)
async def create_customer(
    customer: schemas.CustomerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    customer_data = customer.dict()
    # Set company_id for data isolation
    if current_user.company_id:
        customer_data['company_id'] = current_user.company_id
    
    db_customer = Customer(**customer_data)
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    return db_customer

@app.get("/customers/{customer_id}", response_model=schemas.Customer)
async def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer

@app.put("/customers/{customer_id}", response_model=schemas.Customer)
async def update_customer(
    customer_id: int,
    customer_update: schemas.CustomerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    for field, value in customer_update.dict(exclude_unset=True).items():
        setattr(customer, field, value)
    
    db.commit()
    db.refresh(customer)
    return customer


@app.delete("/customers/{customer_id}")
async def delete_customer(
        customer_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Check if user has permission to delete this customer
    if current_user.company_id and customer.company_id != current_user.company_id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this customer")

    # Delete related records first to avoid foreign key constraints
    # Delete customer invoices
    db.query(Invoice).filter(Invoice.customer_id == customer_id).delete()

    # Delete customer tickets
    db.query(Ticket).filter(Ticket.customer_id == customer_id).delete()

    # Delete customer VLANs
    db.query(CustomerVLAN).filter(CustomerVLAN.customer_id == customer_id).delete()

    # Delete DHCP leases
    db.query(DHCPLease).filter(DHCPLease.customer_id == customer_id).delete()

    # Delete CGNAT allocations
    db.query(CGNATAllocation).filter(CGNATAllocation.customer_id == customer_id).delete()

    # Delete IPv6 delegations
    db.query(IPv6Delegation).filter(IPv6Delegation.customer_id == customer_id).delete()

    # Delete the customer
    db.delete(customer)
    db.commit()

    return {"message": f"Customer {customer.name} has been successfully deleted"}

@app.get("/customers/{customer_id}/network-info")
async def get_customer_network_info(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get comprehensive network information for a customer"""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Get IP assignments
    ip_assignments = db.query(IPAssignment).filter(IPAssignment.customer_id == customer_id).all()
    
    # Get VLAN assignments
    vlan_assignments = db.query(CustomerVLAN).filter(CustomerVLAN.customer_id == customer_id).all()
    
    # Get CGNAT allocations
    cgnat_allocations = db.query(CGNATAllocation).filter(CGNATAllocation.customer_id == customer_id).all()
    
    # Get IPv6 delegations
    ipv6_delegations = db.query(IPv6Delegation).filter(IPv6Delegation.customer_id == customer_id).all()
    
    # Get DHCP leases
    dhcp_leases = db.query(DHCPLease).filter(DHCPLease.customer_id == customer_id).all()
    
    return {
        "customer_id": customer_id,
        "customer_name": customer.name,
        "connection_type": customer.connection_type,
        "ip_assignments": ip_assignments,
        "vlan_assignments": vlan_assignments,
        "cgnat_allocations": cgnat_allocations,
        "ipv6_delegations": ipv6_delegations,
        "dhcp_leases": dhcp_leases
    }

# ============================================================================
# SITE MANAGEMENT ENDPOINTS
# ============================================================================

@app.get("/sites", response_model=List[schemas.Site])
async def get_sites(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return db.query(Site).all()

@app.post("/sites", response_model=schemas.Site)
async def create_site(
    site: schemas.SiteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    db_site = Site(**site.dict())
    db.add(db_site)
    db.commit()
    db.refresh(db_site)
    return db_site

@app.get("/sites/{site_id}", response_model=schemas.Site)
async def get_site(
    site_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    return site

@app.get("/sites/{site_id}/network-topology")
async def get_site_network_topology(
    site_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get network topology for a site - Ubiquiti-like visualization data"""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    
    # Get routers at this site
    routers = db.query(Router).filter(Router.site_id == site_id).all()
    
    # Get equipment at this site
    equipment = db.query(Equipment).filter(Equipment.site_id == site_id).all()
    
    # Get IP subnets at this site
    subnets = db.query(IPSubnet).filter(IPSubnet.site_id == site_id).all()
    
    # Build topology data
    topology_data = {
        "site": {
            "id": site.id,
            "name": site.name,
            "location": site.address,
            "coordinates": {"lat": site.latitude, "lng": site.longitude} if site.latitude and site.longitude else None
        },
        "routers": [],
        "equipment": [],
        "subnets": [],
        "connections": []
    }
    
    for router in routers:
        interfaces = db.query(NetworkInterface).filter(NetworkInterface.router_id == router.id).all()
        monitoring = db.query(NetworkMonitoring).filter(
            NetworkMonitoring.router_id == router.id
        ).order_by(NetworkMonitoring.timestamp.desc()).first()
        
        topology_data["routers"].append({
            "id": router.id,
            "name": router.name,
            "model": router.model,
            "ip_address": router.ip_address,
            "status": router.status,
            "uptime": monitoring.uptime if monitoring else None,
            "cpu_usage": monitoring.cpu_usage if monitoring else None,
            "memory_usage": monitoring.memory_usage if monitoring else None,
            "interfaces": [{"name": i.name, "status": i.status, "ip": i.ip_address} for i in interfaces]
        })
    
    for eq in equipment:
        topology_data["equipment"].append({
            "id": eq.id,
            "name": eq.name,
            "type": eq.equipment_type,
            "model": eq.model,
            "serial_number": eq.serial_number,
            "status": eq.status,
            "location": eq.location
        })
    
    for subnet in subnets:
        assignments = db.query(IPAssignment).filter(IPAssignment.subnet_id == subnet.id).count()
        topology_data["subnets"].append({
            "id": subnet.id,
            "name": subnet.name,
            "network": subnet.network,
            "vlan_id": subnet.vlan_id,
            "type": subnet.subnet_type,
            "assignments": assignments
        })
    
    return topology_data

# ============================================================================
# ROUTER MANAGEMENT ENDPOINTS
# ============================================================================

@app.get("/routers", response_model=List[schemas.Router])
async def get_routers(
    site_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Router)
    if site_id:
        query = query.filter(Router.site_id == site_id)
    if status:
        query = query.filter(Router.status == status)
    return query.all()

@app.post("/routers", response_model=schemas.Router)
async def create_router(
    router: schemas.RouterCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    db_router = Router(**router.dict())
    db.add(db_router)
    db.commit()
    db.refresh(db_router)
    return db_router

@app.post("/routers/onboard")
async def onboard_router(
    router_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Complete router onboarding with automatic configuration generation"""
    try:
        # Create the router
        db_router = Router(**router_data)
        db.add(db_router)
        db.commit()
        db.refresh(db_router)
        
        # Generate Mikrotik configuration
        config = generate_mikrotik_config(router_data)
        
        # Auto-create corresponding IP subnet if provided
        if router_data.get("customer_subnet"):
            subnet_name = f"{db_router.name}-customers"
            subnet_network = router_data["customer_subnet"]
            
            db_subnet = IPSubnet(
                name=subnet_name,
                network=subnet_network,
                gateway=subnet_network.split('/')[0],
                vlan_id=router_data.get("customer_vlan_start", 100),
                subnet_type="customer",
                site_id=db_router.site_id,
                description=f"Auto-created customer subnet for {db_router.name}"
            )
            db.add(db_subnet)
            db.commit()
        
        return {
            "success": True,
            "router_id": db_router.id,
            "message": f"Router {db_router.name} successfully onboarded",
            "configuration": config,
            "next_steps": [
                "1. Connect to your Mikrotik router via Winbox or SSH",
                "2. Copy and paste the generated configuration commands",
                "3. Verify the configuration is applied correctly",
                "4. Test customer connectivity and isolation",
                "5. Monitor the router status in LynxCRM dashboard"
            ]
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Router onboarding failed: {str(e)}")

def generate_mikrotik_config(router_data):
    """Generate Mikrotik RouterOS configuration"""
    config = []
    
    # Basic system configuration
    config.append("# Basic System Configuration")
    config.append(f"/system identity set name=\"{router_data['name']}\"")
    config.append(f"/ip address add address={router_data['ip_address']} interface=ether1")
    
    # VLAN configuration for customer isolation
    if router_data.get("customer_vlan_start"):
        config.append("\n# Customer VLAN Configuration")
        config.append("/interface vlan")
        vlan_start = router_data["customer_vlan_start"]
        for i in range(10):  # Create 10 VLANs
            vlan_id = vlan_start + i
            config.append(f"add interface=ether2 name=customer-vlan{vlan_id} vlan-id={vlan_id}")
    
    # DHCP configuration with Option 82
    if router_data.get("enable_option82"):
        config.append("\n# DHCP Configuration with Option 82")
        config.append("/ip dhcp-server option")
        config.append("add code=82 name=option82 value=0x0000")
        config.append("/ip dhcp-server")
        config.append("add interface=customer-vlan100 name=dhcp-customers option=option82")
    
    # Customer subnet configuration
    if router_data.get("customer_subnet"):
        config.append(f"\n# Customer Subnet Configuration")
        config.append(f"/ip address add address={router_data['customer_subnet']} interface=customer-vlan100")
    
    # Firewall rules for customer isolation
    config.append("\n# Firewall Rules for Customer Isolation")
    config.append("/ip firewall filter")
    config.append("add action=drop chain=forward comment=\"Block inter-customer communication\" src-address-list=customers dst-address-list=customers")
    config.append("add action=accept chain=forward comment=\"Allow customer internet access\"")
    
    return "\n".join(config)

@app.get("/routers/{router_id}/monitoring")
async def get_router_monitoring(
    router_id: int,
    hours: int = 24,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get monitoring data for a router - Ubiquiti-like interface"""
    router = db.query(Router).filter(Router.id == router_id).first()
    if not router:
        raise HTTPException(status_code=404, detail="Router not found")
    
    # Get monitoring data from the last X hours
    from datetime import datetime, timedelta
    since = datetime.utcnow() - timedelta(hours=hours)
    
    monitoring_data = db.query(NetworkMonitoring).filter(
        NetworkMonitoring.router_id == router_id,
        NetworkMonitoring.timestamp >= since
    ).order_by(NetworkMonitoring.timestamp.asc()).all()
    
    # Get interfaces
    interfaces = db.query(NetworkInterface).filter(NetworkInterface.router_id == router_id).all()
    
    # Get customer VLANs
    customer_vlans = db.query(CustomerVLAN).filter(CustomerVLAN.router_id == router_id).all()
    
    return {
        "router": {
            "id": router.id,
            "name": router.name,
            "model": router.model,
            "ip_address": router.ip_address,
            "status": router.status
        },
        "monitoring_data": monitoring_data,
        "interfaces": interfaces,
        "customer_vlans": customer_vlans,
        "statistics": {
            "uptime": monitoring_data[-1].uptime if monitoring_data else None,
            "cpu_usage": monitoring_data[-1].cpu_usage if monitoring_data else None,
            "memory_usage": monitoring_data[-1].memory_usage if monitoring_data else None,
            "temperature": monitoring_data[-1].temperature if monitoring_data else None
        }
    }

@app.get("/routers/{router_id}/vlans")
async def get_router_customer_vlans(
    router_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all customer VLANs for a specific router"""
    router = db.query(Router).filter(Router.id == router_id).first()
    if not router:
        raise HTTPException(status_code=404, detail="Router not found")
    
    vlans = db.query(CustomerVLAN).filter(CustomerVLAN.router_id == router_id).all()
    return vlans

@app.post("/customers/{customer_id}/assign-vlan")
async def assign_customer_vlan(
    customer_id: int,
    router_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Automatically assign a VLAN to a customer"""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    router = db.query(Router).filter(Router.id == router_id).first()
    if not router:
        raise HTTPException(status_code=404, detail="Router not found")
    
    # Check if customer already has a VLAN on this router
    existing_vlan = db.query(CustomerVLAN).filter(
        CustomerVLAN.customer_id == customer_id,
        CustomerVLAN.router_id == router_id
    ).first()
    
    if existing_vlan:
        return {"message": "Customer already has a VLAN assigned", "vlan_id": existing_vlan.vlan_id}
    
    # Find next available VLAN
    used_vlans = db.query(CustomerVLAN.vlan_id).filter(CustomerVLAN.router_id == router_id).all()
    used_vlan_ids = [vlan[0] for vlan in used_vlans]
    
    # Start from the router's customer VLAN start number
    next_vlan = router.customer_vlan_start or 100
    while next_vlan in used_vlan_ids:
        next_vlan += 1
    
    # Create the VLAN assignment
    customer_vlan = CustomerVLAN(
        customer_id=customer_id,
        router_id=router_id,
        vlan_id=next_vlan,
        status="active",
        isolation_enabled=True
    )
    
    db.add(customer_vlan)
    db.commit()
    db.refresh(customer_vlan)
    
    return {
        "message": f"VLAN {next_vlan} assigned to customer {customer.name}",
        "vlan_id": next_vlan,
        "customer_vlan_id": customer_vlan.id
    }

# ============================================================================
# IP MANAGEMENT ENDPOINTS
# ============================================================================

@app.get("/ip-subnets")
async def get_ip_subnets(
    site_id: Optional[int] = None,
    subnet_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(IPSubnet)
    if site_id:
        query = query.filter(IPSubnet.site_id == site_id)
    if subnet_type:
        query = query.filter(IPSubnet.subnet_type == subnet_type)
    return query.all()

@app.post("/ip-subnets")
async def create_ip_subnet(
    subnet_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    db_subnet = IPSubnet(**subnet_data)
    db.add(db_subnet)
    db.commit()
    db.refresh(db_subnet)
    return db_subnet

@app.get("/ip-assignments")
async def get_ip_assignments(
    subnet_id: Optional[int] = None,
    customer_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(IPAssignment)
    if subnet_id:
        query = query.filter(IPAssignment.subnet_id == subnet_id)
    if customer_id:
        query = query.filter(IPAssignment.customer_id == customer_id)
    return query.all()

@app.post("/ip-assignments")
async def create_ip_assignment(
    assignment_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    db_assignment = IPAssignment(**assignment_data)
    db.add(db_assignment)
    db.commit()
    db.refresh(db_assignment)
    return db_assignment

# ============================================================================
# CGNAT MANAGEMENT ENDPOINTS
# ============================================================================

@app.get("/cgnat/pools")
async def get_cgnat_pools(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    pools = db.query(CGNATPool).all()
    pool_data = []
    
    for pool in pools:
        allocations = db.query(CGNATAllocation).filter(CGNATAllocation.pool_id == pool.id).count()
        utilization = (allocations / pool.max_users * 100) if pool.max_users > 0 else 0
        
        pool_data.append({
            "id": pool.id,
            "name": pool.name,
            "public_ip_range": pool.public_ip_range,
            "port_range": f"{pool.port_range_start}-{pool.port_range_end}",
            "max_users": pool.max_users,
            "current_users": allocations,
            "utilization": round(utilization, 2),
            "ports_per_user": pool.ports_per_user,
            "status": pool.status
        })
    
    return pool_data

@app.post("/cgnat/pools")
async def create_cgnat_pool(
    pool_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    pool = CGNATPool(**pool_data)
    db.add(pool)
    db.commit()
    db.refresh(pool)
    return pool

@app.post("/cgnat/allocate")
async def allocate_cgnat_ports(
    customer_id: int,
    pool_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Allocate CGNAT ports to a customer - Splynx-like functionality"""
    pool = db.query(CGNATPool).filter(CGNATPool.id == pool_id).first()
    if not pool:
        raise HTTPException(status_code=404, detail="CGNAT pool not found")
    
    # Check if customer already has allocation
    existing = db.query(CGNATAllocation).filter(
        CGNATAllocation.customer_id == customer_id,
        CGNATAllocation.pool_id == pool_id,
        CGNATAllocation.status == "active"
    ).first()
    
    if existing:
        return {"message": "Customer already has CGNAT allocation", "allocation": existing}
    
    if pool.current_users >= pool.max_users:
        raise HTTPException(status_code=400, detail="CGNAT pool is full")
    
    # Calculate port range
    start_port = pool.port_range_start + (pool.current_users * pool.ports_per_user)
    end_port = start_port + pool.ports_per_user - 1
    
    allocation = CGNATAllocation(
        pool_id=pool_id,
        customer_id=customer_id,
        port_range_start=start_port,
        port_range_end=end_port,
        status="active"
    )
    
    db.add(allocation)
    pool.current_users += 1
    db.commit()
    db.refresh(allocation)
    
    return allocation

@app.get("/cgnat/sessions")
async def get_cgnat_sessions(
    customer_id: Optional[int] = None,
    allocation_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get CGNAT session tracking data"""
    query = db.query(CGNATSession)
    if customer_id:
        query = query.filter(CGNATSession.customer_id == customer_id)
    if allocation_id:
        query = query.filter(CGNATSession.allocation_id == allocation_id)
    
    return query.order_by(CGNATSession.start_time.desc()).limit(1000).all()

# ============================================================================
# IPv6 MANAGEMENT ENDPOINTS
# ============================================================================

@app.get("/ipv6/pools")
async def get_ipv6_pools(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    pools = db.query(IPv6Pool).all()
    pool_data = []
    
    for pool in pools:
        delegations = db.query(IPv6Delegation).filter(IPv6Delegation.pool_id == pool.id).count()
        
        pool_data.append({
            "id": pool.id,
            "name": pool.name,
            "prefix": pool.prefix,
            "delegation_size": pool.delegation_size,
            "total_delegations": delegations,
            "status": pool.status
        })
    
    return pool_data

@app.post("/ipv6/pools")
async def create_ipv6_pool(
    pool_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    pool = IPv6Pool(**pool_data)
    db.add(pool)
    db.commit()
    db.refresh(pool)
    return pool

@app.post("/ipv6/delegate")
async def delegate_ipv6_prefix(
    customer_id: int,
    pool_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delegate IPv6 prefix to a customer"""
    pool = db.query(IPv6Pool).filter(IPv6Pool.id == pool_id).first()
    if not pool:
        raise HTTPException(status_code=404, detail="IPv6 pool not found")
    
    # Check if customer already has delegation
    existing = db.query(IPv6Delegation).filter(
        IPv6Delegation.customer_id == customer_id,
        IPv6Delegation.pool_id == pool_id,
        IPv6Delegation.status == "active"
    ).first()
    
    if existing:
        return {"message": "Customer already has IPv6 delegation", "delegation": existing}
    
    # Simple delegation logic (in production, use proper IPv6 subnetting)
    existing_delegations = db.query(IPv6Delegation).filter(IPv6Delegation.pool_id == pool_id).count()
    
    delegation = IPv6Delegation(
        pool_id=pool_id,
        customer_id=customer_id,
        delegated_prefix=f"{pool.prefix.split('/')[0]}:{existing_delegations + 1}::/{pool.delegation_size}",
        prefix_length=pool.delegation_size,
        status="active"
    )
    
    db.add(delegation)
    db.commit()
    db.refresh(delegation)
    
    return delegation

# ============================================================================
# DHCP MANAGEMENT ENDPOINTS
# ============================================================================

@app.get("/dhcp/leases")
async def get_dhcp_leases(
    router_id: Optional[int] = None,
    customer_id: Optional[int] = None,
    active_only: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get DHCP leases with Option 82 tracking"""
    query = db.query(DHCPLease)
    if router_id:
        query = query.filter(DHCPLease.router_id == router_id)
    if customer_id:
        query = query.filter(DHCPLease.customer_id == customer_id)
    if active_only:
        query = query.filter(DHCPLease.status == "active")
    
    return query.order_by(DHCPLease.lease_time.desc()).all()

@app.post("/dhcp/leases")
async def create_dhcp_lease(
    lease_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create DHCP lease entry"""
    lease = DHCPLease(**lease_data)
    db.add(lease)
    db.commit()
    db.refresh(lease)
    return lease

# ============================================================================
# EQUIPMENT MANAGEMENT ENDPOINTS
# ============================================================================

@app.get("/equipment")
async def get_equipment(
    equipment_type: Optional[str] = None,
    site_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Equipment)
    if equipment_type:
        query = query.filter(Equipment.equipment_type == equipment_type)
    if site_id:
        query = query.filter(Equipment.site_id == site_id)
    if status:
        query = query.filter(Equipment.status == status)
    
    return query.all()

@app.post("/equipment")
async def create_equipment(
    equipment_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    db_equipment = Equipment(**equipment_data)
    db.add(db_equipment)
    db.commit()
    db.refresh(db_equipment)
    return db_equipment

@app.get("/equipment/{equipment_id}")
async def get_equipment_by_id(
    equipment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    equipment = db.query(Equipment).filter(Equipment.id == equipment_id).first()
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")
    return equipment

# ============================================================================
# SERVICE ORDER MANAGEMENT ENDPOINTS
# ============================================================================

@app.get("/service-orders")
async def get_service_orders(
    status: Optional[str] = None,
    customer_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(ServiceOrder)
    if status:
        query = query.filter(ServiceOrder.status == status)
    if customer_id:
        query = query.filter(ServiceOrder.customer_id == customer_id)
    
    return query.order_by(ServiceOrder.created_at.desc()).all()

@app.post("/service-orders")
async def create_service_order(
    order_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    db_order = ServiceOrder(**order_data)
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    return db_order

@app.put("/service-orders/{order_id}/status")
async def update_order_status(
    order_id: int,
    status_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    order = db.query(ServiceOrder).filter(ServiceOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Service order not found")
    
    order.status = status_data["status"]
    if status_data["status"] == "completed":
        order.completed_date = datetime.utcnow()
    
    db.commit()
    db.refresh(order)
    return order

# ============================================================================
# BASIC CRM ENDPOINTS (EXISTING)
# ============================================================================

@app.get("/service-plans", response_model=List[schemas.ServicePlan])
async def get_service_plans(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(ServicePlan).all()


@app.post("/service-plans", response_model=schemas.ServicePlan)
async def create_service_plan(
        service_plan: schemas.ServicePlanCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    plan_data = service_plan.model_dump()
    # Set company_id for data isolation
    if current_user.company_id:
        plan_data['company_id'] = current_user.company_id

    db_plan = ServicePlan(**plan_data)
    db.add(db_plan)
    db.commit()
    db.refresh(db_plan)
    return db_plan


@app.get("/service-plans/{plan_id}", response_model=schemas.ServicePlan)
async def get_service_plan(
        plan_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    plan = db.query(ServicePlan).filter(ServicePlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Service plan not found")
    return plan


@app.put("/service-plans/{plan_id}", response_model=schemas.ServicePlan)
async def update_service_plan(
        plan_id: int,
        service_plan: schemas.ServicePlanUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    plan = db.query(ServicePlan).filter(ServicePlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Service plan not found")

    for field, value in service_plan.model_dump(exclude_unset=True).items():
        setattr(plan, field, value)

    db.commit()
    db.refresh(plan)
    return plan


@app.delete("/service-plans/{plan_id}")
async def delete_service_plan(
        plan_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    plan = db.query(ServicePlan).filter(ServicePlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Service plan not found")

    # Check if any customers are using this plan
    customers_using_plan = db.query(Customer).filter(Customer.service_plan_id == plan_id).count()
    if customers_using_plan > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete service plan. {customers_using_plan} customers are currently using this plan."
        )

    db.delete(plan)
    db.commit()
    return {"message": f"Service plan '{plan.name}' has been successfully deleted"}

@app.get("/invoices", response_model=List[schemas.Invoice])
async def get_invoices(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return db.query(Invoice).all()

@app.post("/invoices", response_model=schemas.Invoice)
async def create_invoice(
    invoice: schemas.InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    db_invoice = Invoice(**invoice.dict())
    db.add(db_invoice)
    db.commit()
    db.refresh(db_invoice)
    return db_invoice

@app.get("/tickets", response_model=List[schemas.Ticket])
async def get_tickets(
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Ticket)
    if status_filter:
        query = query.filter(Ticket.status == status_filter)
    return query.all()

@app.post("/tickets", response_model=schemas.Ticket)
async def create_ticket(
    ticket: schemas.TicketCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    db_ticket = Ticket(**ticket.dict())
    db.add(db_ticket)
    db.commit()
    db.refresh(db_ticket)
    return db_ticket

@app.post("/tickets/{ticket_id}/comments", response_model=schemas.TicketComment)
async def add_ticket_comment(
    ticket_id: int,
    comment: schemas.TicketCommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    
    db_comment = TicketComment(ticket_id=ticket_id, **comment.dict())
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)
    return db_comment


@app.put("/invoices/{invoice_id}", response_model=schemas.Invoice)
async def update_invoice(
        invoice_id: int,
        invoice_update: schemas.InvoiceUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    for key, value in invoice_update.model_dump(exclude_unset=True).items():
        setattr(invoice, key, value)

    db.commit()
    db.refresh(invoice)
    return invoice


@app.delete("/invoices/{invoice_id}")
async def delete_invoice(
        invoice_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    db.delete(invoice)
    db.commit()
    return {"message": f"Invoice ${invoice.amount} has been successfully deleted"}


@app.put("/tickets/{ticket_id}", response_model=schemas.Ticket)
async def update_ticket(
        ticket_id: int,
        ticket_update: schemas.TicketUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    for key, value in ticket_update.model_dump(exclude_unset=True).items():
        setattr(ticket, key, value)

    db.commit()
    db.refresh(ticket)
    return ticket


@app.delete("/tickets/{ticket_id}")
async def delete_ticket(
        ticket_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Delete related comments first
    db.query(TicketComment).filter(TicketComment.ticket_id == ticket_id).delete()

    db.delete(ticket)
    db.commit()
    return {"message": f"Ticket '{ticket.title}' has been successfully deleted"}

# ============================================================================
# SERVICE ORDERS ENDPOINTS
# ============================================================================

@app.get("/service-orders", response_model=List[schemas.ServiceOrder])
async def get_service_orders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return db.query(ServiceOrder).all()

@app.post("/service-orders", response_model=schemas.ServiceOrder)
async def create_service_order(
    order: schemas.ServiceOrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    db_order = ServiceOrder(**order.dict())
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    return db_order

# ============================================================================
# CONTRACTORS & INSTALLERS ENDPOINTS
# ============================================================================

@app.get("/contractors")
async def get_contractors(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all contractors"""
    return [
        {
            "id": 1,
            "name": "John Smith",
            "email": "john.contractor@company.com",
            "phone": "555-123-4567",
            "role": "contractor",
            "specialties": "Fiber Installation, Network Setup",
            "status": "available",
            "created_at": "2025-01-15T10:30:00"
        },
        {
            "id": 2,
            "name": "Mike Johnson",
            "email": "mike.contractor@company.com",
            "phone": "555-234-5678",
            "role": "contractor",
            "specialties": "Equipment Maintenance, Troubleshooting",
            "status": "busy",
            "created_at": "2025-02-01T14:15:00"
        },
        {
            "id": 3,
            "name": "Sarah Davis",
            "email": "sarah.contractor@company.com",
            "phone": "555-345-6789",
            "role": "contractor",
            "specialties": "Customer Premises Equipment",
            "status": "available",
            "created_at": "2025-01-20T09:45:00"
        }
    ]

@app.get("/installers")
async def get_installers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all installers"""
    return [
        {
            "id": 4,
            "name": "Alex Chen",
            "email": "alex.installer@company.com",
            "phone": "555-456-7890",
            "role": "installer",
            "specialties": "Residential Installation, Wireless Setup",
            "status": "available",
            "created_at": "2025-01-10T11:20:00"
        },
        {
            "id": 5,
            "name": "Lisa Wilson",
            "email": "lisa.installer@company.com",
            "phone": "555-567-8901",
            "role": "installer",
            "specialties": "Business Installation, Network Configuration",
            "status": "busy",
            "created_at": "2025-01-25T16:30:00"
        },
        {
            "id": 6,
            "name": "David Brown",
            "email": "david.installer@company.com",
            "phone": "555-678-9012",
            "role": "installer",
            "specialties": "Fiber Termination, Cable Management",
            "status": "unavailable",
            "created_at": "2025-02-05T08:15:00"
        }
    ]

# ============================================================================
# USER MANAGEMENT ENDPOINTS
# ============================================================================

@app.get("/users")
async def get_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all users"""
    users = db.query(User).all()
    return [
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": getattr(user, 'full_name', ''),
            "role": getattr(user, 'role', 'user'),
            "is_active": getattr(user, 'is_active', True),
            "created_at": user.created_at
        }
        for user in users
    ]

@app.post("/users")
async def create_user(
    user_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new user"""
    from .auth import get_password_hash
    
    # Check if username already exists
    existing_user = db.query(User).filter(User.username == user_data.get("username")).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    # Check if email already exists
    existing_email = db.query(User).filter(User.email == user_data.get("email")).first()
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already exists")
    
    # Hash the password
    hashed_password = get_password_hash(user_data.get("password", ""))
    
    # Create user
    db_user = User(
        username=user_data.get("username"),
        email=user_data.get("email"),
        password_hash=hashed_password
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return {
        "id": db_user.id,
        "username": db_user.username,
        "email": db_user.email,
        "full_name": getattr(db_user, 'full_name', ''),
        "role": getattr(db_user, 'role', 'user'),
        "is_active": getattr(db_user, 'is_active', True),
        "created_at": db_user.created_at
    }

@app.get("/users/{user_id}")
async def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get user by ID"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": getattr(user, 'full_name', ''),
        "role": getattr(user, 'role', 'user'),
        "is_active": getattr(user, 'is_active', True),
        "created_at": user.created_at
    }

@app.put("/users/{user_id}")
async def update_user(
    user_id: int,
    user_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update user"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update fields
    for field, value in user_data.items():
        if hasattr(user, field) and field != "password":
            setattr(user, field, value)
    
    # Handle password update
    if "password" in user_data and user_data["password"]:
        from .auth import get_password_hash
        user.password_hash = get_password_hash(user_data["password"])
    
    db.commit()
    db.refresh(user)
    
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": getattr(user, 'full_name', ''),
        "role": getattr(user, 'role', 'user'),
        "is_active": getattr(user, 'is_active', True),
        "created_at": user.created_at
    }

@app.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete user"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    
    db.delete(user)
    db.commit()
    
    return {"message": "User deleted successfully"}

# ============================================================================
# TPLINK TAUC DEVICE MANAGEMENT ENDPOINTS
# ============================================================================

# TPLink service will be imported when needed to avoid startup issues

@app.get("/tplink/devices")
async def get_tplink_devices(
    device_type: Optional[str] = None,
    status: Optional[str] = None,
    site_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all TPLink devices with optional filtering"""
    try:
        query = db.query(TPLinkDevice)
        
        if device_type:
            query = query.filter(TPLinkDevice.device_type == device_type)
        if status:
            query = query.filter(TPLinkDevice.status == status)
        if site_id:
            query = query.filter(TPLinkDevice.site_id == site_id)
        
        devices = query.order_by(TPLinkDevice.name).all()
        return [
            {
                "id": device.id,
                "device_id": device.device_id,
                "sn": device.sn,
                "mac": device.mac,
                "name": device.name,
                "model": device.model,
                "device_type": device.device_type,
                "firmware_version": device.firmware_version,
                "ip_address": device.ip_address,
                "management_domain": device.management_domain,
                "status": device.status,
                "site_id": device.site_id,
                "customer_id": device.customer_id,
                "parent_device_id": device.parent_device_id,
                "temperature": device.temperature,
                "power_consumption": device.power_consumption,
                "uptime": device.uptime,
                "alarm_count": device.alarm_count,
                "last_seen": device.last_seen,
                "created_at": device.created_at,
                "updated_at": device.updated_at
            }
            for device in devices
        ]
    except Exception as e:
        # Return empty list if table doesn't exist yet
        return []

@app.post("/tplink/devices", response_model=schemas.TPLinkDevice)
async def create_tplink_device(
    device: schemas.TPLinkDeviceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Add a new TPLink device to management"""
    db_device = TPLinkDevice(**device.dict())
    db.add(db_device)
    db.commit()
    db.refresh(db_device)
    return db_device

@app.get("/tplink/devices/{device_id}", response_model=schemas.TPLinkDevice)
async def get_tplink_device(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get specific TPLink device details"""
    device = db.query(TPLinkDevice).filter(TPLinkDevice.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device

@app.put("/tplink/devices/{device_id}", response_model=schemas.TPLinkDevice)
async def update_tplink_device(
    device_id: int,
    device_update: schemas.TPLinkDeviceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update TPLink device configuration"""
    device = db.query(TPLinkDevice).filter(TPLinkDevice.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    for field, value in device_update.dict(exclude_unset=True).items():
        setattr(device, field, value)
    
    device.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(device)
    return device

@app.delete("/tplink/devices/{device_id}")
async def delete_tplink_device(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Remove TPLink device from management"""
    device = db.query(TPLinkDevice).filter(TPLinkDevice.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    db.delete(device)
    db.commit()
    return {"message": "Device deleted successfully"}

# Device Status and Monitoring
@app.get("/tplink/devices/{device_id}/status", response_model=schemas.DeviceStatusResponse)
async def get_device_status(
    device_id: int,
    refresh: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get real-time device status"""
    device = db.query(TPLinkDevice).filter(TPLinkDevice.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    if refresh and device.management_domain and device.client_id:
        # Get real-time status from TAUC API
        try:
            from .services.tplink_tauc import create_tplink_service
            service = create_tplink_service(device.management_domain, device.client_id, device.client_secret)
            device_info = await service.get_device_info(device.device_id)
            
            # Update device with latest info
            device.status = device_info.status
            device.last_seen = device_info.last_seen
            device.uptime = getattr(device_info, 'uptime', device.uptime)
            device.updated_at = datetime.utcnow()
            db.commit()
        except Exception as e:
            print(f"Error refreshing device status: {e}")
    
    interface_count = db.query(TPLinkInterface).filter(TPLinkInterface.device_id == device.id).count()
    
    return schemas.DeviceStatusResponse(
        device_id=device.device_id,
        status=device.status,
        uptime=device.uptime,
        temperature=device.temperature,
        power_consumption=device.power_consumption,
        alarm_count=device.alarm_count,
        interface_count=interface_count,
        last_updated=device.updated_at
    )

# Interface Management
@app.get("/tplink/devices/{device_id}/interfaces", response_model=List[schemas.TPLinkInterface])
async def get_device_interfaces(
    device_id: int,
    interface_type: Optional[str] = None,
    refresh: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get device interface list"""
    device = db.query(TPLinkDevice).filter(TPLinkDevice.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    if refresh and device.network_id:
        # Refresh interface data from TAUC API
        try:
            service = create_tplink_service(device.management_domain, device.client_id, device.client_secret)
            interfaces = await service.get_ethernet_interfaces(device.network_id, refresh=True)
            
            # Update database with latest interface data
            for iface in interfaces:
                db_interface = db.query(TPLinkInterface).filter(
                    TPLinkInterface.device_id == device.id,
                    TPLinkInterface.interface_name == iface.interface_name
                ).first()
                
                if not db_interface:
                    db_interface = TPLinkInterface(
                        device_id=device.id,
                        interface_name=iface.interface_name,
                        interface_type="ethernet"
                    )
                    db.add(db_interface)
                
                # Update interface data
                db_interface.alias = iface.alias
                db_interface.status = iface.status
                db_interface.speed = iface.speed
                db_interface.duplex = iface.duplex
                db_interface.mtu = iface.mtu
                db_interface.mac_address = iface.mac_address
                db_interface.rx_bytes = iface.rx_bytes
                db_interface.tx_bytes = iface.tx_bytes
                db_interface.rx_packets = iface.rx_packets
                db_interface.tx_packets = iface.tx_packets
                db_interface.last_updated = datetime.utcnow()
            
            db.commit()
        except Exception as e:
            print(f"Error refreshing interfaces: {e}")
    
    query = db.query(TPLinkInterface).filter(TPLinkInterface.device_id == device.id)
    if interface_type:
        query = query.filter(TPLinkInterface.interface_type == interface_type)
    
    return query.order_by(TPLinkInterface.interface_name).all()

# Port Control
@app.post("/tplink/devices/{device_id}/interfaces/{interface_name}/control")
async def control_port(
    device_id: int,
    interface_name: str,
    control_request: schemas.PortControlRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Control individual port (enable/disable/configure)"""
    device = db.query(TPLinkDevice).filter(TPLinkDevice.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    if not device.management_domain or not device.client_id:
        raise HTTPException(status_code=400, detail="Device not configured for API access")
    
    try:
        service = create_tplink_service(device.management_domain, device.client_id, device.client_secret)
        
        if control_request.action == "enable":
            success = await service.enable_port(device.device_id, interface_name)
        elif control_request.action == "disable":
            success = await service.disable_port(device.device_id, interface_name)
        elif control_request.action == "configure":
            from .services.tplink_tauc import PortConfig
            port_config = PortConfig(
                port_id=interface_name,
                interface_name=interface_name,
                enabled=True,
                speed=control_request.speed or "auto",
                duplex=control_request.duplex or "auto",
                vlan_id=control_request.vlan_id,
                description=control_request.description or ""
            )
            success = await service.configure_port(device.device_id, port_config)
        else:
            raise HTTPException(status_code=400, detail="Invalid action")
        
        if success:
            # Update local interface record
            db_interface = db.query(TPLinkInterface).filter(
                TPLinkInterface.device_id == device.id,
                TPLinkInterface.interface_name == interface_name
            ).first()
            
            if db_interface:
                if control_request.action == "enable":
                    db_interface.admin_status = "enabled"
                elif control_request.action == "disable":
                    db_interface.admin_status = "disabled"
                elif control_request.action == "configure":
                    if control_request.speed:
                        db_interface.speed = control_request.speed
                    if control_request.duplex:
                        db_interface.duplex = control_request.duplex
                    if control_request.vlan_id:
                        db_interface.vlan_id = control_request.vlan_id
                    if control_request.description:
                        db_interface.description = control_request.description
                
                db_interface.last_updated = datetime.utcnow()
                db.commit()
            
            return {"message": f"Port {interface_name} {control_request.action} successful"}
        else:
            raise HTTPException(status_code=500, detail=f"Failed to {control_request.action} port")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error controlling port: {str(e)}")

@app.post("/tplink/devices/{device_id}/bulk-port-control")
async def bulk_port_control(
    device_id: int,
    bulk_request: schemas.BulkPortControlRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Perform bulk port operations"""
    device = db.query(TPLinkDevice).filter(TPLinkDevice.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    if not device.management_domain or not device.client_id:
        raise HTTPException(status_code=400, detail="Device not configured for API access")
    
    try:
        service = create_tplink_service(device.management_domain, device.client_id, device.client_secret)
        results = await service.bulk_port_operation(bulk_request.operations)
        
        successful_ops = sum(results)
        total_ops = len(results)
        
        return {
            "message": f"Bulk operation completed: {successful_ops}/{total_ops} operations successful",
            "results": results
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in bulk operation: {str(e)}")

# OLT Specific Endpoints
@app.get("/tplink/olt/{device_id}/status", response_model=schemas.OLTStatusResponse)
async def get_olt_status(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get OLT specific status and statistics"""
    device = db.query(TPLinkDevice).filter(
        TPLinkDevice.id == device_id,
        TPLinkDevice.device_type.like('%olt%')
    ).first()
    
    if not device:
        raise HTTPException(status_code=404, detail="OLT device not found")
    
    try:
        service = create_tplink_service(device.management_domain, device.client_id, device.client_secret)
        olt_status = await service.get_olt_status(device.device_id)
        
        # Get connected ONTs count
        connected_onts = db.query(TPLinkONTProvision).filter(
            TPLinkONTProvision.olt_device_id == device.id,
            TPLinkONTProvision.provision_status == "provisioned"
        ).count()
        
        return schemas.OLTStatusResponse(
            device_id=device.device_id,
            pon_ports=olt_status.get("pon_ports", []),
            ethernet_ports=olt_status.get("ethernet_ports", []),
            connected_onts=connected_onts,
            total_capacity={"max_onts": 128 if "8" in device.model else 64},  # Assuming 4-port vs 8-port
            performance_metrics=olt_status
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting OLT status: {str(e)}")

@app.get("/tplink/olt/{device_id}/connected-onts")
async def get_connected_onts(
    device_id: int,
    pon_port: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get list of connected ONTs for an OLT"""
    device = db.query(TPLinkDevice).filter(TPLinkDevice.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    query = db.query(TPLinkONTProvision).filter(TPLinkONTProvision.olt_device_id == device.id)
    if pon_port:
        query = query.filter(TPLinkONTProvision.pon_port == pon_port)
    
    return query.order_by(TPLinkONTProvision.pon_port, TPLinkONTProvision.ont_id).all()

# ONT Provisioning
@app.post("/tplink/olt/{device_id}/provision-ont", response_model=schemas.TPLinkONTProvision)
async def provision_ont(
    device_id: int,
    ont_provision: schemas.TPLinkONTProvisionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Provision a new ONT on the OLT"""
    device = db.query(TPLinkDevice).filter(TPLinkDevice.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="OLT device not found")
    
    # Check if ONT already exists
    existing_ont = db.query(TPLinkONTProvision).filter(
        TPLinkONTProvision.serial_number == ont_provision.serial_number
    ).first()
    if existing_ont:
        raise HTTPException(status_code=400, detail="ONT with this serial number already exists")
    
    try:
        service = create_tplink_service(device.management_domain, device.client_id, device.client_secret)
        
        ont_data = {
            "pon_port": ont_provision.pon_port,
            "ont_id": ont_provision.ont_id,
            "serial_number": ont_provision.serial_number,
            "service_profile": ont_provision.service_profile,
            "description": f"Customer {ont_provision.customer_id}"
        }
        
        success = await service.provision_ont(device.device_id, ont_data)
        
        if success:
            # Create database record
            db_ont_provision = TPLinkONTProvision(**ont_provision.dict())
            db_ont_provision.provision_status = "provisioned"
            db_ont_provision.provision_date = datetime.utcnow()
            
            db.add(db_ont_provision)
            db.commit()
            db.refresh(db_ont_provision)
            
            return db_ont_provision
        else:
            raise HTTPException(status_code=500, detail="Failed to provision ONT")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error provisioning ONT: {str(e)}")

# ONT Specific Endpoints
@app.get("/tplink/ont/{device_id}/status", response_model=schemas.ONTStatusResponse)
async def get_ont_status(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get ONT specific status"""
    device = db.query(TPLinkDevice).filter(
        TPLinkDevice.id == device_id,
        TPLinkDevice.device_type.like('%ont%')
    ).first()
    
    if not device:
        raise HTTPException(status_code=404, detail="ONT device not found")
    
    try:
        service = create_tplink_service(device.management_domain, device.client_id, device.client_secret)
        ont_status = await service.get_ont_status(device.device_id)
        ethernet_ports = await service.get_ont_ethernet_ports(device.device_id)
        
        return schemas.ONTStatusResponse(
            device_id=device.device_id,
            pon_status=ont_status.get("pon_status", "unknown"),
            optical_power_rx=ont_status.get("optical_power_rx"),
            optical_power_tx=ont_status.get("optical_power_tx"),
            ethernet_ports=ethernet_ports,
            wifi_status=ont_status.get("wifi_status")
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting ONT status: {str(e)}")

@app.post("/tplink/ont/{device_id}/configure-wifi")
async def configure_ont_wifi(
    device_id: int,
    wifi_config: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Configure WiFi settings on ONT"""
    device = db.query(TPLinkDevice).filter(TPLinkDevice.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="ONT device not found")
    
    try:
        service = create_tplink_service(device.management_domain, device.client_id, device.client_secret)
        success = await service.configure_ont_wifi(device.device_id, wifi_config)
        
        if success:
            return {"message": "WiFi configuration updated successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to configure WiFi")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error configuring WiFi: {str(e)}")

# Performance Monitoring
@app.get("/tplink/devices/{device_id}/performance")
async def get_performance_metrics(
    device_id: int,
    metric_type: str = "all",
    hours: int = 24,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get performance metrics for device"""
    device = db.query(TPLinkDevice).filter(TPLinkDevice.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    # Get metrics from database
    since = datetime.utcnow() - timedelta(hours=hours)
    query = db.query(TPLinkPerformanceMetric).filter(
        TPLinkPerformanceMetric.device_id == device.id,
        TPLinkPerformanceMetric.timestamp >= since
    )
    
    if metric_type != "all":
        query = query.filter(TPLinkPerformanceMetric.metric_type == metric_type)
    
    metrics = query.order_by(TPLinkPerformanceMetric.timestamp.desc()).all()
    
    return {
        "device_id": device.device_id,
        "metric_type": metric_type,
        "period_hours": hours,
        "metrics": [
            {
                "timestamp": metric.timestamp,
                "metric_type": metric.metric_type,
                "value": metric.metric_value,
                "unit": metric.metric_unit,
                "interface": metric.interface_name
            }
            for metric in metrics
        ]
    }

# Alarms Management
@app.get("/tplink/devices/{device_id}/alarms")
async def get_device_alarms(
    device_id: int,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get device alarms"""
    device = db.query(TPLinkDevice).filter(TPLinkDevice.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    query = db.query(TPLinkAlarm).filter(TPLinkAlarm.device_id == device.id)
    
    if status:
        query = query.filter(TPLinkAlarm.status == status)
    if severity:
        query = query.filter(TPLinkAlarm.severity == severity)
    
    return query.order_by(TPLinkAlarm.raised_at.desc()).all()

# ============================================================================
# NETWORK DISCOVERY ENDPOINTS (SNMP/LLDP)
# ============================================================================

@app.post("/network/discover")
async def start_network_discovery(
    network_ranges: List[str],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Start network discovery for specified ranges"""
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="User must be associated with a company")
    
    try:
        from .services.network_discovery import NetworkDiscoveryService
        
        discovery_service = NetworkDiscoveryService(db, current_user.company_id)
        results = await discovery_service.full_network_discovery(network_ranges)
        
        # Save results to database
        discovery_service.save_discovery_results(results)
        
        return {
            "message": "Network discovery completed",
            "started_at": results["started_at"],
            "completed_at": results["completed_at"],
            "network_ranges": results["network_ranges"],
            "active_hosts_count": len(results["active_hosts"]),
            "snmp_devices_count": len(results["snmp_devices"]),
            "lldp_neighbors_count": len(results["lldp_neighbors"]),
            "errors": results["errors"]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Network discovery failed: {str(e)}")

@app.get("/network/discover/status")
async def get_discovery_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get status of network discovery features"""
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="User must be associated with a company")
    
    try:
        from .services.network_discovery import SNMP_AVAILABLE
        
        # Get settings
        settings = db.query(CompanySetting).filter(
            CompanySetting.company_id == current_user.company_id,
            CompanySetting.category == 'network'
        ).all()
        
        settings_dict = {s.setting_key: s.setting_value for s in settings}
        
        return {
            "snmp_available": SNMP_AVAILABLE,
            "lldp_enabled": settings_dict.get("lldp_enabled", "false") == "true",
            "snmp_version": settings_dict.get("snmp_version", "2c"),
            "discovery_interval": int(settings_dict.get("network_discovery_interval", "300")),
            "last_discovery": None  # Would track last discovery time
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting discovery status: {str(e)}")

@app.post("/network/snmp/test")
async def test_snmp_connection(
    host: str,
    community: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Test SNMP connection to a specific host"""
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="User must be associated with a company")
    
    try:
        from .services.network_discovery import NetworkDiscoveryService
        
        discovery_service = NetworkDiscoveryService(db, current_user.company_id)
        
        # Override community if provided
        if community:
            discovery_service.snmp_community = community
        
        # Test basic SNMP connectivity
        system_oids = ['1.3.6.1.2.1.1.1.0', '1.3.6.1.2.1.1.5.0']  # sysDescr, sysName
        result = discovery_service.snmp_get(host, system_oids)
        
        if result:
            return {
                "success": True,
                "host": host,
                "system_description": result.get('1.3.6.1.2.1.1.1.0', 'Unknown'),
                "system_name": result.get('1.3.6.1.2.1.1.5.0', 'Unknown'),
                "community": discovery_service.snmp_community
            }
        else:
            return {
                "success": False,
                "host": host,
                "error": "No SNMP response received"
            }
            
    except Exception as e:
        return {
            "success": False,
            "host": host,
            "error": str(e)
        }

@app.get("/network/devices/discovered")
async def get_discovered_devices(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get list of devices discovered via network discovery"""
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="User must be associated with a company")
    
    try:
        # Get routers with status 'discovered'
        discovered_routers = db.query(Router).filter(
            Router.company_id == current_user.company_id,
            Router.status == 'discovered'
        ).all()
        
        devices = []
        for router in discovered_routers:
            # Get latest monitoring data
            latest_monitoring = db.query(NetworkMonitoring).filter(
                NetworkMonitoring.router_id == router.id
            ).order_by(NetworkMonitoring.timestamp.desc()).first()
            
            devices.append({
                "id": router.id,
                "name": router.name,
                "ip_address": router.management_ip,
                "model": router.model,
                "os_version": router.os_version,
                "status": router.status,
                "last_seen": router.last_seen,
                "discovered_at": router.created_at,
                "monitoring_available": latest_monitoring is not None
            })
        
        return {
            "devices": devices,
            "count": len(devices)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting discovered devices: {str(e)}")

@app.post("/network/devices/{device_id}/adopt")
async def adopt_discovered_device(
    device_id: int,
    device_config: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Adopt a discovered device into active management"""
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="User must be associated with a company")
    
    try:
        router = db.query(Router).filter(
            Router.id == device_id,
            Router.company_id == current_user.company_id,
            Router.status == 'discovered'
        ).first()
        
        if not router:
            raise HTTPException(status_code=404, detail="Discovered device not found")
        
        # Update router with management credentials and configuration
        router.username = device_config.get('username', router.username)
        router.password = device_config.get('password', router.password)
        router.site_id = device_config.get('site_id', router.site_id)
        router.status = 'active'
        
        db.commit()
        
        return {
            "message": "Device adopted successfully",
            "device_id": router.id,
            "device_name": router.name
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adopting device: {str(e)}")

# ============================================================================
# USER INVITATION AND NOTIFICATION ENDPOINTS
# ============================================================================

@app.post("/invitations/send", response_model=schemas.InvitationResponse)
async def send_user_invitation(
    invitation: schemas.UserInvitationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Send user invitation via email"""
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="User must be associated with a company")
    
    # Check if user has permission to invite (admin or company admin)
    if not current_user.is_admin and not current_user.is_company_admin:
        raise HTTPException(status_code=403, detail="Insufficient permissions to send invitations")
    
    try:
        from .services.notifications import NotificationService
        
        # Check if invitation already exists for this email and company
        existing_invitation = db.query(UserInvitation).filter(
            UserInvitation.company_id == current_user.company_id,
            UserInvitation.email == invitation.email,
            UserInvitation.status == 'pending'
        ).first()
        
        if existing_invitation:
            raise HTTPException(status_code=400, detail="Pending invitation already exists for this email")
        
        # Send invitation
        notification_service = NotificationService(db, current_user.company_id)
        result = notification_service.send_user_invitation(
            invitation.email, 
            invitation.role, 
            current_user.username
        )
        
        if result['success']:
            # Store invitation in database
            db_invitation = UserInvitation(
                company_id=current_user.company_id,
                email=invitation.email,
                invitation_token=result['invitation_token'],
                role=invitation.role,
                invited_by_user_id=current_user.id,
                expires_at=datetime.fromisoformat(result['expires_at'].replace('Z', '+00:00'))
            )
            db.add(db_invitation)
            db.commit()
            db.refresh(db_invitation)
        
        return schemas.InvitationResponse(**result)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sending invitation: {str(e)}")

@app.get("/invitations", response_model=List[schemas.UserInvitation])
async def get_company_invitations(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get company invitations"""
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="User must be associated with a company")
    
    if not current_user.is_admin and not current_user.is_company_admin:
        raise HTTPException(status_code=403, detail="Insufficient permissions to view invitations")
    
    query = db.query(UserInvitation).filter(UserInvitation.company_id == current_user.company_id)
    
    if status:
        query = query.filter(UserInvitation.status == status)
    
    return query.order_by(UserInvitation.created_at.desc()).all()

@app.post("/invitations/accept")
async def accept_invitation(
    acceptance: schemas.InvitationAccept,
    db: Session = Depends(get_db)
):
    """Accept user invitation and create account"""
    try:
        from .auth import get_password_hash
        
        # Find invitation
        invitation = db.query(UserInvitation).filter(
            UserInvitation.invitation_token == acceptance.invitation_token,
            UserInvitation.status == 'pending'
        ).first()
        
        if not invitation:
            raise HTTPException(status_code=404, detail="Invalid or expired invitation")
        
        # Check if invitation has expired
        if invitation.expires_at < datetime.utcnow():
            invitation.status = 'expired'
            db.commit()
            raise HTTPException(status_code=400, detail="Invitation has expired")
        
        # Check if user already exists
        existing_user = db.query(User).filter(User.email == invitation.email).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="User with this email already exists")
        
        # Create new user
        new_user = User(
            username=acceptance.username,
            email=invitation.email,
            password_hash=get_password_hash(acceptance.password),
            company_id=invitation.company_id,
            is_admin=False,
            is_company_admin=(invitation.role == 'company_admin')
        )
        
        db.add(new_user)
        
        # Update invitation status
        invitation.status = 'accepted'
        invitation.accepted_at = datetime.utcnow()
        
        db.commit()
        
        return {"message": "Invitation accepted successfully", "user_id": new_user.id}
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error accepting invitation: {str(e)}")

@app.delete("/invitations/{invitation_id}")
async def cancel_invitation(
    invitation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Cancel pending invitation"""
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="User must be associated with a company")
    
    if not current_user.is_admin and not current_user.is_company_admin:
        raise HTTPException(status_code=403, detail="Insufficient permissions to cancel invitations")
    
    invitation = db.query(UserInvitation).filter(
        UserInvitation.id == invitation_id,
        UserInvitation.company_id == current_user.company_id
    ).first()
    
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")
    
    if invitation.status != 'pending':
        raise HTTPException(status_code=400, detail="Can only cancel pending invitations")
    
    invitation.status = 'cancelled'
    db.commit()
    
    return {"message": "Invitation cancelled successfully"}

@app.post("/notifications/test")
async def test_notifications(
    test_config: schemas.NotificationTest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Test notification configuration"""
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="User must be associated with a company")
    
    if not current_user.is_admin and not current_user.is_company_admin:
        raise HTTPException(status_code=403, detail="Insufficient permissions to test notifications")
    
    try:
        from .services.notifications import NotificationService
        
        notification_service = NotificationService(db, current_user.company_id)
        
        if test_config.notification_type == 'email':
            result = notification_service.test_email_configuration()
        elif test_config.notification_type == 'slack':
            result = notification_service.test_slack_configuration()
        else:
            raise HTTPException(status_code=400, detail="Invalid notification type")
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error testing notification: {str(e)}")

@app.post("/notifications/system")
async def send_system_notification(
    message: str,
    notification_type: str = "info",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Send system notification to configured channels"""
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="User must be associated with a company")
    
    if not current_user.is_admin and not current_user.is_company_admin:
        raise HTTPException(status_code=403, detail="Insufficient permissions to send system notifications")
    
    try:
        from .services.notifications import NotificationService
        
        notification_service = NotificationService(db, current_user.company_id)
        success = notification_service.send_system_notification(message, notification_type)
        
        return {
            "success": success,
            "message": "Notification sent successfully" if success else "Failed to send notification"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sending notification: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
