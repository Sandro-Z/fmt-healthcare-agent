from __future__ import annotations

import os
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, text

from wgs_fmt_platform.infrastructure.database import AuthSession, DATABASE_URL, Conversation, Message, SessionLocal, User, create_schema, engine, hash_password, verify_password
from wgs_fmt_platform.infrastructure.memory import RedisMemoryStore
from wgs_fmt_platform.infrastructure.search import HybridKnowledgeSearch

router = APIRouter(tags=["backend-infrastructure"])


class UserCreate(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]{2,79}$")
    email: EmailStr
    password: str = Field(min_length=10, max_length=256)
    display_name: str = Field(default="", max_length=120)
    role: str = Field(default="researcher", pattern="^(admin|researcher|viewer)$")


class LoginPayload(BaseModel):
    identity: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=256)


class RoleUpdate(BaseModel):
    role: str = Field(pattern="^(admin|researcher|viewer)$")


class MemoryCreate(BaseModel):
    user_id: str
    conversation_id: str = ""
    scope: str = Field(default="short", pattern="^(short|long)$")
    content: str = Field(min_length=1, max_length=100_000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    vector: list[float] | None = None
    limit: int = Field(default=10, ge=1, le=50)


class IndexDocumentRequest(BaseModel):
    document_id: str = Field(min_length=1, max_length=255)
    title: str = Field(default="", max_length=1000)
    content: str = Field(min_length=1)
    source: str = Field(default="manual", max_length=100)
    embedding: list[float] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationCreate(BaseModel):
    agent_id: str = Field(default="", max_length=80)
    title: str = Field(default="新对话", max_length=255)
    user_id: str = Field(default="", max_length=36)


def _user(user: User) -> dict[str, Any]:
    return {"id": user.id, "username": user.username, "email": user.email, "display_name": user.display_name, "role": user.role, "is_active": user.is_active, "created_at": user.created_at}


def _new_session(session, user: User) -> dict[str, Any]:
    token = secrets.token_urlsafe(40)
    session.add(AuthSession(user_id=user.id, token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at=datetime.now(UTC) + timedelta(days=7)))
    session.commit()
    return {"access_token": token, "token_type": "bearer", "expires_in": 604800, "user": _user(user)}


def _authenticated_user(authorization: str | None) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "请先登录。")
    token_hash = hashlib.sha256(authorization.split(" ", 1)[1].strip().encode()).hexdigest()
    with SessionLocal() as session:
        auth_session = session.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash))
        if auth_session is None:
            raise HTTPException(401, "登录状态无效，请重新登录。")
        expires_at = auth_session.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            session.delete(auth_session); session.commit()
            raise HTTPException(401, "登录已过期，请重新登录。")
        user = session.get(User, auth_session.user_id)
        if user is None or not user.is_active:
            raise HTTPException(403, "账号已停用。")
        session.expunge(user)
        return user


def ensure_local_user(session) -> User:
    user = session.scalar(select(User).where(User.username == "local-researcher"))
    if user is None:
        user = User(username="local-researcher", email="local@wgs-fmt.invalid", password_hash=hash_password(os.urandom(24).hex()), display_name="研究员")
        session.add(user)
        session.flush()
    return user


def _conversation(row: Conversation, *, include_messages: bool = False) -> dict[str, Any]:
    value = {"id": row.id, "user_id": row.user_id, "title": row.title, "agent_id": row.agent_id, "status": row.status, "created_at": row.created_at, "updated_at": row.updated_at, "message_count": len(row.messages)}
    if include_messages:
        value["messages"] = [{"id": item.id, "role": item.role, "content": item.content, "model": item.model, "trace": item.trace or {}, "created_at": item.created_at} for item in row.messages]
    return value


@router.get("/health")
def infrastructure_health() -> dict[str, Any]:
    status: dict[str, Any] = {}
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        status["database"] = {"ok": True, "driver": engine.url.drivername, "url": DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL}
    except Exception as exc:
        status["database"] = {"ok": False, "error": str(exc)}
    try:
        status["redis"] = {"ok": bool(RedisMemoryStore().client.ping())}
    except Exception as exc:
        status["redis"] = {"ok": False, "error": str(exc)}
    try:
        status["elasticsearch"] = {"ok": bool(HybridKnowledgeSearch().client.ping())}
    except Exception as exc:
        status["elasticsearch"] = {"ok": False, "error": str(exc)}
    return {"ok": all(item["ok"] for item in status.values()), "services": status}


@router.post("/schema/initialize")
def initialize_schema() -> dict[str, Any]:
    try:
        create_schema()
        HybridKnowledgeSearch().ensure_index()
        return {"status": "initialized", "mysql_tables": sorted(User.metadata.tables), "elasticsearch_index": HybridKnowledgeSearch().index}
    except Exception as exc:
        raise HTTPException(503, f"基础设施初始化失败：{exc}") from exc


@router.post("/users", status_code=201)
def create_user(payload: UserCreate, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    actor = _authenticated_user(authorization)
    if actor.role != "admin":
        raise HTTPException(403, "仅管理员可创建指定分组的账号。")
    with SessionLocal() as session:
        if session.scalar(select(User).where((User.username == payload.username) | (User.email == str(payload.email)))):
            raise HTTPException(409, "用户名或邮箱已经存在。")
        user = User(username=payload.username, email=str(payload.email), password_hash=hash_password(payload.password), display_name=payload.display_name, role=payload.role)
        session.add(user)
        session.commit()
        session.refresh(user)
        return _user(user)


@router.post("/auth/register", status_code=201)
def register(payload: UserCreate) -> dict[str, Any]:
    with SessionLocal() as session:
        if session.scalar(select(User).where((User.username == payload.username) | (User.email == str(payload.email)))):
            raise HTTPException(409, "用户名或邮箱已经存在。")
        has_real_user = session.scalar(select(User.id).where(~User.email.like("%.invalid")).limit(1)) is not None
        role = "researcher" if has_real_user else "admin"
        user = User(username=payload.username, email=str(payload.email), password_hash=hash_password(payload.password), display_name=payload.display_name, role=role)
        session.add(user); session.flush()
        return _new_session(session, user)


@router.post("/auth/login")
def login(payload: LoginPayload) -> dict[str, Any]:
    with SessionLocal() as session:
        user = session.scalar(select(User).where((User.username == payload.identity) | (User.email == payload.identity)))
        if user is None or not verify_password(payload.password, user.password_hash):
            raise HTTPException(401, "用户名、邮箱或密码不正确。")
        if not user.is_active:
            raise HTTPException(403, "账号已停用。")
        return _new_session(session, user)


@router.get("/auth/me")
def current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return _user(_authenticated_user(authorization))


@router.post("/auth/logout")
def logout(authorization: str | None = Header(default=None)) -> dict[str, bool]:
    if authorization and authorization.lower().startswith("bearer "):
        token_hash = hashlib.sha256(authorization.split(" ", 1)[1].strip().encode()).hexdigest()
        with SessionLocal() as session:
            auth_session = session.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash))
            if auth_session is not None:
                session.delete(auth_session); session.commit()
    return {"logged_out": True}


@router.get("/auth/users")
def authenticated_users(authorization: str | None = Header(default=None), limit: int = 200) -> dict[str, Any]:
    actor = _authenticated_user(authorization)
    if actor.role != "admin":
        raise HTTPException(403, "仅管理员可查看用户目录。")
    with SessionLocal() as session:
        users = session.scalars(select(User).where(~User.email.like("%.invalid")).order_by(User.created_at.desc()).limit(min(500, max(1, limit)))).all()
        return {"users": [_user(user) for user in users], "count": len(users)}


@router.patch("/auth/users/{user_id}/role")
def update_user_role(user_id: str, payload: RoleUpdate, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    actor = _authenticated_user(authorization)
    if actor.role != "admin":
        raise HTTPException(403, "仅管理员可调整用户分组。")
    if actor.id == user_id and payload.role != "admin":
        raise HTTPException(422, "不能取消自己的管理员权限。")
    with SessionLocal() as session:
        user = session.get(User, user_id)
        if user is None:
            raise HTTPException(404, "用户不存在。")
        user.role = payload.role; session.commit(); session.refresh(user)
        return _user(user)


@router.get("/users")
def list_users(limit: int = 100, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    actor = _authenticated_user(authorization)
    if actor.role != "admin":
        raise HTTPException(403, "仅管理员可查看用户目录。")
    with SessionLocal() as session:
        users = session.scalars(select(User).order_by(User.created_at.desc()).limit(min(500, max(1, limit)))).all()
        return {"users": [_user(user) for user in users], "count": len(users)}


@router.get("/conversations")
def list_conversations(limit: int = 100) -> dict[str, Any]:
    create_schema()
    with SessionLocal() as session:
        user = ensure_local_user(session)
        session.commit()
        rows = session.scalars(select(Conversation).where(Conversation.user_id == user.id, Conversation.status == "active").order_by(Conversation.updated_at.desc()).limit(min(200, max(1, limit)))).all()
        return {"conversations": [_conversation(row) for row in rows], "count": len(rows), "database": engine.url.drivername}


@router.post("/conversations", status_code=201)
def create_conversation(payload: ConversationCreate) -> dict[str, Any]:
    create_schema()
    with SessionLocal() as session:
        user = session.get(User, payload.user_id) if payload.user_id else ensure_local_user(session)
        if user is None:
            raise HTTPException(404, "用户不存在。")
        row = Conversation(user_id=user.id, agent_id=payload.agent_id, title=payload.title or "新对话")
        session.add(row)
        session.commit()
        session.refresh(row)
        return _conversation(row, include_messages=True)


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str) -> dict[str, Any]:
    with SessionLocal() as session:
        row = session.get(Conversation, conversation_id)
        if row is None or row.status != "active":
            raise HTTPException(404, "会话不存在。")
        _ = row.messages
        return _conversation(row, include_messages=True)


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str) -> dict[str, Any]:
    with SessionLocal() as session:
        row = session.get(Conversation, conversation_id)
        if row is None:
            raise HTTPException(404, "会话不存在。")
        row.status = "deleted"
        session.commit()
        return {"deleted": True, "id": conversation_id}


@router.post("/memory", status_code=201)
def remember(payload: MemoryCreate) -> dict[str, Any]:
    try:
        return RedisMemoryStore().remember(payload.user_id, payload.content, scope=payload.scope, conversation_id=payload.conversation_id, metadata=payload.metadata)
    except Exception as exc:
        raise HTTPException(503, f"记忆写入失败：{exc}") from exc


@router.get("/memory/{user_id}")
def recall(user_id: str, scope: str = "short", limit: int = 20) -> dict[str, Any]:
    try:
        rows = RedisMemoryStore().recall(user_id, scope=scope, limit=min(100, max(1, limit)))
        return {"user_id": user_id, "scope": scope, "memories": rows}
    except Exception as exc:
        raise HTTPException(503, f"记忆读取失败：{exc}") from exc


@router.post("/knowledge/index", status_code=202)
def index_document(payload: IndexDocumentRequest) -> dict[str, Any]:
    try:
        search = HybridKnowledgeSearch()
        search.ensure_index()
        search.index_document(payload.document_id, title=payload.title, content=payload.content, source=payload.source, embedding=payload.embedding, metadata=payload.metadata)
        return {"status": "accepted", "document_id": payload.document_id, "index": search.index}
    except Exception as exc:
        raise HTTPException(503, f"知识索引失败：{exc}") from exc


@router.post("/knowledge/search")
async def search_knowledge(payload: SearchRequest) -> dict[str, Any]:
    return await HybridKnowledgeSearch().fused_search(payload.query, vector=payload.vector, limit=payload.limit)
