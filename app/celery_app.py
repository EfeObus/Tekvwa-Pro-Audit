"""
Tekvwa Pro Audit - Celery Configuration

Celery configuration for background task processing.
Uses Redis as the message broker and result backend.
"""

from celery import Celery
from celery.schedules import crontab

from app.config import settings


# Get Redis URL from settings or use default
redis_url = getattr(settings, 'redis_url', 'redis://localhost:6379/0')

# Create Celery app
celery_app = Celery(
    'tekvwa_pro_audit',
    broker=redis_url,
    backend=redis_url,
    include=['app.tasks.celery_tasks'],
)

# Celery configuration
celery_app.conf.update(
    # Serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    
    # Timezone
    timezone='Africa/Lagos',
    enable_utc=True,
    
    # Task execution settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=300,  # 5 minutes
    task_soft_time_limit=240,  # 4 minutes (warning before hard limit)
    
    # Worker settings
    worker_prefetch_multiplier=1,
    worker_concurrency=4,
    
    # Result backend settings
    result_expires=86400,  # 24 hours
    
    # Retry settings
    task_default_retry_delay=60,  # 1 minute
    task_max_retries=3,
    
    # Beat schedule for periodic tasks
    beat_schedule={
        # Check for overdue invoices every day at 8 AM
        'check-overdue-invoices': {
            'task': 'app.tasks.celery_tasks.check_overdue_invoices_task',
            'schedule': crontab(hour=8, minute=0),
        },
        
        # Check low stock items every day at 9 AM
        'check-low-stock': {
            'task': 'app.tasks.celery_tasks.check_low_stock_task',
            'schedule': crontab(hour=9, minute=0),
        },
        
        # VAT filing reminders on the 15th and 19th of each month
        'vat-filing-reminder-15th': {
            'task': 'app.tasks.celery_tasks.check_vat_deadlines_task',
            'schedule': crontab(day_of_month=15, hour=9, minute=0),
        },
        'vat-filing-reminder-19th': {
            'task': 'app.tasks.celery_tasks.check_vat_deadlines_task',
            'schedule': crontab(day_of_month=19, hour=9, minute=0),
        },
        
        # PAYE reminders on the 5th and 8th of each month
        'paye-reminder-5th': {
            'task': 'app.tasks.celery_tasks.check_paye_deadlines_task',
            'schedule': crontab(day_of_month=5, hour=9, minute=0),
        },
        'paye-reminder-8th': {
            'task': 'app.tasks.celery_tasks.check_paye_deadlines_task',
            'schedule': crontab(day_of_month=8, hour=9, minute=0),
        },
        
        # Retry failed NRS submissions every hour
        'retry-nrs-submissions': {
            'task': 'app.tasks.celery_tasks.retry_failed_nrs_submissions_task',
            'schedule': crontab(minute=0),  # Every hour
        },
        
        # Clean up old notifications weekly
        'cleanup-old-notifications': {
            'task': 'app.tasks.celery_tasks.cleanup_notifications_task',
            'schedule': crontab(day_of_week=0, hour=2, minute=0),  # Sunday 2 AM
        },
        
        # Archive old audit logs monthly
        'archive-audit-logs': {
            'task': 'app.tasks.celery_tasks.archive_audit_logs_task',
            'schedule': crontab(day_of_month=1, hour=3, minute=0),  # 1st of month 3 AM
        },
        
        # Generate monthly tax summary reports
        'monthly-tax-summary': {
            'task': 'app.tasks.celery_tasks.generate_monthly_tax_summary_task',
            'schedule': crontab(day_of_month=1, hour=6, minute=0),  # 1st of month 6 AM
        },
        
        # ===========================================
        # BILLING & SUBSCRIPTION TASKS
        # ===========================================
        
        # Check for expired trials every day at 7 AM
        'check-trial-expirations': {
            'task': 'app.tasks.celery_tasks.check_trial_expirations_task',
            'schedule': crontab(hour=7, minute=0),
        },
        
        # Process subscription renewals daily at 6 AM
        'process-subscription-renewals': {
            'task': 'app.tasks.celery_tasks.process_subscription_renewals_task',
            'schedule': crontab(hour=6, minute=0),
        },
        
        # Retry failed payments every 6 hours
        'retry-failed-payments': {
            'task': 'app.tasks.celery_tasks.retry_failed_payments_task',
            'schedule': crontab(hour='*/6', minute=30),
        },
        
        # Send payment reminders daily at 9 AM
        'send-payment-reminders': {
            'task': 'app.tasks.celery_tasks.send_payment_reminders_task',
            'schedule': crontab(hour=9, minute=0),
        },
        
        # Process scheduled cancellations/downgrades daily at 12:05 AM
        'process-scheduled-cancellations': {
            'task': 'app.tasks.celery_tasks.process_scheduled_cancellations_task',
            'schedule': crontab(hour=0, minute=5),
        },
        
        # Check usage alerts every 6 hours
        'check-usage-alerts': {
            'task': 'app.tasks.celery_tasks.check_usage_alerts_task',
            'schedule': crontab(hour='*/6', minute=15),
        },
        
        # ===========================================
        # BILLING FEATURES #30-36 TASKS
        # ===========================================
        
        # #32: Auto-resume paused subscriptions hourly at :45
        'auto-resume-paused-subscriptions': {
            'task': 'app.tasks.celery_tasks.auto_resume_paused_subscriptions_task',
            'schedule': crontab(minute=45),  # Every hour at :45
        },
        
        # #36: Update exchange rates daily at 6:30 AM (before business hours)
        'update-exchange-rates': {
            'task': 'app.tasks.celery_tasks.update_exchange_rates_task',
            'schedule': crontab(hour=6, minute=30),
        },
        
        # #30: Process scheduled usage reports daily at 7:30 AM
        'process-scheduled-usage-reports': {
            'task': 'app.tasks.celery_tasks.process_scheduled_usage_reports_task',
            'schedule': crontab(hour=7, minute=30),
        },
    },
)


# Task routing (optional - for scaling specific task types)
celery_app.conf.task_routes = {
    'app.tasks.celery_tasks.send_email_*': {'queue': 'email'},
    'app.tasks.celery_tasks.nrs_*': {'queue': 'nrs'},
    'app.tasks.celery_tasks.check_trial_*': {'queue': 'billing'},
    'app.tasks.celery_tasks.process_subscription_*': {'queue': 'billing'},
    'app.tasks.celery_tasks.retry_failed_*': {'queue': 'billing'},
    'app.tasks.celery_tasks.send_payment_*': {'queue': 'billing'},
    # Billing features #30-36 routing
    'app.tasks.celery_tasks.auto_resume_paused_*': {'queue': 'billing'},
    'app.tasks.celery_tasks.update_exchange_*': {'queue': 'billing'},
    'app.tasks.celery_tasks.process_scheduled_usage_*': {'queue': 'billing'},
    'app.tasks.celery_tasks.*': {'queue': 'default'},
}
