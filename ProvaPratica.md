
# Prova Prática de Tópicos Especiais III: Computação Distribuída com NTP, REST e PostgreSQL

**Objetivo:**  
Dois alunos (A e B), cada um em seu GitHub Codespace, executam um servidor REST (FastAPI) que troca mensagens entre si. Cada mensagem registra timestamps locais, timestamps NTP (tempo de referência), calcula offset e RTT e grava tudo em um PostgreSQL rodando via `docker-compose`. O arquivo `mensagem.http` é fornecido para testes usando a extensão **REST Client** do VS Code/Codespaces.

---

## Pré-requisitos
- Conta GitHub com acesso a Codespaces (cada aluno terá seu Codespace).
- Docker e docker-compose disponíveis no Codespace
- Python 3.10+ e `pip`.
- Extensão **REST Client** instalada no VS Code/Codespaces.

---

## Estrutura do projeto (em cada repositório do aluno)
```
/project
  ├─ docker-compose.yml
  ├─ app/
  │   ├─ main.py
  │   ├─ db.py
  │   ├─ models.py
  │   ├─ schemas.py
  │   └─ requirements.txt
  ├─ init_sql/
  │   └─ init.sql
  └─ mensagem.http
```

---

## Arquivos principais (copiar/colar nos respectivos arquivos)

### 1) docker-compose.yml
Use o `docker-compose.yml`:
```yaml
version: '3.8'
services:
  postgres:
    image: postgres:15
    container_name: postgres_container_prova_pratica
    restart: always
    environment:
      POSTGRES_USER: root
      POSTGRES_PASSWORD: root
      POSTGRES_DB: bd_postgres
    ports:
      - "5432:5432"
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U root"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  postgres-data:
```

> **Observação:** Este `docker-compose` cria um Postgres local ao Codespace. Não exponha 5432 para a internet.

---

### 2) init_sql/init.sql
```sql
CREATE TABLE IF NOT EXISTS message_events (
  id SERIAL PRIMARY KEY,
  direction VARCHAR(10) NOT NULL,
  peer_url TEXT,
  payload TEXT,
  local_time_utc TIMESTAMP WITH TIME ZONE,
  ntp_time_utc TIMESTAMP WITH TIME ZONE,
  origin_local_time TIMESTAMP WITH TIME ZONE,
  origin_ntp_time TIMESTAMP WITH TIME ZONE,
  send_time TIMESTAMP WITH TIME ZONE,
  receive_time TIMESTAMP WITH TIME ZONE,
  rtt_ms INTEGER,
  offset_ms INTEGER,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);
```

---

### 3) app/requirements.txt
```
fastapi
uvicorn[standard]
httpx
ntplib
sqlalchemy
psycopg2-binary
pydantic
python-dotenv
```

---

### 4) app/db.py
```python
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://root:root@localhost:5432/bd_postgres")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def init_db():
    import app.models  # garante que os models estejam registrados
    Base.metadata.create_all(bind=engine)
```

---

### 5) app/models.py
```python
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
```

---

### 6) app/schemas.py
```python
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
```

---

### 7) app/main.py
```python
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
```

---

## 8) mensagem.http (arquivo para usar com REST Client)
Crie o arquivo `mensagem.http` na raiz do projeto (ou na pasta `app/`) com o seguinte conteúdo. **Altere `@base_url` para a URL pública do seu Codespace** (ex.: `https://meu-codespace-8080.githubpreview.dev`).

```http
# Definição de variáveis (ambiente "local" do REST Client)
@base_url = https://SEU-CODESPACE-URL-8080.githubpreview.dev
@peer_url = https://COLEGA-CODESPACE-URL-8080.githubpreview.dev

###
### 1) Verifica NTP local (útil para checar offset no servidor)
GET {{ base_url }}/ntp
Accept: application/json

###
### 2) Enviar mensagem para o colega usando o endpoint /send (inicia fluxo e grava evento "sent")
POST {{ base_url }}/send
Content-Type: application/json

{
  "target_url": "{{ peer_url }}",
  "payload": "Olá, esta é uma mensagem de teste enviada via REST Client"
}

###
### 3) Simular envio direto ao endpoint /message do colega (útil para testar recebimento sem passar por /send)
POST {{ peer_url }}/message
Content-Type: application/json

{
  "from_url": "{{ base_url }}",
  "payload": "Mensagem direta simulada (envio manual ao /message)",
  "origin_local_time": "2025-01-01T12:00:00+00:00",
  "origin_ntp_time": "2025-01-01T12:00:05+00:00"
}

###
```

> **Como usar no REST Client:**  
> - Abra `mensagem.http` no Codespace (VS Code).  
> - Ajuste `@base_url` e `@peer_url` para os URLs públicos do respectivo Codespace (ambos os alunos devem trocar essas URLs entre si).  
> - Clique em "Send Request" acima do bloco HTTP.  
> - Observe respostas JSON e compare com os registros no banco.

---

## Executando a prática (passo-a-passo)
1. Cada aluno clona o repositório com os arquivos acima em seu Codespace.
2. No Codespace, subir o Postgres:
   ```bash
   docker-compose up -d
   ```
3. User a extensão MySQL para criar a tabela do banco ou execute init_sql/init.sql em psql (Opcional):
   ```bash
   psql postgresql://root:root@localhost:5432/bd_postgres -f init_sql/init.sql
   ```
4. Criar e ativar virtualenv, instalar dependências:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r app/requirements.txt
   ```
5. Rodar o servidor:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8080
   ```
6. Tornar a porta 8080 pública no Codespace, copie a URL pública.  
7. Trocar URLs públicas entre os colegas (A <-> B).  
8. Abrir `mensagem.http`, ajustar `@base_url` e `@peer_url` e executar requisições usando REST Client.  
9. Checar registros no banco.
    ```bash
    psql postgresql://root:root@localhost:5432/bd_postgres -c "SELECT id,direction,peer_url,payload,send_time,receive_time,rtt_ms,offset_ms FROM message_events ORDER BY id;"
    ```
---