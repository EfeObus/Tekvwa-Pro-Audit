#!/usr/bin/env python3
"""Generate SQL for audit logs and execute via psql."""
import random
import uuid
from datetime import datetime, timedelta
import json
import subprocess

ENTITY_ID = '453f0f12-202a-48b2-8c72-91526deeee56'
ORG_ID = 'b3345541-b9cf-4686-a41b-3fe4bf699bf3'
USER_ID = '1839e254-0d36-456c-8bff-34f12b207bd1'
USER_EMAIL = 'admin@efeobu.com'

TABLE_NAMES = ['invoices', 'receipts', 'transactions', 'tax_filings', 'nrs_submissions', 
               'credit_notes', 'fixed_assets', 'payroll_runs', 'bank_statements', 'documents']
DOCUMENT_TYPE_MAP = {
    'invoices': 'invoice', 'receipts': 'receipt', 'transactions': 'transaction',
    'tax_filings': 'tax_filing', 'nrs_submissions': 'nrs_submission', 
    'credit_notes': 'credit_note', 'fixed_assets': 'fixed_asset',
    'payroll_runs': 'payroll', 'bank_statements': 'bank_statement', 'documents': 'supporting_doc'
}
ACTIONS = ['CREATE', 'UPDATE', 'DELETE', 'NRS_SUBMIT', 'EXPORT']

def generate_sql():
    sql_lines = ['BEGIN;']
    
    for year in range(2020, 2026):
        num_logs = 50 + (year - 2020) * 30
        for i in range(num_logs):
            id = str(uuid.uuid4())
            table_name = random.choice(TABLE_NAMES)
            action = random.choice(ACTIONS)
            days_offset = random.randint(0, 364)
            created_at = datetime(year, 1, 1) + timedelta(days=days_offset)
            record_id = str(uuid.uuid4())
            target_type = DOCUMENT_TYPE_MAP.get(table_name, table_name)
            ip = f'192.168.{random.randint(1, 254)}.{random.randint(1, 254)}'
            device_fp = f'fp_{uuid.uuid4().hex[:16]}'
            session_id = f'sess_{uuid.uuid4().hex[:12]}'
            description = f'{table_name.replace("_", " ").title()} record {action}d'
            
            # NRS for submissions
            nrs_irn = None
            nrs_response = None
            if table_name == 'nrs_submissions' or (table_name == 'invoices' and random.random() > 0.5):
                nrs_irn = f'NIG{random.randint(100000000000, 999999999999)}'
                nrs_response = json.dumps({'irn': nrs_irn, 'status': 'acknowledged'}).replace("'", "''")
            
            geo = json.dumps({'country': 'Nigeria', 'city': random.choice(['Lagos', 'Abuja', 'Port Harcourt'])}).replace("'", "''")
            
            nrs_irn_val = f"'{nrs_irn}'" if nrs_irn else 'NULL'
            nrs_resp_val = f"'{nrs_response}'::jsonb" if nrs_response else 'NULL'
            
            sql = f"""INSERT INTO audit_logs (id, entity_id, organization_id, user_id, user_email, action, table_name, record_id, ip_address, user_agent, device_fingerprint, session_id, created_at, description, target_entity_type, target_entity_id, geo_location, nrs_irn, nrs_response) VALUES ('{id}', '{ENTITY_ID}', '{ORG_ID}', '{USER_ID}', '{USER_EMAIL}', '{action}', '{table_name}', '{record_id}', '{ip}'::inet, 'Mozilla/5.0', '{device_fp}', '{session_id}', '{created_at}', '{description}', '{target_type}', '{record_id}', '{geo}'::jsonb, {nrs_irn_val}, {nrs_resp_val});"""
            sql_lines.append(sql)
    
    sql_lines.append('COMMIT;')
    return '\n'.join(sql_lines)

if __name__ == '__main__':
    print("🌱 Generating audit logs SQL...")
    sql = generate_sql()
    
    # Write to file
    with open('/tmp/seed_audit_logs.sql', 'w') as f:
        f.write(sql)
    
    print(f" Generated {sql.count('INSERT')} INSERT statements")
    
    # Execute via psql
    print(" Executing SQL...")
    result = subprocess.run(
        ['psql', 'tekvwa_pro_audit', '-f', '/tmp/seed_audit_logs.sql'],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print("[OK] Successfully seeded audit logs!")
    else:
        print(f"[FAIL] Error: {result.stderr}")
        print(result.stdout[:500] if result.stdout else "")
