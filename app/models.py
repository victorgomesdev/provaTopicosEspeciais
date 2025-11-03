from sqlalchemy import Column, Integer, String, Text, TIMESTAMP
from sqlalchemy.sql import func
from app.db import Base

class MessageEvent(Base):
    __tablename__ = "message_events"

    id = Column(Integer, primary_key=True, index=True)
    direction = Column(String(10), nullable=False)
    peer_url = Column(Text)
    payload = Column(Text)
    local_time_utc = Column(TIMESTAMP(timezone=True))
    ntp_time_utc = Column(TIMESTAMP(timezone=True))
    origin_local_time = Column(TIMESTAMP(timezone=True))
    origin_ntp_time = Column(TIMESTAMP(timezone=True))
    send_time = Column(TIMESTAMP(timezone=True))
    receive_time = Column(TIMESTAMP(timezone=True))
    rtt_ms = Column(Integer)
    offset_ms = Column(Integer)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())