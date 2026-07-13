-- GearTwin AI — PostgreSQL-Schema
-- pgvector wird fuer die Embedding-Spalte der Wissensdatenbank vorausgesetzt.
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

CREATE TYPE subscription_tier AS ENUM ('free', 'premium');
CREATE TYPE diy_skill_level AS ENUM ('beginner', 'intermediate', 'advanced');
CREATE TYPE issue_severity AS ENUM ('info', 'advisory', 'warning', 'critical');
CREATE TYPE knowledge_source_type AS ENUM ('forum', 'recall', 'tuev_report', 'manufacturer_tsb');
CREATE TYPE warning_status AS ENUM ('open', 'acknowledged', 'resolved', 'dismissed');
CREATE TYPE expense_category AS ENUM ('fuel', 'maintenance', 'insurance', 'tax', 'parts', 'other');
CREATE TYPE expense_source AS ENUM ('ocr_receipt', 'csv_import', 'manual');
CREATE TYPE forecast_status AS ENUM ('active', 'fulfilled', 'expired');
CREATE TYPE part_vendor AS ENUM ('autodoc', 'ebay', 'kfzteile24');

CREATE TABLE users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text UNIQUE NOT NULL,
    password_hash text,
    auth_provider text NOT NULL DEFAULT 'email',
    diy_skill_level diy_skill_level NOT NULL DEFAULT 'beginner',
    subscription_tier subscription_tier NOT NULL DEFAULT 'free',
    subscription_expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE vehicles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    vin text,
    hsn text,
    tsn text,
    make text NOT NULL,
    model text NOT NULL,
    variant text,
    engine_code text,
    fuel_type text,
    first_registration_date date,
    current_mileage integer NOT NULL DEFAULT 0,
    mileage_updated_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_vehicles_make_model ON vehicles (make, model);

CREATE TABLE mileage_history (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    vehicle_id uuid NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    mileage integer NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now()
);

-- Strukturierte, deduplizierte Wissensbasis-Eintraege (Ergebnis der RAG-Extraktionspipeline)
CREATE TABLE knowledge_base_issues (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    make text NOT NULL,
    model text NOT NULL,
    engine_code text,
    issue_title text NOT NULL,
    issue_description text NOT NULL,
    typical_mileage_from integer,
    typical_mileage_to integer,
    typical_age_years_from numeric,
    typical_age_years_to numeric,
    severity issue_severity NOT NULL DEFAULT 'advisory',
    avg_cost_workshop_eur numeric(10,2),
    avg_cost_diy_eur numeric(10,2),
    source_type knowledge_source_type NOT NULL,
    source_url text,
    mention_count integer NOT NULL DEFAULT 1,
    confidence_score numeric(4,3) NOT NULL DEFAULT 0.5,
    embedding vector(1536),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_kb_make_model_mileage ON knowledge_base_issues (make, model, typical_mileage_from, typical_mileage_to);
CREATE INDEX idx_kb_embedding ON knowledge_base_issues USING ivfflat (embedding vector_cosine_ops);

CREATE TABLE vehicle_warnings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    vehicle_id uuid NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    issue_id uuid NOT NULL REFERENCES knowledge_base_issues(id),
    status warning_status NOT NULL DEFAULT 'open',
    triggered_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz,
    user_notes text,
    UNIQUE (vehicle_id, issue_id)
);

CREATE TABLE repair_guides (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    vehicle_id uuid REFERENCES vehicles(id) ON DELETE CASCADE,
    issue_id uuid REFERENCES knowledge_base_issues(id),
    title text NOT NULL,
    skill_level diy_skill_level NOT NULL,
    content_markdown text NOT NULL,
    llm_model_used text NOT NULL,
    prompt_version text NOT NULL,
    generated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE guide_steps (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    guide_id uuid NOT NULL REFERENCES repair_guides(id) ON DELETE CASCADE,
    step_number integer NOT NULL,
    instruction text NOT NULL,
    warning_note text,
    estimated_minutes integer,
    UNIQUE (guide_id, step_number)
);

CREATE TABLE parts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    oem_number text NOT NULL,
    name text NOT NULL,
    category text,
    compatible_makes text[] NOT NULL DEFAULT '{}',
    compatible_models text[] NOT NULL DEFAULT '{}',
    UNIQUE (oem_number)
);

CREATE TABLE guide_parts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    guide_id uuid NOT NULL REFERENCES repair_guides(id) ON DELETE CASCADE,
    part_id uuid NOT NULL REFERENCES parts(id),
    quantity integer NOT NULL DEFAULT 1
);

CREATE TABLE part_offers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    part_id uuid NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
    vendor part_vendor NOT NULL,
    vendor_sku text,
    price_eur numeric(10,2) NOT NULL,
    url text NOT NULL,
    fetched_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_part_offers_part_id ON part_offers (part_id, price_eur);

CREATE TABLE tools (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    category text
);

CREATE TABLE guide_tools (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    guide_id uuid NOT NULL REFERENCES repair_guides(id) ON DELETE CASCADE,
    tool_id uuid NOT NULL REFERENCES tools(id),
    required boolean NOT NULL DEFAULT true
);

CREATE TABLE user_tools (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tool_id uuid NOT NULL REFERENCES tools(id),
    owned_since timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, tool_id)
);

CREATE TABLE expenses (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    vehicle_id uuid REFERENCES vehicles(id) ON DELETE SET NULL,
    category expense_category NOT NULL,
    amount_eur numeric(10,2) NOT NULL,
    description text,
    source expense_source NOT NULL,
    transaction_date date NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_expenses_user_date ON expenses (user_id, transaction_date);

CREATE TABLE budget_forecasts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    vehicle_id uuid NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    issue_id uuid REFERENCES knowledge_base_issues(id),
    forecast_month date NOT NULL,
    estimated_cost_workshop_eur numeric(10,2) NOT NULL,
    estimated_cost_diy_eur numeric(10,2),
    recommended_monthly_reserve_eur numeric(10,2) NOT NULL,
    status forecast_status NOT NULL DEFAULT 'active',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE forum_scrape_sources (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_name text NOT NULL,
    base_url text NOT NULL,
    robots_txt_compliant boolean NOT NULL DEFAULT true,
    last_crawled_at timestamptz
);
