from fastapi import APIRouter
from apps.mb.api import router as mb_router

routers = APIRouter()
routers.include_router(mb_router, prefix="/mb", tags=["马帮数据"])
