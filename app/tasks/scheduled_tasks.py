"""
Tekvwa Pro Audit - Background Tasks

Celery-compatible background task definitions.
For production, use Celery with Redis/RabbitMQ.
This module provides the task definitions that can be run either
synchronously (for development) or via Celery (for production).
"""

import asyncio
import logging
from datetime import datetime, date, timedelta
from typing import Optional
import uuid

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ===========================================
# SCHEDULED TASK: INVOICE OVERDUE CHECK
# ===========================================

async def check_overdue_invoices(db: AsyncSession) -> dict:
    """
    Check for invoices that have become overdue and update their status.
    Should run daily.
    """
    from app.models.invoice import Invoice, InvoiceStatus
    
    today = date.today()
    
    # Find finalized invoices past due date
    result = await db.execute(
        select(Invoice)
        .where(Invoice.status == InvoiceStatus.FINALIZED)
        .where(Invoice.due_date < today)
    )
    
    overdue_invoices = result.scalars().all()
    count = 0
    
    for invoice in overdue_invoices:
        invoice.status = InvoiceStatus.OVERDUE
        count += 1
    
    await db.commit()
    
    logger.info(f"Marked {count} invoices as overdue")
    return {"marked_overdue": count}


# ===========================================
# SCHEDULED TASK: LOW STOCK ALERTS
# ===========================================

async def check_low_stock_items(db: AsyncSession) -> dict:
    """
    Check for inventory items below reorder level.
    Should run daily.
    """
    from app.models.inventory import InventoryItem
    
    result = await db.execute(
        select(InventoryItem)
        .where(InventoryItem.quantity_on_hand <= InventoryItem.reorder_level)
        .where(InventoryItem.is_active == True)
    )
    
    low_stock_items = result.scalars().all()
    
    # TODO: Send notifications for low stock items
    logger.info(f"Found {len(low_stock_items)} low stock items")
    
    return {
        "low_stock_count": len(low_stock_items),
        "items": [
            {
                "id": str(item.id),
                "name": item.name,
                "current_stock": item.quantity_on_hand,
                "reorder_level": item.reorder_level,
            }
            for item in low_stock_items
        ]
    }


# ===========================================
# SCHEDULED TASK: VAT FILING REMINDERS
# ===========================================

async def check_vat_filing_deadlines(db: AsyncSession) -> dict:
    """
    Check for upcoming VAT filing deadlines.
    Should run daily.
    """
    from app.models.entity import Entity
    
    today = date.today()
    
    # VAT is due by 21st of the following month
    # So if today is the 15th of the month, remind about current month's VAT
    if today.day >= 15 and today.day <= 21:
        # 1 week warning
        filing_deadline = date(
            today.year if today.month < 12 else today.year + 1,
            today.month + 1 if today.month < 12 else 1,
            21
        )
        
        days_until = (filing_deadline - today).days
        
        # Get all active entities for reminder
        result = await db.execute(
            select(Entity).where(Entity.is_active == True)
        )
        entities = result.scalars().all()
        
        logger.info(f"VAT filing reminder: {days_until} days until deadline")
        
        # TODO: Send notifications
        return {
            "deadline": filing_deadline.isoformat(),
            "days_until": days_until,
            "entities_notified": len(entities),
        }
    
    return {"status": "no_deadline_approaching"}


# ===========================================
# SCHEDULED TASK: AUDIT LOG CLEANUP
# ===========================================

async def archive_old_audit_logs(db: AsyncSession, retention_years: int = 5) -> dict:
    """
    Archive audit logs older than retention period.
    NTAA requires 5-year retention.
    Should run monthly.
    """
    from app.models.audit_consolidated import AuditLog
    
    cutoff_date = datetime.utcnow() - timedelta(days=365 * retention_years)
    
    # Count logs to archive
    count_result = await db.execute(
        select(func.count(AuditLog.id))
        .where(AuditLog.created_at < cutoff_date)
    )
    count = count_result.scalar() or 0
    
    if count > 0:
        # In production, archive to cold storage before deleting
        # For now, just log the count
        logger.info(f"Found {count} audit logs older than {retention_years} years")
    
    return {
        "logs_to_archive": count,
        "cutoff_date": cutoff_date.isoformat(),
    }


# ===========================================
# SCHEDULED TASK: NRS SYNC
# ===========================================

async def sync_pending_nrs_invoices(db: AsyncSession) -> dict:
    """
    Retry submission for invoices that failed NRS submission.
    Should run every hour.
    """
    from app.models.invoice import Invoice, InvoiceStatus
    
    # Find finalized invoices without IRN
    result = await db.execute(
        select(Invoice)
        .where(Invoice.status == InvoiceStatus.FINALIZED)
        .where(Invoice.irn == None)
        .limit(50)  # Process in batches
    )
    
    pending_invoices = result.scalars().all()
    
    success_count = 0
    failed_count = 0
    
    for invoice in pending_invoices:
        try:
            # TODO: Actually submit to NRS
            # from app.services.nrs_service import NRSService
            # nrs = NRSService()
            # result = await nrs.submit_invoice(invoice)
            # if result.success:
            #     invoice.irn = result.irn
            #     success_count += 1
            pass
        except Exception as e:
            logger.error(f"Failed to submit invoice {invoice.id} to NRS: {e}")
            failed_count += 1
    
    await db.commit()
    
    return {
        "pending_count": len(pending_invoices),
        "success_count": success_count,
        "failed_count": failed_count,
    }


# ===========================================
# SCHEDULED TASK: REPORT GENERATION
# ===========================================

async def generate_monthly_reports(db: AsyncSession) -> dict:
    """
    Generate monthly reports for all entities.
    Should run on 1st of each month for previous month.
    """
    from app.models.entity import Entity
    from app.services.reports_service import ReportsService
    
    today = date.today()
    
    # Generate for previous month
    if today.month == 1:
        year = today.year - 1
        month = 12
    else:
        year = today.year
        month = today.month - 1
    
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(year, month + 1, 1) - timedelta(days=1)
    
    # Get all active entities
    result = await db.execute(
        select(Entity).where(Entity.is_active == True)
    )
    entities = result.scalars().all()
    
    reports_generated = 0
    
    for entity in entities:
        try:
            service = ReportsService(db)
            
            # Generate P&L
            pnl = await service.generate_profit_loss(
                entity_id=entity.id,
                start_date=start_date,
                end_date=end_date,
            )
            
            # Generate VAT return
            vat = await service.generate_vat_return(
                entity_id=entity.id,
                year=year,
                month=month,
            )
            
            # TODO: Store reports and notify users
            reports_generated += 1
            
        except Exception as e:
            logger.error(f"Failed to generate reports for entity {entity.id}: {e}")
    
    return {
        "period": f"{year}-{month:02d}",
        "entities_processed": len(entities),
        "reports_generated": reports_generated,
    }


# ===========================================
# SCHEDULED TASK: DATABASE MAINTENANCE
# ===========================================

async def database_maintenance(db: AsyncSession) -> dict:
    """
    Perform database maintenance tasks.
    Should run weekly.
    """
    # Run VACUUM ANALYZE on key tables (PostgreSQL)
    # This is typically done at the database level, not here
    
    # Check for orphaned records, data integrity, etc.
    
    return {"status": "completed"}


# ===========================================
# SCHEDULED TASK: PROCESS SUBSCRIPTION CANCELLATIONS
# ===========================================

async def process_scheduled_cancellations(db: AsyncSession) -> dict:
    """
    Process subscriptions scheduled for cancellation at period end.
    
    This task checks for subscriptions where:
    - cancel_at_period_end is True
    - current_period_end has passed
    
    For each, it:
    - Downgrades to the scheduled tier (usually CORE)
    - Clears cancellation flags
    - Sends notification email
    
    Should run daily (ideally at midnight or early morning).
    """
    from app.models.sku import TenantSKU, SKUTier
    from app.models.organization import Organization
    from app.models.user import User
    from app.services.billing_email_service import BillingEmailService
    
    now = datetime.utcnow()
    today = date.today()
    
    # Find subscriptions scheduled for cancellation where period has ended
    result = await db.execute(
        select(TenantSKU)
        .where(TenantSKU.is_active == True)
        .where(TenantSKU.cancel_at_period_end == True)
        .where(TenantSKU.current_period_end <= today)
    )
    
    scheduled_cancellations = result.scalars().all()
    
    processed_count = 0
    errors = []
    
    for sku in scheduled_cancellations:
        try:
            previous_tier = sku.tier.value
            target_tier = sku.scheduled_downgrade_tier or SKUTier.CORE
            
            # Downgrade to target tier
            sku.tier = target_tier
            sku.intelligence_addon = None  # Remove intelligence addon
            
            # Clear cancellation flags
            sku.cancel_at_period_end = False
            sku.scheduled_downgrade_tier = None
            
            # Update period (start a new free period)
            sku.current_period_start = today
            sku.current_period_end = today + timedelta(days=30)  # Monthly free tier
            
            # Record the downgrade
            sku.upgraded_from = previous_tier
            sku.upgraded_at = now
            sku.notes = f"Downgraded from {previous_tier} to {target_tier.value} on {today.strftime('%Y-%m-%d')} (scheduled cancellation)"
            
            # Send downgrade notification email
            try:
                org_result = await db.execute(
                    select(Organization).where(Organization.id == sku.organization_id)
                )
                org = org_result.scalar_one_or_none()
                
                admin_result = await db.execute(
                    select(User)
                    .where(User.organization_id == sku.organization_id)
                    .where(User.is_active == True)
                    .order_by(User.created_at)
                    .limit(1)
                )
                admin_user = admin_result.scalar_one_or_none()
                
                if admin_user and admin_user.email and org:
                    billing_email_service = BillingEmailService(db)
                    await billing_email_service.send_trial_ended_downgrade(
                        email=admin_user.email,
                        organization_name=org.name,
                        previous_tier=previous_tier,
                    )
                    logger.info(f"Sent downgrade notification to {admin_user.email}")
            except Exception as email_error:
                logger.error(f"Failed to send downgrade email for org {sku.organization_id}: {email_error}")
            
            processed_count += 1
            logger.info(f"Processed scheduled cancellation for org {sku.organization_id}: {previous_tier} -> {target_tier.value}")
            
        except Exception as e:
            logger.error(f"Error processing cancellation for org {sku.organization_id}: {e}")
            errors.append({
                "organization_id": str(sku.organization_id),
                "error": str(e),
            })
    
    await db.commit()
    
    return {
        "scheduled_count": len(scheduled_cancellations),
        "processed_count": processed_count,
        "errors": errors if errors else None,
    }


# ===========================================
# SCHEDULED TASK: PROCESS TRIAL EXPIRATIONS
# ===========================================

async def process_trial_expirations(db: AsyncSession) -> dict:
    """
    Process expired trials and downgrade to Core.
    
    Checks for subscriptions where trial_ends_at has passed.
    
    Should run daily.
    """
    from app.models.sku import TenantSKU, SKUTier
    from app.models.organization import Organization
    from app.models.user import User
    from app.services.billing_email_service import BillingEmailService
    
    now = datetime.utcnow()
    today = date.today()
    
    # Find expired trials (trial_ends_at in the past, still on paid tier)
    result = await db.execute(
        select(TenantSKU)
        .where(TenantSKU.is_active == True)
        .where(TenantSKU.trial_ends_at != None)
        .where(TenantSKU.trial_ends_at <= now)
        .where(TenantSKU.tier != SKUTier.CORE)
    )
    
    expired_trials = result.scalars().all()
    
    processed_count = 0
    errors = []
    
    for sku in expired_trials:
        try:
            previous_tier = sku.tier.value
            
            # Downgrade to Core
            sku.tier = SKUTier.CORE
            sku.intelligence_addon = None
            sku.trial_ends_at = None  # Clear trial
            
            # Update period
            sku.current_period_start = today
            sku.current_period_end = today + timedelta(days=30)
            
            # Record the downgrade
            sku.upgraded_from = previous_tier
            sku.upgraded_at = now
            sku.notes = f"Trial expired. Downgraded from {previous_tier} to Core on {today.strftime('%Y-%m-%d')}"
            
            # Send notification email
            try:
                org_result = await db.execute(
                    select(Organization).where(Organization.id == sku.organization_id)
                )
                org = org_result.scalar_one_or_none()
                
                admin_result = await db.execute(
                    select(User)
                    .where(User.organization_id == sku.organization_id)
                    .where(User.is_active == True)
                    .order_by(User.created_at)
                    .limit(1)
                )
                admin_user = admin_result.scalar_one_or_none()
                
                if admin_user and admin_user.email and org:
                    billing_email_service = BillingEmailService(db)
                    await billing_email_service.send_trial_ended_downgrade(
                        email=admin_user.email,
                        organization_name=org.name,
                        previous_tier=previous_tier,
                    )
            except Exception as email_error:
                logger.error(f"Failed to send trial expiration email for org {sku.organization_id}: {email_error}")
            
            processed_count += 1
            logger.info(f"Processed trial expiration for org {sku.organization_id}: {previous_tier} -> Core")
            
        except Exception as e:
            logger.error(f"Error processing trial expiration for org {sku.organization_id}: {e}")
            errors.append({
                "organization_id": str(sku.organization_id),
                "error": str(e),
            })
    
    await db.commit()
    
    return {
        "expired_count": len(expired_trials),
        "processed_count": processed_count,
        "errors": errors if errors else None,
    }


# ===========================================
# SCHEDULED TASK: AUTO-RESUME PAUSED SUBSCRIPTIONS
# ===========================================

async def auto_resume_paused_subscriptions(db: AsyncSession) -> dict:
    """
    Automatically resume subscriptions that have reached their pause_until date.
    Should run hourly.
    """
    from app.models.sku import TenantSKU
    from app.services.advanced_billing_service import SubscriptionPauseService
    
    now = datetime.utcnow()
    
    # Find paused subscriptions that should be resumed
    result = await db.execute(
        select(TenantSKU)
        .where(TenantSKU.paused_at.isnot(None))
        .where(TenantSKU.pause_until.isnot(None))
        .where(TenantSKU.pause_until <= now)
    )
    
    paused_skus = result.scalars().all()
    resumed_count = 0
    errors = []
    
    pause_service = SubscriptionPauseService(db)
    
    for sku in paused_skus:
        try:
            result = await pause_service.resume_subscription(sku.organization_id)
            if result.get("success"):
                resumed_count += 1
                logger.info(f"Auto-resumed subscription for org {sku.organization_id}")
            else:
                errors.append({
                    "organization_id": str(sku.organization_id),
                    "error": result.get("error", "Unknown error"),
                })
        except Exception as e:
            logger.error(f"Error auto-resuming subscription for org {sku.organization_id}: {e}")
            errors.append({
                "organization_id": str(sku.organization_id),
                "error": str(e),
            })
    
    await db.commit()
    
    logger.info(f"Auto-resume task: {resumed_count} subscriptions resumed out of {len(paused_skus)}")
    return {
        "paused_found": len(paused_skus),
        "resumed_count": resumed_count,
        "errors": errors if errors else None,
    }


# ===========================================
# SCHEDULED TASK: UPDATE EXCHANGE RATES
# ===========================================

async def update_exchange_rates(db: AsyncSession) -> dict:
    """
    Update currency exchange rates from external API.
    Should run daily (or more frequently for volatile markets).
    """
    from app.services.advanced_billing_service import CurrencyService
    
    currency_service = CurrencyService(db)
    
    # In production, you'd fetch from a real exchange rate API like:
    # - Open Exchange Rates (openexchangerates.org)
    # - Fixer.io
    # - ExchangeRate-API
    
    # For now, we'll use reasonable Nigerian market rates
    # These should be replaced with live API calls
    default_rates = {
        "USD": 1550.00,  # 1 USD = 1550 NGN
        "EUR": 1700.00,  # 1 EUR = 1700 NGN
        "GBP": 1950.00,  # 1 GBP = 1950 NGN
    }
    
    updated_count = 0
    errors = []
    
    for currency, rate in default_rates.items():
        try:
            # Try to update or create exchange rate
            await currency_service.update_exchange_rate(
                from_currency="NGN",
                to_currency=currency,
                rate=1 / rate,  # NGN to foreign currency
            )
            await currency_service.update_exchange_rate(
                from_currency=currency,
                to_currency="NGN",
                rate=rate,  # Foreign currency to NGN
            )
            updated_count += 2
        except Exception as e:
            logger.error(f"Error updating exchange rate for {currency}: {e}")
            errors.append({
                "currency": currency,
                "error": str(e),
            })
    
    await db.commit()
    
    logger.info(f"Exchange rates updated: {updated_count} rates processed")
    return {
        "rates_updated": updated_count,
        "errors": errors if errors else None,
    }


# ===========================================
# SCHEDULED TASK: PROCESS SCHEDULED USAGE REPORTS
# ===========================================

async def process_scheduled_usage_reports(db: AsyncSession) -> dict:
    """
    Generate and deliver scheduled usage reports to organizations.
    Should run daily.
    """
    from app.models.sku import ScheduledUsageReport
    from app.services.advanced_billing_service import UsageReportService
    from app.services.billing_email_service import BillingEmailService
    
    today = date.today()
    now = datetime.utcnow()
    
    # Find scheduled reports due today
    result = await db.execute(
        select(ScheduledUsageReport)
        .where(ScheduledUsageReport.is_active == True)
        .where(ScheduledUsageReport.next_run_at <= now)
    )
    
    scheduled_reports = result.scalars().all()
    generated_count = 0
    errors = []
    
    report_service = UsageReportService(db)
    
    for report in scheduled_reports:
        try:
            # Calculate date range based on frequency
            if report.frequency == "weekly":
                start_date = today - timedelta(days=7)
                end_date = today
            elif report.frequency == "monthly":
                start_date = today - timedelta(days=30)
                end_date = today
            elif report.frequency == "quarterly":
                start_date = today - timedelta(days=90)
                end_date = today
            else:
                continue
            
            # Generate the report
            if report.format == "csv":
                filename, content = await report_service.generate_usage_report_csv(
                    report.organization_id,
                    start_date,
                    end_date,
                )
            elif report.format == "pdf":
                filename, content = await report_service.generate_usage_report_pdf(
                    report.organization_id,
                    start_date,
                    end_date,
                )
            else:
                continue
            
            # Save report history
            await report_service.save_report_history(
                organization_id=report.organization_id,
                report_type=report.report_type,
                format=report.format,
                period_start=start_date,
                period_end=end_date,
                file_size=len(content),
            )
            
            # Update next run time
            if report.frequency == "weekly":
                report.next_run_at = now + timedelta(days=7)
            elif report.frequency == "monthly":
                report.next_run_at = now + timedelta(days=30)
            elif report.frequency == "quarterly":
                report.next_run_at = now + timedelta(days=90)
            
            generated_count += 1
            logger.info(f"Generated scheduled usage report for org {report.organization_id}")
            
        except Exception as e:
            logger.error(f"Error generating scheduled report for org {report.organization_id}: {e}")
            errors.append({
                "organization_id": str(report.organization_id),
                "error": str(e),
            })
    
    await db.commit()
    
    logger.info(f"Scheduled reports: {generated_count} generated out of {len(scheduled_reports)}")
    return {
        "reports_due": len(scheduled_reports),
        "generated_count": generated_count,
        "errors": errors if errors else None,
    }


# ===========================================
# SCHEDULED TASK: USAGE ALERT CHECK
# ===========================================

async def check_usage_alerts(db: AsyncSession) -> dict:
    """
    Check usage across all organizations and send alerts.
    
    This task:
    - Gets all active organizations
    - Checks usage against limits for each
    - Sends notifications for thresholds (80%, 90%, 100%)
    
    Should run every 6 hours or daily.
    """
    from app.models.sku import TenantSKU
    from app.services.usage_alert_service import UsageAlertService
    
    # Get all active subscriptions
    result = await db.execute(
        select(TenantSKU)
        .where(TenantSKU.is_active == True)
    )
    tenant_skus = result.scalars().all()
    
    total_alerts = 0
    organizations_checked = 0
    errors = []
    
    alert_service = UsageAlertService(db)
    
    for sku in tenant_skus:
        try:
            organizations_checked += 1
            
            # Check for usage alerts
            alerts = await alert_service.check_usage_alerts(
                organization_id=sku.organization_id,
            )
            
            if alerts:
                # Send notifications for alerts
                from app.services.usage_alert_service import AlertChannel
                notify_result = await alert_service.notify_alerts(
                    alerts=alerts,
                    channels=[AlertChannel.EMAIL, AlertChannel.IN_APP],
                )
                
                total_alerts += len(alerts)
                logger.info(f"Generated {len(alerts)} usage alerts for org {sku.organization_id}, notified: {notify_result}")
            
        except Exception as e:
            logger.error(f"Error checking usage alerts for org {sku.organization_id}: {e}")
            errors.append({
                "organization_id": str(sku.organization_id),
                "error": str(e),
            })
    
    return {
        "organizations_checked": organizations_checked,
        "total_alerts_generated": total_alerts,
        "errors": errors if errors else None,
    }


# ===========================================
# SCHEDULED TASK: DATA RETENTION CLEANUP (Issue #57)
# ===========================================

async def cleanup_expired_usage_data(db: AsyncSession) -> dict:
    """
    Clean up expired usage data based on retention policy (Issue #57).
    
    This task enforces data retention limits on:
    - usage_records: Billing period usage summaries
    - usage_events: Granular usage events (shorter retention)
    - feature_access_logs: Feature gate access logs
    - payment_transactions: Kept longer for compliance (archived, not deleted)
    
    Should run daily at 3 AM (off-peak hours).
    """
    from app.config import settings
    from app.models.sku import UsageRecord, UsageEvent, FeatureAccessLog, PaymentTransaction
    from sqlalchemy import delete
    
    if not settings.enable_data_retention_cleanup:
        logger.info("Data retention cleanup is disabled via ENABLE_DATA_RETENTION_CLEANUP")
        return {"status": "disabled"}
    
    today = date.today()
    results = {
        "usage_records_deleted": 0,
        "usage_events_deleted": 0,
        "feature_access_logs_deleted": 0,
        "payment_transactions_archived": 0,
        "errors": [],
    }
    
    # 1. Clean up old usage_records
    try:
        cutoff_date = today - timedelta(days=settings.usage_records_retention_days)
        
        # Count records to be deleted
        count_result = await db.execute(
            select(func.count(UsageRecord.id))
            .where(UsageRecord.period_end < cutoff_date)
        )
        records_to_delete = count_result.scalar() or 0
        
        if records_to_delete > 0:
            # Delete in batches to avoid lock contention
            batch_size = 1000
            total_deleted = 0
            
            while total_deleted < records_to_delete:
                # Get IDs to delete
                ids_result = await db.execute(
                    select(UsageRecord.id)
                    .where(UsageRecord.period_end < cutoff_date)
                    .limit(batch_size)
                )
                ids_to_delete = [row[0] for row in ids_result.fetchall()]
                
                if not ids_to_delete:
                    break
                
                await db.execute(
                    delete(UsageRecord).where(UsageRecord.id.in_(ids_to_delete))
                )
                await db.commit()
                total_deleted += len(ids_to_delete)
                
            results["usage_records_deleted"] = total_deleted
            logger.info(f"Deleted {total_deleted} expired usage_records (older than {cutoff_date})")
    
    except Exception as e:
        logger.error(f"Error cleaning up usage_records: {e}")
        results["errors"].append(f"usage_records: {str(e)}")
    
    # 2. Clean up old usage_events (shorter retention)
    try:
        cutoff_date = today - timedelta(days=settings.usage_events_retention_days)
        
        count_result = await db.execute(
            select(func.count(UsageEvent.id))
            .where(UsageEvent.created_at < datetime.combine(cutoff_date, datetime.min.time()))
        )
        events_to_delete = count_result.scalar() or 0
        
        if events_to_delete > 0:
            batch_size = 5000  # Larger batches for events
            total_deleted = 0
            
            while total_deleted < events_to_delete:
                ids_result = await db.execute(
                    select(UsageEvent.id)
                    .where(UsageEvent.created_at < datetime.combine(cutoff_date, datetime.min.time()))
                    .limit(batch_size)
                )
                ids_to_delete = [row[0] for row in ids_result.fetchall()]
                
                if not ids_to_delete:
                    break
                
                await db.execute(
                    delete(UsageEvent).where(UsageEvent.id.in_(ids_to_delete))
                )
                await db.commit()
                total_deleted += len(ids_to_delete)
                
            results["usage_events_deleted"] = total_deleted
            logger.info(f"Deleted {total_deleted} expired usage_events (older than {cutoff_date})")
    
    except Exception as e:
        logger.error(f"Error cleaning up usage_events: {e}")
        results["errors"].append(f"usage_events: {str(e)}")
    
    # 3. Clean up old feature_access_logs
    try:
        cutoff_date = today - timedelta(days=settings.feature_access_logs_retention_days)
        
        count_result = await db.execute(
            select(func.count(FeatureAccessLog.id))
            .where(FeatureAccessLog.created_at < datetime.combine(cutoff_date, datetime.min.time()))
        )
        logs_to_delete = count_result.scalar() or 0
        
        if logs_to_delete > 0:
            batch_size = 5000
            total_deleted = 0
            
            while total_deleted < logs_to_delete:
                ids_result = await db.execute(
                    select(FeatureAccessLog.id)
                    .where(FeatureAccessLog.created_at < datetime.combine(cutoff_date, datetime.min.time()))
                    .limit(batch_size)
                )
                ids_to_delete = [row[0] for row in ids_result.fetchall()]
                
                if not ids_to_delete:
                    break
                
                await db.execute(
                    delete(FeatureAccessLog).where(FeatureAccessLog.id.in_(ids_to_delete))
                )
                await db.commit()
                total_deleted += len(ids_to_delete)
                
            results["feature_access_logs_deleted"] = total_deleted
            logger.info(f"Deleted {total_deleted} expired feature_access_logs (older than {cutoff_date})")
    
    except Exception as e:
        logger.error(f"Error cleaning up feature_access_logs: {e}")
        results["errors"].append(f"feature_access_logs: {str(e)}")
    
    # 4. Archive old payment_transactions (soft delete / archive, not hard delete for compliance)
    # Payment records are kept for 7 years per Nigerian tax law, but can be archived
    try:
        cutoff_date = today - timedelta(days=settings.payment_transactions_retention_days)
        
        # Only archive fully processed transactions that are very old
        count_result = await db.execute(
            select(func.count(PaymentTransaction.id))
            .where(PaymentTransaction.created_at < datetime.combine(cutoff_date, datetime.min.time()))
            .where(PaymentTransaction.status.in_(["success", "refunded", "cancelled"]))
            .where(PaymentTransaction.is_archived == False)  # Not already archived
        )
        to_archive = count_result.scalar() or 0
        
        if to_archive > 0:
            # Archive records (set is_archived flag) instead of deleting
            from sqlalchemy import update
            
            await db.execute(
                update(PaymentTransaction)
                .where(PaymentTransaction.created_at < datetime.combine(cutoff_date, datetime.min.time()))
                .where(PaymentTransaction.status.in_(["success", "refunded", "cancelled"]))
                .where(PaymentTransaction.is_archived == False)
                .values(is_archived=True, archived_at=datetime.utcnow())
            )
            await db.commit()
            
            results["payment_transactions_archived"] = to_archive
            logger.info(f"Archived {to_archive} old payment_transactions (older than {cutoff_date})")
    
    except Exception as e:
        # If is_archived column doesn't exist, log and continue
        logger.warning(f"Could not archive payment_transactions (column may not exist): {e}")
        results["errors"].append(f"payment_transactions: {str(e)}")
    
    # Summary
    total_deleted = (
        results["usage_records_deleted"] + 
        results["usage_events_deleted"] + 
        results["feature_access_logs_deleted"]
    )
    
    logger.info(
        f"Data retention cleanup complete: {total_deleted} records deleted, "
        f"{results['payment_transactions_archived']} transactions archived"
    )
    
    return results


# ===========================================
# TASK RUNNER (Development)
# ===========================================

class TaskRunner:
    """
    Simple task runner for development.
    In production, replace with Celery.
    """
    
    def __init__(self, db_session_factory):
        self.db_session_factory = db_session_factory
        self._running = False
    
    async def run_task(self, task_func, *args, **kwargs):
        """Run a single task with a new database session."""
        async with self.db_session_factory() as db:
            try:
                result = await task_func(db, *args, **kwargs)
                logger.info(f"Task {task_func.__name__} completed: {result}")
                return result
            except Exception as e:
                logger.error(f"Task {task_func.__name__} failed: {e}")
                raise
    
    async def run_scheduled_tasks(self):
        """Run all scheduled tasks (for development/testing)."""
        results = {}
        
        tasks = [
            ("check_overdue_invoices", check_overdue_invoices),
            ("check_low_stock_items", check_low_stock_items),
            ("check_vat_filing_deadlines", check_vat_filing_deadlines),
            ("sync_pending_nrs_invoices", sync_pending_nrs_invoices),
            ("process_scheduled_cancellations", process_scheduled_cancellations),
            ("process_trial_expirations", process_trial_expirations),
            ("check_usage_alerts", check_usage_alerts),
            # Billing features #30-36 tasks
            ("auto_resume_paused_subscriptions", auto_resume_paused_subscriptions),
            ("update_exchange_rates", update_exchange_rates),
            ("process_scheduled_usage_reports", process_scheduled_usage_reports),
            # Issue #57: Data retention cleanup
            ("cleanup_expired_usage_data", cleanup_expired_usage_data),
        ]
        
        for name, task_func in tasks:
            try:
                result = await self.run_task(task_func)
                results[name] = {"status": "success", "result": result}
            except Exception as e:
                results[name] = {"status": "error", "error": str(e)}
        
        return results
