import json
from sqlalchemy import select, func, delete
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from app.config import settings
from app.db import SessionLocal, engine
from app.models import (
    Group, GroupStatus, Campaign, CampaignGroup, RewardTier, BannedWord,
    BotUser, Invite, InviteStatus, AdminState, AdminStep
)


def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


def admin_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🆕 Groupes en attente", callback_data="adm_groups_pending")],
        [InlineKeyboardButton("✅ Groupes validés", callback_data="adm_groups_approved")],
        [InlineKeyboardButton("📢 Campagnes pub", callback_data="adm_campaigns")],
        [InlineKeyboardButton("🎁 Paliers / Gofile", callback_data="adm_tiers")],
        [InlineKeyboardButton("🚫 Mots bannis", callback_data="adm_banned")],
        [InlineKeyboardButton("📊 Statistiques", callback_data="adm_stats")],
        [InlineKeyboardButton("ℹ️ Info bot", callback_data="adm_info")],
    ])


def back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu admin", callback_data="adm_menu")]])


async def get_state(session, user_id: int) -> AdminState:
    q = await session.execute(select(AdminState).where(AdminState.telegram_user_id == user_id))
    state = q.scalar_one_or_none()
    if not state:
        state = AdminState(telegram_user_id=user_id, step=AdminStep.idle, data="{}")
        session.add(state)
        await session.flush()
    return state


async def set_state(session, user_id: int, step: AdminStep, data: dict | None = None):
    state = await get_state(session, user_id)
    state.step = step
    state.data = json.dumps(data or {}, ensure_ascii=False)


async def admin_start_message(update: Update):
    await update.message.reply_text(
        "👑 Espace admin détecté.\n\nChoisis une action :",
        reply_markup=admin_menu_keyboard()
    )


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔ Accès refusé.")
        return

    data = query.data

    async with SessionLocal() as session:
        if data == "adm_menu":
            await set_state(session, query.from_user.id, AdminStep.idle)
            await session.commit()
            await query.edit_message_text("👑 Menu admin", reply_markup=admin_menu_keyboard())
            return

        if data == "adm_groups_pending":
            q = await session.execute(select(Group).where(Group.status == GroupStatus.pending).order_by(Group.added_at.desc()))
            groups = q.scalars().all()
            if not groups:
                await query.edit_message_text("🆕 Aucun groupe en attente.", reply_markup=back_keyboard())
                return
            await query.edit_message_text("🆕 Groupes en attente :", reply_markup=back_keyboard())
            for g in groups:
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ Valider", callback_data=f"adm_group_approve_{g.id}"),
                    InlineKeyboardButton("❌ Refuser", callback_data=f"adm_group_reject_{g.id}")
                ]])
                await context.bot.send_message(query.from_user.id, f"Nom : {g.title}\nChat ID : {g.telegram_chat_id}", reply_markup=kb)
            return

        if data.startswith("adm_group_approve_"):
            gid = int(data.replace("adm_group_approve_", ""))
            group = await session.get(Group, gid)
            if group:
                group.status = GroupStatus.approved
                await session.commit()
                await query.edit_message_text(f"✅ Groupe validé : {group.title}", reply_markup=back_keyboard())
            return

        if data.startswith("adm_group_reject_"):
            gid = int(data.replace("adm_group_reject_", ""))
            group = await session.get(Group, gid)
            if group:
                group.status = GroupStatus.rejected
                await session.commit()
                await query.edit_message_text(f"❌ Groupe refusé : {group.title}", reply_markup=back_keyboard())
            return

        if data == "adm_groups_approved":
            q = await session.execute(select(Group).where(Group.status == GroupStatus.approved).order_by(Group.title))
            groups = q.scalars().all()
            text = "✅ Groupes validés :\n\n" + ("\n".join([f"• {g.title} — {g.message_count}/100 messages" for g in groups]) if groups else "Aucun.")
            await query.edit_message_text(text, reply_markup=back_keyboard())
            return

        if data == "adm_campaigns":
            q = await session.execute(select(Campaign).order_by(Campaign.id.desc()))
            campaigns = q.scalars().all()
            kb = [[InlineKeyboardButton("➕ Créer campagne", callback_data="adm_campaign_create")]]
            for c in campaigns[:10]:
                status = "🟢" if c.active else "🔴"
                kb.append([InlineKeyboardButton(f"{status} {c.title}", callback_data=f"adm_campaign_toggle_{c.id}")])
            kb.append([InlineKeyboardButton("⬅️ Menu admin", callback_data="adm_menu")])
            await query.edit_message_text(
                "📢 Campagnes pub\n\n"
                "Bouton sur une campagne = activer/désactiver.\n"
                "Créer campagne = assistant étape par étape.",
                reply_markup=InlineKeyboardMarkup(kb)
            )
            return

        if data.startswith("adm_campaign_toggle_"):
            cid = int(data.replace("adm_campaign_toggle_", ""))
            campaign = await session.get(Campaign, cid)
            if campaign:
                campaign.active = not campaign.active
                await session.commit()
                await query.edit_message_text(f"Campagne mise à jour : {campaign.title}", reply_markup=back_keyboard())
            return

        if data == "adm_campaign_create":
            await set_state(session, query.from_user.id, AdminStep.campaign_title, {})
            await session.commit()
            await query.edit_message_text("📢 Création campagne\n\nEnvoie le titre de la campagne.", reply_markup=back_keyboard())
            return

        if data == "adm_tiers":
            q = await session.execute(select(RewardTier).order_by(RewardTier.required_invites))
            tiers = q.scalars().all()
            text = "🎁 Paliers / Gofile\n\n" + "\n".join([f"• {t.required_invites} invités = {t.media_count} médias\n{t.gofile_link}" for t in tiers])
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Ajouter / Modifier palier", callback_data="adm_tier_create")],
                [InlineKeyboardButton("⬅️ Menu admin", callback_data="adm_menu")]
            ])
            await query.edit_message_text(text[:3800], reply_markup=kb)
            return

        if data == "adm_tier_create":
            await set_state(session, query.from_user.id, AdminStep.tier_required, {})
            await session.commit()
            await query.edit_message_text("🎁 Palier\n\nEnvoie le nombre d'invités requis. Exemple : 10", reply_markup=back_keyboard())
            return

        if data == "adm_banned":
            q = await session.execute(select(BannedWord).order_by(BannedWord.word))
            words = q.scalars().all()
            kb = [[InlineKeyboardButton("➕ Ajouter mot", callback_data="adm_banned_add")]]
            for word in words[:30]:
                kb.append([InlineKeyboardButton(f"❌ {word.word}", callback_data=f"adm_banned_delete_{word.id}")])
            kb.append([InlineKeyboardButton("⬅️ Menu admin", callback_data="adm_menu")])
            text = "🚫 Mots bannis\n\nClique sur un mot pour le supprimer."
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
            return

        if data == "adm_banned_add":
            await set_state(session, query.from_user.id, AdminStep.banned_word, {})
            await session.commit()
            await query.edit_message_text("🚫 Envoie le mot à bannir.", reply_markup=back_keyboard())
            return

        if data.startswith("adm_banned_delete_"):
            wid = int(data.replace("adm_banned_delete_", ""))
            await session.execute(delete(BannedWord).where(BannedWord.id == wid))
            await session.commit()
            await query.edit_message_text("✅ Mot supprimé.", reply_markup=back_keyboard())
            return

        if data == "adm_stats":
            users = (await session.execute(select(func.count(BotUser.id)))).scalar() or 0
            groups = (await session.execute(select(func.count(Group.id)))).scalar() or 0
            pending = (await session.execute(select(func.count(Group.id)).where(Group.status == GroupStatus.pending))).scalar() or 0
            approved = (await session.execute(select(func.count(Group.id)).where(Group.status == GroupStatus.approved))).scalar() or 0
            invites = (await session.execute(select(func.count(Invite.id)))).scalar() or 0
            valid = (await session.execute(select(func.count(Invite.id)).where(Invite.status == InviteStatus.valid))).scalar() or 0

            qtop = await session.execute(
                select(BotUser, func.count(Invite.id).label("c"))
                .join(Invite, Invite.inviter_user_id == BotUser.id)
                .where(Invite.status == InviteStatus.valid)
                .group_by(BotUser.id)
                .order_by(func.count(Invite.id).desc())
                .limit(10)
            )
            top_lines = []
            for user, count in qtop.all():
                label = f"@{user.username}" if user.username else str(user.telegram_user_id)
                top_lines.append(f"• {label}: {count}")

            await query.edit_message_text(
                "📊 Statistiques\n\n"
                f"Utilisateurs : {users}\n"
                f"Groupes : {groups}\n"
                f"Groupes en attente : {pending}\n"
                f"Groupes validés : {approved}\n"
                f"Invitations totales : {invites}\n"
                f"Invitations validées : {valid}\n\n"
                "🏆 Top inviteurs :\n" + ("\n".join(top_lines) if top_lines else "Aucun"),
                reply_markup=back_keyboard()
            )
            return

        if data == "adm_info":
            checks = []
            try:
                me = await context.bot.get_me()
                checks.append(f"✅ Bot connecté : @{me.username}")
            except Exception as e:
                checks.append(f"❌ Bot erreur : {e}")

            try:
                async with engine.begin():
                    pass
                checks.append("✅ Base de données connectée")
            except Exception as e:
                checks.append(f"❌ DB erreur : {e}")

            for label, model in [
                ("Groupes", Group), ("Utilisateurs", BotUser), ("Invitations", Invite),
                ("Campagnes", Campaign), ("Paliers", RewardTier), ("Mots bannis", BannedWord)
            ]:
                try:
                    c = (await session.execute(select(func.count(model.id)))).scalar() or 0
                    checks.append(f"✅ {label}: {c}")
                except Exception as e:
                    checks.append(f"❌ {label}: {e}")

            try:
                webhook = await context.bot.get_webhook_info()
                checks.append(f"✅ Webhook : {webhook.url or 'aucun'}")
            except Exception as e:
                checks.append(f"❌ Webhook : {e}")

            await query.edit_message_text(
                "ℹ️ Info bot\n\n"
                f"Ton ID : {query.from_user.id}\n"
                f"Admin détecté : ✅\n\n" + "\n".join(checks),
                reply_markup=back_keyboard()
            )
            return


async def handle_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not update.message or not is_admin(update.effective_user.id):
        return False

    text = update.message.text or ""
    if text.startswith("/"):
        return False

    async with SessionLocal() as session:
        state = await get_state(session, update.effective_user.id)
        try:
            data = json.loads(state.data or "{}")
        except Exception:
            data = {}

        if state.step == AdminStep.idle:
            return False

        if state.step == AdminStep.campaign_title:
            data["title"] = text
            await set_state(session, update.effective_user.id, AdminStep.campaign_text, data)
            await session.commit()
            await update.message.reply_text("OK. Envoie maintenant le texte de la pub.")
            return True

        if state.step == AdminStep.campaign_text:
            data["text"] = text
            await set_state(session, update.effective_user.id, AdminStep.campaign_photo, data)
            await session.commit()
            await update.message.reply_text("OK. Envoie le file_id de la photo, ou écris `skip`.")
            return True

        if state.step == AdminStep.campaign_photo:
            data["photo_file_id"] = "" if text.lower() == "skip" else text
            await set_state(session, update.effective_user.id, AdminStep.campaign_button, data)
            await session.commit()
            await update.message.reply_text("OK. Envoie le texte du bouton. Exemple : 🎁 Recevoir des médias")
            return True

        if state.step == AdminStep.campaign_button:
            data["button_text"] = text
            campaign = Campaign(
                title=data["title"],
                text=data["text"],
                photo_file_id=data.get("photo_file_id") or None,
                button_text=data["button_text"],
                active=True
            )
            session.add(campaign)
            await session.flush()

            q = await session.execute(select(Group).where(Group.status == GroupStatus.approved).order_by(Group.title))
            groups = q.scalars().all()
            if not groups:
                await set_state(session, update.effective_user.id, AdminStep.idle)
                await session.commit()
                await update.message.reply_text("Campagne créée, mais aucun groupe validé disponible.", reply_markup=admin_menu_keyboard())
                return True

            data = {"campaign_id": campaign.id, "selected": []}
            await set_state(session, update.effective_user.id, AdminStep.idle, data)
            await session.commit()

            kb = []
            for g in groups:
                kb.append([InlineKeyboardButton(f"☐ {g.title}", callback_data=f"adm_camp_select_{campaign.id}_{g.id}")])
            kb.append([InlineKeyboardButton("✅ Terminer sélection", callback_data=f"adm_camp_done_{campaign.id}")])
            await update.message.reply_text("Sélectionne les groupes pour cette campagne :", reply_markup=InlineKeyboardMarkup(kb))
            return True

        if state.step == AdminStep.tier_required:
            data["required_invites"] = int(text)
            await set_state(session, update.effective_user.id, AdminStep.tier_media, data)
            await session.commit()
            await update.message.reply_text("OK. Envoie le nombre de médias. Exemple : 20")
            return True

        if state.step == AdminStep.tier_media:
            data["media_count"] = int(text)
            await set_state(session, update.effective_user.id, AdminStep.tier_link, data)
            await session.commit()
            await update.message.reply_text("OK. Envoie le lien Gofile.")
            return True

        if state.step == AdminStep.tier_link:
            required = int(data["required_invites"])
            q = await session.execute(select(RewardTier).where(RewardTier.required_invites == required))
            tier = q.scalar_one_or_none()
            if not tier:
                tier = RewardTier(required_invites=required, media_count=int(data["media_count"]), gofile_link=text, title=f"Palier {required}")
                session.add(tier)
            else:
                tier.media_count = int(data["media_count"])
                tier.gofile_link = text
            await set_state(session, update.effective_user.id, AdminStep.idle)
            await session.commit()
            await update.message.reply_text("✅ Palier enregistré.", reply_markup=admin_menu_keyboard())
            return True

        if state.step == AdminStep.banned_word:
            word = text.strip().lower()
            if word:
                try:
                    session.add(BannedWord(word=word))
                    await session.commit()
                except Exception:
                    await session.rollback()
            await set_state(session, update.effective_user.id, AdminStep.idle)
            await session.commit()
            await update.message.reply_text("✅ Mot banni ajouté.", reply_markup=admin_menu_keyboard())
            return True

    return False


async def handle_campaign_group_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return False

    data = query.data
    if data.startswith("adm_camp_select_"):
        _, _, _, cid, gid = data.split("_")
        cid, gid = int(cid), int(gid)
        async with SessionLocal() as session:
            q = await session.execute(select(CampaignGroup).where(CampaignGroup.campaign_id == cid, CampaignGroup.group_id == gid))
            existing = q.scalar_one_or_none()
            if existing:
                await session.delete(existing)
            else:
                session.add(CampaignGroup(campaign_id=cid, group_id=gid))
            await session.commit()

            qg = await session.execute(select(Group).where(Group.status == GroupStatus.approved).order_by(Group.title))
            groups = qg.scalars().all()
            qs = await session.execute(select(CampaignGroup.group_id).where(CampaignGroup.campaign_id == cid))
            selected = set(qs.scalars().all())

            kb = []
            for g in groups:
                mark = "☑" if g.id in selected else "☐"
                kb.append([InlineKeyboardButton(f"{mark} {g.title}", callback_data=f"adm_camp_select_{cid}_{g.id}")])
            kb.append([InlineKeyboardButton("✅ Terminer sélection", callback_data=f"adm_camp_done_{cid}")])

        await query.answer("Mis à jour")
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(kb))
        return True

    if data.startswith("adm_camp_done_"):
        await query.answer()
        await query.edit_message_text("✅ Campagne prête.", reply_markup=admin_menu_keyboard())
        return True

    return False
