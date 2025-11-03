from pydantic import BaseModel, HttpUrl
from typing import Optional

class MessagePayload(BaseModel):
    from_url: Optional[str] = None
    payload: Optional[str] = None
    origin_local_time: Optional[str] = None   # ISO 8601
    origin_ntp_time: Optional[str] = None     # ISO 8601

class SendRequest(BaseModel):
    target_url: HttpUrl
    payload: Optional[str] = None