"""Pydantic request/response models for GEO Analyzer."""
from pydantic import BaseModel, EmailStr
from typing import Optional


class RegisterPayload(BaseModel):
    email: EmailStr
    password: str


class LoginPayload(BaseModel):
    email: EmailStr
    password: str


class GeoAnalyzeRequest(BaseModel):
    url: str
    brand_name: Optional[str] = None


class GeoResult(BaseModel):
    analysis_id: str
    status: str
    geo_score: Optional[int] = None
    scores: Optional[dict] = None
    findings: Optional[list] = None
    recommendations: Optional[list] = None
