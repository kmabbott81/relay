-- Relay AI Beta Database Setup
-- Run this in Supabase SQL Editor

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Users table (extends Supabase auth.users)
CREATE TABLE public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT UNIQUE NOT NULL,
    full_name TEXT,
    company TEXT,
    role TEXT DEFAULT 'user',
    beta_access BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    usage_limit INTEGER DEFAULT 100, -- queries per day
    usage_today INTEGER DEFAULT 0
);

-- Knowledge base files
CREATE TABLE public.files (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    content_type TEXT,
    size_bytes BIGINT,
    storage_path TEXT, -- R2/S3 path
    encrypted BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Vector embeddings for search
CREATE TABLE public.embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    file_id UUID NOT NULL REFERENCES public.files(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding vector(1536), -- OpenAI ada-002 dimension
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Search queries (audit trail)
CREATE TABLE public.queries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    query_text TEXT NOT NULL,
    results_count INTEGER,
    latency_ms INTEGER,
    ip_address INET,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Beta feedback
CREATE TABLE public.feedback (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    type TEXT CHECK (type IN ('bug', 'feature', 'general')),
    message TEXT NOT NULL,
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX idx_files_user_id ON public.files(user_id);
CREATE INDEX idx_embeddings_user_id ON public.embeddings(user_id);
CREATE INDEX idx_embeddings_file_id ON public.embeddings(file_id);
CREATE INDEX idx_queries_user_id ON public.queries(user_id);
CREATE INDEX idx_queries_created_at ON public.queries(created_at DESC);

-- Enable Row Level Security
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.files ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.queries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.feedback ENABLE ROW LEVEL SECURITY;

-- RLS Policies

-- Profiles: Users can only see/edit their own profile
CREATE POLICY "Users can view own profile"
    ON public.profiles FOR SELECT
    USING (auth.uid() = id);

CREATE POLICY "Users can update own profile"
    ON public.profiles FOR UPDATE
    USING (auth.uid() = id);

-- Files: Users can only access their own files
CREATE POLICY "Users can view own files"
    ON public.files FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own files"
    ON public.files FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own files"
    ON public.files FOR DELETE
    USING (auth.uid() = user_id);

-- Embeddings: Users can only access their own embeddings
CREATE POLICY "Users can view own embeddings"
    ON public.embeddings FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own embeddings"
    ON public.embeddings FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Queries: Users can only see their own query history
CREATE POLICY "Users can view own queries"
    ON public.queries FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own queries"
    ON public.queries FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Feedback: Anyone can submit, only see their own
CREATE POLICY "Anyone can submit feedback"
    ON public.feedback FOR INSERT
    WITH CHECK (true);

CREATE POLICY "Users can view own feedback"
    ON public.feedback FOR SELECT
    USING (auth.uid() = user_id OR auth.uid() IS NULL);

-- Create profile trigger
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, full_name)
    VALUES (NEW.id, NEW.email, NEW.raw_user_meta_data->>'full_name');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Usage tracking function
CREATE OR REPLACE FUNCTION public.track_usage(user_uuid UUID)
RETURNS BOOLEAN AS $$
DECLARE
    current_usage INTEGER;
    usage_limit INTEGER;
BEGIN
    SELECT usage_today, usage_limit INTO current_usage, usage_limit
    FROM public.profiles
    WHERE id = user_uuid;

    IF current_usage >= usage_limit THEN
        RETURN FALSE; -- Over limit
    END IF;

    UPDATE public.profiles
    SET usage_today = usage_today + 1
    WHERE id = user_uuid;

    RETURN TRUE; -- Within limit
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Reset daily usage (run as cron job)
CREATE OR REPLACE FUNCTION public.reset_daily_usage()
RETURNS void AS $$
BEGIN
    UPDATE public.profiles SET usage_today = 0;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Vector similarity search function
CREATE OR REPLACE FUNCTION public.search_embeddings(
    query_embedding vector(1536),
    user_uuid UUID,
    match_count INTEGER DEFAULT 10
)
RETURNS TABLE (
    file_id UUID,
    chunk_text TEXT,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        e.file_id,
        e.chunk_text,
        1 - (e.embedding <-> query_embedding) AS similarity
    FROM public.embeddings e
    WHERE e.user_id = user_uuid
    ORDER BY e.embedding <-> query_embedding
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Grant permissions
GRANT USAGE ON SCHEMA public TO anon, authenticated;
GRANT ALL ON ALL TABLES IN SCHEMA public TO anon, authenticated;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO anon, authenticated;

-- Success message
DO $$
BEGIN
    RAISE NOTICE 'Beta database setup complete!';
    RAISE NOTICE 'Next steps:';
    RAISE NOTICE '1. Set up Storage bucket for files';
    RAISE NOTICE '2. Enable Email auth in Authentication settings';
    RAISE NOTICE '3. Add beta users via invite';
END $$;
