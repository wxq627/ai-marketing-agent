-- 文件路径: init.sql
-- 功能描述: 数据库初始化脚本，创建核心业务表

CREATE TABLE IF NOT EXISTS campaigns (
    id SERIAL PRIMARY KEY,
    campaign_id VARCHAR(64) UNIQUE NOT NULL,
    objective VARCHAR(255) NOT NULL,
    product VARCHAR(128) NOT NULL,
    budget NUMERIC(15, 2) NOT NULL,
    start_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,
    strategy_package JSONB NOT NULL,
    status VARCHAR(32) DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_campaigns_campaign_id ON campaigns(campaign_id);
CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(status);
CREATE INDEX IF NOT EXISTS idx_campaigns_time_range ON campaigns(start_time, end_time);

CREATE TABLE IF NOT EXISTS touch_logs (
    id SERIAL PRIMARY KEY,
    trace_id VARCHAR(64) NOT NULL,
    campaign_id VARCHAR(64) NOT NULL,
    oneid VARCHAR(64) NOT NULL,
    channel VARCHAR(64) NOT NULL,
    content TEXT,
    status VARCHAR(32) DEFAULT 'pending',
    send_time TIMESTAMP WITH TIME ZONE,
    response_time TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_touch_logs_trace_id ON touch_logs(trace_id);
CREATE INDEX IF NOT EXISTS idx_touch_logs_oneid ON touch_logs(oneid);
CREATE INDEX IF NOT EXISTS idx_touch_logs_channel ON touch_logs(channel);
CREATE INDEX IF NOT EXISTS idx_touch_logs_campaign_id ON touch_logs(campaign_id);
CREATE INDEX IF NOT EXISTS idx_touch_logs_status ON touch_logs(status);

CREATE TABLE IF NOT EXISTS feedbacks (
    id SERIAL PRIMARY KEY,
    trace_id VARCHAR(64) NOT NULL,
    oneid VARCHAR(64) NOT NULL,
    campaign_id VARCHAR(64),
    event_type VARCHAR(64) NOT NULL,
    channel VARCHAR(64),
    detail JSONB,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_feedbacks_trace_id ON feedbacks(trace_id);
CREATE INDEX IF NOT EXISTS idx_feedbacks_oneid ON feedbacks(oneid);
CREATE INDEX IF NOT EXISTS idx_feedbacks_event_type ON feedbacks(event_type);
CREATE INDEX IF NOT EXISTS idx_feedbacks_timestamp ON feedbacks(timestamp);

CREATE TABLE IF NOT EXISTS dialogues (
    id SERIAL PRIMARY KEY,
    conversation_id VARCHAR(64) UNIQUE NOT NULL,
    oneid VARCHAR(64) NOT NULL,
    session_id VARCHAR(64) NOT NULL,
    messages JSONB NOT NULL,
    summary TEXT,
    intent VARCHAR(128),
    sentiment VARCHAR(64),
    status VARCHAR(32) DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_dialogues_conversation_id ON dialogues(conversation_id);
CREATE INDEX IF NOT EXISTS idx_dialogues_oneid ON dialogues(oneid);
CREATE INDEX IF NOT EXISTS idx_dialogues_session_id ON dialogues(session_id);
CREATE INDEX IF NOT EXISTS idx_dialogues_status ON dialogues(status);

CREATE TABLE IF NOT EXISTS customer_profiles_cache (
    id SERIAL PRIMARY KEY,
    oneid VARCHAR(64) UNIQUE NOT NULL,
    profile JSONB NOT NULL,
    last_sync_time TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_customer_profiles_cache_oneid ON customer_profiles_cache(oneid);

CREATE TABLE IF NOT EXISTS frequency_control (
    id SERIAL PRIMARY KEY,
    oneid VARCHAR(64) NOT NULL,
    channel VARCHAR(64) NOT NULL,
    touch_count INTEGER DEFAULT 0,
    last_touch_time TIMESTAMP WITH TIME ZONE,
    period_start_time TIMESTAMP WITH TIME ZONE,
    period_type VARCHAR(32) DEFAULT 'daily',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_frequency_control_oneid_channel ON frequency_control(oneid, channel, period_type);

CREATE TABLE IF NOT EXISTS dispatch_logs (
    id SERIAL PRIMARY KEY,
    trace_id VARCHAR(64) NOT NULL,
    campaign_id VARCHAR(64),
    oneid VARCHAR(64),
    channel VARCHAR(64),
    content TEXT,
    success BOOLEAN DEFAULT FALSE,
    mock_response TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dispatch_logs_trace_id ON dispatch_logs(trace_id);
CREATE INDEX IF NOT EXISTS idx_dispatch_logs_oneid ON dispatch_logs(oneid);
CREATE INDEX IF NOT EXISTS idx_dispatch_logs_channel ON dispatch_logs(channel);

CREATE TABLE IF NOT EXISTS strategy_execution_status (
    id SERIAL PRIMARY KEY,
    campaign_id VARCHAR(64) UNIQUE NOT NULL,
    status VARCHAR(32) DEFAULT 'pending',
    current_step VARCHAR(64),
    executed_at TIMESTAMP WITH TIME ZONE,
    message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_strategy_execution_status_campaign_id ON strategy_execution_status(campaign_id);
CREATE INDEX IF NOT EXISTS idx_strategy_execution_status_status ON strategy_execution_status(status);