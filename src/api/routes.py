from fastapi import APIRouter

from src.api.auth import router as auth_router
from src.api.ingestion import router as ingestion_router
from src.api.qa_cases import router as qa_cases_router
from src.api.real_dataset import router as real_dataset_router

router = APIRouter()
router.include_router(ingestion_router)
router.include_router(auth_router)
router.include_router(qa_cases_router)
router.include_router(real_dataset_router)
