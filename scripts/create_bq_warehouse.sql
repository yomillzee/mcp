-- Run once in BigQuery (Console → SQL) for Penn warehouse datasets.
-- GA4 native export stays in analytics_313855909 — do not duplicate events_* here.

-- Create datasets (adjust project id if needed)
CREATE SCHEMA IF NOT EXISTS `penn-community-b-1699391543298.warehouse_google_ads`
  OPTIONS(location="US");
CREATE SCHEMA IF NOT EXISTS `penn-community-b-1699391543298.warehouse_meta`
  OPTIONS(location="US");
CREATE SCHEMA IF NOT EXISTS `penn-community-b-1699391543298.warehouse_linkedin`
  OPTIONS(location="US");

-- Account-level daily metrics (partitioned). Repeat per dataset.
CREATE TABLE IF NOT EXISTS `penn-community-b-1699391543298.warehouse_google_ads.metrics_account_daily` (
  account_id STRING NOT NULL,
  metric_date DATE NOT NULL,
  spend FLOAT64,
  clicks INT64,
  impressions INT64,
  conversions FLOAT64,
  conversion_value FLOAT64,
  synced_at TIMESTAMP
)
PARTITION BY metric_date
CLUSTER BY account_id;

CREATE TABLE IF NOT EXISTS `penn-community-b-1699391543298.warehouse_meta.metrics_account_daily` (
  account_id STRING NOT NULL,
  metric_date DATE NOT NULL,
  spend FLOAT64,
  clicks INT64,
  impressions INT64,
  conversions FLOAT64,
  conversion_value FLOAT64,
  synced_at TIMESTAMP
)
PARTITION BY metric_date
CLUSTER BY account_id;

CREATE TABLE IF NOT EXISTS `penn-community-b-1699391543298.warehouse_linkedin.metrics_account_daily` (
  account_id STRING NOT NULL,
  metric_date DATE NOT NULL,
  spend FLOAT64,
  clicks INT64,
  impressions INT64,
  conversions FLOAT64,
  conversion_value FLOAT64,
  synced_at TIMESTAMP
)
PARTITION BY metric_date
CLUSTER BY account_id;

-- Optional campaign-level table (schema ready; sync job fills in a later phase)
CREATE TABLE IF NOT EXISTS `penn-community-b-1699391543298.warehouse_google_ads.metrics_campaign_daily` (
  account_id STRING NOT NULL,
  campaign_id STRING NOT NULL,
  campaign_name STRING,
  metric_date DATE NOT NULL,
  spend FLOAT64,
  clicks INT64,
  impressions INT64,
  conversions FLOAT64,
  conversion_value FLOAT64,
  synced_at TIMESTAMP
)
PARTITION BY metric_date
CLUSTER BY account_id, campaign_id;
