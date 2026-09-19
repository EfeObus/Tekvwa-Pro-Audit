#!/usr/bin/env python3
"""Reset test staff passwords to match .env values."""

import asyncio
import sys
sys.path.insert(0, '.')

from app.database import async_session_maker
from app.models.user import User
from app.utils.security import get_password_hash
from sqlalchemy import select

async def reset_passwords():
    async with async_session_maker() as db:
        # Reset Admin password
        result = await db.execute(select(User).where(User.email == 'info@tekvwa.org'))
        admin = result.scalar_one_or_none()
        if admin:
            admin.hashed_password = get_password_hash('TestAdmin@2026!')
            print('✓ Admin password reset: info@tekvwa.org → TestAdmin@2026!')
        else:
            print('✗ Admin user not found')
        
        # Reset IT Dev password
        result = await db.execute(select(User).where(User.email == 'info@tekvwa.org'))
        it_dev = result.scalar_one_or_none()
        if it_dev:
            it_dev.hashed_password = get_password_hash('ItDev@2026!')
            print('✓ IT Dev password reset: info@tekvwa.org → ItDev@2026!')
        else:
            print('✗ IT Dev user not found')
        
        await db.commit()
        print('\n✅ Passwords saved to database!')

if __name__ == '__main__':
    asyncio.run(reset_passwords())
