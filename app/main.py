import logging

from fastapi import FastAPI

from app.api.routes import router
from app.core.config import get_settings
from app.db.session import init_db


settings = get_settings()
logging.basicConfig(level=settings.log_level)

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Dimensional warehouse and REST API for corporate credit rating MASTER sheets.",
)
app.include_router(router)


@app.on_event("startup")
def startup() -> None:
    init_db()
