# LynxMSP - Comprehensive ISP/MSP/WISP Management Platform

LynxMSP is a sophisticated, enterprise-grade management platform designed specifically for Internet Service Providers (ISPs), Managed Service Providers (MSPs), and Wireless Internet Service Providers (WISPs). The platform combines the best features found in industry-leading solutions like Splynx and Ubiquiti's network management tools.

## 🚀 Key Features

### Advanced Network Management
- **Network Topology Visualization** - Ubiquiti-style network topology mapping with real-time status indicators
- **Router Management & Onboarding** - Automated router configuration with Mikrotik RouterOS script generation
- **CGNAT (Carrier-Grade NAT) Management** - Full CGNAT pool management with port allocation and session tracking
- **IPv6 Management** - IPv6 pool management with prefix delegation capabilities
- **DHCP Management** - DHCP lease tracking with Option 82 support for customer identification
- **VLAN Management** - Automated customer VLAN assignment and isolation

### Customer & Business Management
- **Customer Management** - Comprehensive customer database with network service tracking
- **Service Order Management** - Work order tracking for installations and maintenance
- **Billing & Invoicing** - Automated billing with service plan management
- **Support Ticketing** - Built-in helpdesk system for customer support
- **Revenue Analytics** - Advanced reporting and analytics dashboards

### Equipment & Infrastructure
- **Equipment Inventory** - Track all network equipment across multiple sites
- **Site Management** - Multi-site network infrastructure management
- **Monitoring & Alerting** - Real-time network monitoring with performance metrics
- **Network Interface Management** - Detailed interface status and configuration tracking

## 🛠 Technology Stack

### Backend
- **FastAPI** - Modern, fast web framework for building APIs
- **SQLAlchemy** - Python SQL toolkit and Object-Relational Mapping
- **SQLite** - Lightweight, file-based database (easily upgradeable to PostgreSQL)
- **JWT Authentication** - Secure token-based authentication
- **Pydantic** - Data validation using Python type hints

### Frontend
- **React 18** - Modern React with functional components and hooks
- **TypeScript** - Type-safe JavaScript development
- **Material-UI v5** - Google's Material Design component library
- **Recharts** - Beautiful, responsive charts and graphs
- **React Router** - Client-side routing for single-page application

## 🏗 Architecture

### Database Models
The system includes sophisticated database models for:
- **Customer Management** - Customer profiles with connection types (fiber, wireless, ethernet)
- **Network Infrastructure** - Sites, routers, IP subnets, network interfaces
- **IP Management** - IP assignments, CGNAT pools, IPv6 delegations
- **Monitoring** - Network monitoring data, DHCP leases, VLAN assignments
- **Business Operations** - Service plans, invoices, tickets, service orders

### API Endpoints
Comprehensive REST API with endpoints for:
- Authentication and user management
- Customer and site management
- Network equipment and router management
- CGNAT and IPv6 operations
- DHCP and VLAN management
- Monitoring and analytics
- Business operations (invoicing, ticketing, orders)

## 🚀 Getting Started

### Prerequisites
- Node.js 16+ and npm
- Python 3.8+
- Git

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd LynxMSP
   ```

2. **Backend Setup**
   ```bash
   cd backend
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Frontend Setup**
   ```bash
   cd frontend
   npm install
   ```

### Running the Application

1. **Start the Backend**
   ```bash
   cd backend
   source venv/bin/activate  # If not already activated
   python -m app.main
   ```
   The API will be available at `http://localhost:8000`

2. **Start the Frontend**
   ```bash
   cd frontend
   npm start
   ```
   The application will be available at `http://localhost:3000`

### Default Login
- **Username:** admin
- **Password:** admin

## 📊 Platform Features

### Network Topology Dashboard
- Visual network topology with real-time status
- Site-based organization with router and customer counts
- Interactive network equipment monitoring
- Performance metrics and utilization tracking

### Router Management
- **Automated Onboarding Wizard** - Step-by-step router configuration
- **Mikrotik Configuration Generation** - Automatic RouterOS script creation
- **Real-time Monitoring** - CPU, memory, temperature, and uptime tracking
- **Interface Management** - Network interface status and configuration
- **Customer VLAN Management** - Automated VLAN assignment and isolation

### CGNAT Management
- **Pool Management** - Create and manage CGNAT pools with utilization tracking
- **Port Allocation** - Automatic port range assignment to customers
- **Session Tracking** - Real-time CGNAT session monitoring
- **Analytics** - Utilization charts and performance metrics

### Advanced Dashboard
- **Network Overview** - Site status and equipment health
- **Business Metrics** - Customer counts, revenue tracking, service orders
- **Performance Monitoring** - Network utilization and traffic analysis
- **Infrastructure Stats** - CGNAT pools, IPv6 delegations, router status

## 🔧 Configuration Features

### Router Onboarding
The platform includes a sophisticated router onboarding wizard that:
- Generates complete Mikrotik RouterOS configurations
- Sets up customer VLAN isolation
- Configures DHCP with Option 82 for customer tracking
- Implements firewall rules for security and isolation
- Auto-creates corresponding IP subnets and network records

### Network Isolation
- **Customer VLAN Isolation** - Each customer gets a dedicated VLAN
- **Automatic VLAN Assignment** - System assigns next available VLAN ID
- **Firewall Rule Generation** - Prevents inter-customer communication
- **DHCP Option 82** - Links DHCP leases to specific customer locations

## 📈 Monitoring & Analytics

### Real-time Monitoring
- Network equipment performance metrics
- Customer bandwidth utilization
- CGNAT pool utilization
- Service order status tracking

### Business Intelligence
- Revenue tracking and forecasting
- Customer growth analytics
- Network capacity planning
- Equipment maintenance scheduling

## 🔒 Security Features

- JWT-based authentication
- Role-based access control
- Secure API endpoints
- Customer data isolation
- Network security policy enforcement

## 🎯 Target Users

### Internet Service Providers (ISPs)
- Fiber, cable, and DSL internet providers
- Municipal broadband networks
- Regional internet service providers

### Wireless Internet Service Providers (WISPs)
- Fixed wireless providers
- Point-to-point and point-to-multipoint networks
- Rural and remote area connectivity

### Managed Service Providers (MSPs)
- IT service companies
- Network management services
- Business connectivity providers

## 🚀 Advanced Network Features

### Splynx-like Capabilities
- Customer lifecycle management
- Automated billing and invoicing
- Service plan management
- Payment processing integration ready

### Ubiquiti-style Interface
- Visual network topology mapping
- Real-time equipment monitoring
- Performance dashboards
- Alert management system

## 📝 API Documentation

The platform provides comprehensive API documentation with endpoints for:
- `/dashboard/stats` - Dashboard statistics and metrics
- `/dashboard/network-overview` - Network topology data
- `/routers/onboard` - Router onboarding with configuration generation
- `/cgnat/pools` - CGNAT pool management
- `/ipv6/pools` - IPv6 pool and delegation management
- `/customers/{id}/network-info` - Customer network information
- `/sites/{id}/network-topology` - Site topology visualization data

## 🔧 Development

### API Endpoints

#### Authentication
- `POST /auth/login` - User login
- `GET /auth/me` - Get current user

#### Dashboard & Analytics
- `GET /dashboard/stats` - Dashboard statistics
- `GET /dashboard/network-overview` - Network overview

#### Customer Management
- `GET /customers` - List customers (with filters)
- `POST /customers` - Create customer
- `GET /customers/{id}` - Get customer details
- `PUT /customers/{id}` - Update customer
- `GET /customers/{id}/network-info` - Customer network information

#### Network Management
- `GET /sites` - List all sites
- `POST /sites` - Create new site
- `GET /sites/{id}/network-topology` - Site topology data
- `GET /routers` - List routers
- `POST /routers/onboard` - Router onboarding wizard
- `GET /routers/{id}/monitoring` - Router monitoring data

#### CGNAT Management
- `GET /cgnat/pools` - List CGNAT pools
- `POST /cgnat/pools` - Create CGNAT pool
- `POST /cgnat/allocate` - Allocate ports to customer
- `GET /cgnat/sessions` - Active CGNAT sessions

#### IPv6 Management
- `GET /ipv6/pools` - List IPv6 pools
- `POST /ipv6/pools` - Create IPv6 pool
- `POST /ipv6/delegate` - Delegate IPv6 prefix

#### DHCP & IP Management
- `GET /dhcp/leases` - DHCP lease tracking
- `GET /ip-subnets` - IP subnet management
- `GET /ip-assignments` - IP assignment tracking

### Quick Start for Development

#### Backend
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

#### Frontend
```bash
cd frontend
npm install
npm start
```

### Sample Data
The application includes comprehensive seed data:
- 50 sample customers with realistic profiles
- 4 service plan tiers (Basic, Standard, Premium, Enterprise)
- Historical invoices with various payment statuses
- Support tickets with comments and different priorities
- Network infrastructure examples (sites, routers, equipment)

## 🐳 Docker Deployment

### Using Docker Compose
```bash
docker-compose up --build
```

### Manual Docker Build
```bash
# Backend
cd backend
docker build -t lynxmsp-backend .

# Frontend
cd frontend
docker build -t lynxmsp-frontend .
```

## 🔮 Future Enhancements

- Mobile application support
- Advanced reporting engine
- Integration with popular billing systems
- Automated network provisioning
- AI-powered network optimization
- Multi-tenant architecture
- Cloud deployment options
- Integration with monitoring tools (Zabbix, PRTG)

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🤝 Contributing

Contributions are welcome! Please read our contributing guidelines and submit pull requests for any improvements.

## 📞 Support

For support and questions, please open an issue in the GitHub repository or contact the development team.

---

**LynxMSP** - Empowering ISPs, MSPs, and WISPs with professional-grade network management tools.