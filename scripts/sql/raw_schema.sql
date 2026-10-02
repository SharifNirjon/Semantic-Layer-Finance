CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS marts;
CREATE SCHEMA IF NOT EXISTS audit;

DROP TABLE IF EXISTS raw.branches, raw.products, raw.customers, raw.customer_attribute_history, raw.accounts,
  raw.account_monthly_snapshots, raw.transactions, raw.loans, raw.loan_monthly_snapshots, raw.campaigns,
  raw.campaign_responses, raw.gl_daily_balances CASCADE;

CREATE TABLE raw.branches (
  branch_id int PRIMARY KEY, branch_name text NOT NULL, region text NOT NULL, opened_date date NOT NULL);
CREATE TABLE raw.products (
  product_id int PRIMARY KEY, product_code text NOT NULL, product_name text NOT NULL, category text NOT NULL,
  is_casa boolean NOT NULL, interest_rate numeric(6,4) NOT NULL);
CREATE TABLE raw.customers (
  customer_id int PRIMARY KEY, segment text NOT NULL, acquisition_channel text NOT NULL,
  acquisition_date date NOT NULL, home_branch_id int NOT NULL, status text NOT NULL, churn_date date);
CREATE TABLE raw.customer_attribute_history (
  customer_id int NOT NULL, segment text NOT NULL, home_branch_id int NOT NULL,
  valid_from date NOT NULL, valid_to date);
CREATE TABLE raw.accounts (
  account_id int PRIMARY KEY, customer_id int NOT NULL, product_id int NOT NULL, branch_id int NOT NULL,
  open_date date NOT NULL, close_date date, status text NOT NULL);
CREATE TABLE raw.account_monthly_snapshots (
  account_id int NOT NULL, month_end date NOT NULL, closing_balance numeric(18,2) NOT NULL,
  avg_daily_balance numeric(18,2) NOT NULL, interest_accrued numeric(18,2) NOT NULL);
CREATE TABLE raw.transactions (
  txn_id int PRIMARY KEY, account_id int NOT NULL, customer_id int NOT NULL, channel text NOT NULL,
  amount numeric(18,2) NOT NULL, direction text NOT NULL, posting_date date NOT NULL, value_date date NOT NULL);
CREATE TABLE raw.loans (
  loan_id int PRIMARY KEY, account_id int NOT NULL, customer_id int NOT NULL, product_id int NOT NULL,
  branch_id int NOT NULL, principal numeric(18,2) NOT NULL, interest_rate numeric(6,4) NOT NULL,
  term_months int NOT NULL, disbursed_date date NOT NULL, outstanding numeric(18,2) NOT NULL, sector text NOT NULL,
  classification text NOT NULL, days_past_due int NOT NULL);
CREATE TABLE raw.loan_monthly_snapshots (
  loan_id int NOT NULL, account_id int NOT NULL, month_end date NOT NULL, outstanding numeric(18,2) NOT NULL,
  days_past_due int NOT NULL, classification text NOT NULL);
CREATE TABLE raw.campaigns (
  campaign_id int PRIMARY KEY, campaign_name text NOT NULL, channel text NOT NULL, cost numeric(18,2) NOT NULL,
  target_segment text NOT NULL, start_date date NOT NULL, end_date date NOT NULL);
CREATE TABLE raw.campaign_responses (
  response_id int PRIMARY KEY, campaign_id int NOT NULL, customer_id int NOT NULL, responded boolean NOT NULL,
  converted_product text, response_date date NOT NULL);
CREATE TABLE raw.gl_daily_balances (
  gl_date date NOT NULL, gl_code text NOT NULL, gl_name text NOT NULL, balance numeric(20,2) NOT NULL);

CREATE TABLE IF NOT EXISTS audit.tool_calls (
  id bigserial PRIMARY KEY, ts timestamptz NOT NULL DEFAULT now(), user_name text NOT NULL, role text NOT NULL,
  tool text NOT NULL, args jsonb NOT NULL, cube_query jsonb, row_count int, latency_ms int NOT NULL,
  status text NOT NULL, error text);
CREATE INDEX IF NOT EXISTS tool_calls_ts_idx ON audit.tool_calls (ts DESC);
CREATE TABLE IF NOT EXISTS audit.gl_adjustments (
  gl_code text PRIMARY KEY, delta_pct numeric(8,4) NOT NULL, note text, created_at timestamptz DEFAULT now());
