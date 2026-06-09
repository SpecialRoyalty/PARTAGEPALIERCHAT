from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Bot
from app.models import (
    BotUser, Group, GroupStatus, InviteLink, Invite, InviteStatus,
    BannedWord, RewardTier, UserReward
)
from app.config import settings


async def get_or_create_user(session: AsyncSession, tg_user) -> BotUser:
    q = await session.execute(select(BotUser).where(BotUser.telegram_user_id == tg_user.id))
    user = q.scalar_one_or_none()
    if user:
        user.username = tg_user.username
        user.first_name = tg_user.first_name
        return user

    user = BotUser(
        telegram_user_id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
    )
    session.add(user)
    await session.flush()
    return user


async def get_or_create_group(session: AsyncSession, chat) -> Group:
    q = await session.execute(select(Group).where(Group.telegram_chat_id == chat.id))
    group = q.scalar_one_or_none()
    if group:
        group.title = chat.title
        return group

    group = Group(telegram_chat_id=chat.id, title=chat.title, status=GroupStatus.pending)
    session.add(group)
    await session.flush()
    return group


async def is_name_banned(session: AsyncSession, username: str | None, first_name: str | None) -> str | None:
    value = f"{username or ''} {first_name or ''}".lower()
    q = await session.execute(select(BannedWord))
    for row in q.scalars().all():
        if row.word.lower() in value:
            return row.word
    return None


async def valid_invite_count(session: AsyncSession, user_id: int, group_id: int) -> int:
    q = await session.execute(
        select(func.count(Invite.id)).where(
            Invite.inviter_user_id == user_id,
            Invite.group_id == group_id,
            Invite.status == InviteStatus.valid,
        )
    )
    return int(q.scalar() or 0)


async def get_or_create_invite_link(session: AsyncSession, bot: Bot, group: Group, user: BotUser) -> InviteLink:
    q = await session.execute(
        select(InviteLink).where(
            InviteLink.group_id == group.id,
            InviteLink.inviter_user_id == user.id,
        )
    )
    link = q.scalar_one_or_none()
    if link:
        return link

    created = await bot.create_chat_invite_link(
        chat_id=group.telegram_chat_id,
        name=f"user_{user.telegram_user_id}_group_{group.telegram_chat_id}",
        creates_join_request=False,
    )
    link = InviteLink(
        group_id=group.id,
        inviter_user_id=user.id,
        invite_link=created.invite_link,
    )
    session.add(link)
    await session.flush()
    return link


async def notify_admins(bot: Bot, text: str):
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            pass


async def send_due_rewards(session: AsyncSession, bot: Bot, user: BotUser, group: Group):
    count = await valid_invite_count(session, user.id, group.id)

    q = await session.execute(
        select(RewardTier).where(RewardTier.required_invites <= count).order_by(RewardTier.required_invites)
    )
    tiers = q.scalars().all()

    for tier in tiers:
        already = await session.execute(
            select(UserReward).where(UserReward.user_id == user.id, UserReward.tier_id == tier.id)
        )
        if already.scalar_one_or_none():
            continue

        session.add(UserReward(user_id=user.id, tier_id=tier.id))
        await session.flush()

        if tier.required_invites >= 1000:
            await bot.send_message(
                user.telegram_user_id,
                "🏆 Incroyable. Tu viens de débloquer le VIP gratuit à vie.\n\n"
                "Un admin va te contacter pour l’activation. Garde tes messages ouverts."
            )
            await notify_admins(
                bot,
                f"🏆 VIP À VIE débloqué\nUser: {user.telegram_user_id} @{user.username}\nGroupe: {group.title}"
            )
        else:
            await bot.send_message(
                user.telegram_user_id,
                f"🎉 Palier débloqué : {tier.required_invites} invité(s) validé(s)\n"
                f"🎬 Récompense : {tier.media_count} média(s)\n\n"
                f"Ton accès : {tier.gofile_link}\n\n"
                "Continue, les prochains paliers sont encore plus gros."
            )
