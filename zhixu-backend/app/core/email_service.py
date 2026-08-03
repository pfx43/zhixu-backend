import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM_EMAIL, SMTP_FROM_NAME
import logging

logger = logging.getLogger(__name__)


class EmailService:
    """邮件发送服务"""

    @staticmethod
    def send_verification_email(to_email: str, verification_code: str, frontend_url: str) -> bool:
        """
        发送邮箱验证邮件
        
        Args:
            to_email: 收件人邮箱
            verification_code: 验证码
            frontend_url: 前端验证链接 (如 http://localhost:3000/verify?code=xxx)
        
        Returns:
            bool: 发送成功返回 True，失败返回 False
        """
        try:
            # 构建邮件内容
            subject = "邮箱验证 - Zhishi"
            html_body = f"""
            <html>
                <head>
                    <meta charset="utf-8">
                    <style>
                        body {{ font-family: Arial, sans-serif; }}
                        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                        .header {{ background-color: #007bff; color: white; padding: 20px; text-align: center; border-radius: 5px; }}
                        .content {{ margin: 20px 0; line-height: 1.6; }}
                        .code {{ font-size: 32px; font-weight: bold; color: #007bff; text-align: center; margin: 20px 0; }}
                        .link {{ text-align: center; margin: 20px 0; }}
                        .button {{ background-color: #007bff; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block; }}
                        .footer {{ margin-top: 20px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #666; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h1>Zhishi 邮箱验证</h1>
                        </div>
                        <div class="content">
                            <p>您好！</p>
                            <p>感谢您注册 Zhishi。请使用以下验证码验证您的邮箱：</p>
                            <div class="code">{verification_code}</div>
                            <p>验证码有效期为 15 分钟。</p>
                            <div class="link">
                                <a href="{frontend_url}" class="button">点击验证</a>
                            </div>
                            <p style="color: #666; font-size: 14px;">如果上述链接无法点击，请复制以下地址到浏览器打开：</p>
                            <p style="color: #007bff; word-break: break-all;">{frontend_url}</p>
                        </div>
                        <div class="footer">
                            <p>这是一封自动发送的邮件，请勿回复。</p>
                            <p>© 2025 Zhishi. All rights reserved.</p>
                        </div>
                    </div>
                </body>
            </html>
            """

            return EmailService._send_email(to_email, subject, html_body)

        except Exception as e:
            logger.error(f"发送邮箱验证邮件失败: {str(e)}")
            return False

    @staticmethod
    def send_password_reset_email(to_email: str, reset_token: str, frontend_url: str) -> bool:
        """
        发送密码重置邮件
        
        Args:
            to_email: 收件人邮箱
            reset_token: 重置密码的 token
            frontend_url: 前端重置密码链接
        
        Returns:
            bool: 发送成功返回 True，失败返回 False
        """
        try:
            subject = "重置密码 - Zhishi"
            html_body = f"""
            <html>
                <head>
                    <meta charset="utf-8">
                    <style>
                        body {{ font-family: Arial, sans-serif; }}
                        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                        .header {{ background-color: #28a745; color: white; padding: 20px; text-align: center; border-radius: 5px; }}
                        .content {{ margin: 20px 0; line-height: 1.6; }}
                        .link {{ text-align: center; margin: 20px 0; }}
                        .button {{ background-color: #28a745; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block; }}
                        .footer {{ margin-top: 20px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #666; }}
                        .warning {{ color: #dc3545; font-size: 12px; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h1>重置您的密码</h1>
                        </div>
                        <div class="content">
                            <p>您好！</p>
                            <p>我们收到了重置您 Zhishi 账户密码的请求。</p>
                            <p>请点击下方按钮重置您的密码：</p>
                            <div class="link">
                                <a href="{frontend_url}" class="button">重置密码</a>
                            </div>
                            <p style="color: #666; font-size: 14px;">或复制以下链接到浏览器打开：</p>
                            <p style="color: #007bff; word-break: break-all;">{frontend_url}</p>
                            <p class="warning">⚠️ 此链接有效期为 15 分钟，过期后需要重新申请重置。</p>
                            <p class="warning">⚠️ 如果您没有请求重置密码，请忽略此邮件，您的账户仍然安全。</p>
                        </div>
                        <div class="footer">
                            <p>这是一封自动发送的邮件，请勿回复。</p>
                            <p>© 2025 Zhishi. All rights reserved.</p>
                        </div>
                    </div>
                </body>
            </html>
            """

            return EmailService._send_email(to_email, subject, html_body)

        except Exception as e:
            logger.error(f"发送密码重置邮件失败: {str(e)}")
            return False

    @staticmethod
    def _send_email(to_email: str, subject: str, html_body: str) -> bool:
        """
        通用邮件发送方法
        
        Args:
            to_email: 收件人邮箱
            subject: 邮件主题
            html_body: 邮件 HTML 内容
        
        Returns:
            bool: 发送成功返回 True，失败返回 False
        """
        try:
            # 创建邮件对象
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
            msg['To'] = to_email

            # 添加纯文本和 HTML 版本
            text_body = "请使用支持 HTML 的邮件客户端查看此邮件。"
            msg.attach(MIMEText(text_body, 'plain', _charset='utf-8'))
            msg.attach(MIMEText(html_body, 'html', _charset='utf-8'))

            # 连接 SMTP 服务器并发送
            if SMTP_PORT == 465:
                # SSL 加密
                server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
            else:
                # TLS 加密
                server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
                server.starttls()

            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
            server.quit()

            logger.info(f"✅ 邮件发送成功: {to_email}")
            return True

        except Exception as e:
            logger.error(f"❌ 邮件发送失败 ({to_email}): {str(e)}")
            return False


# 创建全局实例
email_service = EmailService()
