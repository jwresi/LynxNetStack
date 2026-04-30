# LynxMSP System Restructuring Plan

## Complete Modular Architecture & Implementation Guide

---

## 🎯 **EXECUTIVE SUMMARY**

**Current State**: Monolithic 2,492-line backend with 89 endpoints in single file
**Target State**: Modular, testable, scalable microservice-ready architecture
**Timeline**: Phased approach over 4 weeks
**Risk Level**: High - requires careful migration strategy

---

## 📊 **CRITICAL ISSUES ANALYSIS**

### Backend Problems (SEVERITY: 🔴 CRITICAL)

- **Single Fat Controller**: 2,492 lines in main.py with 89 endpoints
- **Massive Model File**: 905 lines with 26 models in one file
- **No Service Layer**: Direct database access throughout
- **Zero Testing**: No test infrastructure
- **Hardcoded Configs**: Security vulnerabilities
- **SQLite Production**: Not production-ready database

### Frontend Problems (SEVERITY: 🟡 HIGH)

- **Mixed Responsibilities**: Components handling business logic
- **No State Management**: Props drilling and inconsistent state
- **No Testing**: Frontend completely untested
- **Type Safety Issues**: Build warnings and incomplete typing

### Infrastructure Problems (SEVERITY: 🟠 MEDIUM)

- **Basic Docker Setup**: No proper orchestration
- **No CI/CD**: Manual deployment process
- **No Monitoring**: No observability or logging
- **No Security**: Basic authentication only

---

## 🏗️ **PROPOSED MODULAR ARCHITECTURE**

### Backend Structure (Clean Architecture + DDD)

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app initialization only
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings.py           # Pydantic settings
│   │   ├── database.py           # DB configuration
│   │   └── security.py           # Security config
│   ├── core/
│   │   ├── __init__.py
│   │   ├── dependencies.py       # Dependency injection
│   │   ├── exceptions.py         # Custom exceptions
│   │   ├── middleware.py         # Custom middleware
│   │   └── logging.py            # Logging configuration
│   ├── modules/
│   │   ├── __init__.py
│   │   ├── auth/
│   │   │   ├── __init__.py
│   │   │   ├── models.py         # Auth models
│   │   │   ├── schemas.py        # Auth schemas
│   │   │   ├── services.py       # Auth business logic
│   │   │   ├── repositories.py   # Auth data access
│   │   │   └── routes.py         # Auth endpoints
│   │   ├── customers/
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   ├── schemas.py
│   │   │   ├── services.py
│   │   │   ├── repositories.py
│   │   │   └── routes.py
│   │   ├── billing/
│   │   ├── network/
│   │   ├── tickets/
│   │   ├── equipment/
│   │   └── monitoring/
│   ├── integrations/
│   │   ├── __init__.py
│   │   ├── splynx/
│   │   │   ├── __init__.py
│   │   │   ├── client.py         # Splynx API client
│   │   │   ├── services.py       # Splynx business logic
│   │   │   ├── schemas.py        # Splynx data models
│   │   │   └── exceptions.py     # Splynx specific errors
│   │   ├── mikrotik/
│   │   ├── tplink/
│   │   └── ippay/
│   ├── shared/
│   │   ├── __init__.py
│   │   ├── utils/
│   │   │   ├── __init__.py
│   │   │   ├── datetime.py
│   │   │   ├── validators.py
│   │   │   └── formatters.py
│   │   ├── constants/
│   │   │   ├── __init__.py
│   │   │   ├── enums.py
│   │   │   └── messages.py
│   │   └── types/
│   │       ├── __init__.py
│   │       └── common.py
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py           # Pytest configuration
│       ├── unit/
│       ├── integration/
│       └── e2e/
├── migrations/                    # Alembic migrations
├── docker/
│   ├── Dockerfile.dev
│   ├── Dockerfile.prod
│   └── docker-compose.yml
├── requirements/
│   ├── base.txt
│   ├── dev.txt
│   └── prod.txt
└── scripts/
    ├── setup.sh
    ├── test.sh
    └── deploy.sh
```

### Frontend Structure (Feature-Based)

```
frontend/
├── public/
├── src/
│   ├── app/
│   │   ├── App.tsx
│   │   ├── store.ts               # Redux store
│   │   └── router.tsx             # App routing
│   ├── shared/
│   │   ├── components/
│   │   │   ├── ui/                # Reusable UI components
│   │   │   ├── forms/             # Form components
│   │   │   └── layout/            # Layout components
│   │   ├── hooks/                 # Custom hooks
│   │   ├── utils/                 # Utility functions
│   │   ├── types/                 # TypeScript types
│   │   ├── constants/             # App constants
│   │   └── api/                   # API client
│   ├── features/
│   │   ├── auth/
│   │   │   ├── components/
│   │   │   ├── hooks/
│   │   │   ├── services/
│   │   │   ├── types/
│   │   │   └── store/
│   │   ├── customers/
│   │   ├── billing/
│   │   ├── network/
│   │   ├── tickets/
│   │   └── dashboard/
│   └── tests/
│       ├── __mocks__/
│       ├── unit/
│       ├── integration/
│       └── e2e/
├── package.json
├── tsconfig.json
├── jest.config.js
├── cypress.config.ts
└── docker/
    ├── Dockerfile.dev
    └── Dockerfile.prod
```

---

## 🔄 **MIGRATION STRATEGY**

### Phase 1: Foundation (Week 1)

**Goal**: Establish new architecture without breaking existing functionality

#### 1.1 Backend Foundation

```python
# app/config/settings.py
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite:///./lynxcrm.db"
    
    # Security
    secret_key: str
    access_token_expire_minutes: int = 30
    
    # External APIs
    splynx_url: Optional[str] = None
    splynx_api_key: Optional[str] = None
    mikrotik_enabled: bool = False
    
    class Config:
        env_file = ".env"

settings = Settings()
```

#### 1.2 Dependency Injection Setup

```python
# app/core/dependencies.py
from sqlalchemy.orm import Session
from app.config.database import SessionLocal
from app.modules.auth.services import AuthService
from app.modules.customers.services import CustomerService


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(db)


def get_customer_service(db: Session = Depends(get_db)) -> CustomerService:
    return CustomerService(db)
```

#### 1.3 Module Template

```python
# app/modules/customers/services.py
from sqlalchemy.orm import Session
from typing import List, Optional
from .models import Customer
from .repositories import CustomerRepository
from .schemas import CustomerCreate, CustomerUpdate


class CustomerService:
    def __init__(self, db: Session):
        self.repository = CustomerRepository(db)

    async def get_customers(self, skip: int = 0, limit: int = 100) -> List[Customer]:
        return await self.repository.get_all(skip=skip, limit=limit)

    async def create_customer(self, customer_data: CustomerCreate) -> Customer:
        # Business logic here
        return await self.repository.create(customer_data)

    async def get_customer(self, customer_id: int) -> Optional[Customer]:
        return await self.repository.get_by_id(customer_id)
```

### Phase 2: Module Migration (Week 2)

**Goal**: Extract modules from monolith while maintaining functionality

#### 2.1 Authentication Module

```python
# app/modules/auth/routes.py
from fastapi import APIRouter, Depends, HTTPException
from .services import AuthService
from .schemas import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login", response_model=TokenResponse)
async def login(
        credentials: LoginRequest,
        auth_service: AuthService = Depends(get_auth_service)
):
    try:
        return await auth_service.authenticate(credentials)
    except InvalidCredentialsError as e:
        raise HTTPException(status_code=401, detail=str(e))
```

#### 2.2 Customer Module

```python
# app/modules/customers/repositories.py
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Optional
from .models import Customer
from .schemas import CustomerCreate, CustomerUpdate


class CustomerRepository:
    def __init__(self, db: Session):
        self.db = db

    async def get_all(self, skip: int = 0, limit: int = 100, company_id: Optional[int] = None) -> List[Customer]:
        query = self.db.query(Customer)
        if company_id:
            query = query.filter(Customer.company_id == company_id)
        return query.offset(skip).limit(limit).all()

    async def create(self, customer_data: CustomerCreate) -> Customer:
        customer = Customer(**customer_data.dict())
        self.db.add(customer)
        self.db.commit()
        self.db.refresh(customer)
        return customer
```

### Phase 3: API Integration Modules (Week 3)

**Goal**: Modularize external API integrations

#### 3.1 Splynx Integration

```python
# app/integrations/splynx/client.py
import httpx
from typing import Optional, Dict, Any
from app.config.settings import settings
from .exceptions import SplynxAPIError
from .schemas import SplynxCustomer, SplynxInvoice


class SplynxClient:
    def __init__(self):
        self.base_url = settings.splynx_url
        self.api_key = settings.splynx_api_key
        self.client = httpx.AsyncClient(timeout=30.0)

    async def get_customers(self, limit: int = 100) -> List[SplynxCustomer]:
        try:
            response = await self.client.get(
                f"{self.base_url}/api/2.0/admin/customers/customer",
                headers={"Authorization": f"Splynx-EA (access_token={self.api_key})"},
                params={"limit": limit}
            )
            response.raise_for_status()
            return [SplynxCustomer(**customer) for customer in response.json()["data"]]
        except httpx.HTTPError as e:
            raise SplynxAPIError(f"Failed to fetch customers: {e}")
```

### Phase 4: Testing & Deployment (Week 4)

**Goal**: Comprehensive testing and production deployment

#### 4.1 Unit Testing

```python
# app/tests/unit/test_customer_service.py
import pytest
from unittest.mock import Mock, AsyncMock
from app.modules.customers.services import CustomerService
from app.modules.customers.schemas import CustomerCreate


@pytest.fixture
def mock_repository():
    return Mock()


@pytest.fixture
def customer_service(mock_repository):
    service = CustomerService.__new__(CustomerService)
    service.repository = mock_repository
    return service


@pytest.mark.asyncio
async def test_create_customer(customer_service, mock_repository):
    # Arrange
    customer_data = CustomerCreate(name="Test Customer", email="test@example.com")
    mock_repository.create.return_value = Mock(id=1, name="Test Customer")

    # Act
    result = await customer_service.create_customer(customer_data)

    # Assert
    assert result.id == 1
    mock_repository.create.assert_called_once_with(customer_data)
```

#### 4.2 Integration Testing

```python
# app/tests/integration/test_customer_api.py
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config.database import get_db
from app.tests.conftest import override_get_db

client = TestClient(app)

def test_create_customer():
    app.dependency_overrides[get_db] = override_get_db
    
    customer_data = {
        "name": "Test Customer",
        "email": "test@example.com",
        "phone": "+1234567890"
    }
    
    response = client.post("/customers", json=customer_data)
    
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Customer"
    assert "id" in data
```

---

## 🛠️ **IMPLEMENTATION CHECKLIST**

### Backend Refactoring

- [ ] **Week 1**: Set up new project structure
- [ ] **Week 1**: Create configuration management system
- [ ] **Week 1**: Implement dependency injection
- [ ] **Week 1**: Set up logging and error handling
- [ ] **Week 2**: Extract Auth module
- [ ] **Week 2**: Extract Customer module
- [ ] **Week 2**: Extract Billing module
- [ ] **Week 2**: Extract Network module
- [ ] **Week 3**: Refactor API integrations
- [ ] **Week 3**: Implement caching layer
- [ ] **Week 3**: Add validation middleware
- [ ] **Week 4**: Complete test coverage
- [ ] **Week 4**: Performance optimization
- [ ] **Week 4**: Security hardening

### Frontend Refactoring

- [ ] **Week 1**: Set up Redux store
- [ ] **Week 1**: Create shared component library
- [ ] **Week 1**: Implement proper routing
- [ ] **Week 2**: Convert pages to feature modules
- [ ] **Week 2**: Add proper TypeScript types
- [ ] **Week 2**: Implement error boundaries
- [ ] **Week 3**: Add form validation
- [ ] **Week 3**: Implement real-time updates
- [ ] **Week 4**: Add comprehensive testing
- [ ] **Week 4**: Performance optimization

### Infrastructure

- [ ] **Week 1**: Set up proper Docker containers
- [ ] **Week 1**: Configure environment management
- [ ] **Week 2**: Implement PostgreSQL migration
- [ ] **Week 2**: Set up Redis for caching
- [ ] **Week 3**: Configure CI/CD pipeline
- [ ] **Week 3**: Set up monitoring and logging
- [ ] **Week 4**: Security scanning and hardening
- [ ] **Week 4**: Load testing and optimization

---

## 📈 **SUCCESS METRICS**

### Code Quality

- **Test Coverage**: Target 80%+ for backend, 70%+ for frontend
- **Cyclomatic Complexity**: Max 10 per function
- **File Size**: Max 200 lines per file
- **Code Duplication**: <5%

### Performance

- **API Response Time**: <200ms for 95% of requests
- **Database Query Time**: <50ms average
- **Frontend Load Time**: <2s initial load
- **Memory Usage**: <512MB per container

### Maintainability

- **Module Independence**: Each module can be deployed separately
- **Test Isolation**: Tests run independently
- **Documentation Coverage**: 100% of public APIs documented
- **Dependency Management**: Clear dependency injection

---

## 🚨 **RISK MITIGATION**

### Data Integrity Risks

- **Strategy**: Comprehensive backup before each phase
- **Testing**: Run migration scripts on copy of production data
- **Rollback**: Keep original codebase until new system is proven

### Downtime Risks

- **Strategy**: Blue-green deployment approach
- **Feature Flags**: Gradually enable new features
- **Monitoring**: Real-time health checks during migration

### Performance Risks

- **Strategy**: Load testing at each phase
- **Optimization**: Database indexing and query optimization
- **Caching**: Implement Redis caching layer

---

## 📚 **DELIVERABLES**

1. **✅ Refactored Backend** - Modular, testable, scalable
2. **✅ Refactored Frontend** - Feature-based, typed, tested
3. **✅ Complete Test Suite** - Unit, integration, E2E tests
4. **✅ Docker Configuration** - Production-ready containers
5. **✅ CI/CD Pipeline** - Automated testing and deployment
6. **✅ API Documentation** - OpenAPI/Swagger specs
7. **✅ Deployment Guide** - Step-by-step instructions
8. **✅ Migration Scripts** - Database and data migration
9. **✅ Monitoring Setup** - Logging, metrics, alerts
10. **✅ Security Configuration** - Authentication, authorization, validation

---

**🎯 NEXT STEP: Implement Phase 1 foundation components**

Would you like me to begin implementing the foundational components starting with the configuration management and
dependency injection system?