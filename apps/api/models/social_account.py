import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.config.database import Base


class SocialPlatform(str, enum.Enum):
    LINKEDIN = "linkedin"
    INSTAGRAM = "instagram"
    THREADS = "threads"
    FACEBOOK = "facebook"
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"
    PINTEREST = "pinterest"


class SocialAccountStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class SocialAccount(Base):
    __tablename__ = "social_accounts"
    __table_args__ = (
        # One connection per platform per brand — reconnecting overwrites
        # the existing row rather than accumulating stale duplicates.
        UniqueConstraint("brand_id", "platform", name="uq_social_accounts_brand_platform"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id"), nullable=False
    )
    platform: Mapped[SocialPlatform] = mapped_column(
        Enum(SocialPlatform, name="social_platform"), nullable=False
    )
    external_account_id: Mapped[str | None] = mapped_column(nullable=True)

    # Never stored plaintext — always the Fernet ciphertext returned by
    # packages.integrations.social.encryption.encrypt_token(). Nullable so
    # disconnect can wipe both token columns rather than leaving a dead
    # connection's ciphertext sitting in the table.
    access_token_encrypted: Mapped[str | None] = mapped_column(nullable=True)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scopes: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    status: Mapped[SocialAccountStatus] = mapped_column(
        Enum(SocialAccountStatus, name="social_account_status"),
        nullable=False,
        default=SocialAccountStatus.ACTIVE,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
