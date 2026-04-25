"""Modèles communs Pydantic pour le système de paiement v2."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ProviderName(str, Enum):
    MTN_MOMO = "mtn_momo"
    ORANGE_MONEY = "orange_money"
    CINETPAY = "cinetpay"
    FLUTTERWAVE = "flutterwave"
    NOTCHPAY = "notchpay"
    STRIPE = "stripe"
    PAYPAL = "paypal"
    CAMPAY = "campay"
    WAVE = "wave"
    LEGACY_MANUAL = "legacy_manual"


class PaymentMethod(str, Enum):
    MOBILE_MONEY = "mobile_money"
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
    WALLET = "wallet"
    PAYPAL = "paypal"
    CRYPTO = "crypto"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    INITIATED = "initiated"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    EXPIRED = "expired"


class PaymentRequest(BaseModel):
    reference: str
    amount: float
    currency: str = "XAF"
    description: str = ""
    customer_phone: str = Field(..., description="E.164, ex: +237670000000")
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None
    country_code: Optional[str] = Field(None, description="ISO-2, ex: CM")
    method: PaymentMethod = PaymentMethod.MOBILE_MONEY
    preferred_provider: Optional[ProviderName] = None
    notify_url: Optional[str] = None
    return_url: Optional[str] = None
    cancel_url: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PaymentResponse(BaseModel):
    reference: str
    provider: ProviderName
    status: PaymentStatus
    provider_reference: Optional[str] = None
    payment_url: Optional[str] = None
    ussd_instructions: Optional[str] = None
    raw_provider_response: dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class WebhookEvent(BaseModel):
    provider: ProviderName
    provider_reference: str
    status: PaymentStatus
    amount: Optional[float] = None
    currency: Optional[str] = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    signature_valid: bool = True
