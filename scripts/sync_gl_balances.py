"""
Script to sync GL Account balances from source systems.
This reads from source tables (inventory, invoices, payroll, etc.) and updates 
the corresponding GL account current_balance values.
"""
from sqlalchemy import create_engine, text

# Direct database connection
engine = create_engine('postgresql://localhost:5432/tekvwa_pro_audit')

def sync_gl_balances():
    with engine.connect() as conn:
        # Get the entity ID
        result = conn.execute(text("SELECT id FROM business_entities WHERE name = 'Efe Obus Furniture Manufacturing LTD' LIMIT 1"))
        entity_row = result.fetchone()
        if not entity_row:
            print('Entity not found')
            return
        entity_id = entity_row[0]
        print(f'Entity ID: {entity_id}')
        print('=' * 60)
        
        # Sync Inventory (1140)
        result = conn.execute(text("""
            UPDATE chart_of_accounts 
            SET current_balance = (
                SELECT COALESCE(SUM(unit_cost * quantity_on_hand), 0) 
                FROM inventory_items 
                WHERE entity_id = :entity_id AND is_active = true
            )
            WHERE entity_id = :entity_id AND account_code = '1140'
            RETURNING current_balance
        """), {'entity_id': entity_id})
        inv = result.fetchone()
        print(f'1140 Inventory: ₦{inv[0]:,.2f}' if inv else '1140 Inventory: ₦0.00')
        
        # Sync AR (1130) - from unpaid invoices
        result = conn.execute(text("""
            UPDATE chart_of_accounts 
            SET current_balance = (
                SELECT COALESCE(SUM(total_amount - COALESCE(amount_paid, 0)), 0)
                FROM invoices 
                WHERE entity_id = :entity_id AND status IN ('PENDING', 'SUBMITTED', 'ACCEPTED', 'PARTIALLY_PAID')
            )
            WHERE entity_id = :entity_id AND account_code = '1130'
            RETURNING current_balance
        """), {'entity_id': entity_id})
        ar = result.fetchone()
        print(f'1130 Accounts Receivable: ₦{ar[0]:,.2f}' if ar else '1130 AR: ₦0.00')
        
        # Sync Sales Revenue (4100) - from finalized invoices (subtotal, not total)
        result = conn.execute(text("""
            UPDATE chart_of_accounts 
            SET current_balance = (
                SELECT COALESCE(SUM(subtotal), 0)
                FROM invoices 
                WHERE entity_id = :entity_id AND status NOT IN ('DRAFT', 'CANCELLED')
            )
            WHERE entity_id = :entity_id AND account_code = '4100'
            RETURNING current_balance
        """), {'entity_id': entity_id})
        sales = result.fetchone()
        print(f'4100 Sales Revenue: ₦{sales[0]:,.2f}' if sales else '4100 Sales: ₦0.00')
        
        # Sync VAT Output (2130) - from finalized invoices
        result = conn.execute(text("""
            UPDATE chart_of_accounts 
            SET current_balance = (
                SELECT COALESCE(SUM(vat_amount), 0)
                FROM invoices 
                WHERE entity_id = :entity_id AND status NOT IN ('DRAFT', 'CANCELLED')
            )
            WHERE entity_id = :entity_id AND account_code = '2130'
            RETURNING current_balance
        """), {'entity_id': entity_id})
        vat_out = result.fetchone()
        print(f'2130 VAT Payable: ₦{vat_out[0]:,.2f}' if vat_out else '2130 VAT: ₦0.00')
        
        # Sync AP (2110) - from expense transactions
        result = conn.execute(text("""
            UPDATE chart_of_accounts 
            SET current_balance = (
                SELECT COALESCE(SUM(total_amount), 0)
                FROM transactions 
                WHERE entity_id = :entity_id AND transaction_type = 'EXPENSE'
            )
            WHERE entity_id = :entity_id AND account_code = '2110'
            RETURNING current_balance
        """), {'entity_id': entity_id})
        ap = result.fetchone()
        print(f'2110 Accounts Payable: ₦{ap[0]:,.2f}' if ap else '2110 AP: ₦0.00')
        
        # Sync Fixed Assets (1210) - acquisition cost
        result = conn.execute(text("""
            UPDATE chart_of_accounts 
            SET current_balance = (
                SELECT COALESCE(SUM(acquisition_cost), 0)
                FROM fixed_assets 
                WHERE entity_id = :entity_id AND status != 'DISPOSED'
            )
            WHERE entity_id = :entity_id AND account_code = '1210'
            RETURNING current_balance
        """), {'entity_id': entity_id})
        fa = result.fetchone()
        print(f'1210 Fixed Assets: ₦{fa[0]:,.2f}' if fa else '1210 FA: ₦0.00')
        
        # Sync Accum Depreciation (1220) - contra account (negative)
        result = conn.execute(text("""
            UPDATE chart_of_accounts 
            SET current_balance = (
                SELECT COALESCE(SUM(accumulated_depreciation), 0)
                FROM fixed_assets 
                WHERE entity_id = :entity_id AND status != 'DISPOSED'
            )
            WHERE entity_id = :entity_id AND account_code = '1220'
            RETURNING current_balance
        """), {'entity_id': entity_id})
        ad = result.fetchone()
        print(f'1220 Accum Depreciation: ₦{ad[0]:,.2f}' if ad else '1220 AD: ₦0.00')
        
        # Get Payroll totals
        result = conn.execute(text("""
            SELECT 
                COALESCE(SUM(total_gross_pay), 0) as gross,
                COALESCE(SUM(total_paye), 0) as paye,
                COALESCE(SUM(total_pension_employee + total_pension_employer), 0) as pension,
                COALESCE(SUM(total_nhf), 0) as nhf,
                COALESCE(SUM(total_nsitf), 0) as nsitf,
                COALESCE(SUM(total_net_pay), 0) as net,
                COALESCE(SUM(total_pension_employer), 0) as emp_pension
            FROM payroll_runs 
            WHERE entity_id = :entity_id AND status IN ('COMPLETED', 'APPROVED', 'PAID')
        """), {'entity_id': entity_id})
        pr = result.fetchone()
        
        if pr:
            # Salary Expense (5200)
            conn.execute(text("""
                UPDATE chart_of_accounts SET current_balance = :amount
                WHERE entity_id = :entity_id AND account_code = '5200'
            """), {'entity_id': entity_id, 'amount': pr[0]})
            print(f'5200 Salaries Expense: ₦{pr[0]:,.2f}')
            
            # PAYE Payable (2150)
            conn.execute(text("""
                UPDATE chart_of_accounts SET current_balance = :amount
                WHERE entity_id = :entity_id AND account_code = '2150'
            """), {'entity_id': entity_id, 'amount': pr[1]})
            print(f'2150 PAYE Payable: ₦{pr[1]:,.2f}')
            
            # Pension Payable (2160)
            conn.execute(text("""
                UPDATE chart_of_accounts SET current_balance = :amount
                WHERE entity_id = :entity_id AND account_code = '2160'
            """), {'entity_id': entity_id, 'amount': pr[2]})
            print(f'2160 Pension Payable: ₦{pr[2]:,.2f}')
            
            # NHF Payable (2170)
            conn.execute(text("""
                UPDATE chart_of_accounts SET current_balance = :amount
                WHERE entity_id = :entity_id AND account_code = '2170'
            """), {'entity_id': entity_id, 'amount': pr[3]})
            print(f'2170 NHF Payable: ₦{pr[3]:,.2f}')
            
            # NSITF Payable (2180)
            conn.execute(text("""
                UPDATE chart_of_accounts SET current_balance = :amount
                WHERE entity_id = :entity_id AND account_code = '2180'
            """), {'entity_id': entity_id, 'amount': pr[4]})
            print(f'2180 NSITF Payable: ₦{pr[4]:,.2f}')
            
            # Salaries Payable (2190)
            conn.execute(text("""
                UPDATE chart_of_accounts SET current_balance = :amount
                WHERE entity_id = :entity_id AND account_code = '2190'
            """), {'entity_id': entity_id, 'amount': pr[5]})
            print(f'2190 Salaries Payable: ₦{pr[5]:,.2f}')
            
            # Employer Pension Expense (5210)
            conn.execute(text("""
                UPDATE chart_of_accounts SET current_balance = :amount
                WHERE entity_id = :entity_id AND account_code = '5210'
            """), {'entity_id': entity_id, 'amount': pr[6]})
            print(f'5210 Employer Pension Expense: ₦{pr[6]:,.2f}')
        
        # Sync Bank Accounts (1120)
        result = conn.execute(text("""
            UPDATE chart_of_accounts 
            SET current_balance = (
                SELECT COALESCE(SUM(current_balance), 0)
                FROM bank_accounts 
                WHERE entity_id = :entity_id AND is_active = true
            )
            WHERE entity_id = :entity_id AND account_code = '1120'
            RETURNING current_balance
        """), {'entity_id': entity_id})
        bank = result.fetchone()
        print(f'1120 Bank: ₦{bank[0]:,.2f}' if bank else '1120 Bank: ₦0.00')
        
        conn.commit()
        print('=' * 60)
        print('[OK] GL Sync completed successfully!')

if __name__ == '__main__':
    sync_gl_balances()
