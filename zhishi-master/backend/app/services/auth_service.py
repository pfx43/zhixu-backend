import secrets
import logging
import random
import string
import json
import os
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from datetime import datetime, timedelta, timezone

from app.models import (
    User,
    KbCollection,
    Document,
    DocumentSegment,
    QuestionProvenance,
    QuizSession,
    QuizSessionQuestion,
    QuizAnswer,
    TutorSession,
    UserNote,
    TrainingPlan,
    QuestionTag,
    UserQuestionRef,
    OnboardingState,
)
from app.core.security import get_password_hash, verify_password
from app.core.redis import cache
from app.core.config import ACCESS_TOKEN_EXPIRE_MINUTES, EMAIL_VERIFICATION_EXPIRE_MINUTES, PASSWORD_RESET_EXPIRE_MINUTES, FRONTEND_URL, is_local_rag
from app.core.email_service import email_service
from app.services.dify_kb import DifyKB
from app.crud.kb import seed_default_collections
import app.crud as crud

logger = logging.getLogger(__name__)

class AuthManager:
    @staticmethod
    def _gen_user_hash() -> str:
        """生成 TCN 用户哈希"""
        from app.services.tcn_client import tcn_client
        return tcn_client.generate_user_hash(secrets.randbits(32))

    @staticmethod
    def register(db: Session, email: str, password: str, nickname: str, username: str = None, verification_code: str = None):
        """
        注册逻辑
        1. 校验验证码
        2. 校验 Email 是否存在
        3. 加密落库
        4. 登录返回 Token
        """
        # 1. 校验验证码 — 在 register 被调用前先校验
        if verification_code:
            # 提取手机号用于匹配验证码
            target = email
            if email.endswith('@phone.local'):
                target = email.split('@')[0]
            AuthManager.verify_code(target, verification_code)

        # 2. 校验是否已注册
        if crud.get_user_by_email(db, email=email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该邮箱已被注册"
            )

        # 3. 加密 + 落库
        hashed_pwd = get_password_hash(password)
        final_username = username if username else email.split("@")[0]
        new_user = User(
            email=email,
            password_hash=hashed_pwd,
            username=final_username,
            nickname=nickname,
            is_active=True,
            plan_level=0,
            user_hash=AuthManager._gen_user_hash(),
        )
        try:
            # create user and onboarding record in same transaction
            db.add(new_user)
            db.flush()
            # initialize onboarding state
            try:
                init_state = OnboardingState(
                    user_id=new_user.id,
                    guide_version=1,
                    revision=1,
                    status="in_progress",
                    current_step="channel",
                    steps=None,
                    channel_answer=None,
                    profile_answer=None,
                    tags=None,
                )
                db.add(init_state)
            except Exception:
                # non-fatal: proceed without onboarding init
                logger.warning("初始化 onboarding_state 失败，继续完成注册")

            db.commit()
            db.refresh(new_user)
            logger.info(f"用户注册成功: {email}")
        except Exception as e:
            db.rollback()
            logger.error(f"注册数据库错误: {str(e)}")
            raise HTTPException(status_code=500, detail="注册失败，请稍后重试")

        # 3.5 自动创建 Dify 知识库（仅 RAG_BACKEND=dify 时）
        if not is_local_rag():
            try:
                import uuid
                kb_name = f"{nickname}_{uuid.uuid4().hex[:8]}"
                dataset_id = DifyKB.create_dataset(kb_name, f"用户 {email} 的知识库")
                new_user.dataset_id = dataset_id
                db.commit()
                db.refresh(new_user)
                logger.info(f"Dify 知识库创建成功: user_id={new_user.id}, dataset_id={dataset_id}, name={kb_name}")

                DifyKB.upload_welcome_document(dataset_id)
            except Exception as e:
                logger.warning(f"Dify 知识库初始化失败（不影响注册）: {e}")

        # 3.7 创建默认知识库分区（学习区 / 生活区）
        try:
            seed_default_collections(db, new_user.id, new_user.dataset_id)
            db.commit()
            logger.info(f"默认知识库分区已创建: user_id={new_user.id}")
        except Exception as e:
            db.rollback()
            logger.warning(f"默认知识库分区创建失败（不影响注册）: {e}")

        # 4. 返回 (调用登录逻辑)
        try:
            return AuthManager.login(db=db, email=email, password=password)
        except HTTPException as he:
            if he.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
                logger.warning(
                    f"用户注册成功，但 Redis 服务不可用，未生成登录 Token: {email}"
                )
                return {
                    "id": new_user.id,
                    "email": new_user.email,
                    "nickname": new_user.nickname,
                    "username": new_user.username,
                    "is_active": new_user.is_active,
                    "created_at": new_user.created_at,
                    "access_token": None,
                    "token_type": None,
                    "message": "注册成功，Redis 服务不可用，登录 Token 未生成。请稍后登录。"
                }
            raise

    @staticmethod
    def login(db: Session, password: str = "", email: str = "", phone: str = ""):
        """
        登录逻辑 — 支持邮箱 + 手机号双登录
        1. 验证: 邮箱或手机号 + 密码
        2. 生成: token = secrets.token_hex(16)
        3. 同步: 将用户信息写入 Redis
        """
        user = None
        if email:
            user = crud.get_user_by_email(db, email=email)
        elif phone:
            user = crud.get_user_by_phone(db, phone=phone)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="请提供邮箱或手机号",
            )

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="账号不存在，请先注册",
            )

        if not verify_password(password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="账号或密码错误",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if not user.is_active:
             raise HTTPException(status_code=400, detail="User is inactive")

        # 2. 生成 Token (32 chars hex string)
        token = secrets.token_hex(16)
        
        # 3. 同步 (写入 Redis)
        # 构造用户数据 (保持与之前一致的结构)
        user_data = {
            "user_id": user.id,
            "email": user.email,
            "nickname": user.nickname,
            "level": user.plan_level,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "dataset_id": user.dataset_id,
            "user_hash": user.user_hash,
            "api_limit_daily": user.api_limit_daily,
            "token_limit_monthly": user.token_limit_monthly,
            "knowledge_base_limit": user.knowledge_base_limit,
            "model_access": user.model_access,
            "concurrent_limit": user.concurrent_limit
        }
        
        # Calculate TTL (seconds)
        ttl = ACCESS_TOKEN_EXPIRE_MINUTES * 60
        
        # Store in Redis
        try:
            cache.set_session(token, user_data, ttl=ttl)
        except ConnectionError as exc:
            logger.error(f"Redis 服务不可用: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Redis 服务不可用，请启动 Redis 后重试"
            )
        
        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": ttl,
            # For registration response compatibility (User fields)
            "id": user.id,
            "email": user.email,
            "nickname": user.nickname,
            "username": user.username,
            "is_active": user.is_active,
            "created_at": user.created_at
        }

    @staticmethod
    def send_verification_code(target: str):
        """
        发送验证码（邮箱或手机号）
        - 邮箱: 发送邮件 + 存 Redis
        - 手机号: 仅存 Redis（后续可接入阿里云短信）
        """
        verification_code = ''.join(random.choices(string.digits, k=6))
        ttl = EMAIL_VERIFICATION_EXPIRE_MINUTES * 60
        key = f"verification:{target}"

        try:
            cache.set_value(key, verification_code, ttl)
        except ConnectionError as exc:
            logger.error(f"Redis 服务不可用: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Redis 服务不可用，请启动 Redis 后重试"
            )

        # 邮箱 → 尝试发送邮件，DEV_MODE 跳过
        if "@" in target:
            if os.getenv("DEV_MODE") != "true":
                verification_url = f"{FRONTEND_URL}/verify-email?code={verification_code}&email={target}"
                email_service.send_verification_email(target, verification_code, verification_url)
            msg = f"验证码 {verification_code} 已发送到邮箱，请查收"
            print(f"[DEV] 邮箱 {target} 验证码: {verification_code}")
            return {"message": msg, "expires_in": ttl}
        else:
            # 手机号 — 开发模式打印到控制台
            print(f"[DEV] 手机号 {target} 验证码: {verification_code}")
            return {
                "message": "验证码已发送（开发模式请查看后端日志）",
                "expires_in": ttl
            }

    @staticmethod
    def verify_code(target: str, code: str):
        """
        校验验证码 — 同时检查 email 和 phone 两种 key
        - 成功后删除 Redis 中的验证码
        """
        # 兼容旧 key 名
        keys_to_check = [f"verification:{target}", f"email_verification:{target}"]
        stored = None
        found_key = None
        try:
            for k in keys_to_check:
                stored = cache.get_value(k)
                if stored:
                    found_key = k
                    break
        except ConnectionError as exc:
            raise HTTPException(status_code=503, detail="Redis 不可用")

        if not stored:
            raise HTTPException(status_code=400, detail="验证码已过期，请重新获取")

        if stored != code:
            raise HTTPException(status_code=400, detail="验证码错误")

        try:
            cache.delete_key(found_key)
        except ConnectionError:
            logger.warning(f"无法删除验证码 {target}")

    @staticmethod
    def verify_email(db: Session, email: str, code: str):
        """
        验证邮箱
        
        Args:
            db: 数据库会话
            email: 用户邮箱
            code: 验证码
        
        Returns:
            dict: { "message": "邮箱验证成功" }
        """
        # 检查用户是否存在
        user = crud.get_user_by_email(db, email=email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在"
            )
        
        # 检查验证码是否正确
        try:
            stored_code = cache.get_value(f"email_verification:{email}")
        except ConnectionError as exc:
            logger.error(f"Redis 服务不可用: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Redis 服务不可用，请启动 Redis 后重试"
            )
        if not stored_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="验证码已过期，请重新申请"
            )
        
        if stored_code != code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="验证码错误"
            )
        
        # 删除已使用的验证码
        try:
            cache.delete_key(f"email_verification:{email}")
        except ConnectionError as exc:
            logger.warning(f"无法删除邮箱验证码缓存: {exc}")
        
        # 更新用户的邮箱验证状态
        user.is_email_verified = True
        user.email_verified_at = datetime.now(timezone.utc)
        
        try:
            db.commit()
            db.refresh(user)
            logger.info(f"✅ 用户邮箱验证成功: {email}")
        except Exception as e:
            db.rollback()
            logger.error(f"邮箱验证数据库错误: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="验证失败，请稍后重试"
            )
        
        return {
            "message": "邮箱验证成功",
            "email": user.email,
            "is_email_verified": user.is_email_verified
        }

    @staticmethod
    def send_password_reset(db: Session, email: str):
        """
        发送重置密码邮件
        """
        user = crud.get_user_by_email(db, email=email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在"
            )

        reset_token = secrets.token_hex(32)
        ttl = PASSWORD_RESET_EXPIRE_MINUTES * 60
        try:
            cache.set_value(f"password_reset:{reset_token}", email, ttl)
        except ConnectionError as exc:
            logger.error(f"Redis 服务不可用: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Redis 服务不可用，请启动 Redis 后重试"
            )

        reset_url = f"{FRONTEND_URL}/reset-password?token={reset_token}"
        success = email_service.send_password_reset_email(
            to_email=email,
            reset_token=reset_token,
            frontend_url=reset_url
        )

        if not success:
            # 开发/测试模式：SMTP 不可用时，将 token 返回给前端（生产环境需删除此行）
            logger.warning(f"邮件发送失败，开发模式返回 token: user={email}, token={reset_token}")
            return {
                "message": "重置密码链接已发送到您的邮箱，请在 30 分钟内完成重置",
                "expires_in": ttl,
                "dev_reset_token": reset_token,  # 仅开发模式
            }

        return {
            "message": "重置密码链接已发送到您的邮箱，请在 30 分钟内完成重置",
            "expires_in": ttl
        }

    @staticmethod
    def reset_password(db: Session, reset_token: str, new_password: str):
        """
        使用重置 Token 重置密码
        """
        try:
            email = cache.get_value(f"password_reset:{reset_token}")
        except ConnectionError as exc:
            logger.error(f"Redis 服务不可用: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Redis 服务不可用，请启动 Redis 后重试"
            )
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="重置链接已失效或无效，请重新申请"
            )

        user = crud.get_user_by_email(db, email=email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在"
            )

        if verify_password(new_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="新密码不能与旧密码相同"
            )

        user.password_hash = get_password_hash(new_password)
        try:
            db.commit()
            db.refresh(user)
        except Exception as e:
            db.rollback()
            logger.error(f"重置密码数据库错误: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="密码重置失败，请稍后重试"
            )

        try:
            cache.delete_key(f"password_reset:{reset_token}")
        except ConnectionError as exc:
            logger.warning(f"无法删除密码重置缓存: {exc}")

        # 使该用户所有旧会话失效
        try:
            keys = cache.scan_keys("auth:token:*")
        except ConnectionError as exc:
            logger.warning(f"无法扫描 Redis 会话键: {exc}")
            keys = []

        for key in keys:
            try:
                data = cache.get_value(key)
                if data:
                    payload = json.loads(data)
                    if payload.get("user_id") == user.id:
                        cache.delete_key(key)
            except Exception:
                continue

        return {
            "message": "密码重置成功，请使用新密码登录",
            "email": user.email
        }

    @staticmethod
    def logout(db: Session, token: str):
        """
        删除 Redis 中的当前会话 Token
        """
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="未提供登录 Token"
            )

        try:
            if cache.get_session(token):
                cache.delete_key(f"auth:token:{token}")
        except ConnectionError as exc:
            logger.error(f"Redis 服务不可用: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Redis 服务不可用，请启动 Redis 后重试"
            )

        return {
            "message": "已退出登录，当前会话已从 Redis 移除"
        }

    @staticmethod
    def refresh_token(db: Session, old_token: str):
        """
        刷新 Token
        
        流程：
        1. 验证旧 Token 是否有效
        2. 从 Redis 获取用户信息
        3. 生成新 Token
        4. 将用户信息存入 Redis（新 Token 作为 key）
        5. 删除旧 Token
        
        Args:
            db: 数据库会话
            old_token: 旧 Token
        
        Returns:
            dict: { "access_token": "新token", "token_type": "bearer", "expires_in": ... }
        """
        # 1. 从 Redis 获取用户信息
        user_data = cache.get_session(old_token)
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token 已过期或无效，请重新登录"
            )
        
        # 2. 检查用户是否仍然存在于数据库（防止用户被删除但 Token 仍有效的情况）
        user = db.query(User).filter(User.id == user_data["user_id"]).first()
        if not user or not user.is_active:
            # 删除失效的 Token
            try:
                cache.delete_key(f"auth:token:{old_token}")
            except ConnectionError as exc:
                logger.warning(f"无法删除旧 Token 缓存: {exc}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户已被禁用或删除，请重新登录"
            )
        
        # 3. 生成新 Token
        new_token = secrets.token_hex(16)
        
        # 4. 更新用户数据中的时间戳，保持原有结构
        updated_user_data = user_data.copy()
        
        # 计算 TTL（秒）
        ttl = ACCESS_TOKEN_EXPIRE_MINUTES * 60
        
        # 5. 将用户信息存入 Redis，使用新 Token 作为 key
        try:
            cache.set_session(new_token, updated_user_data, ttl=ttl)
        except ConnectionError as exc:
            logger.error(f"Redis 服务不可用: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Redis 服务不可用，请启动 Redis 后重试"
            )

        # 6. 删除旧 Token（可选：也可保留旧 Token 一段时间以便兼容）
        try:
            cache.delete_key(f"auth:token:{old_token}")
        except ConnectionError as exc:
            logger.warning(f"无法删除旧 Token 缓存: {exc}")
        
        logger.info(f"✅ Token 刷新成功: 用户 ID = {user_data['user_id']}")
        
        return {
            "access_token": new_token,
            "token_type": "bearer",
            "expires_in": ttl,
            "message": "Token 刷新成功"
        }

    @staticmethod
    def _invalidate_user_tokens(user_id: int, preserve_token: str = None):
        """根据 user_id 清理 Redis 中该用户的旧 Token"""
        try:
            keys = cache.scan_keys("auth:token:*")
        except ConnectionError as exc:
            logger.warning(f"Redis 服务不可用，无法扫描 Token: {exc}")
            return

        for key in keys:
            try:
                data = cache.get_value(key)
                if not data:
                    continue
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if payload.get("user_id") == user_id:
                    if preserve_token and key == f"auth:token:{preserve_token}":
                        continue
                    try:
                        cache.delete_key(key)
                    except ConnectionError as exc:
                        logger.warning(f"无法删除 Token 键 {key}: {exc}")
            except ConnectionError as exc:
                logger.warning(f"无法读取 Redis Token 键 {key}: {exc}")
                continue

    @staticmethod
    def change_password(db: Session, user_id: int, old_password: str, new_password: str, current_token: str = None):
        """
        修改用户密码
        
        流程：
        1. 获取用户信息
        2. 验证旧密码是否正确
        3. 哈希新密码
        4. 更新数据库
        5. 删除所有旧 Token（使用户在其他设备上登出）
        
        Args:
            db: 数据库会话
            user_id: 用户 ID
            old_password: 旧密码（明文）
            new_password: 新密码（明文）
            current_token: 当前使用的 Token（可选，用于保留当前会话）
        
        Returns:
            dict: { "message": "密码修改成功", "email": "xxx" }
        """
        # 1. 获取用户信息
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在"
            )
        
        # 2. 验证旧密码
        if not verify_password(old_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="旧密码错误"
            )
        
        # 防止新密码与旧密码相同
        if old_password == new_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="新密码不能与旧密码相同"
            )
        
        # 3. 哈希新密码
        new_password_hash = get_password_hash(new_password)
        
        # 4. 更新数据库
        user.password_hash = new_password_hash
        user.updated_at = datetime.now(timezone.utc)
        
        try:
            db.commit()
            db.refresh(user)
            logger.info(f"✅ 用户密码修改成功: ID = {user_id}")
        except Exception as e:
            db.rollback()
            logger.error(f"修改密码数据库错误: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="密码修改失败，请稍后重试"
            )
        
        # 5. 删除所有旧 Token（使用户在其他设备上登出）
        # 这是为了安全起见，防止已盗取的 Token 继续被使用
        try:
            AuthManager._invalidate_user_tokens(user_id, preserve_token=current_token)
            if current_token:
                logger.info(f"✅ 保留当前 Token，其他会话已失效")
            logger.info(f"✅ 用户所有旧 Token 已失效: ID = {user_id}")
        except Exception as e:
            logger.warning(f"清理 Token 失败（非关键）: {str(e)}")
        
        return {
            "message": "密码修改成功，请使用新密码重新登录其他设备",
            "email": user.email
        }

    @staticmethod
    def delete_account(db: Session, user_id: int):
        """
        注销账号并删除关联数据。

        主流程：
        1. 删除与用户相关的业务数据和用户主记录
        2. 提交数据库事务
        3. 失效用户的所有 token
        4. 删除 Dify 知识库（弱依赖，失败不阻断）
        """
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在"
            )

        email = user.email
        dataset_id = user.dataset_id

        try:
            # 1. 删除与用户相关的业务数据（FK 安全顺序：子表 → 父表）
            #
            # 阶段 1 — 清理引用 documents / document_segments 的子表
            #   QuestionProvenance FK → documents.id / document_segments.id
            #   UserQuestionRef   FK → documents.id / document_segments.id
            #   TutorSession      FK → documents.id / document_segments.id / quiz_answers.id
            document_ids = [doc_id for (doc_id,) in db.query(Document.id).filter(Document.user_id == user_id).all()]
            if document_ids:
                # 1a. question_provenance（FK → documents / document_segments）— 之前完全遗漏
                db.query(QuestionProvenance).filter(
                    QuestionProvenance.document_id.in_(document_ids)
                ).delete(synchronize_session=False)
                segment_ids = [s_id for (s_id,) in db.query(DocumentSegment.id)
                               .filter(DocumentSegment.document_id.in_(document_ids)).all()]
                if segment_ids:
                    db.query(QuestionProvenance).filter(
                        QuestionProvenance.segment_id.in_(segment_ids)
                    ).delete(synchronize_session=False)

                # QuestionTag.document_id 也引用 documents，必须在删除文档前清理。
                # 按 document_id 删除还能处理历史上 user_id 与文档归属不一致的数据。
                db.query(QuestionTag).filter(
                    QuestionTag.document_id.in_(document_ids)
                ).delete(synchronize_session=False)

            # 无文档关联的用户标签仍需在删除用户主记录前清理。
            db.query(QuestionTag).filter(
                QuestionTag.user_id == user_id
            ).delete(synchronize_session=False)

            # 1b. 这两张表直接归属用户，按 user_id 清理可避免未来可空引用造成遗漏
            db.query(UserQuestionRef).filter(
                UserQuestionRef.user_id == user_id
            ).delete(synchronize_session=False)
            db.query(TutorSession).filter(
                TutorSession.user_id == user_id
            ).delete(synchronize_session=False)

            # 阶段 2 — 先清理 quiz 链路；QuizSession 仍引用 Document / KbCollection
            quiz_session_ids = [s_id for (s_id,) in db.query(QuizSession.id).filter(QuizSession.user_id == user_id).all()]
            if quiz_session_ids:
                # 2a. training_plans（FK → quiz_sessions）
                db.query(TrainingPlan).filter(TrainingPlan.user_id == user_id).delete(synchronize_session=False)
                # 2b. quiz_answers（FK → quiz_sessions / global_questions）
                db.query(QuizAnswer).filter(QuizAnswer.user_id == user_id).delete(synchronize_session=False)
                # 2c. quiz_session_questions（FK → quiz_sessions）
                db.query(QuizSessionQuestion).filter(
                    QuizSessionQuestion.session_id.in_(quiz_session_ids)
                ).delete(synchronize_session=False)
            db.query(QuizSession).filter(QuizSession.user_id == user_id).delete(synchronize_session=False)

            # 阶段 3 — quiz 引用已清理，再删除文档、分区及其直接子表
            if document_ids:
                db.query(DocumentSegment).filter(
                    DocumentSegment.document_id.in_(document_ids)
                ).delete(synchronize_session=False)
            db.query(UserNote).filter(UserNote.user_id == user_id).delete(synchronize_session=False)
            db.query(Document).filter(Document.user_id == user_id).delete(synchronize_session=False)
            db.query(KbCollection).filter(KbCollection.user_id == user_id).delete(synchronize_session=False)

            # 阶段 4 — 其余独立表（无 FK 到上述已清理表）+ 用户主记录
            db.query(OnboardingState).filter(OnboardingState.user_id == user_id).delete(synchronize_session=False)

            # 4. 删除用户主记录
            db.delete(user)
            db.commit()
            logger.info(f"✅ 用户账号注销成功: ID = {user_id}")
        except Exception as e:
            db.rollback()
            constraint_info = ""
            if hasattr(e, 'orig') and hasattr(e.orig, 'args') and e.orig.args:
                constraint_info = f" | MySQL detail: {e.orig.args[0] if e.orig.args else ''}"
            logger.error(
                f"注销账号失败 | user_id={user_id} | type={type(e).__name__} | "
                f"message={str(e)}{constraint_info}"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="注销账号失败，请稍后重试"
            )

        # 数据库提交成功后再执行不可回滚的外部副作用，避免回滚后出现部分注销。
        try:
            AuthManager._invalidate_user_tokens(user_id)
            logger.info(f"✅ 用户所有 Token 已失效: ID = {user_id}")
        except Exception as e:
            logger.warning(f"清理用户 Token 失败（账号已注销）: {e}")

        if dataset_id:
            try:
                DifyKB.delete_dataset(dataset_id)
            except Exception as e:
                logger.warning(f"删除 Dify 知识库失败（账号已注销）: {e}")

        return {
            "message": "账号已注销"
        }

