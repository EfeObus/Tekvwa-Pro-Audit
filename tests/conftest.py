"""
Tekvwa Pro Audit - Test Configuration

Pytest fixtures and configuration.
"""

import asyncio
from datetime import datetime, date
from decimal import Decimal
from typing import AsyncGenerator, Generator
from uuid import uuid4

import pytest
import pytest_asyncio
import httpx
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.database import Base, get_async_session
from app.config import settings
from app.models.user import User, UserRole
from app.models.organization import Organization
from app.models.entity import BusinessEntity, BusinessType
from app.models.category import Category, CategoryType
from app.models.vendor import Vendor
from app.models.customer import Customer
from app.models.transaction import Transaction, TransactionType
from app.models.invoice import Invoice, InvoiceStatus
from app.utils.security import get_password_hash
from main import app


# Test database URL (use separate test database)
TEST_DATABASE_URL = settings.database_url_async.replace(
    settings.postgres_db, 
    f"{settings.postgres_db}_test"
)


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test."""
    # Create engine within the async context to avoid event loop mismatch
    test_engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
    )
    
    # Create session factory
    TestSessionLocal = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()
    
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    # Dispose the engine to clean up connections
    await test_engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client with database session override."""
    
    async def override_get_session():
        yield db_session
    
    app.dependency_overrides[get_async_session] = override_get_session
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    
    app.dependency_overrides.clear()


# ===========================================
# DATA FIXTURES
# ===========================================

@pytest_asyncio.fixture
async def test_organization(db_session: AsyncSession) -> Organization:
    """Create a test organization."""
    org = Organization(
        id=uuid4(),
        name="Test Organization",
        slug="test-org",
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession, test_organization: Organization) -> User:
    """Create a test user."""
    user = User(
        id=uuid4(),
        email="testuser@example.com",
        hashed_password=get_password_hash("TestPassword123!"),
        first_name="Test",
        last_name="User",
        organization_id=test_organization.id,
        role=UserRole.OWNER,
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_entity(db_session: AsyncSession, test_organization: Organization) -> BusinessEntity:
    """Create a test business entity."""
    entity = BusinessEntity(
        id=uuid4(),
        name="Test Business Ltd",
        organization_id=test_organization.id,
        business_type=BusinessType.LIMITED_COMPANY,
        tin="12345678-0001",
        rc_number="RC123456",
        address_line1="123 Test Street",
        city="Lagos",
        state="Lagos",
        email="business@example.com",
        phone="+234 812 345 6789",
        is_vat_registered=True,
    )
    db_session.add(entity)
    await db_session.commit()
    await db_session.refresh(entity)
    return entity


@pytest_asyncio.fixture
async def test_category(db_session: AsyncSession, test_entity: BusinessEntity) -> Category:
    """Create a test category."""
    category = Category(
        id=uuid4(),
        name="Office Supplies",
        category_type=CategoryType.EXPENSE,
        description="Office supplies and stationery",
    )
    db_session.add(category)
    await db_session.commit()
    await db_session.refresh(category)
    return category


@pytest_asyncio.fixture
async def test_vendor(db_session: AsyncSession, test_entity: BusinessEntity) -> Vendor:
    """Create a test vendor."""
    vendor = Vendor(
        id=uuid4(),
        name="Acme Supplies Ltd",
        email="vendor@acme.com",
        phone="+234 801 234 5678",
        address="456 Vendor Street, Lagos",
        tin="98765432-0001",
        entity_id=test_entity.id,
    )
    db_session.add(vendor)
    await db_session.commit()
    await db_session.refresh(vendor)
    return vendor


@pytest_asyncio.fixture
async def test_customer(db_session: AsyncSession, test_entity: BusinessEntity) -> Customer:
    """Create a test customer."""
    customer = Customer(
        id=uuid4(),
        name="ABC Corp",
        email="customer@abc.com",
        phone="+234 809 876 5432",
        address="789 Customer Ave, Abuja",
        tin="11223344-0001",
        entity_id=test_entity.id,
    )
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)
    return customer


@pytest_asyncio.fixture
async def test_transaction(
    db_session: AsyncSession, 
    test_entity: BusinessEntity,
    test_category: Category,
    test_vendor: Vendor,
) -> Transaction:
    """Create a test transaction."""
    transaction = Transaction(
        id=uuid4(),
        entity_id=test_entity.id,
        transaction_type=TransactionType.EXPENSE,
        category_id=test_category.id,
        vendor_id=test_vendor.id,
        description="Office supplies purchase",
        amount=Decimal("50000.00"),
        vat_amount=Decimal("3750.00"),
        total_amount=Decimal("53750.00"),
        transaction_date=date.today(),
        reference="TXN-2026-0001",
    )
    db_session.add(transaction)
    await db_session.commit()
    await db_session.refresh(transaction)
    return transaction


@pytest_asyncio.fixture
async def test_invoice(
    db_session: AsyncSession,
    test_entity: BusinessEntity,
    test_customer: Customer,
) -> Invoice:
    """Create a test invoice."""
    invoice = Invoice(
        id=uuid4(),
        entity_id=test_entity.id,
        customer_id=test_customer.id,
        invoice_number="INV-2026-0001",
        issue_date=date.today(),
        due_date=date.today(),
        subtotal=Decimal("100000.00"),
        vat_rate=Decimal("7.5"),
        vat_amount=Decimal("7500.00"),
        total_amount=Decimal("107500.00"),
        status=InvoiceStatus.draft,
    )
    db_session.add(invoice)
    await db_session.commit()
    await db_session.refresh(invoice)
    return invoice


@pytest_asyncio.fixture
async def auth_headers(test_user: User) -> dict:
    """Generate authorization headers for test user."""
    from app.utils.security import create_access_token
    
    token = create_access_token(data={"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}
