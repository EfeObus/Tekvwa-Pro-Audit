"""
Tekvwa Pro Audit - Billing Email Service

Handles all billing-related email notifications.
Supports transactional emails for:
- Payment confirmations
- Invoice notifications
- Trial expiry warnings
- Subscription renewals
- Dunning escalations
- Account status changes
"""

import logging
from datetime import datetime, date
from typing import Any, Dict, List, Optional
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.email_service import EmailService, EmailMessage
from app.config import settings

logger = logging.getLogger(__name__)


class BillingEmailService:
    """Service for sending billing-related transactional emails."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.email_service = EmailService()
        self.company_name = "Tekvwa Pro Audit"
        self.base_url = getattr(settings, 'base_url', 'http://localhost:5120')
        self.support_email = getattr(settings, 'support_email', 'info@tekvwa.org')
        self.billing_email = getattr(settings, 'billing_email', 'info@tekvwa.org')
    
    def _format_naira(self, amount: int) -> str:
        """Format amount as Nigerian Naira."""
        return f"₦{amount:,}"
    
    def _get_base_html_template(self, content: str) -> str:
        """Get base HTML email template with consistent styling."""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.company_name}</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; background-color: #f4f4f4; }}
        .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; padding: 20px; }}
        .header {{ background: #1a365d; color: white; padding: 20px; text-align: center; }}
        .header h1 {{ margin: 0; font-size: 24px; }}
        .content {{ padding: 30px 20px; }}
        .highlight {{ background: #f0f7ff; border-left: 4px solid #1a365d; padding: 15px; margin: 20px 0; }}
        .amount {{ font-size: 28px; font-weight: bold; color: #1a365d; }}
        .button {{ display: inline-block; background: #1a365d; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; margin: 20px 0; }}
        .button:hover {{ background: #2d4a7c; }}
        .warning {{ background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0; }}
        .danger {{ background: #f8d7da; border-left: 4px solid #dc3545; padding: 15px; margin: 20px 0; }}
        .success {{ background: #d4edda; border-left: 4px solid #28a745; padding: 15px; margin: 20px 0; }}
        .footer {{ background: #f8f9fa; padding: 20px; text-align: center; font-size: 12px; color: #666; }}
        .footer a {{ color: #1a365d; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #f8f9fa; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{self.company_name}</h1>
        </div>
        <div class="content">
            {content}
        </div>
        <div class="footer">
            <p>&copy; {datetime.now().year} {self.company_name}. All rights reserved.</p>
            <p>
                <a href="mailto:{self.support_email}">Contact Support</a> |
                <a href="mailto:{self.billing_email}">Billing Inquiries</a>
            </p>
        </div>
    </div>
</body>
</html>
"""
    
    # ===========================================
    # PAYMENT CONFIRMATION EMAILS
    # ===========================================
    
    async def send_payment_success(
        self,
        email: str,
        organization_name: str,
        tier: str,
        amount_naira: int,
        reference: str,
        payment_date: datetime,
        next_billing_date: Optional[date] = None,
    ) -> bool:
        """Send payment success confirmation email."""
        subject = f"Payment Confirmed - {self.company_name}"
        
        content = f"""
        <h2>Payment Successful!</h2>
        
        <p>Dear {organization_name} Team,</p>
        
        <p>Thank you for your payment. Your subscription has been activated.</p>
        
        <div class="success">
            <p class="amount">{self._format_naira(amount_naira)}</p>
            <p>Payment Reference: <strong>{reference}</strong></p>
        </div>
        
        <table>
            <tr>
                <th>Details</th>
                <th>Information</th>
            </tr>
            <tr>
                <td>Organization</td>
                <td>{organization_name}</td>
            </tr>
            <tr>
                <td>Plan</td>
                <td>Pro Audit {tier.title()}</td>
            </tr>
            <tr>
                <td>Amount Paid</td>
                <td>{self._format_naira(amount_naira)}</td>
            </tr>
            <tr>
                <td>Payment Date</td>
                <td>{payment_date.strftime('%B %d, %Y at %I:%M %p')}</td>
            </tr>
            {"<tr><td>Next Billing Date</td><td>" + next_billing_date.strftime('%B %d, %Y') + "</td></tr>" if next_billing_date else ""}
        </table>
        
        <p>
            <a href="/dashboard" class="button">Go to Dashboard</a>
        </p>
        
        <p>If you have any questions about your payment, please contact our billing team.</p>
        """
        
        body_text = f"""
Payment Successful!

Dear {organization_name} Team,

Thank you for your payment of {self._format_naira(amount_naira)}.

Payment Reference: {reference}
Plan: Pro Audit {tier.title()}
Payment Date: {payment_date.strftime('%B %d, %Y')}

Your subscription is now active.

Best regards,
{self.company_name} Team
"""
        
        return await self.email_service.send_email(EmailMessage(
            to=[email],
            subject=subject,
            body_text=body_text,
            body_html=self._get_base_html_template(content),
        ))
    
    async def send_payment_failed(
        self,
        email: str,
        organization_name: str,
        amount_naira: int,
        reason: str,
        retry_url: Optional[str] = None,
    ) -> bool:
        """Send payment failure notification email."""
        subject = f"Payment Failed - Action Required - {self.company_name}"
        
        content = f"""
        <h2>Payment Failed</h2>
        
        <p>Dear {organization_name} Team,</p>
        
        <p>We were unable to process your payment. Please update your payment method to continue your subscription.</p>
        
        <div class="danger">
            <p><strong>Amount:</strong> {self._format_naira(amount_naira)}</p>
            <p><strong>Reason:</strong> {reason}</p>
        </div>
        
        <p>
            <a href="{retry_url or '/billing'}" class="button">Update Payment Method</a>
        </p>
        
        <p>If you believe this is an error, please contact your bank or our support team.</p>
        """
        
        body_text = f"""
Payment Failed - Action Required

Dear {organization_name} Team,

We were unable to process your payment of {self._format_naira(amount_naira)}.

Reason: {reason}

Please update your payment method to continue your subscription.

Visit: {retry_url or '/billing'}

Best regards,
{self.company_name} Team
"""
        
        return await self.email_service.send_email(EmailMessage(
            to=[email],
            subject=subject,
            body_text=body_text,
            body_html=self._get_base_html_template(content),
        ))
    
    # ===========================================
    # TRIAL EMAILS
    # ===========================================
    
    async def send_trial_expiring_warning(
        self,
        email: str,
        organization_name: str,
        tier: str,
        days_remaining: int,
        trial_ends_at: datetime,
    ) -> bool:
        """Send trial expiration warning email."""
        subject = f"Your Trial Expires in {days_remaining} Day{'s' if days_remaining != 1 else ''} - {self.company_name}"
        
        content = f"""
        <h2>Your Trial is Ending Soon</h2>
        
        <p>Dear {organization_name} Team,</p>
        
        <p>Your free trial of Pro Audit {tier.title()} will expire in <strong>{days_remaining} day{'s' if days_remaining != 1 else ''}</strong>.</p>
        
        <div class="warning">
            <p><strong>Trial Ends:</strong> {trial_ends_at.strftime('%B %d, %Y')}</p>
            <p>Don't lose access to your accounting data!</p>
        </div>
        
        <p>To continue using all features, please subscribe before your trial ends.</p>
        
        <p>
            <a href="/pricing" class="button">Subscribe Now</a>
        </p>
        
        <p>If you have any questions, our team is here to help.</p>
        """
        
        body_text = f"""
Your Trial is Ending Soon

Dear {organization_name} Team,

Your free trial of Pro Audit {tier.title()} will expire in {days_remaining} day(s).

Trial Ends: {trial_ends_at.strftime('%B %d, %Y')}

To continue using all features, please subscribe before your trial ends.

Visit: /pricing

Best regards,
{self.company_name} Team
"""
        
        return await self.email_service.send_email(EmailMessage(
            to=[email],
            subject=subject,
            body_text=body_text,
            body_html=self._get_base_html_template(content),
        ))
    
    async def send_trial_expired(
        self,
        email: str,
        organization_name: str,
        tier: str,
        grace_period_days: int,
    ) -> bool:
        """Send trial expired notification with grace period info."""
        subject = f"Trial Expired - {grace_period_days} Day Grace Period - {self.company_name}"
        
        content = f"""
        <h2>Your Trial Has Expired</h2>
        
        <p>Dear {organization_name} Team,</p>
        
        <p>Your free trial of Pro Audit {tier.title()} has expired.</p>
        
        <div class="danger">
            <p><strong>Grace Period:</strong> {grace_period_days} days</p>
            <p>Your account will be downgraded after the grace period ends.</p>
        </div>
        
        <p>Subscribe now to maintain access to all {tier.title()} features and your data.</p>
        
        <p>
            <a href="/pricing" class="button">Subscribe Now</a>
        </p>
        """
        
        body_text = f"""
Your Trial Has Expired

Dear {organization_name} Team,

Your free trial of Pro Audit {tier.title()} has expired.

You have a {grace_period_days}-day grace period to subscribe.

After the grace period, your account will be downgraded.

Visit: /pricing

Best regards,
{self.company_name} Team
"""
        
        return await self.email_service.send_email(EmailMessage(
            to=[email],
            subject=subject,
            body_text=body_text,
            body_html=self._get_base_html_template(content),
        ))
    
    async def send_trial_ended_downgrade(
        self,
        email: str,
        organization_name: str,
        previous_tier: str,
    ) -> bool:
        """Send notification that trial ended and account was downgraded."""
        subject = f"Account Downgraded - Trial Ended - {self.company_name}"
        
        content = f"""
        <h2>Account Downgraded</h2>
        
        <p>Dear {organization_name} Team,</p>
        
        <p>Your trial period has ended and your account has been downgraded to the Core plan.</p>
        
        <div class="highlight">
            <p><strong>Previous Plan:</strong> Pro Audit {previous_tier.title()}</p>
            <p><strong>Current Plan:</strong> Pro Audit Core</p>
        </div>
        
        <p>Some features may no longer be available. You can upgrade at any time to restore full access.</p>
        
        <p>
            <a href="/pricing" class="button">Upgrade Now</a>
        </p>
        
        <p>Your data is safe and will be available when you upgrade.</p>
        """
        
        body_text = f"""
Account Downgraded

Dear {organization_name} Team,

Your trial period has ended and your account has been downgraded to the Core plan.

Previous Plan: Pro Audit {previous_tier.title()}
Current Plan: Pro Audit Core

You can upgrade at any time to restore full access.

Visit: /pricing

Best regards,
{self.company_name} Team
"""
        
        return await self.email_service.send_email(EmailMessage(
            to=[email],
            subject=subject,
            body_text=body_text,
            body_html=self._get_base_html_template(content),
        ))
    
    # ===========================================
    # RENEWAL EMAILS
    # ===========================================
    
    async def send_renewal_upcoming(
        self,
        email: str,
        organization_name: str,
        tier: str,
        amount_naira: int,
        renewal_date: date,
        days_until: int,
    ) -> bool:
        """Send upcoming renewal notice."""
        subject = f"Subscription Renewal in {days_until} Days - {self.company_name}"
        
        content = f"""
        <h2>Upcoming Subscription Renewal</h2>
        
        <p>Dear {organization_name} Team,</p>
        
        <p>Your Pro Audit {tier.title()} subscription will automatically renew in <strong>{days_until} days</strong>.</p>
        
        <div class="highlight">
            <p class="amount">{self._format_naira(amount_naira)}</p>
            <p><strong>Renewal Date:</strong> {renewal_date.strftime('%B %d, %Y')}</p>
        </div>
        
        <p>Your payment method on file will be charged automatically. No action is needed to continue your subscription.</p>
        
        <p>
            <a href="/billing" class="button">Manage Subscription</a>
        </p>
        """
        
        body_text = f"""
Upcoming Subscription Renewal

Dear {organization_name} Team,

Your Pro Audit {tier.title()} subscription will automatically renew in {days_until} days.

Amount: {self._format_naira(amount_naira)}
Renewal Date: {renewal_date.strftime('%B %d, %Y')}

Your payment method will be charged automatically.

Visit /billing to manage your subscription.

Best regards,
{self.company_name} Team
"""
        
        return await self.email_service.send_email(EmailMessage(
            to=[email],
            subject=subject,
            body_text=body_text,
            body_html=self._get_base_html_template(content),
        ))
    
    async def send_renewal_reminder(
        self,
        email: str,
        organization_name: str,
        tier: str,
        amount_naira: int,
        renewal_date: date,
    ) -> bool:
        """Send renewal reminder (3 days before)."""
        subject = f"Payment Reminder - Renewal in 3 Days - {self.company_name}"
        
        content = f"""
        <h2>Payment Reminder</h2>
        
        <p>Dear {organization_name} Team,</p>
        
        <p>This is a reminder that your subscription payment of <strong>{self._format_naira(amount_naira)}</strong> will be processed on <strong>{renewal_date.strftime('%B %d, %Y')}</strong>.</p>
        
        <div class="highlight">
            <p><strong>Plan:</strong> Pro Audit {tier.title()}</p>
            <p><strong>Amount:</strong> {self._format_naira(amount_naira)}</p>
        </div>
        
        <p>Please ensure your payment method is up to date to avoid service interruption.</p>
        
        <p>
            <a href="/billing" class="button">Review Payment Method</a>
        </p>
        """
        
        body_text = f"""
Payment Reminder

Dear {organization_name} Team,

Your subscription payment of {self._format_naira(amount_naira)} will be processed on {renewal_date.strftime('%B %d, %Y')}.

Plan: Pro Audit {tier.title()}

Please ensure your payment method is up to date.

Visit /billing to review.

Best regards,
{self.company_name} Team
"""
        
        return await self.email_service.send_email(EmailMessage(
            to=[email],
            subject=subject,
            body_text=body_text,
            body_html=self._get_base_html_template(content),
        ))
    
    async def send_renewal_final_notice(
        self,
        email: str,
        organization_name: str,
        tier: str,
        amount_naira: int,
        renewal_date: date,
    ) -> bool:
        """Send final renewal notice (1 day before)."""
        subject = f"Final Notice - Payment Tomorrow - {self.company_name}"
        
        content = f"""
        <h2>Final Payment Notice</h2>
        
        <p>Dear {organization_name} Team,</p>
        
        <p>Your subscription payment will be processed <strong>tomorrow</strong>.</p>
        
        <div class="warning">
            <p><strong>Plan:</strong> Pro Audit {tier.title()}</p>
            <p><strong>Amount:</strong> {self._format_naira(amount_naira)}</p>
            <p><strong>Charge Date:</strong> {renewal_date.strftime('%B %d, %Y')}</p>
        </div>
        
        <p>If you need to update your payment method, please do so now.</p>
        
        <p>
            <a href="/billing" class="button">Update Payment Method</a>
        </p>
        """
        
        body_text = f"""
Final Payment Notice

Dear {organization_name} Team,

Your subscription payment will be processed tomorrow.

Plan: Pro Audit {tier.title()}
Amount: {self._format_naira(amount_naira)}
Charge Date: {renewal_date.strftime('%B %d, %Y')}

Update your payment method now if needed: /billing

Best regards,
{self.company_name} Team
"""
        
        return await self.email_service.send_email(EmailMessage(
            to=[email],
            subject=subject,
            body_text=body_text,
            body_html=self._get_base_html_template(content),
        ))
    
    async def send_renewal_invoice(
        self,
        email: str,
        organization_name: str,
        tier: str,
        amount_naira: int,
        payment_url: str,
        due_date: datetime,
    ) -> bool:
        """Send renewal invoice with payment link."""
        subject = f"Invoice - Subscription Renewal - {self.company_name}"
        
        content = f"""
        <h2>Subscription Renewal Invoice</h2>
        
        <p>Dear {organization_name} Team,</p>
        
        <p>Please find your subscription renewal invoice below.</p>
        
        <div class="highlight">
            <p class="amount">{self._format_naira(amount_naira)}</p>
            <p><strong>Plan:</strong> Pro Audit {tier.title()}</p>
            <p><strong>Due Date:</strong> {due_date.strftime('%B %d, %Y')}</p>
        </div>
        
        <p>
            <a href="{payment_url}" class="button">Pay Now</a>
        </p>
        
        <p>Payment is due by {due_date.strftime('%B %d, %Y')}. Late payments may result in service interruption.</p>
        """
        
        body_text = f"""
Subscription Renewal Invoice

Dear {organization_name} Team,

Your subscription renewal invoice:

Plan: Pro Audit {tier.title()}
Amount: {self._format_naira(amount_naira)}
Due Date: {due_date.strftime('%B %d, %Y')}

Pay now: {payment_url}

Best regards,
{self.company_name} Team
"""
        
        return await self.email_service.send_email(EmailMessage(
            to=[email],
            subject=subject,
            body_text=body_text,
            body_html=self._get_base_html_template(content),
        ))
    
    # ===========================================
    # DUNNING EMAILS
    # ===========================================
    
    async def send_payment_retry_notice(
        self,
        email: str,
        organization_name: str,
        attempt_number: int,
        amount_naira: int,
        days_until_suspension: int,
    ) -> bool:
        """Send payment retry notification."""
        subject = f"Payment Retry Required - Attempt {attempt_number} - {self.company_name}"
        
        content = f"""
        <h2>Payment Retry Required</h2>
        
        <p>Dear {organization_name} Team,</p>
        
        <p>We attempted to process your payment but it was unsuccessful. This is retry attempt #{attempt_number}.</p>
        
        <div class="warning">
            <p><strong>Amount Due:</strong> {self._format_naira(amount_naira)}</p>
            <p><strong>Days Until Suspension:</strong> {days_until_suspension}</p>
        </div>
        
        <p>Please update your payment method to avoid service interruption.</p>
        
        <p>
            <a href="/billing" class="button">Update Payment Method</a>
        </p>
        """
        
        body_text = f"""
Payment Retry Required

Dear {organization_name} Team,

We attempted to process your payment but it was unsuccessful.
This is retry attempt #{attempt_number}.

Amount Due: {self._format_naira(amount_naira)}
Days Until Suspension: {days_until_suspension}

Please update your payment method: /billing

Best regards,
{self.company_name} Team
"""
        
        return await self.email_service.send_email(EmailMessage(
            to=[email],
            subject=subject,
            body_text=body_text,
            body_html=self._get_base_html_template(content),
        ))
    
    async def send_dunning_escalation(
        self,
        email: str,
        organization_name: str,
        dunning_level: str,
        amount_naira: int,
    ) -> bool:
        """Send dunning escalation notification."""
        urgency_map = {
            "warning": ("Action Required", "warning"),
            "urgent": ("Urgent: Immediate Action Required", "danger"),
            "final": ("Final Notice: Account Will Be Suspended", "danger"),
        }
        
        title, style = urgency_map.get(dunning_level, ("Payment Required", "warning"))
        subject = f"{title} - {self.company_name}"
        
        content = f"""
        <h2>{title}</h2>
        
        <p>Dear {organization_name} Team,</p>
        
        <p>Your account has an outstanding balance that requires immediate attention.</p>
        
        <div class="{style}">
            <p><strong>Amount Due:</strong> {self._format_naira(amount_naira)}</p>
            <p><strong>Status:</strong> {dunning_level.title()} Notice</p>
        </div>
        
        <p>Please make payment immediately to avoid service interruption.</p>
        
        <p>
            <a href="/billing" class="button">Pay Now</a>
        </p>
        
        <p>If you have already made payment, please disregard this notice.</p>
        """
        
        body_text = f"""
{title}

Dear {organization_name} Team,

Your account has an outstanding balance of {self._format_naira(amount_naira)}.

Status: {dunning_level.title()} Notice

Please make payment immediately: /billing

Best regards,
{self.company_name} Team
"""
        
        return await self.email_service.send_email(EmailMessage(
            to=[email],
            subject=subject,
            body_text=body_text,
            body_html=self._get_base_html_template(content),
        ))
    
    async def send_account_suspended(
        self,
        email: str,
        organization_name: str,
        reason: str,
        amount_naira: int,
    ) -> bool:
        """Send account suspension notification."""
        subject = f"Account Suspended - Payment Required - {self.company_name}"
        
        content = f"""
        <h2>Account Suspended</h2>
        
        <p>Dear {organization_name} Team,</p>
        
        <p>Your account has been suspended due to non-payment.</p>
        
        <div class="danger">
            <p><strong>Reason:</strong> {reason}</p>
            <p><strong>Amount Due:</strong> {self._format_naira(amount_naira)}</p>
        </div>
        
        <p>Your data is safe and will be available once payment is made. To reactivate your account, please pay the outstanding balance.</p>
        
        <p>
            <a href="/billing" class="button">Reactivate Account</a>
        </p>
        
        <p>If you have questions, please contact our billing team at {self.billing_email}.</p>
        """
        
        body_text = f"""
Account Suspended

Dear {organization_name} Team,

Your account has been suspended due to non-payment.

Reason: {reason}
Amount Due: {self._format_naira(amount_naira)}

Your data is safe. To reactivate, please pay the outstanding balance.

Visit: /billing

Contact billing: {self.billing_email}

Best regards,
{self.company_name} Team
"""
        
        return await self.email_service.send_email(EmailMessage(
            to=[email],
            subject=subject,
            body_text=body_text,
            body_html=self._get_base_html_template(content),
        ))
    
    async def send_account_reactivated(
        self,
        email: str,
        organization_name: str,
        tier: str,
    ) -> bool:
        """Send account reactivation confirmation."""
        subject = f"Account Reactivated - Welcome Back! - {self.company_name}"
        
        content = f"""
        <h2>Account Reactivated!</h2>
        
        <p>Dear {organization_name} Team,</p>
        
        <p>Great news! Your account has been reactivated.</p>
        
        <div class="success">
            <p><strong>Plan:</strong> Pro Audit {tier.title()}</p>
            <p>All your data and features are now available.</p>
        </div>
        
        <p>
            <a href="/dashboard" class="button">Go to Dashboard</a>
        </p>
        
        <p>Thank you for being a valued customer!</p>
        """
        
        body_text = f"""
Account Reactivated!

Dear {organization_name} Team,

Your account has been reactivated.

Plan: Pro Audit {tier.title()}

All your data and features are now available.

Visit: /dashboard

Best regards,
{self.company_name} Team
"""
        
        return await self.email_service.send_email(EmailMessage(
            to=[email],
            subject=subject,
            body_text=body_text,
            body_html=self._get_base_html_template(content),
        ))
    
    # ===========================================
    # INVOICE EMAILS
    # ===========================================
    
    async def send_invoice_created(
        self,
        email: str,
        organization_name: str,
        invoice_number: str,
        amount_naira: int,
        due_date: date,
        invoice_url: str,
        pdf_attachment: Optional[bytes] = None,
    ) -> bool:
        """Send invoice created notification with optional PDF attachment."""
        subject = f"Invoice {invoice_number} - {self.company_name}"
        
        content = f"""
        <h2>Invoice {invoice_number}</h2>
        
        <p>Dear {organization_name} Team,</p>
        
        <p>Please find your invoice attached.</p>
        
        <div class="highlight">
            <p><strong>Invoice Number:</strong> {invoice_number}</p>
            <p><strong>Amount:</strong> {self._format_naira(amount_naira)}</p>
            <p><strong>Due Date:</strong> {due_date.strftime('%B %d, %Y')}</p>
        </div>
        
        <p>
            <a href="{invoice_url}" class="button">View Invoice</a>
        </p>
        """
        
        body_text = f"""
Invoice {invoice_number}

Dear {organization_name} Team,

Invoice Number: {invoice_number}
Amount: {self._format_naira(amount_naira)}
Due Date: {due_date.strftime('%B %d, %Y')}

View invoice: {invoice_url}

Best regards,
{self.company_name} Team
"""
        
        attachments = None
        if pdf_attachment:
            attachments = [{
                "filename": f"{invoice_number}.pdf",
                "content": pdf_attachment,
                "content_type": "application/pdf",
            }]
        
        return await self.email_service.send_email(EmailMessage(
            to=[email],
            subject=subject,
            body_text=body_text,
            body_html=self._get_base_html_template(content),
            attachments=attachments,
        ))

    # ===========================================
    # USAGE ALERT EMAILS
    # ===========================================
    
    async def send_usage_alert(
        self,
        email: str,
        organization_name: str,
        metric_name: str,
        current_usage: int,
        limit: int,
        percentage: float,
        threshold: str,
        upgrade_url: str = "/settings?tab=billing",
    ) -> bool:
        """
        Send usage limit alert notification.
        
        Args:
            email: Recipient email
            organization_name: Organization name
            metric_name: Human-readable metric name (e.g., "Transactions", "Users")
            current_usage: Current usage count
            limit: Usage limit for the tier
            percentage: Usage percentage
            threshold: Alert threshold level ("80", "90", "100")
            upgrade_url: URL to upgrade subscription
            
        Returns:
            True if email sent successfully
        """
        # Determine severity and styling
        if threshold == "100":
            severity = "CRITICAL"
            alert_class = "danger"
            icon = "[!]"
            subject = f"[CRITICAL] {metric_name} Limit Exceeded - {self.company_name}"
        elif threshold == "90":
            severity = "WARNING"
            alert_class = "warning"
            icon = "[*]"
            subject = f"[WARNING] {metric_name} Usage at {percentage:.0f}% - {self.company_name}"
        else:  # 80%
            severity = "NOTICE"
            alert_class = "highlight"
            icon = "[i]"
            subject = f"{metric_name} Usage Approaching Limit - {self.company_name}"
        
        remaining = limit - current_usage
        remaining_text = f"{remaining:,} remaining" if remaining > 0 else "Limit reached"
        
        content = f"""
        <h2>{icon} Usage Alert: {metric_name}</h2>
        
        <p>Dear {organization_name} Team,</p>
        
        <div class="{alert_class}">
            <p><strong>Alert Level:</strong> {severity}</p>
            <p><strong>Metric:</strong> {metric_name}</p>
            <p><strong>Current Usage:</strong> {current_usage:,} of {limit:,} ({percentage:.1f}%)</p>
            <p><strong>Status:</strong> {remaining_text}</p>
        </div>
        
        {"<p><strong>Action Required:</strong> You have reached your monthly limit. Some features may be restricted until your billing period resets or you upgrade your plan.</p>" if threshold == "100" else ""}
        
        {"<p><strong>Recommendation:</strong> Your usage is approaching the limit. Consider upgrading your plan to avoid service interruption.</p>" if threshold == "90" else ""}
        
        {"<p><strong>Heads Up:</strong> Your usage is at 80% of your monthly limit. You may want to monitor your usage or consider an upgrade.</p>" if threshold == "80" else ""}
        
        <p>
            <a href="{upgrade_url}" class="button">View Usage & Upgrade Options</a>
        </p>
        
        <p>If you have questions about your usage or plan options, please contact our support team.</p>
        """
        
        body_text = f"""
{icon} Usage Alert: {metric_name}

Dear {organization_name} Team,

Alert Level: {severity}
Metric: {metric_name}
Current Usage: {current_usage:,} of {limit:,} ({percentage:.1f}%)
Status: {remaining_text}

{"Action Required: You have reached your monthly limit." if threshold == "100" else ""}
{"Recommendation: Consider upgrading to avoid service interruption." if threshold == "90" else ""}
{"Heads Up: Your usage is at 80% of your monthly limit." if threshold == "80" else ""}

View usage and upgrade options: {upgrade_url}

Best regards,
{self.company_name} Team
"""
        
        return await self.email_service.send_email(EmailMessage(
            to=[email],
            subject=subject,
            body_text=body_text,
            body_html=self._get_base_html_template(content),
        ))

    # ===========================================
    # REFUND NOTIFICATION EMAILS
    # ===========================================
    
    async def send_refund_processed(
        self,
        email: str,
        organization_name: str,
        amount_naira: int,
        original_reference: str,
        refund_reference: str,
        reason: Optional[str] = None,
    ) -> bool:
        """Send refund confirmation email."""
        subject = f"Refund Processed - {self._format_naira(amount_naira)}"
        
        reason_text = f"<p><strong>Reason:</strong> {reason}</p>" if reason else ""
        
        content = f"""
        <h2>Refund Processed Successfully</h2>
        
        <p>Dear {organization_name} Team,</p>
        
        <p>Your refund has been processed successfully. The funds will be credited to your original payment method within 5-10 business days.</p>
        
        <div class="success">
            <p class="amount">{self._format_naira(amount_naira)}</p>
            <p style="margin: 5px 0;"><strong>Refund Reference:</strong> {refund_reference}</p>
            <p style="margin: 5px 0;"><strong>Original Payment:</strong> {original_reference}</p>
            {reason_text}
        </div>
        
        <h3>What's Next?</h3>
        <ul>
            <li>Bank transfers: 1-3 business days</li>
            <li>Card payments: 5-10 business days (depending on your bank)</li>
            <li>The exact timing depends on your payment provider</li>
        </ul>
        
        <p>If you have any questions about this refund, please contact our support team.</p>
        
        <p>
            <a href="mailto:{self.support_email}" class="button">Contact Support</a>
        </p>
        """
        
        body_text = f"""
Refund Processed Successfully

Dear {organization_name} Team,

Your refund has been processed successfully.

Amount: {self._format_naira(amount_naira)}
Refund Reference: {refund_reference}
Original Payment: {original_reference}
{f"Reason: {reason}" if reason else ""}

The funds will be credited to your original payment method within 5-10 business days.

Questions? Contact us at {self.support_email}

Best regards,
{self.company_name} Team
"""
        
        return await self.email_service.send_email(EmailMessage(
            to=[email],
            subject=subject,
            body_text=body_text,
            body_html=self._get_base_html_template(content),
        ))
    
    async def send_refund_failed(
        self,
        email: str,
        organization_name: str,
        amount_naira: int,
        original_reference: str,
        failure_reason: str,
    ) -> bool:
        """Send refund failure notification email."""
        subject = f"Refund Issue - Action Required"
        
        content = f"""
        <h2>Refund Processing Issue</h2>
        
        <p>Dear {organization_name} Team,</p>
        
        <p>We encountered an issue while processing your refund. Our team is looking into this matter.</p>
        
        <div class="danger">
            <p><strong>Refund Amount:</strong> {self._format_naira(amount_naira)}</p>
            <p style="margin: 5px 0;"><strong>Original Payment:</strong> {original_reference}</p>
            <p style="margin: 5px 0;"><strong>Issue:</strong> {failure_reason}</p>
        </div>
        
        <h3>What's Happening?</h3>
        <p>Our billing team has been notified and will manually process this refund within 2-3 business days. You don't need to take any action.</p>
        
        <p>If you have urgent concerns, please contact our support team with the reference number above.</p>
        
        <p>
            <a href="mailto:{self.support_email}" class="button">Contact Support</a>
        </p>
        """
        
        body_text = f"""
Refund Processing Issue

Dear {organization_name} Team,

We encountered an issue while processing your refund.

Refund Amount: {self._format_naira(amount_naira)}
Original Payment: {original_reference}
Issue: {failure_reason}

Our billing team has been notified and will manually process this refund within 2-3 business days.

Questions? Contact us at {self.support_email}

Best regards,
{self.company_name} Team
"""
        
        return await self.email_service.send_email(EmailMessage(
            to=[email],
            subject=subject,
            body_text=body_text,
            body_html=self._get_base_html_template(content),
        ))
    
    async def send_paystack_invoice_notification(
        self,
        email: str,
        organization_name: str,
        invoice_id: str,
        amount_naira: int,
        due_date: datetime,
        description: str = "Subscription payment",
    ) -> bool:
        """Send Paystack invoice notification email (for subscription billing)."""
        subject = f"Invoice #{invoice_id} - {self._format_naira(amount_naira)} Due"
        due_str = due_date.strftime("%B %d, %Y")
        
        content = f"""
        <h2>New Invoice</h2>
        
        <p>Dear {organization_name} Team,</p>
        
        <p>A new invoice has been generated for your account.</p>
        
        <div class="highlight">
            <p style="margin: 5px 0;"><strong>Invoice #:</strong> {invoice_id}</p>
            <p class="amount">{self._format_naira(amount_naira)}</p>
            <p style="margin: 5px 0;"><strong>Description:</strong> {description}</p>
            <p style="margin: 5px 0;"><strong>Due Date:</strong> {due_str}</p>
        </div>
        
        <p>If you have automatic payment enabled, this invoice will be charged automatically. Otherwise, please ensure payment is made by the due date to avoid service interruption.</p>
        
        <p>
            <a href="{self.base_url}/billing" class="button">View Invoice</a>
        </p>
        """
        
        body_text = f"""
New Invoice Generated

Dear {organization_name} Team,

A new invoice has been generated:

Invoice #: {invoice_id}
Amount: {self._format_naira(amount_naira)}
Description: {description}
Due Date: {due_str}

View your invoice at: {self.base_url}/billing

Best regards,
{self.company_name} Team
"""
        
        return await self.email_service.send_email(EmailMessage(
            to=[email],
            subject=subject,
            body_text=body_text,
            body_html=self._get_base_html_template(content),
        ))
    
    async def send_scheduled_cancellation(
        self,
        email: str,
        organization_name: str,
        tier: str,
        effective_date: Optional[datetime] = None,
    ) -> bool:
        """
        Send notification that subscription is scheduled for cancellation.
        
        Args:
            email: Recipient email
            organization_name: Name of the organization
            tier: Current tier being cancelled
            effective_date: When cancellation takes effect
            
        Returns:
            True if email sent successfully
        """
        effective_str = effective_date.strftime("%B %d, %Y") if effective_date else "end of current billing period"
        
        subject = f"Subscription Cancellation Scheduled - {self.company_name}"
        
        content = f"""
        <h2 style="color: #f39c12;">Subscription Cancellation Scheduled</h2>
        
        <p>Dear {organization_name} Team,</p>
        
        <p>This email confirms that your subscription cancellation request has been received. Your current subscription details:</p>
        
        <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
            <p style="margin: 5px 0;"><strong>Current Plan:</strong> {tier.title()}</p>
            <p style="margin: 5px 0;"><strong>Status:</strong> Scheduled for cancellation</p>
            <p style="margin: 5px 0;"><strong>Effective Date:</strong> {effective_str}</p>
        </div>
        
        <h3>What Happens Next?</h3>
        <ul>
            <li>You'll retain full access to all {tier.title()} features until {effective_str}</li>
            <li>After that date, your account will be downgraded to the Core (free) plan</li>
            <li>Your data will be preserved, but some features may become unavailable</li>
        </ul>
        
        <h3>Changed Your Mind?</h3>
        <p>You can reactivate your subscription at any time before the effective date to keep your current plan.</p>
        
        <p>
            <a href="{self.base_url}/billing" class="button">Manage Subscription</a>
        </p>
        
        <p>Thank you for being a {self.company_name} customer. If you have any feedback about your experience, we'd love to hear from you.</p>
        """
        
        body_text = f"""
Subscription Cancellation Scheduled

Dear {organization_name} Team,

Your subscription cancellation request has been received.

Current Plan: {tier.title()}
Status: Scheduled for cancellation
Effective Date: {effective_str}

What Happens Next?
- You'll retain full access until {effective_str}
- After that, your account will be downgraded to the Core (free) plan
- Your data will be preserved

Changed Your Mind?
You can reactivate at any time before the effective date.

Manage your subscription at: {self.base_url}/billing

Best regards,
{self.company_name} Team
"""
        
        return await self.email_service.send_email(EmailMessage(
            to=[email],
            subject=subject,
            body_text=body_text,
            body_html=self._get_base_html_template(content),
        ))
