# ============================================================================
# Email Utilities
# ============================================================================
# File: app/utils/email.py
# Purpose: Email sending via Mailgun (async)
# Status: Production-Ready ✅

from typing import List, Optional
import logging
from app.config import settings


logger = logging.getLogger(__name__)


# ============================================================================
# EMAIL TEMPLATES
# ============================================================================

def get_welcome_email_body(username: str) -> tuple:
    """
    Get welcome email template
    
    Args:
        username: User's username
    
    Returns:
        tuple: (subject, html_body)
    """
    subject = "Welcome to EventAI Platform! 🎉"
    
    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h1>Welcome to EventAI, {username}!</h1>
            
            <p>We're excited to have you join our community of event enthusiasts, speakers, and learners.</p>
            
            <h2>Get Started:</h2>
            <ul>
                <li>Complete your profile to help others get to know you</li>
                <li>Browse upcoming sessions and events</li>
                <li>Connect with speakers and fellow attendees</li>
                <li>Explore learning paths and challenges</li>
            </ul>
            
            <p>If you have any questions, feel free to contact us at {settings.mailgun_from_email}</p>
            
            <p>Happy learning!</p>
            <p>The EventAI Team</p>
        </body>
    </html>
    """
    
    return subject, html_body


def get_verification_email_body(username: str, verification_code: str) -> tuple:
    """
    Get email verification template
    
    Args:
        username: User's username
        verification_code: 6-digit verification code
    
    Returns:
        tuple: (subject, html_body)
    """
    subject = "Verify Your Email Address - EventAI"
    
    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h1>Email Verification Required</h1>
            
            <p>Hi {username},</p>
            
            <p>To complete your registration on EventAI, please verify your email address by entering the following code:</p>
            
            <div style="text-align: center; margin: 30px 0;">
                <h2 style="letter-spacing: 5px; color: #007bff;">{verification_code}</h2>
            </div>
            
            <p>This code will expire in 15 minutes.</p>
            
            <p>If you didn't create this account, please ignore this email.</p>
            
            <p>The EventAI Team</p>
        </body>
    </html>
    """
    
    return subject, html_body


def get_password_reset_email_body(username: str, reset_token: str, reset_url: str) -> tuple:
    """
    Get password reset template
    
    Args:
        username: User's username
        reset_token: Password reset token
        reset_url: Reset URL
    
    Returns:
        tuple: (subject, html_body)
    """
    subject = "Reset Your Password - EventAI"
    
    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h1>Password Reset Request</h1>
            
            <p>Hi {username},</p>
            
            <p>We received a request to reset your password. Click the link below to proceed:</p>
            
            <p style="margin: 30px 0;">
                <a href="{reset_url}" style="background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
                    Reset Password
                </a>
            </p>
            
            <p>This link will expire in 1 hour.</p>
            
            <p>If you didn't request this reset, please ignore this email.</p>
            
            <p>The EventAI Team</p>
        </body>
    </html>
    """
    
    return subject, html_body


def get_announcement_email_body(title: str, content: str) -> tuple:
    """
    Get announcement email template
    
    Args:
        title: Announcement title
        content: Announcement content
    
    Returns:
        tuple: (subject, html_body)
    """
    subject = f"📢 {title} - EventAI"
    
    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h1>{title}</h1>
            
            <div style="background-color: #f8f9fa; padding: 20px; border-radius: 5px;">
                {content}
            </div>
            
            <p>Log in to EventAI to see more details.</p>
            
            <p>The EventAI Team</p>
        </body>
    </html>
    """
    
    return subject, html_body


def get_session_reminder_email_body(username: str, session_title: str, start_time: str) -> tuple:
    """
    Get session reminder template
    
    Args:
        username: User's username
        session_title: Session title
        start_time: Session start time
    
    Returns:
        tuple: (subject, html_body)
    """
    subject = f"📅 Reminder: {session_title} starts soon!"
    
    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h1>Session Reminder</h1>
            
            <p>Hi {username},</p>
            
            <p>Don't forget! Your registered session is starting soon:</p>
            
            <div style="background-color: #fff3cd; padding: 20px; border-radius: 5px; margin: 20px 0;">
                <h3>{session_title}</h3>
                <p><strong>Start Time:</strong> {start_time}</p>
            </div>
            
            <p>Log in to EventAI to join the session.</p>
            
            <p>The EventAI Team</p>
        </body>
    </html>
    """
    
    return subject, html_body


def get_badge_earned_email_body(username: str, badge_name: str) -> tuple:
    """
    Get badge earned template
    
    Args:
        username: User's username
        badge_name: Badge name
    
    Returns:
        tuple: (subject, html_body)
    """
    subject = f"🏆 Congratulations! You earned the {badge_name} badge!"
    
    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h1>Achievement Unlocked! 🎉</h1>
            
            <p>Hi {username},</p>
            
            <p>Congratulations! You've earned the <strong>{badge_name}</strong> badge for your participation and engagement on EventAI.</p>
            
            <p>Keep up the great work and earn more badges!</p>
            
            <p>The EventAI Team</p>
        </body>
    </html>
    """
    
    return subject, html_body


# ============================================================================
# EMAIL SENDING (MAILGUN)
# ============================================================================

def send_email(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
    reply_to: Optional[str] = None
) -> bool:
    """
    Send email via Mailgun
    
    Args:
        to_email: Recipient email
        subject: Email subject
        html_body: HTML email body
        text_body: Plain text fallback
        reply_to: Reply-to email
    
    Returns:
        bool: True if sent successfully
    """
    try:
        import requests
        
        # Mailgun API endpoint
        url = f"https://api.mailgun.net/v3/{settings.mailgun_domain}/messages"
        
        # Request data
        data = {
            "from": f"{settings.mailgun_from_name} <{settings.mailgun_from_email}>",
            "to": to_email,
            "subject": subject,
            "html": html_body,
            "text": text_body or subject,
        }
        
        if reply_to:
            data["h:Reply-To"] = reply_to
        
        # Send via Mailgun
        response = requests.post(
            url,
            auth=("api", settings.mailgun_api_key),
            data=data,
            timeout=10
        )
        
        if response.status_code == 200:
            logger.info(f"Email sent successfully to {to_email}")
            return True
        else:
            logger.error(f"Email send failed: {response.status_code} - {response.text}")
            return False
    
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")
        return False


# ============================================================================
# ASYNC EMAIL SENDING (with Celery)
# ============================================================================

def send_welcome_email(user_email: str, username: str) -> bool:
    """
    Send welcome email
    
    Args:
        user_email: User's email
        username: User's username
    
    Returns:
        bool: Success status
    """
    subject, html_body = get_welcome_email_body(username)
    return send_email(user_email, subject, html_body)


def send_verification_email(user_email: str, username: str, verification_code: str) -> bool:
    """
    Send email verification code
    
    Args:
        user_email: User's email
        username: User's username
        verification_code: 6-digit code
    
    Returns:
        bool: Success status
    """
    subject, html_body = get_verification_email_body(username, verification_code)
    return send_email(user_email, subject, html_body)


def send_password_reset_email(
    user_email: str,
    username: str,
    reset_token: str,
    frontend_url: str = "http://localhost:3000"
) -> bool:
    """
    Send password reset email
    
    Args:
        user_email: User's email
        username: User's username
        reset_token: Reset token
        frontend_url: Frontend base URL
    
    Returns:
        bool: Success status
    """
    reset_url = f"{frontend_url}/auth/reset-password?token={reset_token}"
    subject, html_body = get_password_reset_email_body(username, reset_token, reset_url)
    return send_email(user_email, subject, html_body)


def send_announcement_email(
    user_email: str,
    title: str,
    content: str
) -> bool:
    """
    Send announcement email
    
    Args:
        user_email: User's email
        title: Announcement title
        content: Announcement content
    
    Returns:
        bool: Success status
    """
    subject, html_body = get_announcement_email_body(title, content)
    return send_email(user_email, subject, html_body)


def send_session_reminder_email(
    user_email: str,
    username: str,
    session_title: str,
    start_time: str
) -> bool:
    """
    Send session reminder email
    
    Args:
        user_email: User's email
        username: User's username
        session_title: Session title
        start_time: Session start time
    
    Returns:
        bool: Success status
    """
    subject, html_body = get_session_reminder_email_body(username, session_title, start_time)
    return send_email(user_email, subject, html_body)


def send_badge_earned_email(
    user_email: str,
    username: str,
    badge_name: str
) -> bool:
    """
    Send badge earned email
    
    Args:
        user_email: User's email
        username: User's username
        badge_name: Badge name
    
    Returns:
        bool: Success status
    """
    subject, html_body = get_badge_earned_email_body(username, badge_name)
    return send_email(user_email, subject, html_body)