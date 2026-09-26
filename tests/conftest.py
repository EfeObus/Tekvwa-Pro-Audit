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
        invoice_date=date.today(),
        due_date=date.today(),
        subtotal=Decimal("100000.00"),
        vat_rate=Decimal("7.5"),
        vat_amount=Decimal("7500.00"),
        total_amount=Decimal("107500.00"),
        status=InvoiceStatus.DRAFT,
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


# ===========================================
# CROSS-TENANT ISOLATION FIXTURES (Finding 18, docs/IMPLEMENTATION_ROADMAP.md Phase 2)
#
# A second, fully independent organization/user/entity, for the parameterized
# "Org A user + Org B entity_id -> 403/404" suite the audit recommended. Deliberately
# reuses the exact same shape as test_organization/test_user/test_entity above (including
# UserRole.OWNER) so that an admin/owner bypass on the WRONG organization is exactly what
# these tests prove doesn't happen -- get_entity_by_id()'s organization_id filter must
# reject cross-org access regardless of role.
# ===========================================

@pytest_asyncio.fixture
async def other_organization(db_session: AsyncSession) -> Organization:
    """A second, independent organization (Org B)."""
    org = Organization(
        id=uuid4(),
        name="Other Test Organization",
        slug="other-test-org",
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest_asyncio.fixture
async def other_user(db_session: AsyncSession, other_organization: Organization) -> User:
    """Org B's user -- same role (OWNER) as test_user, different organization."""
    user = User(
        id=uuid4(),
        email="otheruser@example.com",
        hashed_password=get_password_hash("TestPassword123!"),
        first_name="Other",
        last_name="User",
        organization_id=other_organization.id,
        role=UserRole.OWNER,
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def other_entity(db_session: AsyncSession, other_organization: Organization) -> BusinessEntity:
    """Org B's business entity -- the foreign entity_id an Org A user must be rejected for."""
    entity = BusinessEntity(
        id=uuid4(),
        name="Other Business Ltd",
        organization_id=other_organization.id,
        business_type=BusinessType.LIMITED_COMPANY,
        tin="98765432-0001",
        rc_number="RC987654",
        address_line1="456 Other Street",
        city="Abuja",
        state="FCT",
        email="other-business@example.com",
        phone="+234 802 000 0000",
        is_vat_registered=True,
    )
    db_session.add(entity)
    await db_session.commit()
    await db_session.refresh(entity)
    return entity


@pytest_asyncio.fixture
async def other_auth_headers(other_user: User) -> dict:
    """Generate authorization headers for Org B's user."""
    from app.utils.security import create_access_token

    token = create_access_token(data={"sub": str(other_user.id)})
    return {"Authorization": f"Bearer {token}"}
