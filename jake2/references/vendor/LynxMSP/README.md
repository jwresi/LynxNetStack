# LynxCRM - Comprehensive ISP/MSP Management Platform

A professional ISP/MSP/WISP management platform built with FastAPI and React. This system combines billing, customer management, and network infrastructure management—like Splynx meets Netbox with a modern UI.

---

## Features

### Core Functionality
- **Customer Management**: Add, edit, and view customer profiles with service plans
- **Service Plans**: Predefined internet service tiers with pricing
- **Billing System**: Invoice generation and payment tracking
- **Support Tickets**: Customer support ticket management with comments
- **Dashboard**: Key metrics and business insights

### Technical Features
- Modern React frontend with Material-UI
- FastAPI backend with SQLAlchemy ORM
- JWT authentication
- SQLite database for easy deployment
- Docker containerization (production-ready)
- Responsive design

---

## Project Structure

```
LynxMSP/
├── backend/         # FastAPI backend
├── frontend/        # React frontend (with Nginx for production)
├── docker-compose.yml         # Dev compose file
├── docker-compose.prod.yml    # Production compose file
├── archived/        # Legacy/unused files
├── backend/archived/ # Archived backend files
├── DOCKER.md        # Docker and deployment guide
├── README.md        # This file
```

---

## Quick Start (Development)

### Prerequisites
- Docker and Docker Compose
- Git

### Local Development

1. Clone the repository:
   ```bash
git clone <repository-url>
cd LynxMSP
```
2. Start the application (development mode):
   ```bash
docker-compose up --build
```
3. Access the application:
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

---

## Production Deployment

### 1. Build and Start (Production)
```bash
docker-compose -f docker-compose.prod.yml up --build -d
```
- Frontend: http://localhost
- Backend API: http://localhost:8000

### 2. Environment Variables
- **Backend**
  - `DATABASE_URL`: SQLite database path (default: `sqlite:///data/lynxcrm.db`)
  - `SECRET_KEY`: JWT signing key (**change in production!**)
  - `CORS_ORIGINS`: Allowed CORS origins
- **Frontend**
  - `REACT_APP_API_URL`: Backend API URL (default: `http://localhost:8000`)

### 3. Production Docker/Compose Highlights
- **Frontend**: Multi-stage Dockerfile builds React app, then serves with Nginx using `nginx.conf`.
- **Backend**: Runs Uvicorn without `--reload` for production stability.
- **Resource Limits**: Compose file sets memory/CPU limits for both frontend and backend.
- **Volumes**: Data is persisted via Docker volumes.
- **Healthchecks**: Backend health is checked via `/auth/health`.

### 4. Security Checklist
- [ ] Change all default secrets and admin credentials
- [ ] Set up HTTPS/SSL (use a reverse proxy or cloud load balancer)
- [ ] Regularly update dependencies and base images
- [ ] Set resource limits (already in compose)
- [ ] Use Docker networks for service isolation

---

## Sample Data
- 50 sample customers with realistic profiles
- 4 service plan tiers (Basic, Standard, Premium, Enterprise)
- Historical invoices with various payment statuses
- Support tickets with comments and different priorities
- Admin user account for immediate access

---

## API Overview

- **Authentication**
  - `POST /auth/login` - User login
  - `GET /auth/me` - Get current user
- **Customers**
  - `GET /customers` - List customers
  - `POST /customers` - Create customer
  - `GET /customers/{id}` - Get customer details
  - `PUT /customers/{id}` - Update customer
- **Service Plans**
  - `GET /service-plans` - List available service plans
- **Invoices**
  - `GET /invoices` - List all invoices
  - `POST /invoices` - Generate new invoice
  - `GET /invoices/{id}` - Get invoice details
  - `PUT /invoices/{id}/payment-status` - Update payment status
- **Support Tickets**
  - `GET /tickets` - List tickets
  - `POST /tickets` - Create new ticket
  - `GET /tickets/{id}` - Get ticket details
  - `PUT /tickets/{id}/status` - Update ticket status
  - `POST /tickets/{id}/comments` - Add comment to ticket
- **Dashboard**
  - `GET /dashboard/stats` - Get dashboard statistics

---

## Contributor Guide

### How to Add Features
- **Backend**: Add endpoints in `backend/app/main.py` and models in `backend/app/database.py`.
- **Frontend**: Add pages/components in `frontend/src/pages` or `frontend/src/components`.
- **Tests**: Add or update tests in `frontend/src/tests` or backend test scripts.

### How to Update/Deploy
- Pull latest code, rebuild, and restart containers:
  ```bash
  git pull
  docker-compose -f docker-compose.prod.yml down
  docker-compose -f docker-compose.prod.yml up --build -d
  ```

### How to Back Up Data
- Data is stored in a Docker volume (`lynxmsp_data`).
- See `DOCKER.md` for backup/restore scripts and details.

### Project Conventions
- **Backend**: FastAPI, SQLAlchemy, Pydantic, JWT
- **Frontend**: React, TypeScript, Material-UI, Axios
- **Docker**: Multi-stage builds, Nginx for static serving, resource limits
- **Code Style**: Use Black for Python, Prettier for JS/TS (recommended)

---

## Business Workflows

### Customer Onboarding
1. Add new customer with contact information
2. Assign appropriate service plan
3. Generate first invoice
4. Monitor service activation

### Billing Process
1. Generate monthly invoices for all customers
2. Track payment status
3. Handle overdue accounts
4. Manage service suspensions

### Support Management
1. Receive customer support requests
2. Assign priority levels
3. Track resolution progress
4. Maintain communication history

---

## Security & Best Practices
- JWT-based authentication
- Bcrypt password hashing
- CORS protection
- Input validation
- Regular dependency updates
- Use HTTPS in production
- Set resource limits in Docker Compose

---

## Support & Troubleshooting

- API documentation: http://localhost:8000/docs
- Check logs: `docker-compose logs -f`
- Check service status: `docker-compose ps`
- For more, see `DOCKER.md` and comments in the codebase.

---

## License

This project is provided as-is for demonstration and internal use. For commercial or production use, review all dependencies and security settings.
