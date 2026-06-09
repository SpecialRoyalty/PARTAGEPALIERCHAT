import json
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from app.models import BotUser, Group, InviteLink, Invite, InviteStatus, BannedWord, RewardTier, UserReward
from app.config import settings


def user_label(user: BotUser | None) -> str:
    if not user:
        return "Utilisateur"
    if user.username:
        return f"@{user.username}"
    if user.first_name:
        return user.first_name
    return str(user.telegram_user_id)


async def get_or_create_user(session: AsyncSession, tg_user) -> BotUser:
    q = await session.execute(select(BotUser).where(BotUser.telegram_user_id == tg_user.id))
    user = q.scalar_one_or_none()
    if user:
        user.username = tg_user.username
        user.first_name = tg_user.first_name
        return user
    user = BotUser(telegram_user_id=tg_user.id, username=tg_user.username, first_name=tg_user.first_name)
    session.add(user)
    await session.flush()
    return user


async def get_or_create_group(session: AsyncSession, chat) -> Group:
    q = await session.execute(select(Group).where(Group.telegram_chat_id == chat.id))
    group = q.scalar_one_or_none()
    if group:
        group.title = chat.title
        return group
    from app.models import GroupStatus
    group = Group(telegram_chat_id=chat.id, title=chat.title, status=GroupStatus.pending)
    session.add(group)
    await session.flush()
    return group


async def notify_admins(bot: Bot, text: str, reply_markup=None):
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, text, reply_markup=reply_markup)
        except Exception:
            pass


async def is_name_banned(session: AsyncSession, username: str | None, first_name: str | None) -> str | None:
    value = f"{username or ''} {first_name or ''}".lower()
    q = await session.execute(select(BannedWord))
    for row in q.scalars().all():
        if row.word.lower() in value:
            return row.word
    return None


async def valid_invite_count(session: AsyncSession, user_id: int, group_id: int) -> int:
    q = await session.execute(select(func.count(Invite.id)).where(
        Invite.inviter_user_id == user_id,
        Invite.group_id == group_id,
        Invite.status == InviteStatus.valid
    ))
    return int(q.scalar() or 0)


async def next_tier(session: AsyncSession, count: int) -> RewardTier | None:
    q = await session.execute(
        select(RewardTier)
        .where(RewardTier.required_invites > count)
        .order_by(RewardTier.required_invites.asc())
        .limit(1)
    )
    return q.scalar_one_or_none()


async def score_text(session: AsyncSession, user: BotUser, group: Group, invite_link: str | None = None) -> str:
    count = await valid_invite_count(session, user.id, group.id)
    tier = await next_tier(session, count)
    if tier:
        remaining = tier.required_invites - count
        next_part = f"🎯 Prochain palier : {tier.required_invites} invité(s)\n⏳ Il t'en manque : {remaining}"
    else:
        next_part = "🏆 Tous les paliers sont débloqués."
    link_part = f"\n\n🔗 Ton lien :\n{invite_link}" if invite_link else ""
    return (
        "🏆 Ton tableau de bord\n\n"
        f"✅ Invités validés : {count}\n"
        f"{next_part}"
        f"{link_part}\n\n"
        "🔥 Continue à partager ton lien pour débloquer plus de médias."
    )


async def get_or_create_invite_link(session: AsyncSession, bot: Bot, group: Group, user: BotUser) -> InviteLink:
    q = await session.execute(select(InviteLink).where(
        InviteLink.group_id == group.id,
        InviteLink.inviter_user_id == user.id
    ))
    link = q.scalar_one_or_none()
    if link:
        return link

    created = await bot.create_chat_invite_link(
        chat_id=group.telegram_chat_id,
        name=f"user_{user.telegram_user_id}_group_{group.telegram_chat_id}",
        creates_join_request=False
    )
    link = InviteLink(group_id=group.id, inviter_user_id=user.id, invite_link=created.invite_link)
    session.add(link)
    await session.flush()
    return link


async def notify_inviter_join_detected(bot: Bot, inviter: BotUser, invited: BotUser, group: Group):
    try:
        await bot.send_message(
            inviter.telegram_user_id,
            "👀 Nouvelle personne détectée avec ton lien.\n\n"
            f"👤 {user_label(invited)}\n"
            f"📍 Groupe : {group.title}\n\n"
            "⏳ Validation en cours..."
        )
    except Exception:
        pass


async def notify_inviter_validated(session: AsyncSession, bot: Bot, inviter: BotUser, invited: BotUser, group: Group):
    count = await valid_invite_count(session, inviter.id, group.id)
    tier = await next_tier(session, count)
    if tier:
        remaining = tier.required_invites - count
        line = f"🔥 Plus que {remaining} invité(s) pour débloquer le prochain pack."
    else:
        line = "🏆 Tu as atteint le plus haut niveau."

    try:
        await bot.send_message(
            inviter.telegram_user_id,
            "✅ Invitation validée.\n\n"
            f"👤 {user_label(invited)}\n"
            f"📈 Score : {count} invité(s) validé(s)\n\n"
            f"{line}"
        )
    except Exception:
        pass


async def send_due_rewards(session: AsyncSession, bot: Bot, user: BotUser, group: Group):
    count = await valid_invite_count(session, user.id, group.id)
    q = await session.execute(select(RewardTier).where(RewardTier.required_invites <= count).order_by(RewardTier.required_invites))
    tiers = q.scalars().all()

    for tier in tiers:
        q2 = await session.execute(select(UserReward).where(UserReward.user_id == user.id, UserReward.tier_id == tier.id))
        if q2.scalar_one_or_none():
            continue

        session.add(UserReward(user_id=user.id, tier_id=tier.id))
        await session.flush()

        if tier.required_invites >= 1000:
            await bot.send_message(
                user.telegram_user_id,
                "🏆 VIP gratuit à vie débloqué.\n\n"
                "Un admin va te contacter pour l'activation."
            )
            await notify_admins(
                bot,
                f"🏆 VIP À VIE débloqué\nUser: {user.telegram_user_id} {user_label(user)}\nGroupe: {group.title}"
            )
        else:
            await bot.send_message(
                user.telegram_user_id,
                "🎉 Félicitations !\n\n"
                f"Tu viens d'atteindre {tier.required_invites} invité(s) validé(s).\n"
                f"🎁 Récompense débloquée : {tier.media_count} média(s)\n\n"
                f"🔗 Lien :\n{tier.gofile_link}\n\n"
                "Continue : le prochain palier est encore plus gros."
            )
