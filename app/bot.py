from datetime import datetime
from sqlalchemy import select
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ChatMemberHandler, CallbackQueryHandler, ContextTypes, filters
from app.config import settings
from app.db import SessionLocal
from app.models import Group, GroupStatus, Campaign, CampaignGroup, InviteLink, Invite, InviteStatus, BotUser
from app.services import (
    get_or_create_user, get_or_create_group, get_or_create_invite_link,
    notify_admins, is_name_banned, valid_invite_count, send_due_rewards,
    notify_inviter_join_detected, notify_inviter_validated, score_text
)
from app.admin_telegram import (
    is_admin, admin_start_message, admin_callback, handle_admin_text,
    handle_campaign_group_selection
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if is_admin(user.id) and not context.args:
        await admin_start_message(update)
        return

    payload = context.args[0] if context.args else None

    async with SessionLocal() as session:
        db_user = await get_or_create_user(session, user)

        if payload and payload.startswith("get_"):
            group_id = int(payload.replace("get_", ""))
            group = await session.get(Group, group_id)

            if not group or group.status != GroupStatus.approved:
                await update.message.reply_text("Ce groupe n’est pas disponible pour le moment.")
                return

            if db_user.active_group_id and db_user.active_group_id != group.id:
                await update.message.reply_text(
                    "⚠️ Tu participes déjà à une mission dans un autre groupe.\n\n"
                    "Termine cette mission avant d’en commencer une nouvelle."
                )
                return

            db_user.active_group_id = group.id
            invite_link = await get_or_create_invite_link(session, context.bot, group, db_user)
            count = await valid_invite_count(session, db_user.id, group.id)
            await session.commit()

            await update.message.reply_text(
                "🎁 Ta mission privée est prête.\n\n"
                "Invite des personnes dans le groupe avec TON lien personnel.\n"
                "Plus tu fais entrer de monde, plus tu débloques de médias.\n\n"
                f"🔗 Ton lien unique :\n{invite_link.invite_link}\n\n"
                f"✅ Invités validés : {count}\n\n"
                "🔥 Paliers disponibles :\n"
                "1 invité = 1 média\n"
                "10 invités = 20 médias\n"
                "50 invités = 100 médias\n"
                "100 invités = 200 médias\n"
                "300 invités = 500 médias\n"
                "500 invités = 1500 médias\n"
                "1000 invités = VIP gratuit à vie\n\n"
                "Conseil : partage ton lien dans tes groupes, stories, canaux et DM. Leakmedia / Tiktok / Discord"
                "UNIQUEMENT DES PERSONNES FR sinon tu seras ban ! "
            )
            return

        await session.commit()

    await update.message.reply_text(
        "Bienvenue 👋\n\n"
        "Clique sur le bouton dans un groupe partenaire pour recevoir ton lien privé."
    )


async def score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with SessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user)
        if not user.active_group_id:
            await update.message.reply_text("Tu n'as pas encore de mission active.")
            await session.commit()
            return

        group = await session.get(Group, user.active_group_id)
        link = await get_or_create_invite_link(session, context.bot, group, user)
        text = await score_text(session, user, group, link.invite_link)
        await session.commit()
        await update.message.reply_text(text)


async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    handled = await handle_admin_text(update, context)
    if handled:
        return


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    if await handle_campaign_group_selection(update, context):
        return

    if query.data and query.data.startswith("adm_"):
        await admin_callback(update, context)
        return


async def count_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not update.message:
        return
    if update.effective_chat.type not in ("group", "supergroup"):
        return

    async with SessionLocal() as session:
        group = await get_or_create_group(session, update.effective_chat)
        if group.status != GroupStatus.approved:
            await session.commit()
            return

        group.message_count += 1
        if group.message_count >= 100:
            group.message_count = 0
            await session.commit()
            await publish_campaign(context, group.id)
        else:
            await session.commit()



async def send_campaign_message(context: ContextTypes.DEFAULT_TYPE, group: Group, campaign: Campaign, delete_after: bool = True):
    bot_username = (await context.bot.get_me()).username
    start_url = f"https://t.me/{bot_username}?start=get_{group.id}"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(campaign.button_text, url=start_url)]])

    commercial_text = (
        f"{campaign.text}\n\n"
        "⚡ Accès privé limité\n"
        "🎬 Débloque tes médias en invitant tes amis\n"
        "🏆 Les meilleurs repartent avec le VIP à vie"
    )

    if campaign.photo_file_id:
        msg = await context.bot.send_photo(
            chat_id=group.telegram_chat_id,
            photo=campaign.photo_file_id,
            caption=commercial_text,
            reply_markup=keyboard
        )
    else:
        msg = await context.bot.send_message(
            chat_id=group.telegram_chat_id,
            text=commercial_text,
            reply_markup=keyboard
        )

    if delete_after:
        context.job_queue.run_once(
            delete_message_job,
            when=20 * 60,
            data={"chat_id": group.telegram_chat_id, "message_id": msg.message_id}
        )


async def publish_campaign(context: ContextTypes.DEFAULT_TYPE, group_id: int):
    """Publication automatique : suppression après 20 minutes."""
    async with SessionLocal() as session:
        group = await session.get(Group, group_id)
        if not group or group.status != GroupStatus.approved:
            return

        q = await session.execute(
            select(Campaign)
            .join(CampaignGroup, CampaignGroup.campaign_id == Campaign.id)
            .where(CampaignGroup.group_id == group.id, Campaign.active == True)
            .order_by(Campaign.id.desc()).limit(1)
        )
        campaign = q.scalar_one_or_none()
        if not campaign:
            return

        await send_campaign_message(context, group, campaign, delete_after=True)


async def publish_campaign_manual(context: ContextTypes.DEFAULT_TYPE, campaign_id: int):
    """Publication manuelle admin : ne s'efface pas automatiquement."""
    async with SessionLocal() as session:
        campaign = await session.get(Campaign, campaign_id)
        if not campaign:
            return 0

        q = await session.execute(
            select(Group)
            .join(CampaignGroup, CampaignGroup.group_id == Group.id)
            .where(CampaignGroup.campaign_id == campaign.id, Group.status == GroupStatus.approved)
        )
        groups = q.scalars().all()
        sent = 0
        for group in groups:
            try:
                await send_campaign_message(context, group, campaign, delete_after=False)
                sent += 1
            except Exception:
                pass
        return sent


async def delete_message_job(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    try:
        await context.bot.delete_message(data["chat_id"], data["message_id"])
    except Exception:
        pass


async def my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member = update.my_chat_member
    if not member:
        return

    chat = member.chat
    if chat.type not in ("group", "supergroup"):
        return

    async with SessionLocal() as session:
        group = await get_or_create_group(session, chat)

        if member.new_chat_member.status in ("member", "administrator"):
            if group.status not in (GroupStatus.approved, GroupStatus.rejected):
                group.status = GroupStatus.pending
            await session.commit()

            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Valider", callback_data=f"adm_group_approve_{group.id}"),
                InlineKeyboardButton("❌ Refuser", callback_data=f"adm_group_reject_{group.id}")
            ]])
            await notify_admins(
                context.bot,
                f"🆕 Bot ajouté dans un groupe\n\n"
                f"Nom : {chat.title}\n"
                f"Chat ID : {chat.id}\n\n"
                "Valide ou refuse ce groupe :",
                reply_markup=kb
            )
        else:
            await session.commit()


async def chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cm = update.chat_member
    if not cm:
        return

    if cm.old_chat_member.status in ("left", "kicked") and cm.new_chat_member.status in ("member", "administrator", "restricted"):
        await handle_new_member(update, context)


async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cm = update.chat_member
    chat = cm.chat
    joined_tg_user = cm.new_chat_member.user

    async with SessionLocal() as session:
        group = await get_or_create_group(session, chat)
        if group.status != GroupStatus.approved:
            await session.commit()
            return

        banned_word = await is_name_banned(session, joined_tg_user.username, joined_tg_user.first_name)
        if banned_word:
            joined_db_user = await get_or_create_user(session, joined_tg_user)
            try:
                await context.bot.ban_chat_member(chat.id, joined_tg_user.id)
            except Exception:
                pass
            await notify_admins(
                context.bot,
                f"🚫 Ban auto\n"
                f"User : {joined_tg_user.id} @{joined_tg_user.username}\n"
                f"Groupe : {chat.title}\n"
                f"Mot détecté : {banned_word}"
            )
            await session.commit()
            return

        invite_link = cm.invite_link.invite_link if cm.invite_link else None
        if not invite_link:
            await session.commit()
            return

        q = await session.execute(select(InviteLink).where(InviteLink.invite_link == invite_link))
        db_link = q.scalar_one_or_none()
        if not db_link:
            await session.commit()
            return

        invited = await get_or_create_user(session, joined_tg_user)
        inviter = await session.get(BotUser, db_link.inviter_user_id)

        existing = await session.execute(select(Invite).where(
            Invite.group_id == group.id,
            Invite.invited_user_id == invited.id
        ))
        if existing.scalar_one_or_none():
            await session.commit()
            return

        invite = Invite(
            group_id=group.id,
            inviter_user_id=db_link.inviter_user_id,
            invited_user_id=invited.id,
            status=InviteStatus.pending
        )
        session.add(invite)
        await session.flush()
        invite_id = invite.id

        await notify_inviter_join_detected(context.bot, inviter, invited, group)
        await session.commit()

    context.job_queue.run_once(
        validate_invite_job,
        when=10 * 60,
        data={"invite_id": invite_id, "chat_id": chat.id, "joined_user_id": joined_tg_user.id}
    )


async def validate_invite_job(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data

    async with SessionLocal() as session:
        invite = await session.get(Invite, data["invite_id"])
        if not invite or invite.status != InviteStatus.pending:
            return

        inviter = await session.get(BotUser, invite.inviter_user_id)
        invited = await session.get(BotUser, invite.invited_user_id)
        group = await session.get(Group, invite.group_id)

        try:
            member = await context.bot.get_chat_member(data["chat_id"], data["joined_user_id"])
            if member.status in ("member", "administrator", "restricted"):
                invite.status = InviteStatus.valid
                invite.validated_at = datetime.utcnow()

                await session.flush()
                await notify_inviter_validated(session, context.bot, inviter, invited, group)
                await send_due_rewards(session, context.bot, inviter, group)
            else:
                invite.status = InviteStatus.invalid
                try:
                    await context.bot.send_message(
                        inviter.telegram_user_id,
                        "❌ Une invitation n'a pas été validée.\n\n"
                        "La personne n'est plus dans le groupe."
                    )
                except Exception:
                    pass
        except Exception:
            invite.status = InviteStatus.invalid

        await session.commit()


def build_application() -> Application:
    app = Application.builder().token(settings.BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("score", score))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(ChatMemberHandler(my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(ChatMemberHandler(chat_member_update, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & ~filters.COMMAND, count_messages))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & (filters.TEXT | filters.PHOTO) & ~filters.COMMAND, text_router))

    return app
