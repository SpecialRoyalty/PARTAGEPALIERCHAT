import uvicorn
from fastapi import FastAPI, Request
from telegram import Update
from app.config import settings
from app.models import Base, RewardTier
from app.db import engine, SessionLocal
from app.bot import build_application
from app.admin import router as admin_router
from sqlalchemy import select

api = FastAPI(title="Telegram Growth Bot")
telegram_app = build_application()

api.include_router(admin_router)


@api.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await seed_default_tiers()

    await telegram_app.initialize()
    await telegram_app.start()

    if settings.WEBHOOK_BASE_URL:
        webhook_url = settings.WEBHOOK_BASE_URL.rstrip("/") + f"/telegram/{settings.BOT_TOKEN}"
        await telegram_app.bot.set_webhook(
            webhook_url,
            allowed_updates=["message", "my_chat_member", "chat_member", "callback_query"]
        )


@api.on_event("shutdown")
async def shutdown():
    await telegram_app.stop()
    await telegram_app.shutdown()


@api.get("/health")
async def health():
    return {"ok": True}


@api.post("/telegram/{token}")
async def telegram_webhook(token: str, request: Request):
    if token != settings.BOT_TOKEN:
        return {"ok": False}
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}


async def seed_default_tiers():
    defaults = [
        (1, 1, "À remplacer par ton lien Gofile"),
        (10, 20, "À remplacer par ton lien Gofile"),
        (50, 100, "À remplacer par ton lien Gofile"),
        (100, 200, "À remplacer par ton lien Gofile"),
        (300, 500, "À remplacer par ton lien Gofile"),
        (500, 1500, "À remplacer par ton lien Gofile"),
        (1000, 0, "VIP gratuit à vie"),
    ]
    async with SessionLocal() as session:
        for required, media_count, link in defaults:
            q = await session.execute(select(RewardTier).where(RewardTier.required_invites == required))
            if not q.scalar_one_or_none():
                session.add(RewardTier(
                    required_invites=required,
                    media_count=media_count,
                    gofile_link=link,
                    title=f"Palier {required}"
                ))
        await session.commit()


if __name__ == "__main__":
    uvicorn.run("app.main:api", host="0.0.0.0", port=settings.PORT)
