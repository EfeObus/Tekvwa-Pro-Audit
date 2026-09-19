# Migration Guide

## Overview

This guide covers data migration procedures for Tekvwa Pro Audit, including:
- Database schema upgrades
- Data migration from legacy systems
- Version upgrade procedures
- Rollback strategies

---

## Table of Contents

1. [Pre-Migration Checklist](#pre-migration-checklist)
2. [Database Migrations (Alembic)](#database-migrations-alembic)
3. [Version Upgrades](#version-upgrades)
4. [Data Import from Legacy Systems](#data-import-from-legacy-systems)
5. [Multi-Tenant Migration](#multi-tenant-migration)
6. [Rollback Procedures](#rollback-procedures)
7. [Post-Migration Validation](#post-migration-validation)

---

## Pre-Migration Checklist

### Before Any Migration

- [ ] **Backup Database**
  ```bash
  pg_dump -h localhost -U proaudit -d tekvwa_pro_audit > backup_$(date +%Y%m%d_%H%M%S).sql
  ```

- [ ] **Document Current State**
  ```bash
  # Record current migration version
  alembic current
  
  # Count records in critical tables
  psql -c "SELECT 'journal_entries' as table_name, COUNT(*) FROM journal_entries UNION ALL SELECT 'gl_accounts', COUNT(*) FROM gl_accounts;"
  ```

- [ ] **Notify Users**
  - Schedule maintenance window
  - Communicate expected downtime
  - Prepare rollback plan

- [ ] **Test in Staging**
  - Run migration on staging environment first
  - Verify data integrity
  - Test critical workflows

---

## Database Migrations (Alembic)

### View Migration Status

```bash
# Show current migration version
alembic current

# Show all available migrations
alembic history

# Show pending migrations
alembic history -r current:head
```

### Run Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Apply specific migration
alembic upgrade <revision_id>

# Apply next migration only
alembic upgrade +1
```

### Create New Migration

```bash
# Auto-generate migration from model changes
alembic revision --autogenerate -m "add_exchange_rates_table"

# Create empty migration for custom SQL
alembic revision -m "seed_initial_gl_accounts"
```

### Migration Best Practices

1. **Review Auto-Generated Migrations**
   - Check column types match models
   - Verify foreign key constraints
   - Add data migrations if needed

2. **Include Both Upgrade and Downgrade**
   ```python
   def upgrade():
       op.create_table('exchange_rates', ...)
       
   def downgrade():
       op.drop_table('exchange_rates')
   ```

3. **Handle Large Tables Carefully**
   - Add indexes concurrently
   - Batch data updates
   - Consider online schema changes

---

## Version Upgrades

### From v1.x to v2.x

#### New Features in v2.x
- Multi-currency support with IAS 21 compliance
- Group consolidation
- Budget management
- Enhanced reporting

#### Migration Steps

1. **Backup and Stop Services**
   ```bash
   # Stop the application
   docker-compose down
   
   # Backup database
   pg_dump -h localhost -U proaudit -d tekvwa_pro_audit > backup_v1_to_v2.sql
   ```

2. **Update Application Code**
   ```bash
   git fetch origin
   git checkout v2.0.0
   pip install -r requirements.txt
   ```

3. **Run Database Migrations**
   ```bash
   alembic upgrade head
   ```

4. **Run Data Migration Scripts**
   ```bash
   # Migrate tenant SKU structure
   python scripts/migrate_tenant_skus.py
   
   # Seed exchange rates
   python scripts/seed_exchange_rates.py
   
   # Generate historical journal entries for FX
   python scripts/generate_historical_journal_entries.py
   ```

5. **Update Configuration**
   ```bash
   # Update environment variables
   export FUNCTIONAL_CURRENCY=NGN
   export SUPPORTED_CURRENCIES=NGN,USD,EUR,GBP
   export FX_RATE_SOURCE=manual
   ```

6. **Restart Services**
   ```bash
   docker-compose up -d
   ```

7. **Validate Migration**
   ```bash
   python scripts/validate_v2_migration.py
   ```

---

## Data Import from Legacy Systems

### Supported Import Formats

| Format | Description | Tool |
|--------|-------------|------|
| CSV | Chart of Accounts, Opening Balances | `/api/v1/import/csv` |
| Excel | Trial Balance, Budget | `/api/v1/import/excel` |
| JSON | Full data export/import | `/api/v1/import/json` |
| QIF/OFX | Bank transactions | `/api/v1/import/banking` |

### Import Chart of Accounts

#### CSV Format
```csv
account_code,account_name,account_type,parent_code,normal_balance
1000,Cash and Cash Equivalents,asset,,debit
1100,Accounts Receivable,asset,,debit
2000,Accounts Payable,liability,,credit
3000,Share Capital,equity,,credit
4000,Revenue,revenue,,credit
5000,Cost of Sales,expense,,debit
```

#### Import API
```json
POST /api/v1/import/chart-of-accounts
Content-Type: multipart/form-data

file: chart_of_accounts.csv
tenant_id: tenant-uuid
replace_existing: false
```

### Import Opening Balances

#### CSV Format
```csv
account_code,debit,credit,description
1000,50000000,0,Opening cash balance
1100,25000000,0,Opening receivables
2000,0,15000000,Opening payables
3000,0,60000000,Share capital
```

#### Import API
```json
POST /api/v1/import/opening-balances
{
  "file": "opening_balances.csv",
  "as_of_date": "2026-01-01",
  "tenant_id": "tenant-uuid",
  "create_journal_entry": true
}
```

### Import Historical Transactions

#### Transaction CSV Format
```csv
date,reference,description,account_code,debit,credit
2025-01-15,INV-001,Sales to Customer A,1100,100000,0
2025-01-15,INV-001,Sales to Customer A,4000,0,100000
2025-01-20,PMT-001,Payment from Customer A,1000,100000,0
2025-01-20,PMT-001,Payment from Customer A,1100,0,100000
```

#### Bulk Import Script
```bash
python scripts/import_historical_transactions.py \
  --file transactions_2025.csv \
  --tenant-id tenant-uuid \
  --validate-only  # First pass: validation
  
python scripts/import_historical_transactions.py \
  --file transactions_2025.csv \
  --tenant-id tenant-uuid \
  --execute  # Second pass: actual import
```

### Import from Specific Systems

#### QuickBooks
```bash
python scripts/import_quickbooks.py \
  --iif-file company_export.iif \
  --tenant-id tenant-uuid \
  --map-file quickbooks_mapping.json
```

#### Sage
```bash
python scripts/import_sage.py \
  --csv-folder sage_export/ \
  --tenant-id tenant-uuid
```

---

## Multi-Tenant Migration

### Adding New Tenant

```json
POST /api/v1/tenants
{
  "name": "New Company Ltd",
  "business_type": "limited_company",
  "industry": "manufacturing",
  "fiscal_year_end": "12-31",
  "functional_currency": "NGN",
  "sku_tier": "professional"
}
```

### Tenant Data Isolation

Each tenant's data is isolated by `tenant_id`. When migrating:

1. **Export from Source Tenant**
   ```bash
   python scripts/export_tenant_data.py \
     --tenant-id source-tenant-uuid \
     --output tenant_backup.json
   ```

2. **Import to Destination**
   ```bash
   python scripts/import_tenant_data.py \
     --file tenant_backup.json \
     --new-tenant-id destination-tenant-uuid \
     --remap-ids true
   ```

### Merging Tenants

When consolidating multiple entities:

```bash
python scripts/merge_tenants.py \
  --parent-tenant parent-uuid \
  --child-tenants child1-uuid,child2-uuid \
  --merger-date 2026-01-01 \
  --strategy absorb  # or 'consolidate'
```

---

## Rollback Procedures

### Database Rollback

```bash
# Rollback last migration
alembic downgrade -1

# Rollback to specific revision
alembic downgrade <revision_id>

# Rollback all migrations
alembic downgrade base
```

### Full System Rollback

1. **Stop Services**
   ```bash
   docker-compose down
   ```

2. **Restore Database**
   ```bash
   # Drop current database
   dropdb tekvwa_pro_audit
   
   # Create fresh database
   createdb tekvwa_pro_audit
   
   # Restore from backup
   psql tekvwa_pro_audit < backup_pre_migration.sql
   ```

3. **Restore Application Code**
   ```bash
   git checkout v1.0.0  # Previous stable version
   pip install -r requirements.txt
   ```

4. **Restart Services**
   ```bash
   docker-compose up -d
   ```

### Partial Rollback (Data Only)

For data-level rollbacks without schema changes:

```bash
python scripts/rollback_data_changes.py \
  --since "2026-01-15 10:00:00" \
  --tables journal_entries,gl_transactions \
  --backup-file data_backup_20260115.json
```

---

## Post-Migration Validation

### Automated Validation Script

```bash
python scripts/validate_migration.py --full
```

### Validation Checks

1. **Record Counts**
   ```sql
   -- Compare before and after counts
   SELECT 
     (SELECT COUNT(*) FROM gl_accounts) as gl_accounts,
     (SELECT COUNT(*) FROM journal_entries) as journal_entries,
     (SELECT COUNT(*) FROM tenants) as tenants;
   ```

2. **Trial Balance Check**
   ```sql
   -- Verify trial balance still balances
   SELECT 
     SUM(CASE WHEN normal_balance = 'debit' THEN balance ELSE 0 END) as total_debits,
     SUM(CASE WHEN normal_balance = 'credit' THEN balance ELSE 0 END) as total_credits
   FROM gl_accounts
   WHERE tenant_id = 'tenant-uuid';
   ```

3. **Foreign Key Integrity**
   ```sql
   -- Check for orphaned records
   SELECT je.id 
   FROM journal_entries je
   LEFT JOIN tenants t ON je.tenant_id = t.id
   WHERE t.id IS NULL;
   ```

4. **Data Type Validation**
   ```sql
   -- Check currency amounts are valid
   SELECT COUNT(*) 
   FROM transactions 
   WHERE amount < 0 OR amount IS NULL;
   ```

### Manual Validation Checklist

- [ ] Login works for all user roles
- [ ] Dashboard loads without errors
- [ ] Can create new journal entries
- [ ] Reports generate correctly
- [ ] Multi-currency transactions work
- [ ] Audit trail is intact

---

## Migration Scripts Reference

| Script | Description |
|--------|-------------|
| `migrate_tenant_skus.py` | Update tenant SKU structure |
| `seed_exchange_rates.py` | Populate exchange rate history |
| `generate_historical_journal_entries.py` | Backfill journal entries |
| `import_historical_transactions.py` | Bulk transaction import |
| `export_tenant_data.py` | Export tenant for backup |
| `import_tenant_data.py` | Import tenant data |
| `validate_migration.py` | Post-migration validation |
| `rollback_data_changes.py` | Selective data rollback |

---

## Troubleshooting

### Migration Fails Midway

1. Check the error message in Alembic output
2. Review the migration script for issues
3. Fix the issue and run:
   ```bash
   alembic upgrade head
   ```

### Data Import Errors

Common issues:
- **Duplicate primary keys**: Use `--skip-duplicates` flag
- **Missing foreign keys**: Import parent records first
- **Invalid data types**: Review CSV column types
- **Encoding issues**: Save CSV as UTF-8

### Performance Issues During Migration

For large datasets:
```bash
# Increase batch size
python scripts/import_transactions.py --batch-size 5000

# Disable indexes during import
python scripts/import_transactions.py --disable-indexes

# Use COPY instead of INSERT
python scripts/import_transactions.py --use-copy
```

---

## Support

For migration assistance:
- Review documentation in `/docs`
- Check logs in `/logs/migration.log`
- Contact support with migration ID and error details
