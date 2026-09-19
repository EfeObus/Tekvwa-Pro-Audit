"""
Tekvwa Pro Audit - Demo Companies Seeder

Creates two complete demo companies:
1. Okonkwo & Sons Trading (Core tier) - Benin City
2. Lagos Prime Ventures (Professional tier) - Ajah, Lagos

Each company has:
- 15+ staff members
- 5 years of transaction history
- Inventory items
- 10 years of payroll history
- Invoices and full business data
"""

import asyncio
import uuid
import random
import string
from datetime import datetime, date, timedelta
from decimal import Decimal
import hashlib
import secrets

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Database connection
DATABASE_URL = "postgresql+asyncpg://efeobukohwo:12345@localhost:5432/tekvwa_pro_audit"

# Password hashing (bcrypt)
def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    import bcrypt
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode(), salt).decode()

# ============================================================================
# COMPANY CONFIGURATIONS
# ============================================================================

CORE_COMPANY = {
    "name": "Okonkwo & Sons Trading",
    "slug": "okonkwo-sons-trading",
    "email": "info@okonkwotrading.com",
    "phone": "+234 802 345 6789",
    "tier": "core",
    "location": {
        "address_line1": "45 Akpakpava Road",
        "address_line2": "Near First Bank",
        "city": "Benin City",
        "state": "Edo",
        "lga": "Oredo",
        "country": "Nigeria"
    },
    "business_type": "Trading & General Merchandise",
    "tin": "12345678-0001",
    "rc_number": "RC-BN-2018-001234",
    "admin_user": {
        "email": "admin@okonkwotrading.com",
        "password": "Okonkwo2024!",
        "first_name": "Chukwuemeka",
        "last_name": "Okonkwo",
        "phone": "+234 802 345 6789"
    }
}

PROFESSIONAL_COMPANY = {
    "name": "Lagos Prime Ventures Ltd",
    "slug": "lagos-prime-ventures",
    "email": "contact@lagosprime.com",
    "phone": "+234 812 987 6543",
    "tier": "professional",
    "location": {
        "address_line1": "12 Addo Road",
        "address_line2": "Abraham Adesanya Estate",
        "city": "Ajah",
        "state": "Lagos",
        "lga": "Eti-Osa",
        "country": "Nigeria"
    },
    "business_type": "Technology & Consulting Services",
    "tin": "98765432-0001",
    "rc_number": "RC-LG-2015-005678",
    "admin_user": {
        "email": "admin@lagosprime.com",
        "password": "LagosPrime2024!",
        "first_name": "Adebayo",
        "last_name": "Fashola",
        "phone": "+234 812 987 6543"
    }
}

# Staff templates for each company
CORE_STAFF = [
    {"first_name": "Osaze", "last_name": "Okonkwo", "email": "osaze@okonkwotrading.com", "role": "accountant", "department": "Finance", "salary": 180000},
    {"first_name": "Ehi", "last_name": "Aigbe", "email": "ehi@okonkwotrading.com", "role": "user", "department": "Sales", "salary": 120000},
    {"first_name": "Osamudiamen", "last_name": "Omoruyi", "email": "osamudiamen@okonkwotrading.com", "role": "user", "department": "Warehouse", "salary": 95000},
    {"first_name": "Isoken", "last_name": "Ogiemwonyi", "email": "isoken@okonkwotrading.com", "role": "user", "department": "Sales", "salary": 110000},
    {"first_name": "Nosakhare", "last_name": "Ehigie", "email": "nosakhare@okonkwotrading.com", "role": "user", "department": "Logistics", "salary": 85000},
    {"first_name": "Abieyuwa", "last_name": "Igbinoba", "email": "abieyuwa@okonkwotrading.com", "role": "user", "department": "Admin", "salary": 90000},
    {"first_name": "Ehizogie", "last_name": "Airhiavbere", "email": "ehizogie@okonkwotrading.com", "role": "user", "department": "Sales", "salary": 105000},
    {"first_name": "Uyiosa", "last_name": "Obasogie", "email": "uyiosa@okonkwotrading.com", "role": "user", "department": "Warehouse", "salary": 80000},
    {"first_name": "Omosede", "last_name": "Iyayi", "email": "omosede@okonkwotrading.com", "role": "user", "department": "Customer Service", "salary": 75000},
    {"first_name": "Eghosa", "last_name": "Omoregie", "email": "eghosa@okonkwotrading.com", "role": "user", "department": "Sales", "salary": 100000},
    {"first_name": "Osaretin", "last_name": "Idemudia", "email": "osaretin@okonkwotrading.com", "role": "user", "department": "Procurement", "salary": 130000},
    {"first_name": "Isioma", "last_name": "Ogbeide", "email": "isioma@okonkwotrading.com", "role": "user", "department": "Finance", "salary": 140000},
    {"first_name": "Odianosen", "last_name": "Ehikhamenor", "email": "odianosen@okonkwotrading.com", "role": "user", "department": "IT", "salary": 150000},
    {"first_name": "Osatohanmwen", "last_name": "Ighodaro", "email": "osatohan@okonkwotrading.com", "role": "user", "department": "Logistics", "salary": 88000},
    {"first_name": "Efosa", "last_name": "Okonoboh", "email": "efosa@okonkwotrading.com", "role": "user", "department": "Security", "salary": 65000},
]

PROFESSIONAL_STAFF = [
    {"first_name": "Oluwaseun", "last_name": "Adeyemi", "email": "seun@lagosprime.com", "role": "accountant", "department": "Finance", "salary": 350000},
    {"first_name": "Chidinma", "last_name": "Nwosu", "email": "chidinma@lagosprime.com", "role": "user", "department": "Consulting", "salary": 280000},
    {"first_name": "Temitope", "last_name": "Bakare", "email": "temi@lagosprime.com", "role": "user", "department": "Technology", "salary": 320000},
    {"first_name": "Olumide", "last_name": "Ogunleye", "email": "olumide@lagosprime.com", "role": "user", "department": "Sales", "salary": 250000},
    {"first_name": "Funmilayo", "last_name": "Ajayi", "email": "funmi@lagosprime.com", "role": "user", "department": "HR", "salary": 220000},
    {"first_name": "Babatunde", "last_name": "Olatunji", "email": "tunde@lagosprime.com", "role": "user", "department": "Technology", "salary": 380000},
    {"first_name": "Adaeze", "last_name": "Okwu", "email": "adaeze@lagosprime.com", "role": "user", "department": "Marketing", "salary": 200000},
    {"first_name": "Emeka", "last_name": "Okafor", "email": "emeka@lagosprime.com", "role": "user", "department": "Consulting", "salary": 300000},
    {"first_name": "Yetunde", "last_name": "Balogun", "email": "yetunde@lagosprime.com", "role": "user", "department": "Admin", "salary": 180000},
    {"first_name": "Chinedu", "last_name": "Eze", "email": "chinedu@lagosprime.com", "role": "user", "department": "Technology", "salary": 400000},
    {"first_name": "Aisha", "last_name": "Mohammed", "email": "aisha@lagosprime.com", "role": "user", "department": "Finance", "salary": 270000},
    {"first_name": "Kayode", "last_name": "Adeleke", "email": "kayode@lagosprime.com", "role": "user", "department": "Sales", "salary": 230000},
    {"first_name": "Ngozi", "last_name": "Umeh", "email": "ngozi@lagosprime.com", "role": "user", "department": "Customer Success", "salary": 210000},
    {"first_name": "Femi", "last_name": "Adebisi", "email": "femi@lagosprime.com", "role": "user", "department": "Consulting", "salary": 290000},
    {"first_name": "Blessing", "last_name": "Osagie", "email": "blessing@lagosprime.com", "role": "user", "department": "Marketing", "salary": 190000},
    {"first_name": "Ikechukwu", "last_name": "Nnamdi", "email": "ike@lagosprime.com", "role": "user", "department": "Technology", "salary": 420000},
]

# Inventory items for Core company (Trading)
CORE_INVENTORY = [
    {"name": "Rice (50kg bag)", "sku": "RICE-50KG", "category": "Food Commodities", "unit_price": 45000, "quantity": 500, "reorder_level": 100},
    {"name": "Palm Oil (25L)", "sku": "PALM-25L", "category": "Food Commodities", "unit_price": 32000, "quantity": 300, "reorder_level": 50},
    {"name": "Cement (Dangote)", "sku": "CEM-DAN", "category": "Building Materials", "unit_price": 5500, "quantity": 1000, "reorder_level": 200},
    {"name": "Iron Rod (12mm)", "sku": "IRON-12MM", "category": "Building Materials", "unit_price": 450000, "quantity": 50, "reorder_level": 10},
    {"name": "Sugar (50kg)", "sku": "SUG-50KG", "category": "Food Commodities", "unit_price": 48000, "quantity": 200, "reorder_level": 40},
    {"name": "Flour (50kg)", "sku": "FLR-50KG", "category": "Food Commodities", "unit_price": 35000, "quantity": 250, "reorder_level": 50},
    {"name": "Groundnut Oil (25L)", "sku": "GNO-25L", "category": "Food Commodities", "unit_price": 38000, "quantity": 150, "reorder_level": 30},
    {"name": "Roofing Sheets (Bundle)", "sku": "ROOF-BDL", "category": "Building Materials", "unit_price": 85000, "quantity": 100, "reorder_level": 20},
    {"name": "Beans (100kg)", "sku": "BEAN-100", "category": "Food Commodities", "unit_price": 120000, "quantity": 80, "reorder_level": 15},
    {"name": "Garri (50kg)", "sku": "GARRI-50", "category": "Food Commodities", "unit_price": 28000, "quantity": 400, "reorder_level": 80},
    {"name": "Nails (25kg box)", "sku": "NAIL-25", "category": "Building Materials", "unit_price": 25000, "quantity": 200, "reorder_level": 40},
    {"name": "Paint (20L bucket)", "sku": "PAINT-20", "category": "Building Materials", "unit_price": 35000, "quantity": 150, "reorder_level": 30},
]

# Inventory for Professional company (Tech/Consulting)
PROFESSIONAL_INVENTORY = [
    {"name": "Dell Laptop (Latitude)", "sku": "DELL-LAT", "category": "IT Equipment", "unit_price": 650000, "quantity": 25, "reorder_level": 5},
    {"name": "HP Monitor 27\"", "sku": "HP-MON27", "category": "IT Equipment", "unit_price": 180000, "quantity": 40, "reorder_level": 10},
    {"name": "Wireless Mouse", "sku": "MOUSE-WL", "category": "IT Accessories", "unit_price": 15000, "quantity": 100, "reorder_level": 20},
    {"name": "USB-C Hub", "sku": "USB-HUB", "category": "IT Accessories", "unit_price": 25000, "quantity": 50, "reorder_level": 10},
    {"name": "Office Chair (Executive)", "sku": "CHAIR-EX", "category": "Furniture", "unit_price": 120000, "quantity": 30, "reorder_level": 5},
    {"name": "Standing Desk", "sku": "DESK-STD", "category": "Furniture", "unit_price": 250000, "quantity": 15, "reorder_level": 3},
    {"name": "Projector (Epson)", "sku": "PROJ-EPS", "category": "IT Equipment", "unit_price": 450000, "quantity": 5, "reorder_level": 1},
    {"name": "Whiteboard (Large)", "sku": "WHTBRD-L", "category": "Office Supplies", "unit_price": 45000, "quantity": 20, "reorder_level": 4},
    {"name": "Network Switch (48 port)", "sku": "NET-SW48", "category": "Networking", "unit_price": 380000, "quantity": 8, "reorder_level": 2},
    {"name": "UPS (3KVA)", "sku": "UPS-3KVA", "category": "Power", "unit_price": 280000, "quantity": 12, "reorder_level": 3},
    {"name": "Server (Dell PowerEdge)", "sku": "SRV-DELL", "category": "IT Equipment", "unit_price": 2500000, "quantity": 3, "reorder_level": 1},
    {"name": "Software License (Annual)", "sku": "SOFT-LIC", "category": "Software", "unit_price": 150000, "quantity": 50, "reorder_level": 10},
]

# Customer templates
CORE_CUSTOMERS = [
    {"name": "Omoruyi Construction Ltd", "email": "info@omoruyiconstruction.com", "phone": "+234 803 111 2222"},
    {"name": "Benin City Supermarket", "email": "orders@beninsuper.com", "phone": "+234 802 333 4444"},
    {"name": "Oredo Building Supplies", "email": "sales@oredo.com", "phone": "+234 805 555 6666"},
    {"name": "Ugbowo Retailers Association", "email": "ugboworetailers@gmail.com", "phone": "+234 806 777 8888"},
    {"name": "Ring Road Merchants", "email": "ringroad@yahoo.com", "phone": "+234 807 999 0000"},
    {"name": "Sapele Road Traders", "email": "sapeletraders@gmail.com", "phone": "+234 808 111 3333"},
    {"name": "Ikpoba Hill Distributors", "email": "ikpoba@outlook.com", "phone": "+234 809 222 4444"},
    {"name": "New Benin Market Union", "email": "newbeninmarket@gmail.com", "phone": "+234 810 333 5555"},
]

PROFESSIONAL_CUSTOMERS = [
    {"name": "First Bank of Nigeria", "email": "vendor@firstbanknigeria.com", "phone": "+234 1 905 2000"},
    {"name": "MTN Nigeria Communications", "email": "procurement@mtn.com.ng", "phone": "+234 803 000 0000"},
    {"name": "Dangote Industries Ltd", "email": "it@dangote.com", "phone": "+234 1 448 0000"},
    {"name": "Access Bank Plc", "email": "tech@accessbankplc.com", "phone": "+234 1 280 5000"},
    {"name": "Nestle Nigeria Plc", "email": "digital@ng.nestle.com", "phone": "+234 1 279 3100"},
    {"name": "Nigerian Breweries Plc", "email": "systems@nbplc.com", "phone": "+234 1 271 0290"},
    {"name": "Zenith Bank Plc", "email": "vendor@zenithbank.com", "phone": "+234 1 278 0000"},
    {"name": "Unilever Nigeria Plc", "email": "it.nigeria@unilever.com", "phone": "+234 1 280 0100"},
    {"name": "Shell Nigeria", "email": "procurement.ng@shell.com", "phone": "+234 1 277 0000"},
    {"name": "Guaranty Trust Bank", "email": "technology@gtbank.com", "phone": "+234 1 448 0000"},
]

# Vendor templates
CORE_VENDORS = [
    {"name": "Olam Nigeria Ltd", "email": "sales@olam.com.ng", "phone": "+234 1 270 1234"},
    {"name": "Dangote Cement Depot", "email": "depot@dangotecement.com", "phone": "+234 802 100 2000"},
    {"name": "BUA Foods Distribution", "email": "orders@buafoods.com", "phone": "+234 803 200 3000"},
    {"name": "Lafarge Africa Supplies", "email": "supplies@lafarge.com", "phone": "+234 804 300 4000"},
    {"name": "Dufil Prima Foods", "email": "wholesale@dufil.com", "phone": "+234 805 400 5000"},
]

PROFESSIONAL_VENDORS = [
    {"name": "TD Africa (Dell Partner)", "email": "sales@tdafrica.com", "phone": "+234 1 461 0000"},
    {"name": "Zinox Technologies", "email": "corporate@zinox.com", "phone": "+234 1 271 0000"},
    {"name": "MainOne Cable Company", "email": "enterprise@mainone.net", "phone": "+234 1 700 1000"},
    {"name": "Rack Centre", "email": "sales@rfrdc.com", "phone": "+234 1 342 0000"},
    {"name": "Microsoft Nigeria", "email": "enterprise@microsoft.com", "phone": "+234 1 271 0000"},
    {"name": "Oracle Nigeria", "email": "sales@oracle.com", "phone": "+234 1 271 5000"},
]

async def create_company_data(session: AsyncSession, company_config: dict, staff_list: list, 
                               inventory_list: list, customers_list: list, vendors_list: list):
    """Create a complete company with all related data."""
    
    print(f"\n{'='*60}")
    print(f"Creating company: {company_config['name']}")
    print(f"{'='*60}")
    
    # Generate IDs
    org_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    
    # Hash password
    admin_password_hash = hash_password(company_config['admin_user']['password'])
    
    # 1. Create Organization
    print("Creating organization...")
    await session.execute(text("""
        INSERT INTO organizations (id, name, slug, email, phone, organization_type, subscription_tier, verification_status, created_at, updated_at)
        VALUES (:id, :name, :slug, :email, :phone, 'SME', :tier, 'VERIFIED', NOW(), NOW())
        ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
    """), {
        "id": str(org_id),
        "name": company_config['name'],
        "slug": company_config['slug'],
        "email": company_config['email'],
        "phone": company_config['phone'],
        "tier": company_config['tier'].upper() if company_config['tier'] != 'core' else 'FREE'
    })
    
    # 2. Create Business Entity
    print("Creating business entity...")
    await session.execute(text("""
        INSERT INTO business_entities (id, organization_id, name, legal_name, tin, rc_number,
            address_line1, address_line2, city, state, lga, country, email, phone,
            fiscal_year_start_month, currency, is_vat_registered, business_type, is_active, 
            annual_turnover_threshold, is_development_levy_exempt, b2c_realtime_reporting_enabled,
            created_at, updated_at)
        VALUES (:id, :org_id, :name, :legal_name, :tin, :rc_number,
            :addr1, :addr2, :city, :state, :lga, :country, :email, :phone,
            1, 'NGN', true, 'LIMITED_COMPANY', true,
            false, false, false,
            NOW(), NOW())
        ON CONFLICT DO NOTHING
    """), {
        "id": str(entity_id),
        "org_id": str(org_id),
        "name": company_config['name'],
        "legal_name": company_config['name'],
        "tin": company_config['tin'],
        "rc_number": company_config['rc_number'],
        "addr1": company_config['location']['address_line1'],
        "addr2": company_config['location']['address_line2'],
        "city": company_config['location']['city'],
        "state": company_config['location']['state'],
        "lga": company_config['location']['lga'],
        "country": company_config['location']['country'],
        "email": company_config['email'],
        "phone": company_config['phone']
    })
    
    # Role mapping - convert lowercase to DB enum values
    ROLE_MAP = {
        'admin': 'ADMIN',
        'accountant': 'ACCOUNTANT',
        'user': 'VIEWER',
        'auditor': 'AUDITOR',
        'payroll_manager': 'PAYROLL_MANAGER',
        'inventory_manager': 'INVENTORY_MANAGER',
        'owner': 'OWNER',
    }
    
    # 3. Create Admin User
    print("Creating admin user...")
    await session.execute(text("""
        INSERT INTO users (id, email, hashed_password, first_name, last_name, phone_number, 
            organization_id, role, is_active, is_verified, is_superuser, created_at, updated_at)
        VALUES (:id, :email, :password, :first_name, :last_name, :phone,
            :org_id, 'ADMIN', true, true, false, NOW(), NOW())
        ON CONFLICT (email) DO UPDATE SET 
            hashed_password = EXCLUDED.hashed_password,
            organization_id = EXCLUDED.organization_id
    """), {
        "id": str(admin_id),
        "email": company_config['admin_user']['email'],
        "password": admin_password_hash,
        "first_name": company_config['admin_user']['first_name'],
        "last_name": company_config['admin_user']['last_name'],
        "phone": company_config['admin_user']['phone'],
        "org_id": str(org_id)
    })
    
    # Give admin access to entity
    await session.execute(text("""
        INSERT INTO user_entity_access (id, user_id, entity_id, can_write, can_delete, created_at, updated_at)
        VALUES (:id, :user_id, :entity_id, true, true, NOW(), NOW())
        ON CONFLICT DO NOTHING
    """), {"id": str(uuid.uuid4()), "user_id": str(admin_id), "entity_id": str(entity_id)})
    
    # 4. Create TenantSKU
    print("Creating tenant SKU...")
    period_start = date.today().replace(day=1)
    period_end = (period_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    
    await session.execute(text("""
        INSERT INTO tenant_skus (id, organization_id, tier, intelligence_addon, billing_cycle, 
            current_period_start, current_period_end, is_active, created_at, updated_at)
        VALUES (:id, :org_id, :tier, 'standard', 'monthly', :period_start, :period_end, true, NOW(), NOW())
        ON CONFLICT (organization_id) DO UPDATE SET tier = EXCLUDED.tier
    """), {
        "id": str(uuid.uuid4()),
        "org_id": str(org_id),
        "tier": company_config['tier'],
        "period_start": period_start,
        "period_end": period_end
    })
    
    # 5. Create Staff/Users
    print(f"Creating {len(staff_list)} staff members...")
    user_ids = []
    employee_ids = []
    
    for staff in staff_list:
        user_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        user_ids.append(user_id)
        employee_ids.append((employee_id, staff))
        
        staff_password_hash = hash_password("Staff2024!")
        db_role = ROLE_MAP.get(staff['role'], 'VIEWER')
        
        await session.execute(text("""
            INSERT INTO users (id, email, hashed_password, first_name, last_name, 
                organization_id, role, is_active, is_verified, is_superuser, created_at, updated_at)
            VALUES (:id, :email, :password, :first_name, :last_name,
                :org_id, :role, true, true, false, NOW(), NOW())
            ON CONFLICT (email) DO UPDATE SET organization_id = EXCLUDED.organization_id
        """), {
            "id": str(user_id),
            "email": staff['email'],
            "password": staff_password_hash,
            "first_name": staff['first_name'],
            "last_name": staff['last_name'],
            "org_id": str(org_id),
            "role": db_role
        })
        
        # Entity access
        await session.execute(text("""
            INSERT INTO user_entity_access (id, user_id, entity_id, can_write, can_delete, created_at, updated_at)
            VALUES (:id, :user_id, :entity_id, :can_write, false, NOW(), NOW())
            ON CONFLICT DO NOTHING
        """), {
            "id": str(uuid.uuid4()),
            "user_id": str(user_id),
            "entity_id": str(entity_id),
            "can_write": staff['role'] in ['admin', 'accountant']
        })
    
    # 6. Create Employees (for payroll)
    print("Creating employee records for payroll...")
    for emp_id, staff in employee_ids:
        hire_date = date.today() - timedelta(days=random.randint(365, 3650))  # 1-10 years ago
        
        await session.execute(text("""
            INSERT INTO employees (
                id, entity_id, employee_id, first_name, last_name, email, phone_number,
                department, job_title, employment_type, employment_status, hire_date, 
                payroll_frequency, currency, basic_salary, housing_allowance, transport_allowance,
                meal_allowance, utility_allowance, annual_leave_days, sick_leave_days, leave_balance,
                is_pension_exempt, is_nhf_exempt, annual_rent_paid, has_life_insurance, 
                monthly_insurance_premium, is_active, created_at, updated_at
            )
            VALUES (
                :id, :entity_id, :emp_num, :first_name, :last_name, :email, :phone,
                :department, :job_title, 'FULL_TIME', 'ACTIVE', :hire_date,
                'MONTHLY', 'NGN', :salary, :housing, :transport,
                :meal, :utility, 21, 10, 21.0,
                false, false, 0, false,
                0, true, NOW(), NOW()
            )
            ON CONFLICT DO NOTHING
        """), {
            "id": str(emp_id),
            "entity_id": str(entity_id),
            "emp_num": f"EMP{random.randint(1000, 9999)}",
            "first_name": staff['first_name'],
            "last_name": staff['last_name'],
            "email": staff['email'],
            "phone": f"+234 80{random.randint(1,9)} {random.randint(100,999)} {random.randint(1000,9999)}",
            "department": staff['department'],
            "job_title": f"{staff['department']} Staff",
            "hire_date": hire_date,
            "salary": staff['salary'] * 0.6,  # Basic is 60% of gross
            "housing": staff['salary'] * 0.2,  # Housing 20%
            "transport": staff['salary'] * 0.1,  # Transport 10%
            "meal": staff['salary'] * 0.05,  # Meal 5%
            "utility": staff['salary'] * 0.05,  # Utility 5%
        })
    
    # 7. Create Inventory Items
    print(f"Creating {len(inventory_list)} inventory items...")
    inventory_ids = []
    
    for item in inventory_list:
        inv_id = uuid.uuid4()
        inventory_ids.append((inv_id, item))
        
        await session.execute(text("""
            INSERT INTO inventory_items (id, entity_id, name, sku, category, unit_cost, unit_price, 
                quantity_on_hand, reorder_level, reorder_quantity, unit_of_measure, is_active, is_tracked, created_at, updated_at)
            VALUES (:id, :entity_id, :name, :sku, :category, :unit_cost, :unit_price,
                :quantity, :reorder_level, :reorder_qty, 'unit', true, true, NOW(), NOW())
            ON CONFLICT DO NOTHING
        """), {
            "id": str(inv_id),
            "entity_id": str(entity_id),
            "name": item['name'],
            "sku": item['sku'],
            "category": item['category'],
            "unit_cost": item['unit_price'] * 0.7,  # Cost is 70% of price
            "unit_price": item['unit_price'],
            "quantity": item['quantity'],
            "reorder_level": item['reorder_level'],
            "reorder_qty": item['reorder_level'] * 2  # Reorder quantity is 2x reorder level
        })
    
    # 8. Create Customers
    print(f"Creating {len(customers_list)} customers...")
    customer_ids = []
    
    for customer in customers_list:
        cust_id = uuid.uuid4()
        customer_ids.append((cust_id, customer))
        
        await session.execute(text("""
            INSERT INTO customers (id, entity_id, name, email, phone, is_business,
                is_active, created_at, updated_at)
            VALUES (:id, :entity_id, :name, :email, :phone, true,
                true, NOW(), NOW())
            ON CONFLICT DO NOTHING
        """), {
            "id": str(cust_id),
            "entity_id": str(entity_id),
            "name": customer['name'],
            "email": customer['email'],
            "phone": customer['phone']
        })
    
    # 9. Create Vendors
    print(f"Creating {len(vendors_list)} vendors...")
    vendor_ids = []
    
    for vendor in vendors_list:
        vend_id = uuid.uuid4()
        vendor_ids.append((vend_id, vendor))
        
        await session.execute(text("""
            INSERT INTO vendors (id, entity_id, name, email, phone, country,
                tin_verified, is_vat_registered, is_active, created_at, updated_at)
            VALUES (:id, :entity_id, :name, :email, :phone, 'Nigeria',
                false, true, true, NOW(), NOW())
            ON CONFLICT DO NOTHING
        """), {
            "id": str(vend_id),
            "entity_id": str(entity_id),
            "name": vendor['name'],
            "email": vendor['email'],
            "phone": vendor['phone']
        })
    
    # 10. Create 5 Years of Transactions
    print("Creating 5 years of transaction history...")
    transaction_count = 0
    
    for year_offset in range(5):
        year = date.today().year - year_offset
        
        # Monthly transactions
        for month in range(1, 13):
            if year == date.today().year and month > date.today().month:
                continue
            
            # 15-30 transactions per month
            num_transactions = random.randint(15, 30)
            
            for _ in range(num_transactions):
                trans_date = date(year, month, random.randint(1, 28))
                trans_type = random.choice(['INCOME', 'INCOME', 'INCOME', 'EXPENSE', 'EXPENSE'])
                
                if trans_type == 'INCOME':
                    amount = random.randint(50000, 2000000)
                    description = f"Payment from {random.choice(customers_list)['name']}"
                else:
                    amount = random.randint(20000, 500000)
                    description = f"Payment to {random.choice(vendors_list)['name']}"
                
                vat_amount = amount * 0.075 if random.random() > 0.3 else 0
                total_amount = amount + vat_amount
                
                await session.execute(text("""
                    INSERT INTO transactions (id, entity_id, transaction_type, amount, vat_amount, total_amount,
                        wht_amount, currency, exchange_rate, functional_amount, functional_vat_amount, 
                        functional_total_amount, realized_fx_gain_loss, description, transaction_date, 
                        wren_status, vat_recoverable, is_recurring, created_at, updated_at)
                    VALUES (:id, :entity_id, :type, :amount, :vat, :total,
                        0, 'NGN', 1.0, :amount, :vat, :total, 0,
                        :description, :trans_date, 'COMPLIANT', true, false, NOW(), NOW())
                """), {
                    "id": str(uuid.uuid4()),
                    "entity_id": str(entity_id),
                    "type": trans_type,
                    "amount": amount,
                    "vat": vat_amount,
                    "total": total_amount,
                    "description": description,
                    "trans_date": trans_date
                })
                transaction_count += 1
    
    print(f"  Created {transaction_count} transactions")
    
    # 11. Create 10 Years of Payroll History
    print("Creating 10 years of payroll history...")
    payroll_count = 0
    
    for year_offset in range(10):
        year = date.today().year - year_offset
        
        for month in range(1, 13):
            if year == date.today().year and month > date.today().month:
                continue
            
            pay_date = date(year, month, 25) if date(year, month, 25) <= date.today() else None
            if not pay_date:
                continue
            
            # Create payroll run
            payroll_run_id = uuid.uuid4()
            period_start = date(year, month, 1)
            period_end = (period_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            
            total_gross = 0
            total_net = 0
            total_deductions = 0
            total_paye = 0
            total_pension_emp = 0
            total_pension_er = 0
            total_nhf = 0
            
            await session.execute(text("""
                INSERT INTO payroll_runs (id, entity_id, payroll_code, name, frequency,
                    period_start, period_end, payment_date, status, total_employees,
                    total_gross_pay, total_deductions, total_net_pay, total_employer_contributions,
                    total_paye, total_pension_employee, total_pension_employer, total_nhf, total_nsitf, total_itf,
                    is_locked, created_at, updated_at)
                VALUES (:id, :entity_id, :code, :name, 'MONTHLY',
                    :period_start, :period_end, :pay_date, 'COMPLETED', :emp_count,
                    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                    true, NOW(), NOW())
                ON CONFLICT DO NOTHING
            """), {
                "id": str(payroll_run_id),
                "entity_id": str(entity_id),
                "code": f"PR-{year}{month:02d}",
                "name": f"Payroll {year}-{month:02d}",
                "period_start": period_start,
                "period_end": period_end,
                "pay_date": pay_date,
                "emp_count": len(employee_ids)
            })
            
            # Create payslips for each employee
            for emp_id, staff in employee_ids:
                gross = staff['salary']
                basic = gross * 0.6
                housing = gross * 0.2
                transport = gross * 0.1
                meal = gross * 0.05
                utility = gross * 0.05
                
                # Deductions
                paye = int(gross * 0.07)
                pension_emp = int(gross * 0.08)
                nhf_amount = int(gross * 0.025)
                deductions = paye + pension_emp + nhf_amount
                net = gross - deductions
                pension_er = int(gross * 0.10)
                
                total_gross += gross
                total_net += net
                total_deductions += deductions
                total_paye += paye
                total_pension_emp += pension_emp
                total_pension_er += pension_er
                total_nhf += nhf_amount
                
                payslip_number = f"PS-{year}{month:02d}-{random.randint(1000,9999)}"
                
                await session.execute(text("""
                    INSERT INTO payslips (id, payroll_run_id, employee_id, payslip_number,
                        days_in_period, days_worked, days_absent,
                        basic_salary, housing_allowance, transport_allowance, meal_allowance, utility_allowance,
                        overtime_pay, bonus, other_earnings, gross_pay,
                        paye_tax, pension_employee, nhf, loan_deduction, salary_advance_deduction,
                        cooperative_deduction, union_dues, other_deductions, total_deductions, net_pay,
                        pension_employer, nsitf, itf, hmo_employer, group_life_insurance,
                        consolidated_relief, rent_relief, pension_relief, nhf_relief, taxable_income,
                        is_paid, is_emailed, created_at, updated_at)
                    VALUES (:id, :run_id, :emp_id, :payslip_num,
                        30, 30, 0,
                        :basic, :housing, :transport, :meal, :utility,
                        0, 0, 0, :gross,
                        :paye, :pension_emp, :nhf, 0, 0,
                        0, 0, 0, :deductions, :net,
                        :pension_er, 0, 0, 0, 0,
                        0, 0, 0, 0, :taxable,
                        true, false, NOW(), NOW())
                    ON CONFLICT DO NOTHING
                """), {
                    "id": str(uuid.uuid4()),
                    "run_id": str(payroll_run_id),
                    "emp_id": str(emp_id),
                    "payslip_num": payslip_number,
                    "basic": basic,
                    "housing": housing,
                    "transport": transport,
                    "meal": meal,
                    "utility": utility,
                    "gross": gross,
                    "paye": paye,
                    "pension_emp": pension_emp,
                    "nhf": nhf_amount,
                    "deductions": deductions,
                    "net": net,
                    "pension_er": pension_er,
                    "taxable": gross * 0.8
                })
                payroll_count += 1
            
            # Update payroll run totals
            await session.execute(text("""
                UPDATE payroll_runs SET 
                    total_gross_pay = :gross, total_net_pay = :net, total_deductions = :deductions,
                    total_paye = :paye, total_pension_employee = :pension_emp, 
                    total_pension_employer = :pension_er, total_nhf = :nhf,
                    total_employer_contributions = :employer_contrib
                WHERE id = :id
            """), {
                "id": str(payroll_run_id), 
                "gross": total_gross, 
                "net": total_net,
                "deductions": total_deductions,
                "paye": total_paye,
                "pension_emp": total_pension_emp,
                "pension_er": total_pension_er,
                "nhf": total_nhf,
                "employer_contrib": total_pension_er
            })
    
    print(f"  Created {payroll_count} payslips")
    
    # 12. Create Invoices (5 years)
    print("Creating 5 years of invoices...")
    invoice_count = 0
    
    for year_offset in range(5):
        year = date.today().year - year_offset
        
        for month in range(1, 13):
            if year == date.today().year and month > date.today().month:
                continue
            
            # 5-15 invoices per month
            num_invoices = random.randint(5, 15)
            
            for inv_num in range(num_invoices):
                inv_date = date(year, month, random.randint(1, 28))
                due_date = inv_date + timedelta(days=30)
                
                customer = random.choice(customer_ids)
                
                # Invoice items
                num_items = random.randint(1, 5)
                subtotal = 0
                items_data = []
                
                for _ in range(num_items):
                    item = random.choice(inventory_ids)
                    qty = random.randint(1, 20)
                    unit_price = item[1]['unit_price']
                    line_total = qty * unit_price
                    subtotal += line_total
                    items_data.append({
                        "description": item[1]['name'],
                        "quantity": qty,
                        "unit_price": unit_price,
                        "total": line_total
                    })
                
                vat = int(subtotal * 0.075)  # 7.5% VAT
                total = subtotal + vat
                
                status = 'PAID' if random.random() < 0.85 else random.choice(['PENDING', 'PARTIALLY_PAID'])
                amount_paid = total if status == 'PAID' else (total * 0.5 if status == 'PARTIALLY_PAID' else 0)
                
                invoice_id = uuid.uuid4()
                invoice_number = f"INV-{year}{month:02d}-{inv_num+1:04d}"
                
                await session.execute(text("""
                    INSERT INTO invoices (id, entity_id, customer_id, invoice_number,
                        invoice_date, due_date, subtotal, vat_amount, discount_amount, total_amount,
                        amount_paid, vat_treatment, vat_rate, status, 
                        is_disputed, is_nrs_locked, is_credit_note, is_b2c_reportable,
                        created_at, updated_at)
                    VALUES (:id, :entity_id, :customer_id, :inv_number,
                        :inv_date, :due_date, :subtotal, :vat, 0, :total,
                        :amount_paid, 'STANDARD', 7.5, :status,
                        false, false, false, false,
                        NOW(), NOW())
                    ON CONFLICT DO NOTHING
                """), {
                    "id": str(invoice_id),
                    "entity_id": str(entity_id),
                    "customer_id": str(customer[0]),
                    "inv_number": invoice_number,
                    "inv_date": inv_date,
                    "due_date": due_date,
                    "subtotal": subtotal,
                    "vat": vat,
                    "total": total,
                    "amount_paid": amount_paid,
                    "status": status
                })
                
                invoice_count += 1
    
    print(f"  Created {invoice_count} invoices")
    
    await session.commit()
    
    return {
        "organization_id": str(org_id),
        "entity_id": str(entity_id),
        "admin_id": str(admin_id),
        "staff_count": len(staff_list),
        "transaction_count": transaction_count,
        "payroll_count": payroll_count,
        "invoice_count": invoice_count
    }


async def main():
    """Main function to seed demo companies."""
    print("\n" + "="*70)
    print("Tekvwa Pro Audit - Demo Companies Seeder")
    print("="*70)
    
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    results = {}
    
    async with async_session() as session:
        # Create Core company (Okonkwo & Sons - Benin City)
        results['core'] = await create_company_data(
            session, CORE_COMPANY, CORE_STAFF, CORE_INVENTORY, 
            CORE_CUSTOMERS, CORE_VENDORS
        )
        
        # Create Professional company (Lagos Prime - Ajah)
        results['professional'] = await create_company_data(
            session, PROFESSIONAL_COMPANY, PROFESSIONAL_STAFF, 
            PROFESSIONAL_INVENTORY, PROFESSIONAL_CUSTOMERS, PROFESSIONAL_VENDORS
        )
    
    await engine.dispose()
    
    # Print summary
    print("\n" + "="*70)
    print("DEMO COMPANIES CREATED SUCCESSFULLY!")
    print("="*70)
    
    print("\n" + "-"*70)
    print("CORE TIER - Okonkwo & Sons Trading (Benin City)")
    print("-"*70)
    print(f"  Organization ID: {results['core']['organization_id']}")
    print(f"  Admin Login: {CORE_COMPANY['admin_user']['email']}")
    print(f"  Password: {CORE_COMPANY['admin_user']['password']}")
    print(f"  Staff: {results['core']['staff_count']} members")
    print(f"  Transactions: {results['core']['transaction_count']} records (5 years)")
    print(f"  Payslips: {results['core']['payroll_count']} records (10 years)")
    print(f"  Invoices: {results['core']['invoice_count']} records (5 years)")
    
    print("\n" + "-"*70)
    print("PROFESSIONAL TIER - Lagos Prime Ventures Ltd (Ajah, Lagos)")
    print("-"*70)
    print(f"  Organization ID: {results['professional']['organization_id']}")
    print(f"  Admin Login: {PROFESSIONAL_COMPANY['admin_user']['email']}")
    print(f"  Password: {PROFESSIONAL_COMPANY['admin_user']['password']}")
    print(f"  Staff: {results['professional']['staff_count']} members")
    print(f"  Transactions: {results['professional']['transaction_count']} records (5 years)")
    print(f"  Payslips: {results['professional']['payroll_count']} records (10 years)")
    print(f"  Invoices: {results['professional']['invoice_count']} records (5 years)")
    
    print("\n" + "="*70)
    print("Staff password for all non-admin users: Staff2024!")
    print("="*70 + "\n")
    
    return results


if __name__ == "__main__":
    asyncio.run(main())
