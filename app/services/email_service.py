"""
Tekvwa Pro Audit - Email Service

Handles transactional email sending.
Supports SendGrid, Mailgun, or SMTP.
"""

import logging
import smtplib
import ssl
from typing import Any, Dict, List, Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class EmailProvider:
    """Email provider types."""
    SMTP = "smtp"
    SENDGRID = "sendgrid"
    MAILGUN = "mailgun"
    AWS_SES = "aws_ses"
    MOCK = "mock"


@dataclass
class EmailMessage:
    """Email message data structure."""
    to: List[str]
    subject: str
    body_text: str
    body_html: Optional[str] = None
    cc: Optional[List[str]] = None
    bcc: Optional[List[str]] = None
    reply_to: Optional[str] = None
    attachments: Optional[List[Dict[str, Any]]] = None


class EmailService:
    """Service for sending transactional emails."""
    
    def __init__(self):
        # SMTP settings from config (Outlook/Office365)
        self.smtp_host = settings.mail_server
        self.smtp_port = settings.mail_port
        self.smtp_username = settings.mail_username
        self.smtp_password = settings.mail_password
        self.smtp_use_tls = settings.mail_use_tls
        
        # From email - use username if mail_from not set
        self.from_email = settings.mail_from or settings.mail_username
        self.from_name = settings.mail_from_name or 'Tekvwa Pro Audit'
        
        # Provider settings
        self.provider = getattr(settings, 'email_provider', None)
        self.sendgrid_api_key = getattr(settings, 'sendgrid_api_key', None)
        self.mailgun_api_key = getattr(settings, 'mailgun_api_key', None)
        self.mailgun_domain = getattr(settings, 'mailgun_domain', None)
    
    def _determine_provider(self) -> str:
        """Determine which email provider to use based on configuration."""
        if self.sendgrid_api_key:
            return EmailProvider.SENDGRID
        elif self.mailgun_api_key and self.mailgun_domain:
            return EmailProvider.MAILGUN
        elif self.smtp_host:
            return EmailProvider.SMTP
        else:
            return EmailProvider.MOCK
    
    async def send_email(self, message: EmailMessage) -> bool:
        """
        Send an email using the configured provider.
        """
        provider = self._determine_provider()
        
        try:
            if provider == EmailProvider.SENDGRID:
                return await self._send_via_sendgrid(message)
            elif provider == EmailProvider.MAILGUN:
                return await self._send_via_mailgun(message)
            elif provider == EmailProvider.SMTP:
                return await self._send_via_smtp(message)
            else:
                return await self._send_mock(message)
        except Exception as e:
            logger.error(f"Failed to send email via {provider}: {e}")
            return False
    
    async def _send_via_sendgrid(self, message: EmailMessage) -> bool:
        """Send email via SendGrid API."""
        try:
            url = "https://api.sendgrid.com/v3/mail/send"
            
            payload = {
                "personalizations": [
                    {
                        "to": [{"email": email} for email in message.to],
                    }
                ],
                "from": {
                    "email": self.from_email,
                    "name": self.from_name,
                },
                "subject": message.subject,
                "content": [
                    {"type": "text/plain", "value": message.body_text},
                ],
            }
            
            # Add HTML content if provided
            if message.body_html:
                payload["content"].append({
                    "type": "text/html",
                    "value": message.body_html,
                })
            
            # Add CC recipients
            if message.cc:
                payload["personalizations"][0]["cc"] = [
                    {"email": email} for email in message.cc
                ]
            
            # Add BCC recipients
            if message.bcc:
                payload["personalizations"][0]["bcc"] = [
                    {"email": email} for email in message.bcc
                ]
            
            # Add reply-to
            if message.reply_to:
                payload["reply_to"] = {"email": message.reply_to}
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.sendgrid_api_key}",
                        "Content-Type": "application/json",
                    },
                )
                
                if response.status_code in [200, 202]:
                    logger.info(f"Email sent via SendGrid to {message.to}")
                    return True
                else:
                    logger.error(f"SendGrid API error: {response.status_code} - {response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"SendGrid send failed: {e}")
            return False
    
    async def _send_via_mailgun(self, message: EmailMessage) -> bool:
        """Send email via Mailgun API."""
        try:
            url = f"https://api.mailgun.net/v3/{self.mailgun_domain}/messages"
            
            data = {
                "from": f"{self.from_name} <{self.from_email}>",
                "to": message.to,
                "subject": message.subject,
                "text": message.body_text,
            }
            
            if message.body_html:
                data["html"] = message.body_html
            
            if message.cc:
                data["cc"] = message.cc
            
            if message.bcc:
                data["bcc"] = message.bcc
            
            if message.reply_to:
                data["h:Reply-To"] = message.reply_to
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    data=data,
                    auth=("api", self.mailgun_api_key),
                )
                
                if response.status_code == 200:
                    logger.info(f"Email sent via Mailgun to {message.to}")
                    return True
                else:
                    logger.error(f"Mailgun API error: {response.status_code} - {response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Mailgun send failed: {e}")
            return False
    
    async def _send_via_smtp(self, message: EmailMessage) -> bool:
        """Send email via SMTP."""
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = message.subject
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = ', '.join(message.to)
            
            if message.cc:
                msg['Cc'] = ', '.join(message.cc)
            
            if message.reply_to:
                msg['Reply-To'] = message.reply_to
            
            # Attach text and HTML parts
            part1 = MIMEText(message.body_text, 'plain')
            msg.attach(part1)
            
            if message.body_html:
                part2 = MIMEText(message.body_html, 'html')
                msg.attach(part2)
            
            # Handle attachments
            if message.attachments:
                for attachment in message.attachments:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(attachment['content'])
                    encoders.encode_base64(part)
                    part.add_header(
                        'Content-Disposition',
                        f'attachment; filename="{attachment["filename"]}"'
                    )
                    msg.attach(part)
            
            # Get all recipients
            all_recipients = message.to.copy()
            if message.cc:
                all_recipients.extend(message.cc)
            if message.bcc:
                all_recipients.extend(message.bcc)
            
            # Send via SMTP
            if self.smtp_use_tls:
                context = ssl.create_default_context()
                with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                    server.starttls(context=context)
                    if self.smtp_username and self.smtp_password:
                        server.login(self.smtp_username, self.smtp_password)
                    server.sendmail(self.from_email, all_recipients, msg.as_string())
            else:
                with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                    if self.smtp_username and self.smtp_password:
                        server.login(self.smtp_username, self.smtp_password)
                    server.sendmail(self.from_email, all_recipients, msg.as_string())
            
            logger.info(f"Email sent via SMTP to {message.to}")
            return True
            
        except Exception as e:
            logger.error(f"SMTP send failed: {e}")
            return False
    
    async def _send_mock(self, message: EmailMessage) -> bool:
        """Mock email sending for development."""
        logger.info(f"[MOCK EMAIL] To: {message.to} | Subject: {message.subject}")
        logger.debug(f"[MOCK EMAIL] Body: {message.body_text[:200]}...")
        return True
    
    # ===========================================
    # TRANSACTIONAL EMAIL TEMPLATES
    # ===========================================
    
    async def send_welcome_email(
        self,
        to_email: str,
        first_name: str,
    ) -> bool:
        """Send welcome email to new users."""
        subject = "Welcome to Tekvwa Pro Audit!"
        
        body_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h1 style="color: #16a34a;">Welcome to Tekvwa Pro Audit!</h1>
                <p>Hi {first_name},</p>
                <p>Thank you for joining Tekvwa Pro Audit, Nigeria's premier tax compliance and business management platform.</p>
                <p>Here's what you can do next:</p>
                <ul>
                    <li>Set up your business entity</li>
                    <li>Connect your NRS e-invoicing</li>
                    <li>Start tracking income and expenses</li>
                    <li>Generate tax-compliant reports</li>
                </ul>
                <p>
                    <a href="https://app.tekvwa.com/dashboard" 
                       style="display: inline-block; background-color: #16a34a; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px;">
                        Go to Dashboard
                    </a>
                </p>
                <p>If you have any questions, our support team is here to help.</p>
                <p>Best regards,<br>The Tekvwa Team</p>
            </div>
        </body>
        </html>
        """
        
        body_text = f"""
        Welcome to Tekvwa Pro Audit!
        
        Hi {first_name},
        
        Thank you for joining Tekvwa Pro Audit, Nigeria's premier tax compliance and business management platform.
        
        Here's what you can do next:
        - Set up your business entity
        - Connect your NRS e-invoicing
        - Start tracking income and expenses
        - Generate tax-compliant reports
        
        Visit your dashboard: https://app.tekvwa.com/dashboard
        
        Best regards,
        The Tekvwa Team
        """
        
        return await self.send_email(EmailMessage(
            to=[to_email],
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        ))
    
    async def send_invoice_email(
        self,
        to_email: str,
        customer_name: str,
        invoice_number: str,
        amount: float,
        due_date: str,
        invoice_url: str,
    ) -> bool:
        """Send invoice to customer."""
        subject = f"Invoice {invoice_number} from Tekvwa"
        
        body_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h1 style="color: #16a34a;">Invoice {invoice_number}</h1>
                <p>Dear {customer_name},</p>
                <p>Please find attached your invoice for ₦{amount:,.2f}.</p>
                <p><strong>Due Date:</strong> {due_date}</p>
                <p>
                    <a href="{invoice_url}" 
                       style="display: inline-block; background-color: #16a34a; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px;">
                        View Invoice
                    </a>
                </p>
                <p>Thank you for your business.</p>
            </div>
        </body>
        </html>
        """
        
        body_text = f"""
        Invoice {invoice_number}
        
        Dear {customer_name},
        
        Please find attached your invoice for ₦{amount:,.2f}.
        
        Due Date: {due_date}
        
        View your invoice: {invoice_url}
        
        Thank you for your business.
        """
        
        return await self.send_email(EmailMessage(
            to=[to_email],
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        ))
    
    async def send_payment_confirmation(
        self,
        to_email: str,
        customer_name: str,
        invoice_number: str,
        amount: float,
        payment_date: str,
    ) -> bool:
        """Send payment confirmation to customer."""
        subject = f"Payment Received - Invoice {invoice_number}"
        
        body_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h1 style="color: #16a34a;">Payment Received</h1>
                <p>Dear {customer_name},</p>
                <p>We have received your payment of ₦{amount:,.2f} for invoice {invoice_number}.</p>
                <p><strong>Payment Date:</strong> {payment_date}</p>
                <p>Thank you for your prompt payment.</p>
            </div>
        </body>
        </html>
        """
        
        body_text = f"""
        Payment Received
        
        Dear {customer_name},
        
        We have received your payment of ₦{amount:,.2f} for invoice {invoice_number}.
        
        Payment Date: {payment_date}
        
        Thank you for your prompt payment.
        """
        
        return await self.send_email(EmailMessage(
            to=[to_email],
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        ))
    
    async def send_overdue_reminder(
        self,
        to_email: str,
        customer_name: str,
        invoice_number: str,
        amount: float,
        days_overdue: int,
        invoice_url: str,
    ) -> bool:
        """Send overdue invoice reminder to customer."""
        subject = f"Payment Reminder - Invoice {invoice_number} ({days_overdue} days overdue)"
        
        body_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h1 style="color: #dc2626;">Payment Reminder</h1>
                <p>Dear {customer_name},</p>
                <p>This is a friendly reminder that invoice {invoice_number} for ₦{amount:,.2f} is now <strong>{days_overdue} days overdue</strong>.</p>
                <p>Please arrange for payment at your earliest convenience.</p>
                <p>
                    <a href="{invoice_url}" 
                       style="display: inline-block; background-color: #dc2626; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px;">
                        View Invoice & Pay
                    </a>
                </p>
                <p>If you have already made payment, please disregard this reminder.</p>
            </div>
        </body>
        </html>
        """
        
        body_text = f"""
        Payment Reminder
        
        Dear {customer_name},
        
        This is a friendly reminder that invoice {invoice_number} for ₦{amount:,.2f} is now {days_overdue} days overdue.
        
        Please arrange for payment at your earliest convenience.
        
        View invoice: {invoice_url}
        
        If you have already made payment, please disregard this reminder.
        """
        
        return await self.send_email(EmailMessage(
            to=[to_email],
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        ))
    
    async def send_vat_reminder(
        self,
        to_email: str,
        business_name: str,
        period: str,
        deadline: str,
        vat_amount: float,
    ) -> bool:
        """Send VAT filing reminder."""
        subject = f"VAT Filing Reminder - {period}"
        
        body_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h1 style="color: #16a34a;">VAT Filing Reminder</h1>
                <p>Dear {business_name},</p>
                <p>This is a reminder that your VAT return for <strong>{period}</strong> is due on <strong>{deadline}</strong>.</p>
                <p>Estimated VAT payable: <strong>₦{vat_amount:,.2f}</strong></p>
                <p>
                    <a href="https://app.tekvwa.com/reports?tab=tax" 
                       style="display: inline-block; background-color: #16a34a; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px;">
                        View VAT Report
                    </a>
                </p>
                <p>Don't forget to file on time to avoid penalties.</p>
            </div>
        </body>
        </html>
        """
        
        body_text = f"""
        VAT Filing Reminder
        
        Dear {business_name},
        
        This is a reminder that your VAT return for {period} is due on {deadline}.
        
        Estimated VAT payable: ₦{vat_amount:,.2f}
        
        View VAT report: https://app.tekvwa.com/reports?tab=tax
        
        Don't forget to file on time to avoid penalties.
        """
        
        return await self.send_email(EmailMessage(
            to=[to_email],
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        ))
    
    async def send_password_reset(
        self,
        to_email: str,
        reset_url: str,
    ) -> bool:
        """Send password reset email."""
        subject = "Reset Your Password - Tekvwa Pro Audit"
        
        body_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h1 style="color: #16a34a;">Reset Your Password</h1>
                <p>You requested to reset your password. Click the button below to set a new password:</p>
                <p>
                    <a href="{reset_url}" 
                       style="display: inline-block; background-color: #16a34a; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px;">
                        Reset Password
                    </a>
                </p>
                <p>This link will expire in 1 hour.</p>
                <p>If you didn't request this, you can safely ignore this email.</p>
            </div>
        </body>
        </html>
        """
        
        body_text = f"""
        Reset Your Password
        
        You requested to reset your password. Visit the link below to set a new password:
        
        {reset_url}
        
        This link will expire in 1 hour.
        
        If you didn't request this, you can safely ignore this email.
        """
        
        return await self.send_email(EmailMessage(
            to=[to_email],
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        ))

    async def send_verification_email(
        self,
        to_email: str,
        user_name: str,
        verification_url: str,
    ) -> bool:
        """Send email verification link to new users."""
        subject = "Verify Your Email - Tekvwa Pro Audit"
        
        body_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h1 style="color: #16a34a;">Verify Your Email Address</h1>
                <p>Hi {user_name},</p>
                <p>Thank you for registering with Tekvwa Pro Audit! Please verify your email address by clicking the button below:</p>
                <p>
                    <a href="{verification_url}" 
                       style="display: inline-block; background-color: #16a34a; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px;">
                        Verify Email Address
                    </a>
                </p>
                <p>This link will expire in 24 hours.</p>
                <p>If you didn't create an account with Tekvwa Pro Audit, you can safely ignore this email.</p>
                <p>Best regards,<br>The Tekvwa Team</p>
            </div>
        </body>
        </html>
        """
        
        body_text = f"""
        Verify Your Email Address
        
        Hi {user_name},
        
        Thank you for registering with Tekvwa Pro Audit! Please verify your email address by visiting the link below:
        
        {verification_url}
        
        This link will expire in 24 hours.
        
        If you didn't create an account with Tekvwa Pro Audit, you can safely ignore this email.
        
        Best regards,
        The Tekvwa Team
        """
        
        return await self.send_email(EmailMessage(
            to=[to_email],
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        ))
