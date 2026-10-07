"""Document registrar + номенклатура дел schemas (ТЗ 3.10)."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

DOC_TYPES = ("incoming", "outgoing", "internal")
RESET_PERIODS = ("never", "yearly", "monthly")
CASE_STATUSES = ("open", "closed", "archived")


class DocTypeConfigRead(BaseModel):
    doc_type: str
    prefix: str
    suffix: str
    include_department: bool
    seq_padding: int
    reset_period: str
    model_config = {"from_attributes": True}


class DocTypeConfigUpdate(BaseModel):
    prefix: str | None = Field(default=None, max_length=32)
    suffix: str | None = Field(default=None, max_length=32)
    include_department: bool | None = None
    seq_padding: int | None = Field(default=None, ge=1, le=10)
    reset_period: str | None = Field(default=None, pattern=r"^(never|yearly|monthly)$")


class RegisterDocumentRequest(BaseModel):
    entity_id: uuid.UUID
    record_id: uuid.UUID
    doc_type: str = Field(pattern=r"^(incoming|outgoing|internal)$")
    department_code: str | None = Field(default=None, max_length=32)
    filing_case_id: uuid.UUID | None = None


class DocumentRegistrationRead(BaseModel):
    id: uuid.UUID
    entity_id: uuid.UUID
    record_id: uuid.UUID
    doc_type: str
    department_code: str | None
    registration_no: str
    filing_case_id: uuid.UUID | None
    registered_by: uuid.UUID | None
    registered_at: datetime
    model_config = {"from_attributes": True}


class FilingCaseCreate(BaseModel):
    index_code: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=512)
    parent_id: uuid.UUID | None = None
    retention_years: int | None = Field(default=None, ge=1, le=100)
    storage_location: str | None = Field(default=None, max_length=256)
    close_by: date | None = None
    responsible_user_id: uuid.UUID | None = None


class FilingCaseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=512)
    retention_years: int | None = Field(default=None, ge=1, le=100)
    storage_location: str | None = Field(default=None, max_length=256)
    status: str | None = Field(default=None, pattern=r"^(open|closed|archived)$")
    close_by: date | None = None
    responsible_user_id: uuid.UUID | None = None


class FilingCaseRead(BaseModel):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    index_code: str
    title: str
    retention_years: int | None
    storage_location: str | None
    status: str
    close_by: date | None
    closed_at: datetime | None
    responsible_user_id: uuid.UUID | None
    created_at: datetime
    model_config = {"from_attributes": True}
