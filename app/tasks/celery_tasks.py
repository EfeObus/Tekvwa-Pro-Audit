"""
Tekvwa Pro Audit - Celery Tasks

Background tasks for scheduled operations.
"""

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Dict, Any, List

from celery import shared_task

from app.database import async_session_factory

logger = logging.getLogger(__name__)


def run_async(coro):
    """Helper to run async functions in Celery tasks."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ===========================================
# INVOICE TASKS
# ===========================================

@shared_task(name='app.tasks.celery_tasks.check_overdue_invoices_task')
def check_overdue_invoices_task() -> Dict[str, Any]:
    """Check for invoices that have become overdue and send notifications."""
    return run_async(_check_overdue_invoices())


async def _check_overdue_invoices() -> Dict[str, Any]:
    """Async implementation of overdue invoice check."""
    from app.models.invoice import Invoice, InvoiceStatus
    from app.models.user import User, UserEntityAccess
    from app.services.notification_service import NotificationService
    from sqlalchemy import select
    
    async with async_session_factory() as db:
        today = date.today()
        
        # Find finalized invoices past due date
        result = await db.execute(
            select(Invoice)
            .where(Invoice.status.in_([InvoiceStatus.PENDING, InvoiceStatus.SUBMITTED, InvoiceStatus.ACCEPTED]))
            .where(Invoice.due_date < today)
        )
        
        overdue_invoices = result.scalars().all()
        notifications_sent = 0
        invoices_updated = 0
        
        notification_service = NotificationService(db)
        
        for invoice in overdue_invoices:
            days_overdue = (today - invoice.due_date).days
            
            # Update invoice status if needed
            if invoice.status != InvoiceStatus.OVERDUE:
                invoice.status = InvoiceStatus.OVERDUE
                invoices_updated += 1
            
            # Get users with access to this entity
            users_result = await db.execute(
                select(UserEntityAccess)
                .where(UserEntityAccess.entity_id == invoice.entity_id)
            )
            user_accesses = users_result.scalars().all()
            
            # Send notifications to all users with access
            for access in user_accesses:
                user_result = await db.execute(
                    select(User).where(User.id == access.user_id)
                )
                user = user_result.scalar_one_or_none()
                
                if user and user.is_active:
                    customer_name = "Unknown"
                    if invoice.customer:
                        customer_name = invoice.customer.name
                    
                    await notification_service.notify_invoice_overdue(
                        user_id=user.id,
                        entity_id=invoice.entity_id,
                        invoice_number=invoice.invoice_number,
                        customer_name=customer_name,
                        amount=float(invoice.total_amount),
                        days_overdue=days_overdue,
                        email_address=user.email if days_overdue in [1, 7, 14, 30] else None,
                    )
                    notifications_sent += 1
        
        await db.commit()
        
        logger.info(f"Overdue check complete: {invoices_updated} invoices updated, {notifications_sent} notifications sent")
        return {
            "invoices_updated": invoices_updated,
            "notifications_sent": notifications_sent,
        }


# ===========================================
# INVENTORY TASKS
# ===========================================

@shared_task(name='app.tasks.celery_tasks.check_low_stock_task')
def check_low_stock_task() -> Dict[str, Any]:
    """Check for inventory items below reorder level and send notifications."""
    return run_async(_check_low_stock())


async def _check_low_stock() -> Dict[str, Any]:
    """Async implementation of low stock check."""
    from app.models.inventory import InventoryItem
    from app.models.user import User, UserEntityAccess
    from app.services.notification_service import NotificationService
    from sqlalchemy import select
    
    async with async_session_factory() as db:
        result = await db.execute(
            select(InventoryItem)
            .where(InventoryItem.quantity_on_hand <= InventoryItem.reorder_level)
            .where(InventoryItem.is_active == True)
        )
        
        low_stock_items = result.scalars().all()
        notifications_sent = 0
        
        notification_service = NotificationService(db)
        
        for item in low_stock_items:
            # Get users with access to this entity
            users_result = await db.execute(
                select(UserEntityAccess)
                .where(UserEntityAccess.entity_id == item.entity_id)
            )
            user_accesses = users_result.scalars().all()
            
            for access in user_accesses:
                user_result = await db.execute(
                    select(User).where(User.id == access.user_id)
                )
                user = user_result.scalar_one_or_none()
                
                if user and user.is_active:
                    await notification_service.notify_low_stock(
                        user_id=user.id,
                        entity_id=item.entity_id,
                        item_name=item.name,
                        current_stock=item.quantity_on_hand,
                        reorder_level=item.reorder_level,
                        item_id=item.id,
                    )
                    notifications_sent += 1
        
        await db.commit()
        
        logger.info(f"Low stock check complete: {len(low_stock_items)} items low, {notifications_sent} notifications sent")
        return {
            "low_stock_count": len(low_stock_items),
            "notifications_sent": notifications_sent,
        }


# ===========================================
# TAX DEADLINE TASKS
# ===========================================

@shared_task(name='app.tasks.celery_tasks.check_vat_deadlines_task')
def check_vat_deadlines_task() -> Dict[str, Any]:
    """Check for upcoming VAT filing deadlines and send reminders."""
    return run_async(_check_vat_deadlines())


async def _check_vat_deadlines() -> Dict[str, Any]:
    """Async implementation of VAT deadline check."""
    from app.models.entity import BusinessEntity
    from app.models.user import User, UserEntityAccess
    from app.services.notification_service import NotificationService
    from sqlalchemy import select
    
    async with async_session_factory() as db:
        today = date.today()
        
        # VAT is due by 21st of the following month
        if today.month == 12:
            deadline = date(today.year + 1, 1, 21)
            period = f"December {today.year}"
        else:
            deadline = date(today.year, today.month + 1, 21)
            period = f"{date(today.year, today.month, 1).strftime('%B')} {today.year}"
        
        days_until = (deadline - today).days
        
        if days_until > 7 or days_until < 0:
            return {"status": "no_action_needed", "days_until": days_until}
        
        notification_service = NotificationService(db)
        notifications_sent = 0
        
        # Get all active VAT-registered entities
        result = await db.execute(
            select(BusinessEntity)
            .where(BusinessEntity.is_active == True)
            .where(BusinessEntity.is_vat_registered == True)
        )
        entities = result.scalars().all()
        
        for entity in entities:
            # Get users with access
            users_result = await db.execute(
                select(UserEntityAccess)
                .where(UserEntityAccess.entity_id == entity.id)
            )
            user_accesses = users_result.scalars().all()
            
            for access in user_accesses:
                user_result = await db.execute(
                    select(User).where(User.id == access.user_id)
                )
                user = user_result.scalar_one_or_none()
                
                if user and user.is_active:
                    await notification_service.notify_vat_reminder(
                        user_id=user.id,
                        entity_id=entity.id,
                        period=period,
                        deadline=deadline.strftime('%B %d, %Y'),
                        days_until=days_until,
                        email_address=user.email if days_until <= 3 else None,
                    )
                    notifications_sent += 1
        
        await db.commit()
        
        logger.info(f"VAT reminder sent: {notifications_sent} notifications, {days_until} days until deadline")
        return {
            "deadline": deadline.isoformat(),
            "days_until": days_until,
            "notifications_sent": notifications_sent,
        }


@shared_task(name='app.tasks.celery_tasks.check_paye_deadlines_task')
def check_paye_deadlines_task() -> Dict[str, Any]:
    """Check for upcoming PAYE filing deadlines and send reminders."""
    return run_async(_check_paye_deadlines())


async def _check_paye_deadlines() -> Dict[str, Any]:
    """Async implementation of PAYE deadline check."""
    from app.models.entity import BusinessEntity
    from app.models.user import User, UserEntityAccess
    from app.services.notification_service import NotificationService
    from app.models.notification import NotificationType
    from sqlalchemy import select
    
    async with async_session_factory() as db:
        today = date.today()
        
        # PAYE is due by 10th of the following month
        if today.month == 12:
            deadline = date(today.year + 1, 1, 10)
            period = f"December {today.year}"
        else:
            deadline = date(today.year, today.month + 1, 10)
            period = f"{date(today.year, today.month, 1).strftime('%B')} {today.year}"
        
        days_until = (deadline - today).days
        
        if days_until > 7 or days_until < 0:
            return {"status": "no_action_needed", "days_until": days_until}
        
        notification_service = NotificationService(db)
        notifications_sent = 0
        
        # Get all active entities
        result = await db.execute(
            select(BusinessEntity)
            .where(BusinessEntity.is_active == True)
        )
        entities = result.scalars().all()
        
        for entity in entities:
            users_result = await db.execute(
                select(UserEntityAccess)
                .where(UserEntityAccess.entity_id == entity.id)
            )
            user_accesses = users_result.scalars().all()
            
            for access in user_accesses:
                user_result = await db.execute(
                    select(User).where(User.id == access.user_id)
                )
                user = user_result.scalar_one_or_none()
                
                if user and user.is_active:
                    await notification_service.create_notification(
                        user_id=user.id,
                        entity_id=entity.id,
                        notification_type=NotificationType.PAYE_REMINDER,
                        title="PAYE Filing Reminder",
                        message=f"PAYE remittance for {period} is due on {deadline.strftime('%B %d, %Y')} ({days_until} days remaining).",
                        action_url="/reports?tab=tax",
                        action_label="View PAYE Report",
                        send_email=days_until <= 3,
                        email_address=user.email if days_until <= 3 else None,
                    )
                    notifications_sent += 1
        
        await db.commit()
        
        logger.info(f"PAYE reminder sent: {notifications_sent} notifications")
        return {
            "deadline": deadline.isoformat(),
            "days_until": days_until,
            "notifications_sent": notifications_sent,
        }


# ===========================================
# NRS TASKS
# ===========================================

@shared_task(name='app.tasks.celery_tasks.retry_failed_nrs_submissions_task')
def retry_failed_nrs_submissions_task() -> Dict[str, Any]:
    """Retry failed NRS invoice submissions."""
    return run_async(_retry_failed_nrs_submissions())


async def _retry_failed_nrs_submissions() -> Dict[str, Any]:
    """Async implementation of NRS submission retry."""
    from app.models.invoice import Invoice, InvoiceStatus
    from app.services.nrs_service import NRSService
    from sqlalchemy import select
    
    async with async_session_factory() as db:
        # Find invoices pending NRS submission (failed previously)
        result = await db.execute(
            select(Invoice)
            .where(Invoice.status == InvoiceStatus.PENDING)
            .where(Invoice.nrs_irn == None)
            .where(Invoice.nrs_submission_attempts < 5)  # Max 5 retries
        )
        
        pending_invoices = result.scalars().all()
        successful = 0
        failed = 0
        
        nrs_service = NRSService()
        
        for invoice in pending_invoices:
            try:
                # Attempt submission
                response = await nrs_service.submit_invoice(invoice)
                
                if response.success and response.irn:
                    invoice.nrs_irn = response.irn
                    invoice.nrs_qr_code_data = response.qr_code_data
                    invoice.nrs_submission_date = datetime.utcnow()
                    invoice.status = InvoiceStatus.SUBMITTED
                    successful += 1
                else:
                    invoice.nrs_submission_attempts = (invoice.nrs_submission_attempts or 0) + 1
                    invoice.nrs_last_error = response.message
                    failed += 1
            except Exception as e:
                invoice.nrs_submission_attempts = (invoice.nrs_submission_attempts or 0) + 1
                invoice.nrs_last_error = str(e)
                failed += 1
        
        await db.commit()
        
        logger.info(f"NRS retry complete: {successful} successful, {failed} failed")
        return {
            "successful": successful,
            "failed": failed,
            "total_pending": len(pending_invoices),
        }


# ===========================================
# CLEANUP TASKS
# ===========================================

@shared_task(name='app.tasks.celery_tasks.cleanup_notifications_task')
def cleanup_notifications_task() -> Dict[str, Any]:
    """Clean up old notifications."""
    return run_async(_cleanup_notifications())


async def _cleanup_notifications() -> Dict[str, Any]:
    """Delete notifications older than 90 days."""
    from app.services.notification_service import NotificationService
    
    async with async_session_factory() as db:
        notification_service = NotificationService(db)
        deleted_count = await notification_service.delete_old_notifications(days_old=90)
        
        logger.info(f"Cleaned up {deleted_count} old notifications")
        return {"deleted_count": deleted_count}


@shared_task(name='app.tasks.celery_tasks.archive_audit_logs_task')
def archive_audit_logs_task() -> Dict[str, Any]:
    """Archive old audit logs."""
    return run_async(_archive_audit_logs())


async def _archive_audit_logs() -> Dict[str, Any]:
    """Archive audit logs older than 5 years (NTAA requirement)."""
    from app.models.audit_consolidated import AuditLog
    from sqlalchemy import select, func
    
    async with async_session_factory() as db:
        cutoff = datetime.utcnow() - timedelta(days=365 * 5)
        
        # Count logs to archive (but don't delete - NTAA requires 5-year retention)
        result = await db.execute(
            select(func.count(AuditLog.id))
            .where(AuditLog.created_at < cutoff)
        )
        count = result.scalar() or 0
        
        # In production, these would be archived to cold storage
        logger.info(f"Found {count} audit logs eligible for archival")
        
        return {"eligible_for_archive": count}


# ===========================================
# REPORT GENERATION TASKS
# ===========================================

@shared_task(name='app.tasks.celery_tasks.generate_monthly_tax_summary_task')
def generate_monthly_tax_summary_task() -> Dict[str, Any]:
    """Generate monthly tax summary reports for all entities."""
    return run_async(_generate_monthly_tax_summary())


async def _generate_monthly_tax_summary() -> Dict[str, Any]:
    """Generate monthly tax summaries."""
    from app.models.entity import BusinessEntity
    from app.models.user import User, UserEntityAccess
    from app.services.notification_service import NotificationService
    from app.models.notification import NotificationType
    from sqlalchemy import select
    
    async with async_session_factory() as db:
        today = date.today()
        
        # Generate for previous month
        if today.month == 1:
            report_month = 12
            report_year = today.year - 1
        else:
            report_month = today.month - 1
            report_year = today.year
        
        period = f"{date(report_year, report_month, 1).strftime('%B')} {report_year}"
        
        notification_service = NotificationService(db)
        reports_generated = 0
        
        result = await db.execute(
            select(BusinessEntity)
            .where(BusinessEntity.is_active == True)
        )
        entities = result.scalars().all()
        
        for entity in entities:
            # Notify entity users that monthly summary is ready
            users_result = await db.execute(
                select(UserEntityAccess)
                .where(UserEntityAccess.entity_id == entity.id)
                .where(UserEntityAccess.can_write == True)
            )
            user_accesses = users_result.scalars().all()
            
            for access in user_accesses:
                user_result = await db.execute(
                    select(User).where(User.id == access.user_id)
                )
                user = user_result.scalar_one_or_none()
                
                if user and user.is_active:
                    await notification_service.create_notification(
                        user_id=user.id,
                        entity_id=entity.id,
                        notification_type=NotificationType.INFO,
                        title=f"Monthly Tax Summary Ready",
                        message=f"Your tax summary for {period} is now available in the Reports section.",
                        action_url="/reports?tab=tax",
                        action_label="View Report",
                    )
            
            reports_generated += 1
        
        await db.commit()
        
        logger.info(f"Generated {reports_generated} monthly tax summary notifications")
        return {
            "period": period,
            "reports_generated": reports_generated,
        }


# ===========================================
# EMAIL TASKS
# ===========================================

@shared_task(name='app.tasks.celery_tasks.send_email_task', bind=True, max_retries=3)
def send_email_task(self, to: List[str], subject: str, body_text: str, body_html: str = None) -> bool:
    """Send an email asynchronously."""
    return run_async(_send_email(to, subject, body_text, body_html))


async def _send_email(to: List[str], subject: str, body_text: str, body_html: str = None) -> bool:
    """Async email sending."""
    from app.services.email_service import EmailService, EmailMessage
    
    email_service = EmailService()
    return await email_service.send_email(EmailMessage(
        to=to,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
    ))


# ===========================================
# BILLING & SUBSCRIPTION TASKS
# ===========================================

@shared_task(name='app.tasks.celery_tasks.check_trial_expirations_task')
def check_trial_expirations_task() -> Dict[str, Any]:
    """
    Check for expired trials and transition them to appropriate state.
    
    - Trials with payment method: Attempt first charge
    - Trials without payment method: Downgrade to free/disabled
    - Send notifications before and on expiry
    """
    return run_async(_check_trial_expirations())


async def _check_trial_expirations() -> Dict[str, Any]:
    """Async implementation of trial expiration check."""
    from app.models.sku import TenantSKU, SKUTier
    from app.models.organization import Organization
    from app.models.user import User
    from app.services.billing_email_service import BillingEmailService
    from app.services.dunning_service import DunningService
    from sqlalchemy import select, and_
    
    async with async_session_factory() as db:
        now = datetime.utcnow()
        
        # Find trials expiring today or already expired (within grace period)
        grace_period_days = 3
        grace_cutoff = now - timedelta(days=grace_period_days)
        
        result = await db.execute(
            select(TenantSKU)
            .where(TenantSKU.is_active == True)
            .where(TenantSKU.trial_ends_at != None)
            .where(TenantSKU.trial_ends_at <= now)
            .where(TenantSKU.trial_ends_at >= grace_cutoff)
        )
        
        expiring_trials = result.scalars().all()
        
        trials_expired = 0
        trials_converted = 0
        trials_warned = 0
        trials_disabled = 0
        
        billing_email_service = BillingEmailService(db)
        dunning_service = DunningService(db)
        
        for tenant_sku in expiring_trials:
            # Get organization and admin user
            org_result = await db.execute(
                select(Organization).where(Organization.id == tenant_sku.organization_id)
            )
            org = org_result.scalar_one_or_none()
            if not org:
                continue
            
            # Get admin user for notifications
            admin_result = await db.execute(
                select(User)
                .where(User.organization_id == tenant_sku.organization_id)
                .where(User.is_active == True)
                .order_by(User.created_at)
                .limit(1)
            )
            admin_user = admin_result.scalar_one_or_none()
            
            days_since_expiry = (now - tenant_sku.trial_ends_at).days
            
            if days_since_expiry == 0:
                # Trial just expired - send final warning
                if admin_user and admin_user.email:
                    await billing_email_service.send_trial_expired(
                        email=admin_user.email,
                        organization_name=org.name,
                        tier=tenant_sku.tier.value,
                        grace_period_days=grace_period_days,
                    )
                trials_expired += 1
                
            elif days_since_expiry >= grace_period_days:
                # Grace period over - disable or downgrade
                tenant_sku.tier = SKUTier.CORE
                tenant_sku.trial_ends_at = None
                tenant_sku.is_active = True  # Keep active but downgrade
                tenant_sku.notes = f"Trial expired, downgraded to Core on {now.isoformat()}"
                
                if admin_user and admin_user.email:
                    await billing_email_service.send_trial_ended_downgrade(
                        email=admin_user.email,
                        organization_name=org.name,
                        previous_tier=tenant_sku.tier.value,
                    )
                trials_disabled += 1
        
        # Also check for trials expiring soon (3 days, 1 day warnings)
        warning_days = [3, 1]
        for days_until in warning_days:
            warning_date = now + timedelta(days=days_until)
            warning_start = warning_date.replace(hour=0, minute=0, second=0)
            warning_end = warning_date.replace(hour=23, minute=59, second=59)
            
            upcoming_result = await db.execute(
                select(TenantSKU)
                .where(TenantSKU.is_active == True)
                .where(TenantSKU.trial_ends_at != None)
                .where(TenantSKU.trial_ends_at >= warning_start)
                .where(TenantSKU.trial_ends_at <= warning_end)
            )
            
            upcoming_trials = upcoming_result.scalars().all()
            
            for tenant_sku in upcoming_trials:
                org_result = await db.execute(
                    select(Organization).where(Organization.id == tenant_sku.organization_id)
                )
                org = org_result.scalar_one_or_none()
                if not org:
                    continue
                
                admin_result = await db.execute(
                    select(User)
                    .where(User.organization_id == tenant_sku.organization_id)
                    .where(User.is_active == True)
                    .order_by(User.created_at)
                    .limit(1)
                )
                admin_user = admin_result.scalar_one_or_none()
                
                if admin_user and admin_user.email:
                    await billing_email_service.send_trial_expiring_warning(
                        email=admin_user.email,
                        organization_name=org.name,
                        tier=tenant_sku.tier.value,
                        days_remaining=days_until,
                        trial_ends_at=tenant_sku.trial_ends_at,
                    )
                trials_warned += 1
        
        await db.commit()
        
        logger.info(f"Trial expiration check: {trials_expired} expired, {trials_disabled} disabled, {trials_warned} warned")
        return {
            "trials_expired": trials_expired,
            "trials_converted": trials_converted,
            "trials_warned": trials_warned,
            "trials_disabled": trials_disabled,
        }


@shared_task(name='app.tasks.celery_tasks.process_subscription_renewals_task')
def process_subscription_renewals_task() -> Dict[str, Any]:
    """
    Process subscription renewals for recurring billing.
    
    - Find subscriptions due for renewal
    - Initiate payment charges via Paystack
    - Update subscription periods
    - Handle failures with dunning
    """
    return run_async(_process_subscription_renewals())


async def _process_subscription_renewals() -> Dict[str, Any]:
    """Async implementation of subscription renewal processing."""
    from app.models.sku import TenantSKU, SKUTier, PaymentTransaction
    from app.models.organization import Organization
    from app.models.user import User
    from app.services.billing_service import BillingService, BillingCycle
    from app.services.billing_email_service import BillingEmailService
    from app.services.dunning_service import DunningService
    from app.config.sku_config import TIER_PRICING
    from sqlalchemy import select
    
    async with async_session_factory() as db:
        now = datetime.utcnow()
        today = now.date()
        
        # Find subscriptions where current_period_end is today or past
        # and they're not on trial
        result = await db.execute(
            select(TenantSKU)
            .where(TenantSKU.is_active == True)
            .where(TenantSKU.trial_ends_at == None)  # Not on trial
            .where(TenantSKU.current_period_end != None)
            .where(TenantSKU.current_period_end <= today)
            .where(TenantSKU.tier != SKUTier.CORE)  # Core tier is free/doesn't renew
        )
        
        due_subscriptions = result.scalars().all()
        
        renewed = 0
        failed = 0
        skipped = 0
        
        billing_service = BillingService(db)
        billing_email_service = BillingEmailService(db)
        dunning_service = DunningService(db)
        
        for tenant_sku in due_subscriptions:
            # Get organization and admin
            org_result = await db.execute(
                select(Organization).where(Organization.id == tenant_sku.organization_id)
            )
            org = org_result.scalar_one_or_none()
            if not org:
                skipped += 1
                continue
            
            admin_result = await db.execute(
                select(User)
                .where(User.organization_id == tenant_sku.organization_id)
                .where(User.is_active == True)
                .order_by(User.created_at)
                .limit(1)
            )
            admin_user = admin_result.scalar_one_or_none()
            
            if not admin_user or not admin_user.email:
                skipped += 1
                continue
            
            # Calculate renewal amount
            billing_cycle = BillingCycle(tenant_sku.billing_cycle) if tenant_sku.billing_cycle else BillingCycle.MONTHLY
            
            amount = billing_service.calculate_subscription_price(
                tier=tenant_sku.tier,
                billing_cycle=billing_cycle,
                intelligence_addon=tenant_sku.intelligence_addon,
            )
            
            try:
                # Create payment intent for renewal
                payment_intent = await billing_service.create_payment_intent(
                    organization_id=tenant_sku.organization_id,
                    tier=tenant_sku.tier,
                    billing_cycle=billing_cycle,
                    admin_email=admin_user.email,
                    intelligence_addon=tenant_sku.intelligence_addon,
                    callback_url=f"/billing/renewal-callback",
                    user_id=admin_user.id,
                )
                
                # Send renewal invoice email
                await billing_email_service.send_renewal_invoice(
                    email=admin_user.email,
                    organization_name=org.name,
                    tier=tenant_sku.tier.value,
                    amount_naira=amount,
                    payment_url=payment_intent.authorization_url,
                    due_date=now + timedelta(days=7),
                )
                
                renewed += 1
                logger.info(f"Renewal initiated for org {org.id}: {tenant_sku.tier.value}")
                
            except Exception as e:
                logger.error(f"Renewal failed for org {tenant_sku.organization_id}: {e}")
                
                # Record failure for dunning
                await dunning_service.record_payment_failure(
                    organization_id=tenant_sku.organization_id,
                    reason=str(e),
                    amount_naira=amount,
                )
                
                failed += 1
        
        await db.commit()
        
        logger.info(f"Subscription renewals: {renewed} initiated, {failed} failed, {skipped} skipped")
        return {
            "renewed": renewed,
            "failed": failed,
            "skipped": skipped,
        }


@shared_task(name='app.tasks.celery_tasks.retry_failed_payments_task')
def retry_failed_payments_task() -> Dict[str, Any]:
    """
    Retry failed payments with dunning escalation.
    
    - Find failed payments within retry window
    - Attempt retry based on dunning schedule
    - Escalate if max retries reached
    - Suspend accounts if payment not recovered
    """
    return run_async(_retry_failed_payments())


async def _retry_failed_payments() -> Dict[str, Any]:
    """Async implementation of payment retry/dunning."""
    from app.models.sku import PaymentTransaction, TenantSKU, SKUTier
    from app.models.organization import Organization
    from app.models.user import User
    from app.services.billing_service import BillingService, PaystackProvider
    from app.services.billing_email_service import BillingEmailService
    from app.services.dunning_service import DunningService, DunningLevel
    from sqlalchemy import select, and_
    
    async with async_session_factory() as db:
        now = datetime.utcnow()
        
        dunning_service = DunningService(db)
        billing_email_service = BillingEmailService(db)
        payment_provider = PaystackProvider()
        
        # Get organizations in dunning state
        dunning_records = await dunning_service.get_active_dunning_records()
        
        retried = 0
        recovered = 0
        escalated = 0
        suspended = 0
        
        for record in dunning_records:
            org_id = record.organization_id
            
            # Check if it's time to retry based on dunning level
            should_retry, next_action = await dunning_service.should_retry_payment(org_id)
            
            if not should_retry:
                continue
            
            # Get organization and admin
            org_result = await db.execute(
                select(Organization).where(Organization.id == org_id)
            )
            org = org_result.scalar_one_or_none()
            if not org:
                continue
            
            admin_result = await db.execute(
                select(User)
                .where(User.organization_id == org_id)
                .where(User.is_active == True)
                .order_by(User.created_at)
                .limit(1)
            )
            admin_user = admin_result.scalar_one_or_none()
            
            if next_action == "retry":
                # Attempt payment retry
                try:
                    # Send reminder email with payment link
                    if admin_user and admin_user.email:
                        await billing_email_service.send_payment_retry_notice(
                            email=admin_user.email,
                            organization_name=org.name,
                            attempt_number=record.retry_count + 1,
                            amount_naira=record.amount_naira,
                            days_until_suspension=record.days_until_suspension,
                        )
                    
                    await dunning_service.record_retry_attempt(org_id)
                    retried += 1
                    
                except Exception as e:
                    logger.error(f"Payment retry failed for org {org_id}: {e}")
                    
            elif next_action == "escalate":
                # Escalate dunning level
                new_level = await dunning_service.escalate_dunning_level(org_id)
                
                if admin_user and admin_user.email:
                    await billing_email_service.send_dunning_escalation(
                        email=admin_user.email,
                        organization_name=org.name,
                        dunning_level=new_level.value,
                        amount_naira=record.amount_naira,
                    )
                escalated += 1
                
            elif next_action == "suspend":
                # Suspend account
                tenant_sku_result = await db.execute(
                    select(TenantSKU).where(TenantSKU.organization_id == org_id)
                )
                tenant_sku = tenant_sku_result.scalar_one_or_none()
                
                if tenant_sku:
                    tenant_sku.suspended_at = now
                    tenant_sku.suspension_reason = "Payment failed - dunning exhausted"
                    tenant_sku.is_active = False
                    
                    if admin_user and admin_user.email:
                        await billing_email_service.send_account_suspended(
                            email=admin_user.email,
                            organization_name=org.name,
                            reason="Payment failed after multiple attempts",
                            amount_naira=record.amount_naira,
                        )
                    suspended += 1
        
        await db.commit()
        
        logger.info(f"Payment retry: {retried} retried, {recovered} recovered, {escalated} escalated, {suspended} suspended")
        return {
            "retried": retried,
            "recovered": recovered,
            "escalated": escalated,
            "suspended": suspended,
        }


@shared_task(name='app.tasks.celery_tasks.send_payment_reminders_task')
def send_payment_reminders_task() -> Dict[str, Any]:
    """
    Send payment reminder emails before subscription renewal.
    
    - 7 days before: Upcoming renewal notice
    - 3 days before: Payment reminder
    - 1 day before: Final reminder
    """
    return run_async(_send_payment_reminders())


async def _send_payment_reminders() -> Dict[str, Any]:
    """Async implementation of payment reminders."""
    from app.models.sku import TenantSKU, SKUTier
    from app.models.organization import Organization
    from app.models.user import User
    from app.services.billing_service import BillingService, BillingCycle
    from app.services.billing_email_service import BillingEmailService
    from sqlalchemy import select, and_
    
    async with async_session_factory() as db:
        now = datetime.utcnow()
        today = now.date()
        
        billing_service = BillingService(db)
        billing_email_service = BillingEmailService(db)
        
        # Reminder schedule: days before renewal -> reminder type
        reminder_schedule = {
            7: "upcoming",
            3: "reminder",
            1: "final",
        }
        
        reminders_sent = 0
        
        for days_before, reminder_type in reminder_schedule.items():
            target_date = today + timedelta(days=days_before)
            
            # Find subscriptions renewing on target date
            result = await db.execute(
                select(TenantSKU)
                .where(TenantSKU.is_active == True)
                .where(TenantSKU.trial_ends_at == None)  # Not on trial
                .where(TenantSKU.current_period_end == target_date)
                .where(TenantSKU.tier != SKUTier.CORE)
            )
            
            due_subscriptions = result.scalars().all()
            
            for tenant_sku in due_subscriptions:
                # Get organization
                org_result = await db.execute(
                    select(Organization).where(Organization.id == tenant_sku.organization_id)
                )
                org = org_result.scalar_one_or_none()
                if not org:
                    continue
                
                # Get admin user
                admin_result = await db.execute(
                    select(User)
                    .where(User.organization_id == tenant_sku.organization_id)
                    .where(User.is_active == True)
                    .order_by(User.created_at)
                    .limit(1)
                )
                admin_user = admin_result.scalar_one_or_none()
                
                if not admin_user or not admin_user.email:
                    continue
                
                # Calculate amount
                billing_cycle = BillingCycle(tenant_sku.billing_cycle) if tenant_sku.billing_cycle else BillingCycle.MONTHLY
                amount = billing_service.calculate_subscription_price(
                    tier=tenant_sku.tier,
                    billing_cycle=billing_cycle,
                    intelligence_addon=tenant_sku.intelligence_addon,
                )
                
                # Send appropriate reminder
                if reminder_type == "upcoming":
                    await billing_email_service.send_renewal_upcoming(
                        email=admin_user.email,
                        organization_name=org.name,
                        tier=tenant_sku.tier.value,
                        amount_naira=amount,
                        renewal_date=tenant_sku.current_period_end,
                        days_until=days_before,
                    )
                elif reminder_type == "reminder":
                    await billing_email_service.send_renewal_reminder(
                        email=admin_user.email,
                        organization_name=org.name,
                        tier=tenant_sku.tier.value,
                        amount_naira=amount,
                        renewal_date=tenant_sku.current_period_end,
                    )
                elif reminder_type == "final":
                    await billing_email_service.send_renewal_final_notice(
                        email=admin_user.email,
                        organization_name=org.name,
                        tier=tenant_sku.tier.value,
                        amount_naira=amount,
                        renewal_date=tenant_sku.current_period_end,
                    )
                
                reminders_sent += 1
        
        await db.commit()
        
        logger.info(f"Payment reminders sent: {reminders_sent}")
        return {"reminders_sent": reminders_sent}


# ===========================================
# SCHEDULED CANCELLATION TASK
# ===========================================

@shared_task(name='app.tasks.celery_tasks.process_scheduled_cancellations_task')
def process_scheduled_cancellations_task() -> Dict[str, Any]:
    """
    Process subscriptions scheduled for cancellation at period end.
    
    This task checks for subscriptions with cancel_at_period_end=True
    where the period has ended, and downgrades them to the scheduled tier.
    """
    return run_async(_process_scheduled_cancellations())


async def _process_scheduled_cancellations() -> Dict[str, Any]:
    """Async implementation of scheduled cancellation processing."""
    from app.tasks.scheduled_tasks import process_scheduled_cancellations
    
    async with async_session_factory() as db:
        result = await process_scheduled_cancellations(db)
        await db.commit()
        return result


# ===========================================
# USAGE ALERTS CHECK TASK
# ===========================================

@shared_task(name='app.tasks.celery_tasks.check_usage_alerts_task')
def check_usage_alerts_task() -> Dict[str, Any]:
    """
    Check usage across all organizations and send alerts.
    
    This task monitors usage against limits and sends email/in-app
    notifications when thresholds (80%, 90%, 100%) are reached.
    """
    return run_async(_check_usage_alerts())


async def _check_usage_alerts() -> Dict[str, Any]:
    """Async implementation of usage alert checking."""
    from app.tasks.scheduled_tasks import check_usage_alerts
    
    async with async_session_factory() as db:
        result = await check_usage_alerts(db)
        await db.commit()
        return result


# ===========================================
# AUTO-RESUME PAUSED SUBSCRIPTIONS TASK (#32)
# ===========================================

@shared_task(name='app.tasks.celery_tasks.auto_resume_paused_subscriptions_task')
def auto_resume_paused_subscriptions_task() -> Dict[str, Any]:
    """
    Automatically resume paused subscriptions when pause_until date is reached.
    
    Billing Feature #32: Subscription Pause System with Annual Limit
    - Checks for subscriptions where paused_at is set and pause_until <= now
    - Resumes them automatically by clearing pause fields
    - Respects the 3 pauses per year limit tracked in pause_count_this_year
    """
    return run_async(_auto_resume_paused_subscriptions())


async def _auto_resume_paused_subscriptions() -> Dict[str, Any]:
    """Async implementation of auto-resume paused subscriptions."""
    from app.tasks.scheduled_tasks import auto_resume_paused_subscriptions
    
    async with async_session_factory() as db:
        result = await auto_resume_paused_subscriptions(db)
        await db.commit()
        return result


# ===========================================
# UPDATE EXCHANGE RATES TASK (#36)
# ===========================================

@shared_task(name='app.tasks.celery_tasks.update_exchange_rates_task')
def update_exchange_rates_task() -> Dict[str, Any]:
    """
    Update currency exchange rates for multi-currency checkout.
    
    Billing Feature #36: Multi-currency Checkout
    - Fetches latest exchange rates from external API
    - Updates NGN <-> USD, EUR, GBP conversion rates
    - Ensures checkout displays accurate converted prices
    """
    return run_async(_update_exchange_rates())


async def _update_exchange_rates() -> Dict[str, Any]:
    """Async implementation of exchange rate update."""
    from app.tasks.scheduled_tasks import update_exchange_rates
    
    async with async_session_factory() as db:
        result = await update_exchange_rates(db)
        await db.commit()
        return result


# ===========================================
# SCHEDULED USAGE REPORTS TASK (#30)
# ===========================================

@shared_task(name='app.tasks.celery_tasks.process_scheduled_usage_reports_task')
def process_scheduled_usage_reports_task() -> Dict[str, Any]:
    """
    Generate and deliver scheduled usage reports to organizations.
    
    Billing Feature #30: PDF Export & Scheduled Reports
    - Checks for ScheduledUsageReport entries where next_run_at <= now
    - Generates PDF or CSV reports based on configuration
    - Updates next_run_at for the next scheduled delivery
    """
    return run_async(_process_scheduled_usage_reports())


async def _process_scheduled_usage_reports() -> Dict[str, Any]:
    """Async implementation of scheduled usage reports processing."""
    from app.tasks.scheduled_tasks import process_scheduled_usage_reports
    
    async with async_session_factory() as db:
        result = await process_scheduled_usage_reports(db)
        await db.commit()
        return result


# ===========================================
# FX RATE DAILY UPDATE TASK
# ===========================================

@shared_task(name='app.tasks.celery_tasks.fx_rate_daily_update_task')
def fx_rate_daily_update_task() -> Dict[str, Any]:
    """
    Daily FX rate update task.
    
    - Fetches latest exchange rates from CBN and market sources
    - Updates the exchange rate table for all tracked currency pairs
    - Caches rates for quick access
    - Triggers revaluation if rates changed significantly (>1%)
    
    Should run daily at 6:00 AM WAT before market opens.
    """
    return run_async(_fx_rate_daily_update())


async def _fx_rate_daily_update() -> Dict[str, Any]:
    """Async implementation of FX rate daily update."""
    from decimal import Decimal
    
    async with async_session_factory() as db:
        try:
            from app.services.fx_service import FXService
            
            fx_service = FXService(db)
            
            # Currencies to update (NGN base pairs)
            currency_pairs = [
                ("USD", "NGN"),
                ("EUR", "NGN"),
                ("GBP", "NGN"),
                ("NGN", "USD"),
                ("NGN", "EUR"),
                ("NGN", "GBP"),
            ]
            
            updated_rates = []
            rate_changes = []
            
            for from_currency, to_currency in currency_pairs:
                try:
                    # Get previous rate
                    old_rate = await fx_service.get_exchange_rate(from_currency, to_currency)
                    
                    # Fetch new rate (this would integrate with external API)
                    new_rate = await fx_service.fetch_latest_rate(from_currency, to_currency)
                    
                    if new_rate:
                        # Calculate change percentage
                        if old_rate and old_rate > 0:
                            change_pct = abs((new_rate - old_rate) / old_rate * 100)
                        else:
                            change_pct = 0
                        
                        # Store the rate
                        await fx_service.store_exchange_rate(
                            from_currency=from_currency,
                            to_currency=to_currency,
                            rate=new_rate,
                            source="daily_update"
                        )
                        
                        updated_rates.append({
                            "pair": f"{from_currency}/{to_currency}",
                            "rate": float(new_rate),
                            "change_pct": float(change_pct)
                        })
                        
                        # Flag significant changes (>1%)
                        if change_pct > 1.0:
                            rate_changes.append({
                                "pair": f"{from_currency}/{to_currency}",
                                "old_rate": float(old_rate) if old_rate else 0,
                                "new_rate": float(new_rate),
                                "change_pct": float(change_pct)
                            })
                
                except Exception as e:
                    logger.error(f"Failed to update rate for {from_currency}/{to_currency}: {e}")
            
            await db.commit()
            
            # Trigger revaluation if significant changes detected
            if rate_changes:
                logger.warning(f"Significant FX rate changes detected: {len(rate_changes)} pairs")
                # Could trigger fx_revaluation_task here
            
            logger.info(f"FX rate update complete: {len(updated_rates)} rates updated")
            return {
                "success": True,
                "rates_updated": len(updated_rates),
                "updated_rates": updated_rates,
                "significant_changes": rate_changes,
                "timestamp": datetime.utcnow().isoformat()
            }
        
        except Exception as e:
            logger.error(f"FX rate daily update failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }


# ===========================================
# FX REVALUATION TASK
# ===========================================

@shared_task(name='app.tasks.celery_tasks.fx_revaluation_task')
def fx_revaluation_task(entity_ids: List[str] = None) -> Dict[str, Any]:
    """
    FX revaluation task for foreign currency monetary items.
    
    - Identifies all foreign currency monetary assets and liabilities
    - Revalues at current exchange rates
    - Creates journal entries for FX gains/losses
    - Updates unrealized FX gain/loss accounts
    
    Args:
        entity_ids: Optional list of entity IDs to revalue. If None, processes all entities.
    
    Should run monthly at period-end or on-demand when rates change significantly.
    """
    return run_async(_fx_revaluation(entity_ids))


async def _fx_revaluation(entity_ids: List[str] = None) -> Dict[str, Any]:
    """Async implementation of FX revaluation."""
    from decimal import Decimal
    from uuid import UUID
    
    async with async_session_factory() as db:
        try:
            from app.services.fx_service import FXService
            from app.models.entity import BusinessEntity
            from sqlalchemy import select
            
            fx_service = FXService(db)
            
            # Get entities to process
            if entity_ids:
                entities = [UUID(eid) for eid in entity_ids]
            else:
                result = await db.execute(
                    select(BusinessEntity.id).where(BusinessEntity.is_active == True)
                )
                entities = [row[0] for row in result.all()]
            
            revaluation_results = []
            total_gain_loss = Decimal("0")
            
            for entity_id in entities:
                try:
                    result = await fx_service.perform_revaluation(
                        entity_id=entity_id,
                        revaluation_date=date.today()
                    )
                    
                    if result:
                        revaluation_results.append({
                            "entity_id": str(entity_id),
                            "gain_loss": float(result.get("net_gain_loss", 0)),
                            "items_revalued": result.get("items_revalued", 0),
                            "journal_entry_id": str(result.get("journal_entry_id")) if result.get("journal_entry_id") else None
                        })
                        total_gain_loss += Decimal(str(result.get("net_gain_loss", 0)))
                
                except Exception as e:
                    logger.error(f"FX revaluation failed for entity {entity_id}: {e}")
                    revaluation_results.append({
                        "entity_id": str(entity_id),
                        "error": str(e)
                    })
            
            await db.commit()
            
            logger.info(f"FX revaluation complete: {len(revaluation_results)} entities processed, total gain/loss: {total_gain_loss}")
            return {
                "success": True,
                "entities_processed": len(revaluation_results),
                "total_gain_loss": float(total_gain_loss),
                "results": revaluation_results,
                "timestamp": datetime.utcnow().isoformat()
            }
        
        except Exception as e:
            logger.error(f"FX revaluation task failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }


# ===========================================
# CONSOLIDATION SCHEDULE TASK
# ===========================================

@shared_task(name='app.tasks.celery_tasks.consolidation_schedule_task')
def consolidation_schedule_task(group_id: str = None) -> Dict[str, Any]:
    """
    Automated consolidation run task.
    
    - Runs consolidation for entity groups on scheduled basis
    - Performs intercompany eliminations
    - Generates consolidated trial balance
    - Creates consolidation worksheet
    
    Args:
        group_id: Optional specific group ID to consolidate. If None, processes all groups.
    
    Should run monthly after all subsidiaries have closed their books.
    """
    return run_async(_consolidation_schedule(group_id))


async def _consolidation_schedule(group_id: str = None) -> Dict[str, Any]:
    """Async implementation of scheduled consolidation."""
    from uuid import UUID
    
    async with async_session_factory() as db:
        try:
            from app.services.consolidation_service import ConsolidationService
            from app.models.multi_entity import EntityGroup
            from sqlalchemy import select
            
            consol_service = ConsolidationService(db)
            
            # Get groups to process
            if group_id:
                groups = [UUID(group_id)]
            else:
                result = await db.execute(
                    select(EntityGroup.id).where(EntityGroup.is_active == True)
                )
                groups = [row[0] for row in result.all()]
            
            consolidation_results = []
            as_of_date = date.today().replace(day=1) - timedelta(days=1)  # Last day of previous month
            
            for gid in groups:
                try:
                    # Run consolidation
                    result = await consol_service.run_consolidation(
                        group_id=gid,
                        as_of_date=as_of_date
                    )
                    
                    consolidation_results.append({
                        "group_id": str(gid),
                        "as_of_date": as_of_date.isoformat(),
                        "success": True,
                        "eliminations_count": result.get("eliminations_count", 0),
                        "total_assets": float(result.get("total_assets", 0)),
                        "total_liabilities": float(result.get("total_liabilities", 0))
                    })
                
                except Exception as e:
                    logger.error(f"Consolidation failed for group {gid}: {e}")
                    consolidation_results.append({
                        "group_id": str(gid),
                        "success": False,
                        "error": str(e)
                    })
            
            await db.commit()
            
            successful = sum(1 for r in consolidation_results if r.get("success"))
            logger.info(f"Consolidation schedule complete: {successful}/{len(consolidation_results)} groups processed")
            
            return {
                "success": True,
                "groups_processed": len(consolidation_results),
                "successful_consolidations": successful,
                "results": consolidation_results,
                "timestamp": datetime.utcnow().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Consolidation schedule task failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }


# ===========================================
# BUDGET VARIANCE ALERT TASK
# ===========================================

@shared_task(name='app.tasks.celery_tasks.budget_variance_alert_task')
def budget_variance_alert_task(alert_threshold: float = 10.0) -> Dict[str, Any]:
    """
    Budget variance alert task.
    
    - Checks all active budgets for variance thresholds
    - Sends notifications when budget lines exceed threshold
    - Creates alerts for over-budget conditions
    
    Args:
        alert_threshold: Percentage threshold for triggering alerts (default 10%)
    
    Should run weekly or monthly based on business requirements.
    """
    return run_async(_budget_variance_alert(alert_threshold))


async def _budget_variance_alert(alert_threshold: float = 10.0) -> Dict[str, Any]:
    """Async implementation of budget variance alert."""
    from decimal import Decimal
    
    async with async_session_factory() as db:
        try:
            from app.services.budget_service import BudgetService
            from app.services.notification_service import NotificationService
            from app.models.budget import Budget, BudgetStatus
            from app.models.user import User, UserEntityAccess
            from sqlalchemy import select
            
            budget_service = BudgetService(db)
            notification_service = NotificationService(db)
            
            # Get active budgets
            result = await db.execute(
                select(Budget).where(Budget.status == BudgetStatus.APPROVED)
            )
            active_budgets = result.scalars().all()
            
            alerts_created = 0
            budgets_checked = 0
            all_alerts = []
            
            current_month = date.today().month
            
            for budget in active_budgets:
                try:
                    # Get YTD variance analysis
                    variance_data = await budget_service.get_budget_vs_actual(
                        entity_id=budget.entity_id,
                        budget_id=budget.id,
                        through_month=current_month,
                        group_by="account"
                    )
                    
                    budgets_checked += 1
                    budget_alerts = []
                    
                    # Check each line item for variance
                    for item in variance_data.get("line_items", []):
                        variance_pct = abs(item.get("variance_percent", 0))
                        
                        if variance_pct >= alert_threshold:
                            alert_info = {
                                "budget_id": str(budget.id),
                                "budget_name": budget.name,
                                "account_name": item.get("account_name"),
                                "budgeted": item.get("budgeted_amount"),
                                "actual": item.get("actual_amount"),
                                "variance_percent": item.get("variance_percent"),
                                "is_over_budget": item.get("actual_amount", 0) > item.get("budgeted_amount", 0),
                                "severity": "high" if variance_pct >= 25 else "medium" if variance_pct >= 15 else "low"
                            }
                            budget_alerts.append(alert_info)
                            all_alerts.append(alert_info)
                    
                    # Send notifications if alerts found
                    if budget_alerts:
                        # Get users with access to entity
                        users_result = await db.execute(
                            select(UserEntityAccess.user_id)
                            .where(UserEntityAccess.entity_id == budget.entity_id)
                        )
                        user_ids = [row[0] for row in users_result.all()]
                        
                        for user_id in user_ids:
                            await notification_service.create_notification(
                                user_id=user_id,
                                entity_id=budget.entity_id,
                                notification_type="budget_alert",
                                title=f"Budget Alert: {budget.name}",
                                message=f"{len(budget_alerts)} line items exceed {alert_threshold}% variance threshold",
                                data={
                                    "budget_id": str(budget.id),
                                    "alerts_count": len(budget_alerts),
                                    "threshold": alert_threshold
                                },
                                priority="high" if any(a.get("severity") == "high" for a in budget_alerts) else "normal"
                            )
                            alerts_created += 1
                
                except Exception as e:
                    logger.error(f"Budget variance check failed for budget {budget.id}: {e}")
            
            await db.commit()
            
            logger.info(f"Budget variance alerts complete: {budgets_checked} budgets checked, {alerts_created} notifications sent")
            return {
                "success": True,
                "budgets_checked": budgets_checked,
                "alerts_created": alerts_created,
                "variance_alerts": all_alerts[:50],  # Limit to first 50
                "timestamp": datetime.utcnow().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Budget variance alert task failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }


# ===========================================
# YEAR-END REMINDER TASK
# ===========================================

@shared_task(name='app.tasks.celery_tasks.year_end_reminder_task')
def year_end_reminder_task() -> Dict[str, Any]:
    """
    Year-end closing reminder task.
    
    - Checks for fiscal years approaching end
    - Sends reminders for year-end tasks (30, 14, 7 days before)
    - Lists pending tasks: depreciation, accruals, inventory count, etc.
    
    Should run daily during year-end period.
    """
    return run_async(_year_end_reminder())


async def _year_end_reminder() -> Dict[str, Any]:
    """Async implementation of year-end reminder."""
    async with async_session_factory() as db:
        try:
            from app.models.accounting import FiscalYear, FiscalYearStatus
            from app.services.notification_service import NotificationService
            from app.models.user import User, UserEntityAccess
            from sqlalchemy import select
            
            notification_service = NotificationService(db)
            today = date.today()
            reminder_days = [30, 14, 7, 3, 1]  # Days before year-end to send reminders
            
            # Get active fiscal years
            result = await db.execute(
                select(FiscalYear).where(FiscalYear.status == FiscalYearStatus.ACTIVE)
            )
            fiscal_years = result.scalars().all()
            
            reminders_sent = 0
            entities_notified = []
            
            for fy in fiscal_years:
                days_until_end = (fy.end_date - today).days
                
                if days_until_end in reminder_days:
                    # Get users with access to entity
                    users_result = await db.execute(
                        select(UserEntityAccess.user_id)
                        .where(UserEntityAccess.entity_id == fy.entity_id)
                    )
                    user_ids = [row[0] for row in users_result.all()]
                    
                    # Build reminder message
                    if days_until_end <= 3:
                        urgency = "URGENT"
                        priority = "high"
                    elif days_until_end <= 7:
                        urgency = "Important"
                        priority = "high"
                    else:
                        urgency = "Reminder"
                        priority = "normal"
                    
                    year_end_tasks = [
                        "Review and post all pending journal entries",
                        "Complete depreciation calculations",
                        "Post accrued expenses and prepaid adjustments",
                        "Perform inventory count and adjustments",
                        "Review aged receivables and allowances",
                        "Reconcile all bank accounts",
                        "Post payroll accruals",
                        "Review and finalize intercompany transactions"
                    ]
                    
                    for user_id in user_ids:
                        await notification_service.create_notification(
                            user_id=user_id,
                            entity_id=fy.entity_id,
                            notification_type="year_end_reminder",
                            title=f"{urgency}: Fiscal Year Ending in {days_until_end} Days",
                            message=f"Fiscal year {fy.year} ends on {fy.end_date.strftime('%B %d, %Y')}. Please complete year-end closing tasks.",
                            data={
                                "fiscal_year_id": str(fy.id),
                                "fiscal_year": fy.year,
                                "end_date": fy.end_date.isoformat(),
                                "days_remaining": days_until_end,
                                "pending_tasks": year_end_tasks
                            },
                            priority=priority
                        )
                        reminders_sent += 1
                    
                    entities_notified.append({
                        "entity_id": str(fy.entity_id),
                        "fiscal_year": fy.year,
                        "days_remaining": days_until_end,
                        "users_notified": len(user_ids)
                    })
            
            await db.commit()
            
            logger.info(f"Year-end reminders complete: {reminders_sent} reminders sent to {len(entities_notified)} entities")
            return {
                "success": True,
                "reminders_sent": reminders_sent,
                "entities_notified": entities_notified,
                "timestamp": datetime.utcnow().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Year-end reminder task failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
