import enum
from datetime import datetime
from sqlalchemy import (
    BigInteger, String, Text, DateTime, ForeignKey, Integer, Boolean,
    UniqueConstraint, Enum
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class GroupStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class InviteStatus(str, enum.Enum):
    pending = "pending"
    valid = "valid"
    invalid = "invalid"
    banned = "banned"


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    title: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[GroupStatus] = mapped_column(Enum(GroupStatus), default=GroupStatus.pending)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BotUser(Base):
    __tablename__ = "bot_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(255))
    active_group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), default="Campagne")
    text: Mapped[str] = mapped_column(Text)
    photo_file_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    button_text: Mapped[str] = mapped_column(String(120), default="🎁 Recevoir des médias")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class CampaignGroup(Base):
    __tablename__ = "campaign_groups"
    __table_args__ = (UniqueConstraint("campaign_id", "group_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"))
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"))


class InviteLink(Base):
    __tablename__ = "invite_links"
    __table_args__ = (UniqueConstraint("group_id", "inviter_user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"))
    inviter_user_id: Mapped[int] = mapped_column(ForeignKey("bot_users.id"))
    invite_link: Mapped[str] = mapped_column(String(700), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Invite(Base):
    __tablename__ = "invites"
    __table_args__ = (UniqueConstraint("group_id", "invited_user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"))
    inviter_user_id: Mapped[int] = mapped_column(ForeignKey("bot_users.id"))
    invited_user_id: Mapped[int] = mapped_column(ForeignKey("bot_users.id"))
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[InviteStatus] = mapped_column(Enum(InviteStatus), default=InviteStatus.pending)


class RewardTier(Base):
    __tablename__ = "reward_tiers"

    id: Mapped[int] = mapped_column(primary_key=True)
    required_invites: Mapped[int] = mapped_column(Integer, unique=True)
    media_count: Mapped[int] = mapped_column(Integer)
    gofile_link: Mapped[str] = mapped_column(String(1000))
    title: Mapped[str] = mapped_column(String(255), default="")


class UserReward(Base):
    __tablename__ = "user_rewards"
    __table_args__ = (UniqueConstraint("user_id", "tier_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("bot_users.id"))
    tier_id: Mapped[int] = mapped_column(ForeignKey("reward_tiers.id"))
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BannedWord(Base):
    __tablename__ = "banned_words"

    id: Mapped[int] = mapped_column(primary_key=True)
    word: Mapped[str] = mapped_column(String(255), unique=True)


class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True)
