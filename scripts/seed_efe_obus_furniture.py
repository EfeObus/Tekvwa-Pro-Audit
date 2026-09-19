"""
Seed Script: Efe Obus Furniture Manufacturing LTD
==================================================
A comprehensive test company with full data for testing Tekvwa Pro Audit.

Owner: Efe Obukohwo
Email: efeobukohwo64@gmail.com
Password: Efeobus12345

Company: Efe Obus Furniture Manufacturing LTD
Type: Large Corporation
Industry: Furniture Manufacturing

This script creates:
- Organization and Business Entity
- Owner user with full RBAC permissions
- 15 Employees across departments
- 35 Customers (B2B and B2C)
- 20 Vendors/Suppliers
- Inventory items (raw materials, WIP, finished goods)
- Fixed Assets (machinery, vehicles, buildings)
- Transaction history
- Invoices
- Categories for income/expense tracking
"""

import asyncio
import uuid
import random
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List

# Add project root to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext

from app.database import async_session_maker, engine
from app.models.organization import Organization, OrganizationType, SubscriptionTier, VerificationStatus
from app.models.entity import BusinessEntity, BusinessType
from app.models.user import User, UserRole
from app.models.customer import Customer
from app.models.vendor import Vendor
from app.models.inventory import InventoryItem, StockMovement, StockMovementType
from app.models.fixed_asset import FixedAsset, AssetCategory, AssetStatus, DepreciationMethod
from app.models.payroll import (
    Employee, EmploymentType, EmploymentStatus, PayrollFrequency,
    BankName, PensionFundAdministrator, EmployeeBankAccount
)
from app.models.category import Category, CategoryType, VATTreatment
from app.models.transaction import Transaction, TransactionType, WRENStatus
from app.models.invoice import Invoice, InvoiceStatus, InvoiceLineItem

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a password for storing."""
    return pwd_context.hash(password)


# =============================================================================
# COMPANY DATA
# =============================================================================

COMPANY_DATA = {
    "organization": {
        "name": "Efe Obus Furniture Manufacturing LTD",
        "slug": "efe-obus-furniture",
        "email": "info@efeobusfurniture.com.ng",
        "phone": "+234 802 345 6789",
        "organization_type": OrganizationType.CORPORATION,
        "subscription_tier": SubscriptionTier.ENTERPRISE,
        "verification_status": VerificationStatus.VERIFIED,
    },
    "entity": {
        "name": "Efe Obus Furniture Manufacturing LTD",
        "legal_name": "Efe Obus Furniture Manufacturing Limited",
        "tin": "12345678-0001",
        "rc_number": "RC 1234567",
        "address_line1": "Plot 45, Industrial Layout",
        "address_line2": "Agbor-Obi Road",
        "city": "Agbor",
        "state": "Delta",
        "lga": "Ika South",
        "country": "Nigeria",
        "email": "accounts@efeobusfurniture.com.ng",
        "phone": "+234 802 345 6789",
        "website": "https://efeobusfurniture.com.ng",
        "fiscal_year_start_month": 1,
        "currency": "NGN",
        "is_vat_registered": True,
        "vat_registration_date": date(2020, 1, 15),
        "business_type": BusinessType.LIMITED_COMPANY,
        "annual_turnover": Decimal("850000000.00"),  # 850M NGN
        "fixed_assets_value": Decimal("450000000.00"),  # 450M NGN
        "is_development_levy_exempt": False,
        "b2c_realtime_reporting_enabled": True,
    },
    "owner": {
        "email": "efeobukohwo64@gmail.com",
        "password": "Efeobus12345",
        "first_name": "Efe",
        "last_name": "Obukohwo",
        "phone_number": "+234 803 456 7890",
        "role": UserRole.OWNER,
    }
}


# =============================================================================
# CATEGORIES DATA
# =============================================================================

CATEGORIES_DATA = [
    # Income Categories
    {"name": "Furniture Sales", "code": "INC001", "category_type": CategoryType.INCOME, "wren_default": True},
    {"name": "Custom Orders", "code": "INC002", "category_type": CategoryType.INCOME, "wren_default": True},
    {"name": "Installation Services", "code": "INC003", "category_type": CategoryType.INCOME, "wren_default": True},
    {"name": "Delivery Charges", "code": "INC004", "category_type": CategoryType.INCOME, "wren_default": True},
    {"name": "Repairs & Restoration", "code": "INC005", "category_type": CategoryType.INCOME, "wren_default": True},
    {"name": "Scrap Sales", "code": "INC006", "category_type": CategoryType.INCOME, "wren_default": True},
    {"name": "Interest Income", "code": "INC007", "category_type": CategoryType.INCOME, "wren_default": True},
    
    # Expense Categories
    {"name": "Raw Materials - Wood", "code": "EXP001", "category_type": CategoryType.EXPENSE, "wren_default": True},
    {"name": "Raw Materials - Fabrics", "code": "EXP002", "category_type": CategoryType.EXPENSE, "wren_default": True},
    {"name": "Raw Materials - Hardware", "code": "EXP003", "category_type": CategoryType.EXPENSE, "wren_default": True},
    {"name": "Salaries & Wages", "code": "EXP004", "category_type": CategoryType.EXPENSE, "wren_default": True},
    {"name": "Electricity & Power", "code": "EXP005", "category_type": CategoryType.EXPENSE, "wren_default": True},
    {"name": "Fuel & Generator", "code": "EXP006", "category_type": CategoryType.EXPENSE, "wren_default": True},
    {"name": "Vehicle Maintenance", "code": "EXP007", "category_type": CategoryType.EXPENSE, "wren_default": True},
    {"name": "Equipment Maintenance", "code": "EXP008", "category_type": CategoryType.EXPENSE, "wren_default": True},
    {"name": "Rent & Rates", "code": "EXP009", "category_type": CategoryType.EXPENSE, "wren_default": True},
    {"name": "Insurance", "code": "EXP010", "category_type": CategoryType.EXPENSE, "wren_default": True},
    {"name": "Professional Fees", "code": "EXP011", "category_type": CategoryType.EXPENSE, "wren_default": True},
    {"name": "Advertising & Marketing", "code": "EXP012", "category_type": CategoryType.EXPENSE, "wren_default": True},
    {"name": "Office Supplies", "code": "EXP013", "category_type": CategoryType.EXPENSE, "wren_default": True},
    {"name": "Telecommunications", "code": "EXP014", "category_type": CategoryType.EXPENSE, "wren_default": True},
    {"name": "Bank Charges", "code": "EXP015", "category_type": CategoryType.EXPENSE, "wren_default": True},
    {"name": "Entertainment", "code": "EXP016", "category_type": CategoryType.EXPENSE, "wren_default": False, "wren_review_required": True},
    {"name": "Travel & Transport", "code": "EXP017", "category_type": CategoryType.EXPENSE, "wren_default": True},
    {"name": "Training & Development", "code": "EXP018", "category_type": CategoryType.EXPENSE, "wren_default": True},
    {"name": "Security Services", "code": "EXP019", "category_type": CategoryType.EXPENSE, "wren_default": True},
    {"name": "Cleaning & Sanitation", "code": "EXP020", "category_type": CategoryType.EXPENSE, "wren_default": True},
]


# =============================================================================
# EMPLOYEES DATA (15 employees across departments)
# =============================================================================

EMPLOYEES_DATA = [
    # Management
    {
        "employee_id": "EMP001",
        "title": "Mr.",
        "first_name": "Efe",
        "middle_name": "Obus",
        "last_name": "Obukohwo",
        "email": "ceo@efeobusfurniture.com.ng",
        "phone_number": "+234 803 456 7890",
        "date_of_birth": date(1980, 5, 15),
        "gender": "Male",
        "marital_status": "Married",
        "address": "15 Executive Drive, GRA",
        "city": "Agbor",
        "state": "Delta",
        "lga": "Ika South",
        "nin": "12345678901",
        "bvn": "22345678901",
        "tin": "TIN12345678",
        "tax_state": "Delta",
        "pension_pin": "PEN123456789",
        "pfa": PensionFundAdministrator.STANBIC_IBTC_PENSION,
        "department": "Executive",
        "job_title": "Chief Executive Officer",
        "job_grade": "E1",
        "hire_date": date(2015, 1, 1),
        "confirmation_date": date(2015, 1, 1),
        "basic_salary": Decimal("2500000.00"),
        "housing_allowance": Decimal("1000000.00"),
        "transport_allowance": Decimal("500000.00"),
        "bank_name": BankName.GTBANK,
        "account_number": "0123456789",
        "account_name": "Efe Obus Obukohwo",
    },
    {
        "employee_id": "EMP002",
        "title": "Mrs.",
        "first_name": "Adaeze",
        "middle_name": "Chioma",
        "last_name": "Okonkwo",
        "email": "cfo@efeobusfurniture.com.ng",
        "phone_number": "+234 805 123 4567",
        "date_of_birth": date(1985, 8, 22),
        "gender": "Female",
        "marital_status": "Married",
        "address": "23 Finance Street",
        "city": "Agbor",
        "state": "Delta",
        "lga": "Ika South",
        "nin": "23456789012",
        "bvn": "33456789012",
        "tin": "TIN23456789",
        "tax_state": "Delta",
        "pension_pin": "PEN234567890",
        "pfa": PensionFundAdministrator.ARM_PENSION,
        "department": "Finance",
        "job_title": "Chief Financial Officer",
        "job_grade": "E2",
        "hire_date": date(2016, 3, 15),
        "confirmation_date": date(2016, 6, 15),
        "basic_salary": Decimal("1800000.00"),
        "housing_allowance": Decimal("720000.00"),
        "transport_allowance": Decimal("360000.00"),
        "bank_name": BankName.ZENITH_BANK,
        "account_number": "1234567890",
        "account_name": "Adaeze Chioma Okonkwo",
    },
    {
        "employee_id": "EMP003",
        "title": "Mr.",
        "first_name": "Chukwuemeka",
        "middle_name": "Ifeanyi",
        "last_name": "Nwosu",
        "email": "production@efeobusfurniture.com.ng",
        "phone_number": "+234 806 234 5678",
        "date_of_birth": date(1978, 3, 10),
        "gender": "Male",
        "marital_status": "Married",
        "address": "45 Factory Road",
        "city": "Agbor",
        "state": "Delta",
        "lga": "Ika South",
        "nin": "34567890123",
        "bvn": "44567890123",
        "tin": "TIN34567890",
        "tax_state": "Delta",
        "pension_pin": "PEN345678901",
        "pfa": PensionFundAdministrator.LEADWAY_PENSURE,
        "department": "Production",
        "job_title": "Production Manager",
        "job_grade": "M1",
        "hire_date": date(2017, 1, 10),
        "confirmation_date": date(2017, 4, 10),
        "basic_salary": Decimal("850000.00"),
        "housing_allowance": Decimal("340000.00"),
        "transport_allowance": Decimal("170000.00"),
        "bank_name": BankName.FIRST_BANK,
        "account_number": "2345678901",
        "account_name": "Chukwuemeka Ifeanyi Nwosu",
    },
    # Production Workers
    {
        "employee_id": "EMP004",
        "title": "Mr.",
        "first_name": "Obiora",
        "last_name": "Eze",
        "email": "obiora.eze@efeobusfurniture.com.ng",
        "phone_number": "+234 807 345 6789",
        "date_of_birth": date(1990, 7, 18),
        "gender": "Male",
        "marital_status": "Single",
        "address": "12 Carpenter Street",
        "city": "Agbor",
        "state": "Delta",
        "lga": "Ika South",
        "department": "Production",
        "job_title": "Senior Carpenter",
        "job_grade": "S1",
        "hire_date": date(2018, 5, 1),
        "confirmation_date": date(2018, 8, 1),
        "basic_salary": Decimal("280000.00"),
        "housing_allowance": Decimal("112000.00"),
        "transport_allowance": Decimal("56000.00"),
        "bank_name": BankName.ACCESS_BANK,
        "account_number": "3456789012",
        "account_name": "Obiora Eze",
    },
    {
        "employee_id": "EMP005",
        "title": "Mr.",
        "first_name": "Tochukwu",
        "last_name": "Okeke",
        "email": "tochukwu.okeke@efeobusfurniture.com.ng",
        "phone_number": "+234 808 456 7890",
        "date_of_birth": date(1992, 11, 5),
        "gender": "Male",
        "marital_status": "Married",
        "address": "8 Wood Lane",
        "city": "Agbor",
        "state": "Delta",
        "lga": "Ika South",
        "department": "Production",
        "job_title": "Carpenter",
        "job_grade": "S2",
        "hire_date": date(2019, 2, 15),
        "confirmation_date": date(2019, 5, 15),
        "basic_salary": Decimal("180000.00"),
        "housing_allowance": Decimal("72000.00"),
        "transport_allowance": Decimal("36000.00"),
        "bank_name": BankName.UBA,
        "account_number": "4567890123",
        "account_name": "Tochukwu Okeke",
    },
    {
        "employee_id": "EMP006",
        "title": "Mr.",
        "first_name": "Emeka",
        "last_name": "Obi",
        "email": "emeka.obi@efeobusfurniture.com.ng",
        "phone_number": "+234 809 567 8901",
        "date_of_birth": date(1988, 4, 20),
        "gender": "Male",
        "marital_status": "Married",
        "address": "22 Timber Close",
        "city": "Agbor",
        "state": "Delta",
        "lga": "Ika South",
        "department": "Production",
        "job_title": "Upholsterer",
        "job_grade": "S2",
        "hire_date": date(2019, 6, 1),
        "confirmation_date": date(2019, 9, 1),
        "basic_salary": Decimal("200000.00"),
        "housing_allowance": Decimal("80000.00"),
        "transport_allowance": Decimal("40000.00"),
        "bank_name": BankName.FIDELITY_BANK,
        "account_number": "5678901234",
        "account_name": "Emeka Obi",
    },
    {
        "employee_id": "EMP007",
        "title": "Miss",
        "first_name": "Ngozi",
        "last_name": "Agu",
        "email": "ngozi.agu@efeobusfurniture.com.ng",
        "phone_number": "+234 810 678 9012",
        "date_of_birth": date(1995, 9, 12),
        "gender": "Female",
        "marital_status": "Single",
        "address": "5 Design Avenue",
        "city": "Agbor",
        "state": "Delta",
        "lga": "Ika South",
        "department": "Design",
        "job_title": "Furniture Designer",
        "job_grade": "S1",
        "hire_date": date(2020, 1, 15),
        "confirmation_date": date(2020, 4, 15),
        "basic_salary": Decimal("320000.00"),
        "housing_allowance": Decimal("128000.00"),
        "transport_allowance": Decimal("64000.00"),
        "bank_name": BankName.KUDA,
        "account_number": "6789012345",
        "account_name": "Ngozi Agu",
    },
    # Sales & Marketing
    {
        "employee_id": "EMP008",
        "title": "Mr.",
        "first_name": "Chibuike",
        "last_name": "Nnaji",
        "email": "sales@efeobusfurniture.com.ng",
        "phone_number": "+234 811 789 0123",
        "date_of_birth": date(1987, 12, 25),
        "gender": "Male",
        "marital_status": "Married",
        "address": "30 Commerce Road",
        "city": "Agbor",
        "state": "Delta",
        "lga": "Ika South",
        "department": "Sales",
        "job_title": "Sales Manager",
        "job_grade": "M2",
        "hire_date": date(2018, 3, 1),
        "confirmation_date": date(2018, 6, 1),
        "basic_salary": Decimal("550000.00"),
        "housing_allowance": Decimal("220000.00"),
        "transport_allowance": Decimal("110000.00"),
        "bank_name": BankName.STERLING_BANK,
        "account_number": "7890123456",
        "account_name": "Chibuike Nnaji",
    },
    {
        "employee_id": "EMP009",
        "title": "Miss",
        "first_name": "Amaka",
        "last_name": "Igwe",
        "email": "amaka.igwe@efeobusfurniture.com.ng",
        "phone_number": "+234 812 890 1234",
        "date_of_birth": date(1993, 6, 8),
        "gender": "Female",
        "marital_status": "Single",
        "address": "18 Marketing Plaza",
        "city": "Agbor",
        "state": "Delta",
        "lga": "Ika South",
        "department": "Sales",
        "job_title": "Sales Executive",
        "job_grade": "S2",
        "hire_date": date(2021, 1, 10),
        "confirmation_date": date(2021, 4, 10),
        "basic_salary": Decimal("220000.00"),
        "housing_allowance": Decimal("88000.00"),
        "transport_allowance": Decimal("44000.00"),
        "bank_name": BankName.WEMA_BANK,
        "account_number": "8901234567",
        "account_name": "Amaka Igwe",
    },
    # Finance & Admin
    {
        "employee_id": "EMP010",
        "title": "Mr.",
        "first_name": "Ikechukwu",
        "last_name": "Okafor",
        "email": "accounts@efeobusfurniture.com.ng",
        "phone_number": "+234 813 901 2345",
        "date_of_birth": date(1989, 2, 14),
        "gender": "Male",
        "marital_status": "Married",
        "address": "7 Accounts Lane",
        "city": "Agbor",
        "state": "Delta",
        "lga": "Ika South",
        "department": "Finance",
        "job_title": "Senior Accountant",
        "job_grade": "S1",
        "hire_date": date(2019, 8, 1),
        "confirmation_date": date(2019, 11, 1),
        "basic_salary": Decimal("380000.00"),
        "housing_allowance": Decimal("152000.00"),
        "transport_allowance": Decimal("76000.00"),
        "bank_name": BankName.STANBIC_IBTC,
        "account_number": "9012345678",
        "account_name": "Ikechukwu Okafor",
    },
    {
        "employee_id": "EMP011",
        "title": "Mrs.",
        "first_name": "Blessing",
        "last_name": "Udoh",
        "email": "hr@efeobusfurniture.com.ng",
        "phone_number": "+234 814 012 3456",
        "date_of_birth": date(1986, 10, 30),
        "gender": "Female",
        "marital_status": "Married",
        "address": "14 HR Complex",
        "city": "Agbor",
        "state": "Delta",
        "lga": "Ika South",
        "department": "Human Resources",
        "job_title": "HR Manager",
        "job_grade": "M2",
        "hire_date": date(2017, 7, 1),
        "confirmation_date": date(2017, 10, 1),
        "basic_salary": Decimal("480000.00"),
        "housing_allowance": Decimal("192000.00"),
        "transport_allowance": Decimal("96000.00"),
        "bank_name": BankName.FCMB,
        "account_number": "0123456780",
        "account_name": "Blessing Udoh",
    },
    # Warehouse & Logistics
    {
        "employee_id": "EMP012",
        "title": "Mr.",
        "first_name": "Uchenna",
        "last_name": "Onwuka",
        "email": "warehouse@efeobusfurniture.com.ng",
        "phone_number": "+234 815 123 4567",
        "date_of_birth": date(1991, 1, 5),
        "gender": "Male",
        "marital_status": "Single",
        "address": "3 Warehouse Road",
        "city": "Agbor",
        "state": "Delta",
        "lga": "Ika South",
        "department": "Warehouse",
        "job_title": "Warehouse Supervisor",
        "job_grade": "S1",
        "hire_date": date(2020, 3, 1),
        "confirmation_date": date(2020, 6, 1),
        "basic_salary": Decimal("250000.00"),
        "housing_allowance": Decimal("100000.00"),
        "transport_allowance": Decimal("50000.00"),
        "bank_name": BankName.UNION_BANK,
        "account_number": "1234567891",
        "account_name": "Uchenna Onwuka",
    },
    {
        "employee_id": "EMP013",
        "title": "Mr.",
        "first_name": "Obinna",
        "last_name": "Madu",
        "email": "driver1@efeobusfurniture.com.ng",
        "phone_number": "+234 816 234 5678",
        "date_of_birth": date(1985, 7, 22),
        "gender": "Male",
        "marital_status": "Married",
        "address": "9 Transport Close",
        "city": "Agbor",
        "state": "Delta",
        "lga": "Ika South",
        "department": "Logistics",
        "job_title": "Driver",
        "job_grade": "S3",
        "hire_date": date(2018, 9, 1),
        "confirmation_date": date(2018, 12, 1),
        "basic_salary": Decimal("120000.00"),
        "housing_allowance": Decimal("48000.00"),
        "transport_allowance": Decimal("24000.00"),
        "bank_name": BankName.OPAY,
        "account_number": "2345678912",
        "account_name": "Obinna Madu",
    },
    # Quality & Security
    {
        "employee_id": "EMP014",
        "title": "Mr.",
        "first_name": "Kingsley",
        "last_name": "Ani",
        "email": "qc@efeobusfurniture.com.ng",
        "phone_number": "+234 817 345 6789",
        "date_of_birth": date(1984, 4, 15),
        "gender": "Male",
        "marital_status": "Married",
        "address": "21 Quality Street",
        "city": "Agbor",
        "state": "Delta",
        "lga": "Ika South",
        "department": "Quality Control",
        "job_title": "Quality Control Officer",
        "job_grade": "S1",
        "hire_date": date(2019, 4, 1),
        "confirmation_date": date(2019, 7, 1),
        "basic_salary": Decimal("300000.00"),
        "housing_allowance": Decimal("120000.00"),
        "transport_allowance": Decimal("60000.00"),
        "bank_name": BankName.POLARIS_BANK,
        "account_number": "3456789123",
        "account_name": "Kingsley Ani",
    },
    {
        "employee_id": "EMP015",
        "title": "Mr.",
        "first_name": "Sunday",
        "last_name": "Okoro",
        "email": "security@efeobusfurniture.com.ng",
        "phone_number": "+234 818 456 7890",
        "date_of_birth": date(1975, 12, 1),
        "gender": "Male",
        "marital_status": "Married",
        "address": "1 Security Post",
        "city": "Agbor",
        "state": "Delta",
        "lga": "Ika South",
        "department": "Security",
        "job_title": "Chief Security Officer",
        "job_grade": "S2",
        "hire_date": date(2016, 1, 1),
        "confirmation_date": date(2016, 4, 1),
        "basic_salary": Decimal("150000.00"),
        "housing_allowance": Decimal("60000.00"),
        "transport_allowance": Decimal("30000.00"),
        "bank_name": BankName.MONIEPOINT,
        "account_number": "4567891234",
        "account_name": "Sunday Okoro",
    },
]


# =============================================================================
# Helper function to run async seed
# =============================================================================

async def seed_database():
    """Main seed function to populate the database."""
    print("=" * 60)
    print("SEEDING: Efe Obus Furniture Manufacturing LTD")
    print("=" * 60)
    
    async with async_session_maker() as session:
        try:
            # Step 1: Create Organization
            print("\n[1/10] Creating Organization...")
            org = await create_organization(session)
            
            # Step 2: Create Business Entity
            print("[2/10] Creating Business Entity...")
            entity = await create_entity(session, org.id)
            
            # Step 3: Create Owner User
            print("[3/10] Creating Owner User...")
            owner = await create_owner(session, org.id)
            
            # Step 4: Create Categories
            print("[4/10] Creating Categories...")
            categories = await create_categories(session)
            
            # Step 5: Create Employees
            print("[5/10] Creating Employees...")
            employees = await create_employees(session, entity.id)
            
            # Step 6: Create Customers
            print("[6/10] Creating Customers...")
            customers = await create_customers(session, entity.id)
            
            # Step 7: Create Vendors
            print("[7/10] Creating Vendors...")
            vendors = await create_vendors(session, entity.id)
            
            # Step 8: Create Inventory
            print("[8/10] Creating Inventory...")
            inventory = await create_inventory(session, entity.id)
            
            # Step 9: Create Fixed Assets
            print("[9/10] Creating Fixed Assets...")
            assets = await create_fixed_assets(session, entity.id)
            
            # Step 10: Create Transactions & Invoices
            print("[10/10] Creating Transactions & Invoices...")
            await create_transactions_and_invoices(session, entity.id, categories, customers, vendors, owner.id)
            
            await session.commit()
            
            print("\n" + "=" * 60)
            print("[OK] SEED COMPLETED SUCCESSFULLY!")
            print("=" * 60)
            print(f"\nCompany: Efe Obus Furniture Manufacturing LTD")
            print(f"Owner: Efe Obukohwo")
            print(f"Email: efeobukohwo64@gmail.com")
            print(f"Password: Efeobus12345")
            print(f"\nCreated:")
            print(f"  - 1 Organization")
            print(f"  - 1 Business Entity")
            print(f"  - 1 Owner User")
            print(f"  - {len(CATEGORIES_DATA)} Categories")
            print(f"  - {len(employees)} Employees")
            print(f"  - {len(customers)} Customers")
            print(f"  - {len(vendors)} Vendors")
            print(f"  - {len(inventory)} Inventory Items")
            print(f"  - {len(assets)} Fixed Assets")
            print("=" * 60)
            
        except Exception as e:
            await session.rollback()
            print(f"\n[FAIL] ERROR: {e}")
            raise


async def create_organization(session: AsyncSession) -> Organization:
    """Create the organization with TenantSKU for commercial feature gating."""
    from app.models.sku import TenantSKU, SKUTier, IntelligenceAddon
    
    org_data = COMPANY_DATA["organization"]
    org = Organization(**org_data)
    session.add(org)
    await session.flush()
    
    # Create TenantSKU for commercial feature gating
    today = date.today()
    tenant_sku = TenantSKU(
        organization_id=org.id,
        tier=SKUTier.ENTERPRISE,
        intelligence_addon=IntelligenceAddon.ADVANCED,
        billing_cycle="annual",
        is_active=True,
        current_period_start=today,
        current_period_end=date(today.year + 1, today.month, today.day),
        notes="Seeded demo organization - Efe Obus Furniture Manufacturing LTD",
    )
    session.add(tenant_sku)
    await session.flush()
    
    return org


async def create_entity(session: AsyncSession, org_id: uuid.UUID) -> BusinessEntity:
    """Create the business entity."""
    entity_data = COMPANY_DATA["entity"].copy()
    entity_data["organization_id"] = org_id
    entity = BusinessEntity(**entity_data)
    session.add(entity)
    await session.flush()
    return entity


async def create_owner(session: AsyncSession, org_id: uuid.UUID) -> User:
    """Create the owner user."""
    owner_data = COMPANY_DATA["owner"].copy()
    owner_data["organization_id"] = org_id
    owner_data["hashed_password"] = hash_password(owner_data.pop("password"))
    owner_data["is_verified"] = True  # Email verified
    owner_data["is_active"] = True
    owner = User(**owner_data)
    session.add(owner)
    await session.flush()
    return owner


async def create_categories(session: AsyncSession) -> List[Category]:
    """Create expense and income categories."""
    categories = []
    for cat_data in CATEGORIES_DATA:
        cat = Category(**cat_data, is_system=False, is_active=True)
        session.add(cat)
        categories.append(cat)
    await session.flush()
    return categories


async def create_employees(session: AsyncSession, entity_id: uuid.UUID) -> List[Employee]:
    """Create employees."""
    employees = []
    for emp_data in EMPLOYEES_DATA:
        # Extract bank info
        bank_name = emp_data.pop("bank_name", None)
        account_number = emp_data.pop("account_number", None)
        account_name = emp_data.pop("account_name", None)
        
        # Calculate default allowances based on basic salary if not provided
        basic = emp_data.get("basic_salary", Decimal("0"))
        if "meal_allowance" not in emp_data:
            emp_data["meal_allowance"] = Decimal(str(float(basic) * 0.10))  # 10% of basic
        if "utility_allowance" not in emp_data:
            emp_data["utility_allowance"] = Decimal(str(float(basic) * 0.08))  # 8% of basic
        
        # Create employee
        emp = Employee(
            entity_id=entity_id,
            employment_type=EmploymentType.FULL_TIME,
            employment_status=EmploymentStatus.ACTIVE,
            payroll_frequency=PayrollFrequency.MONTHLY,
            is_active=True,
            **emp_data
        )
        session.add(emp)
        await session.flush()
        
        # Create bank account if provided
        if bank_name and account_number:
            bank_acc = EmployeeBankAccount(
                employee_id=emp.id,
                bank_name=bank_name,
                account_number=account_number,
                account_name=account_name or f"{emp.first_name} {emp.last_name}",
                is_primary=True,
                is_active=True,
            )
            session.add(bank_acc)
        
        employees.append(emp)
    
    await session.flush()
    return employees


async def create_customers(session: AsyncSession, entity_id: uuid.UUID) -> List[Customer]:
    """Create customers - defined in Part 2."""
    # Import customer data from part 2
    from scripts.seed_data_customers import CUSTOMERS_DATA
    
    customers = []
    for cust_data in CUSTOMERS_DATA:
        cust = Customer(entity_id=entity_id, is_active=True, **cust_data)
        session.add(cust)
        customers.append(cust)
    
    await session.flush()
    return customers


async def create_vendors(session: AsyncSession, entity_id: uuid.UUID) -> List[Vendor]:
    """Create vendors - defined in Part 2."""
    from scripts.seed_data_vendors import VENDORS_DATA
    
    vendors = []
    for vend_data in VENDORS_DATA:
        vend = Vendor(entity_id=entity_id, is_active=True, **vend_data)
        session.add(vend)
        vendors.append(vend)
    
    await session.flush()
    return vendors


async def create_inventory(session: AsyncSession, entity_id: uuid.UUID) -> List[InventoryItem]:
    """Create inventory items - defined in Part 3."""
    from scripts.seed_data_inventory import INVENTORY_DATA
    
    items = []
    for item_data in INVENTORY_DATA:
        item = InventoryItem(entity_id=entity_id, is_active=True, is_tracked=True, **item_data)
        session.add(item)
        items.append(item)
    
    await session.flush()
    return items


async def create_fixed_assets(session: AsyncSession, entity_id: uuid.UUID) -> List[FixedAsset]:
    """Create fixed assets - defined in Part 3."""
    from scripts.seed_data_assets import FIXED_ASSETS_DATA
    
    assets = []
    for asset_data in FIXED_ASSETS_DATA:
        asset = FixedAsset(entity_id=entity_id, status=AssetStatus.ACTIVE, **asset_data)
        session.add(asset)
        assets.append(asset)
    
    await session.flush()
    return assets


async def create_transactions_and_invoices(
    session: AsyncSession,
    entity_id: uuid.UUID,
    categories: List[Category],
    customers: List[Customer],
    vendors: List[Vendor],
    owner_id: uuid.UUID
):
    """Create transactions and invoices - defined in Part 4."""
    from scripts.seed_data_transactions import create_sample_transactions
    await create_sample_transactions(session, entity_id, categories, customers, vendors, owner_id)


if __name__ == "__main__":
    asyncio.run(seed_database())
