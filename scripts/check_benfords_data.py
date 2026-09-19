#!/usr/bin/env python3
"""Check data availability for Benford's Law analysis."""

import psycopg2
from datetime import date

def main():
    conn = psycopg2.connect(
        host="localhost",
        database="tekvwa_pro_audit",
        user="efeobukohwo",
        password="12345"
    )
    cur = conn.cursor()
    
    entity_id = '453f0f12-202a-48b2-8c72-91526deeee56'
    start_date = '2026-01-01'
    end_date = '2026-12-31'
    
    print("=" * 70)
    print("BENFORD'S LAW DATA ANALYSIS REPORT")
    print("Entity: Efe Obus Furniture Manufacturing Company")
    print(f"Entity ID: {entity_id}")
    print(f"Fiscal Year: 2026 ({start_date} to {end_date})")
    print("=" * 70)
    print()
    
    # 1. Transactions
    cur.execute("""
        SELECT COUNT(*) FROM transactions 
        WHERE entity_id = %s 
        AND transaction_date >= %s AND transaction_date <= %s
        AND amount > 0
    """, (entity_id, start_date, end_date))
    txn = cur.fetchone()[0]
    print(f"1. Transactions (amount > 0):          {txn}")
    
    # 2. Journal Entries
    cur.execute("""
        SELECT COUNT(*) FROM journal_entries 
        WHERE entity_id = %s 
        AND entry_date >= %s AND entry_date <= %s
        AND status = 'POSTED' AND total_debit > 0
    """, (entity_id, start_date, end_date))
    je = cur.fetchone()[0]
    print(f"2. Journal Entries (posted, debit>0): {je}")
    
    # 3. Invoices
    cur.execute("""
        SELECT COUNT(*) FROM invoices 
        WHERE entity_id = %s 
        AND invoice_date >= %s AND invoice_date <= %s
        AND total_amount > 0
    """, (entity_id, start_date, end_date))
    inv = cur.fetchone()[0]
    print(f"3. Invoices (total_amount > 0):        {inv}")
    
    # 4. Sales
    try:
        cur.execute("""
            SELECT COUNT(*) FROM sales 
            WHERE entity_id = %s 
            AND sale_date >= %s AND sale_date <= %s
            AND total_amount > 0
        """, (entity_id, start_date, end_date))
        sales = cur.fetchone()[0]
    except Exception:
        sales = 0
    print(f"4. Sales (total_amount > 0):           {sales}")
    
    # 5. Expense Claims
    try:
        cur.execute("""
            SELECT COUNT(*) FROM expense_claims 
            WHERE entity_id = %s 
            AND claim_date >= %s AND claim_date <= %s
            AND total_amount > 0
        """, (entity_id, start_date, end_date))
        exp = cur.fetchone()[0]
    except Exception:
        exp = 0
    print(f"5. Expense Claims (total_amount > 0):  {exp}")
    
    print("-" * 70)
    total = txn + je + inv + sales + exp
    required = 100
    shortfall = max(0, required - total)
    print(f"TOTAL RECORDS:                          {total}")
    print(f"REQUIRED FOR BENFORD'S LAW:            {required}")
    print(f"SHORTFALL:                              {shortfall}")
    print()
    
    if total >= required:
        print("STATUS: [OK] SUFFICIENT DATA - Benford's Law analysis can proceed")
    else:
        print("STATUS: [FAIL] INSUFFICIENT DATA - Need more records")
        print()
        print("RECOMMENDATION:")
        print(f"  Add {shortfall} more financial records to enable Benford's Law analysis")
        print("  Options: Add transactions, invoices, journal entries, sales, or expenses")
    
    print("=" * 70)
    conn.close()

if __name__ == "__main__":
    main()
