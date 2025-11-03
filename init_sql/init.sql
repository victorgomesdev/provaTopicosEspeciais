CREATE TABLE IF NOT EXISTS message_events (
  id serializable PRIMARY KEY,
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