from fastapi import APIRouter
from apps.mb.api import router as mb_router
from apps.logistic.api import router as logistic_router

routers = APIRouter()
routers.include_router(mb_router, prefix="/mb", tags=["马帮数据"])
routers.include_router(logistic_router, prefix="/logistic", tags=["物流数据"])
