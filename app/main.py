import os
from datetime import datetime, timezone
from fastapi import FastAPI, Request
from app.db import SessionLocal, init_db
from app.models import MessageEvent
from app.schemas import MessagePayload, SendRequest
import ntplib
import httpx
from sqlalchemy.exc import SQLAlchemyError

app = FastAPI(title="SyncLab - Exchange & NTP Demo")

NTP_SERVER = os.getenv("NTP_SERVER", "pool.ntp.org")
init_db()

def get_ntp_time():
    client = ntplib.NTPClient()
    try:
        resp = client.request(NTP_SERVER, version=3)
        ntp_ts = datetime.fromtimestamp(resp.tx_time, tz=timezone.utc)
        return ntp_ts, resp
    except Exception as e:
        return None, e

def now_utc():
    return datetime.now(timezone.utc)

@app.get("/ntp")
def ntp_check():
    local = now_utc()
    ntp_time, resp = get_ntp_time()
    if ntp_time is None:
        return {"error": str(resp)}
    offset_ms = int((local - ntp_time).total_seconds() * 1000)
    return {
        "local_time": local.isoformat(),
        "ntp_time": ntp_time.isoformat(),
        "offset_ms": offset_ms,
        "ntp_server": NTP_SERVER
    }

@app.post("/message")
async def receive_message(payload: MessagePayload, request: Request):
    local_recv = now_utc()
    ntp_time, ntp_resp = get_ntp_time()
    offset_ms = None
    if ntp_time:
        offset_ms = int((local_recv - ntp_time).total_seconds() * 1000)

    db = SessionLocal()
    try:
        mevent = MessageEvent(
            direction="received",
            peer_url=payload.from_url if payload.from_url else None,
            payload=payload.payload,
            origin_local_time=(payload.origin_local_time if payload.origin_local_time else None),
            origin_ntp_time=(payload.origin_ntp_time if payload.origin_ntp_time else None),
            local_time_utc=local_recv,
            ntp_time_utc=ntp_time,
            offset_ms=offset_ms,
            receive_time=local_recv
        )
        db.add(mevent)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
    finally:
        db.close()

    return {
        "received_at_local": local_recv.isoformat(),
        "received_at_ntp": ntp_time.isoformat() if ntp_time else None,
        "offset_ms": offset_ms
    }

@app.post("/send")
async def send_message(req: SendRequest):
    target = str(req.target_url).rstrip("/")
    payload_text = req.payload or ""
    origin_local = now_utc()
    origin_ntp, _ = get_ntp_time()
    offset_ms = None
    if origin_ntp:
        offset_ms = int((origin_local - origin_ntp).total_seconds() * 1000)

    message_body = {
        "from_url": os.getenv("PUBLIC_URL", "unknown"),
        "payload": payload_text,
        "origin_local_time": origin_local.isoformat(),
        "origin_ntp_time": origin_ntp.isoformat() if origin_ntp else None
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        send_ts = now_utc()
        try:
            r = await client.post(f"{target}/message", json=message_body)
            recv_ts = now_utc()
            rtt_ms = int((recv_ts - send_ts).total_seconds() * 1000)
            ack = r.json() if r.status_code == 200 else {"error": r.text}
        except Exception as e:
            recv_ts = now_utc()
            rtt_ms = int((recv_ts - send_ts).total_seconds() * 1000)
            ack = {"error": str(e)}

    db = SessionLocal()
    try:
        mevent = MessageEvent(
            direction="sent",
            peer_url=target,
            payload=payload_text,
            origin_local_time=origin_local,
            origin_ntp_time=(origin_ntp if origin_ntp else None),
            send_time=send_ts,
            receive_time=recv_ts,
            rtt_ms=rtt_ms,
            local_time_utc=now_utc(),
            ntp_time_utc=origin_ntp,
            offset_ms=offset_ms
        )
        db.add(mevent)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
    finally:
        db.close()

    return {
        "target": target,
        "send_ts": send_ts.isoformat(),
        "recv_ack_ts": recv_ts.isoformat(),
        "rtt_ms": rtt_ms,
        "ack": ack
    }