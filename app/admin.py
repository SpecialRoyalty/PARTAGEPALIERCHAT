from fastapi import APIRouter, Depends, Header, HTTPException, Form
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.db import get_session
from app.models import (
    Group, GroupStatus, Campaign, CampaignGroup, RewardTier, BannedWord
)

router = APIRouter(prefix="/admin", tags=["admin"])


def check_admin(x_admin_token: str = Header(default="")):
    if x_admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/groups", dependencies=[Depends(check_admin)])
async def list_groups(session: AsyncSession = Depends(get_session)):
    q = await session.execute(select(Group).order_by(Group.added_at.desc()))
    return q.scalars().all()


@router.post("/groups/{group_id}/approve", dependencies=[Depends(check_admin)])
async def approve_group(group_id: int, session: AsyncSession = Depends(get_session)):
    group = await session.get(Group, group_id)
    if not group:
        raise HTTPException(404, "Group not found")
    group.status = GroupStatus.approved
    await session.commit()
    return {"ok": True}


@router.post("/groups/{group_id}/reject", dependencies=[Depends(check_admin)])
async def reject_group(group_id: int, session: AsyncSession = Depends(get_session)):
    group = await session.get(Group, group_id)
    if not group:
        raise HTTPException(404, "Group not found")
    group.status = GroupStatus.rejected
    await session.commit()
    return {"ok": True}


@router.post("/campaigns", dependencies=[Depends(check_admin)])
async def create_campaign(
    title: str = Form(...),
    text: str = Form(...),
    photo_file_id: str = Form(default=""),
    button_text: str = Form(default="🎁 Recevoir des médias"),
    group_ids: str = Form(default=""),
    session: AsyncSession = Depends(get_session)
):
    campaign = Campaign(
        title=title,
        text=text,
        photo_file_id=photo_file_id or None,
        button_text=button_text,
        active=True
    )
    session.add(campaign)
    await session.flush()

    ids = [int(x) for x in group_ids.split(",") if x.strip()]
    for gid in ids:
        session.add(CampaignGroup(campaign_id=campaign.id, group_id=gid))

    await session.commit()
    return {"ok": True, "campaign_id": campaign.id}


@router.get("/campaigns", dependencies=[Depends(check_admin)])
async def list_campaigns(session: AsyncSession = Depends(get_session)):
    q = await session.execute(select(Campaign).order_by(Campaign.id.desc()))
    return q.scalars().all()


@router.post("/tiers", dependencies=[Depends(check_admin)])
async def upsert_tier(
    required_invites: int = Form(...),
    media_count: int = Form(...),
    gofile_link: str = Form(...),
    title: str = Form(default=""),
    session: AsyncSession = Depends(get_session)
):
    q = await session.execute(select(RewardTier).where(RewardTier.required_invites == required_invites))
    tier = q.scalar_one_or_none()
    if not tier:
        tier = RewardTier(required_invites=required_invites, media_count=media_count, gofile_link=gofile_link, title=title)
        session.add(tier)
    else:
        tier.media_count = media_count
        tier.gofile_link = gofile_link
        tier.title = title
    await session.commit()
    return {"ok": True}


@router.get("/tiers", dependencies=[Depends(check_admin)])
async def list_tiers(session: AsyncSession = Depends(get_session)):
    q = await session.execute(select(RewardTier).order_by(RewardTier.required_invites))
    return q.scalars().all()


@router.post("/banned-words", dependencies=[Depends(check_admin)])
async def add_banned_word(
    word: str = Form(...),
    session: AsyncSession = Depends(get_session)
):
    word = word.strip().lower()
    if not word:
        raise HTTPException(400, "Empty word")
    session.add(BannedWord(word=word))
    try:
        await session.commit()
    except Exception:
        await session.rollback()
    return {"ok": True}


@router.get("/banned-words", dependencies=[Depends(check_admin)])
async def list_banned_words(session: AsyncSession = Depends(get_session)):
    q = await session.execute(select(BannedWord).order_by(BannedWord.word))
    return q.scalars().all()


@router.delete("/banned-words/{word_id}", dependencies=[Depends(check_admin)])
async def delete_banned_word(word_id: int, session: AsyncSession = Depends(get_session)):
    await session.execute(delete(BannedWord).where(BannedWord.id == word_id))
    await session.commit()
    return {"ok": True}
