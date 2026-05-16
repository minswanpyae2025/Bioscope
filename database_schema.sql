-- Supabase Database Schema for Bioscope Telegram Bot

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Users Table
CREATE TABLE users (
    id BIGINT PRIMARY KEY, -- Telegram user ID
    username TEXT,
    first_name TEXT,
    tier TEXT DEFAULT 'free', -- 'free' or 'premium'
    premium_expires_at TIMESTAMP WITH TIME ZONE, -- NULL for free users
    daily_requests_used INT DEFAULT 0, -- Reset every day
    last_request_date DATE,
    streak_days INT DEFAULT 0, -- Consecutive days active
    last_activity_date DATE,
    joined_channels JSONB, -- Cached list of channels they have joined
    joined_check_cache TIMESTAMP WITH TIME ZONE, -- Last time joined check was performed
    last_watched_video_id INT REFERENCES videos(id) ON DELETE SET NULL, -- Track last watched for recommendations
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Videos Table (Updated for Resolution-based caching)
CREATE TABLE videos (
    id SERIAL PRIMARY KEY, -- Internal ID
    post_id TEXT NOT NULL, -- Movie ID or TV episode ID from Bioscope API
    type TEXT NOT NULL, -- 'movie' or 'tv_episode'
    resolution TEXT NOT NULL, -- e.g., '1080p', '720p'
    title TEXT,
    quality TEXT,
    telegram_file_id TEXT, -- file_id of the video in Telegram (after leeching)
    dump_message_id BIGINT, -- message ID in the dump channel
    is_alive BOOLEAN DEFAULT FALSE, -- whether the Telegram file still exists
    last_checked TIMESTAMP WITH TIME ZONE DEFAULT NOW(), -- last time we verified is_alive
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(post_id, type, resolution)
);

-- 3. User Requests Table
CREATE TABLE user_requests (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    video_id INT REFERENCES videos(id) ON DELETE CASCADE,
    requested_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    token_cost INT DEFAULT 0, -- Tokens deducted (for free user)
    status TEXT DEFAULT 'queued', -- 'queued', 'downloading', 'uploaded', 'failed'
    telegram_message_id BIGINT -- message ID of the final video sent to user
);

-- 4. Ads Table
CREATE TABLE ads (
    id SERIAL PRIMARY KEY,
    title TEXT,
    video_file_id TEXT, -- Telegram file_id of the ad video
    text TEXT, -- Message text shown with ad
    inline_link TEXT, -- URL for inline keyboard button
    required_watch_seconds INT DEFAULT 10,
    view_count INT DEFAULT 0, -- How many times sent
    reward_tokens INT DEFAULT 5,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 5. User Ad Views
CREATE TABLE user_ad_views (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    ad_id INT REFERENCES ads(id) ON DELETE CASCADE,
    watched_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    reward_tokens INT DEFAULT 0
);

-- 6. Tokens Table
CREATE TABLE tokens (
    user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    balance INT DEFAULT 0
);

-- 7. Surveys & Responses
CREATE TABLE surveys (
    id SERIAL PRIMARY KEY,
    question TEXT NOT NULL,
    options JSONB, -- e.g., ["A", "B", "C"]
    reward_tokens INT DEFAULT 10,
    active_until TIMESTAMP WITH TIME ZONE
);

CREATE TABLE survey_responses (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    survey_id INT REFERENCES surveys(id) ON DELETE CASCADE,
    response TEXT,
    answered_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, survey_id)
);

-- 8. Invites
CREATE TABLE invites (
    id SERIAL PRIMARY KEY,
    inviter_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    invitee_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    reward_given BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(invitee_id)
);

-- 9. Preferences (For "For You" feature)
CREATE TABLE preferences (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    genre_id INT, -- From Bioscope API
    tag_id INT, -- From Bioscope API
    weight INT DEFAULT 1, -- Count of times they watched content with that genre/tag
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, genre_id, tag_id)
);

-- 10. Watchlist
CREATE TABLE watchlist (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    video_post_id TEXT NOT NULL, -- Keep track of post_id (Bioscope ID) directly for easier querying
    video_type TEXT NOT NULL, -- 'movie' or 'tv_episode'
    added_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, video_post_id, video_type)
);

-- 11. User Ratings
CREATE TABLE user_ratings (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    video_post_id TEXT NOT NULL,
    video_type TEXT NOT NULL,
    rating TEXT CHECK (rating IN ('like', 'dislike')),
    rated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, video_post_id, video_type)
);

-- 12. Admin Config
CREATE TABLE admin_config (
    key TEXT PRIMARY KEY,
    value JSONB -- Use JSONB for flexible values (ints, strings, arrays)
);

-- Insert default admin config
INSERT INTO admin_config (key, value) VALUES
('dump_channel_id', '-1000000000000'),
('trash_channel_id', '-1000000000000'),
('free_daily_limit', '5'),
('free_cooldown_seconds', '0'),
('premium_daily_limit', '50'),
('premium_cooldown_seconds', '0'),
('required_channels', '[]'),
('ad_watch_required', 'true'),
('default_ad_id', 'null'),
('streak_reward_premium_hours', '24');
