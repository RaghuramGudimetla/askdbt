#!/usr/bin/env python3
"""
Generate comprehensive sample_data/manifest.json and sample_data/catalog.json
matching every field present in a real dbt 1.7 project.

Run: python sample_data/generate_sample_data.py
"""

import hashlib
import json
import time
from pathlib import Path

OUT_DIR = Path(__file__).parent
PROJECT = "banking"
DATABASE = "WAREHOUSE"

# ---------------------------------------------------------------------------
# SQL (raw_code / compiled_code) for every model
# ---------------------------------------------------------------------------
SQL = {
    # ── STAGING ─────────────────────────────────────────────────────────────
    "stg_customers": {
        "raw": """\
with source as (
    select * from {{ source('banking_raw', 'customers') }}
),
kyc_raw as (
    select customer_number, status as kyc_status
    from {{ source('banking_raw', 'kyc') }}
),
renamed as (
    select
        md5(cast(s.customer_number as varchar))  as customer_id,
        s.customer_number,
        lower(trim(s.first_name))                as first_name,
        lower(trim(s.last_name))                 as last_name,
        lower(trim(s.email))                     as email_address,
        s.phone                                  as phone_number,
        cast(s.dob as date)                      as date_of_birth,
        s.nationality_code,
        s.city,
        s.postcode,
        coalesce(k.kyc_status, 'PENDING')        as kyc_status,
        s.is_deleted,
        s.loaded_at                              as _loaded_at,
        'CORE_BANKING'                           as _source_system
    from source s
    left join kyc_raw k using (customer_number)
)
select * from renamed""",
        "compiled": """\
with source as (
    select * from WAREHOUSE.RAW.customers
),
kyc_raw as (
    select customer_number, status as kyc_status
    from WAREHOUSE.RAW.kyc
),
renamed as (
    select
        md5(cast(s.customer_number as varchar))  as customer_id,
        s.customer_number,
        lower(trim(s.first_name))                as first_name,
        lower(trim(s.last_name))                 as last_name,
        lower(trim(s.email))                     as email_address,
        s.phone                                  as phone_number,
        cast(s.dob as date)                      as date_of_birth,
        s.nationality_code,
        s.city,
        s.postcode,
        coalesce(k.kyc_status, 'PENDING')        as kyc_status,
        s.is_deleted,
        s.loaded_at                              as _loaded_at,
        'CORE_BANKING'                           as _source_system
    from source s
    left join kyc_raw k using (customer_number)
)
select * from renamed""",
    },
    "stg_accounts": {
        "raw": """\
with source as (
    select * from {{ source('banking_raw', 'accounts') }}
),
renamed as (
    select
        md5(cast(account_number as varchar))     as account_id,
        account_number,
        md5(cast(customer_number as varchar))    as customer_id,
        product_code,
        branch_code,
        cast(opened_date as date)               as opened_date,
        cast(closed_date as date)               as closed_date,
        upper(status)                           as account_status,
        cast(credit_limit as numeric(18,2))     as credit_limit,
        cast(current_balance as numeric(18,2))  as current_balance,
        currency_code,
        is_overdrawn,
        loaded_at                               as _loaded_at
    from source
    where account_number is not null
)
select * from renamed""",
        "compiled": """\
with source as (
    select * from WAREHOUSE.RAW.accounts
),
renamed as (
    select
        md5(cast(account_number as varchar))     as account_id,
        account_number,
        md5(cast(customer_number as varchar))    as customer_id,
        product_code,
        branch_code,
        cast(opened_date as date)               as opened_date,
        cast(closed_date as date)               as closed_date,
        upper(status)                           as account_status,
        cast(credit_limit as numeric(18,2))     as credit_limit,
        cast(current_balance as numeric(18,2))  as current_balance,
        currency_code,
        is_overdrawn,
        loaded_at                               as _loaded_at
    from source
    where account_number is not null
)
select * from renamed""",
    },
    "stg_transactions": {
        "raw": """\
{{
    config(
        materialized='incremental',
        unique_key='transaction_id',
        incremental_strategy='merge'
    )
}}

with source as (
    select * from {{ source('banking_raw', 'transactions') }}
    {% if is_incremental() %}
        where loaded_at > (select max(_loaded_at) from {{ this }})
    {% endif %}
),
renamed as (
    select
        transaction_id,
        md5(cast(account_number as varchar))    as account_id,
        cast(transaction_date as date)          as transaction_date,
        cast(transaction_datetime as timestamp) as transaction_datetime,
        upper(transaction_type)                 as transaction_type,
        upper(channel)                          as channel,
        cast(amount as numeric(18,2))           as amount,
        currency_code,
        upper(direction)                        as direction,
        merchant_name,
        merchant_category_code                 as mcc,
        cast(running_balance as numeric(18,2))  as running_balance,
        is_flagged_fraud,
        loaded_at                               as _loaded_at
    from source
)
select * from renamed""",
        "compiled": """\
with source as (
    select * from WAREHOUSE.RAW.transactions
    where loaded_at > (select max(_loaded_at) from WAREHOUSE.STAGING.stg_transactions)
),
renamed as (
    select
        transaction_id,
        md5(cast(account_number as varchar))    as account_id,
        cast(transaction_date as date)          as transaction_date,
        cast(transaction_datetime as timestamp) as transaction_datetime,
        upper(transaction_type)                 as transaction_type,
        upper(channel)                          as channel,
        cast(amount as numeric(18,2))           as amount,
        currency_code,
        upper(direction)                        as direction,
        merchant_name,
        merchant_category_code                 as mcc,
        cast(running_balance as numeric(18,2))  as running_balance,
        is_flagged_fraud,
        loaded_at                               as _loaded_at
    from source
)
select * from renamed""",
    },
    "stg_loan_schedule": {
        "raw": """\
with source as (
    select * from {{ source('banking_raw', 'loan_schedule') }}
),
renamed as (
    select
        loan_schedule_id,
        md5(cast(account_number as varchar))    as account_id,
        cast(due_date as date)                  as due_date,
        cast(paid_date as date)                 as paid_date,
        cast(principal_due as numeric(18,2))    as principal_due,
        cast(interest_due as numeric(18,2))     as interest_due,
        cast(principal_paid as numeric(18,2))   as principal_paid,
        cast(interest_paid as numeric(18,2))    as interest_paid,
        upper(repayment_status)                 as repayment_status,
        installment_number,
        loaded_at                               as _loaded_at
    from source
)
select * from renamed""",
        "compiled": """\
with source as (
    select * from WAREHOUSE.RAW.loan_schedule
),
renamed as (
    select
        loan_schedule_id,
        md5(cast(account_number as varchar))    as account_id,
        cast(due_date as date)                  as due_date,
        cast(paid_date as date)                 as paid_date,
        cast(principal_due as numeric(18,2))    as principal_due,
        cast(interest_due as numeric(18,2))     as interest_due,
        cast(principal_paid as numeric(18,2))   as principal_paid,
        cast(interest_paid as numeric(18,2))    as interest_paid,
        upper(repayment_status)                 as repayment_status,
        installment_number,
        loaded_at                               as _loaded_at
    from source
)
select * from renamed""",
    },
    "stg_kyc_verifications": {
        "raw": """\
with source as (
    select * from {{ source('banking_raw', 'kyc') }}
),
renamed as (
    select
        verification_id,
        customer_number,
        upper(status)                           as verification_status,
        upper(provider)                         as provider,
        cast(verified_at as timestamp)          as verified_at,
        cast(expires_at as timestamp)           as expires_at,
        risk_score,
        upper(risk_tier)                        as risk_tier,
        loaded_at                               as _loaded_at
    from source
)
select * from renamed""",
        "compiled": """\
with source as (
    select * from WAREHOUSE.RAW.kyc
),
renamed as (
    select
        verification_id,
        customer_number,
        upper(status)                           as verification_status,
        upper(provider)                         as provider,
        cast(verified_at as timestamp)          as verified_at,
        cast(expires_at as timestamp)           as expires_at,
        risk_score,
        upper(risk_tier)                        as risk_tier,
        loaded_at                               as _loaded_at
    from source
)
select * from renamed""",
    },
    # ── DIMENSIONS ──────────────────────────────────────────────────────────
    "dim_customers": {
        "raw": """\
with customers as (
    select * from {{ ref('stg_customers') }}
    where is_deleted = false
),
kyc as (
    select
        customer_number,
        verification_status,
        risk_score,
        risk_tier,
        verified_at,
        expires_at,
        row_number() over (
            partition by customer_number order by verified_at desc
        ) as rn
    from {{ ref('stg_kyc_verifications') }}
),
latest_kyc as (
    select * from kyc where rn = 1
),
final as (
    select
        c.customer_id,
        c.customer_number,
        c.first_name,
        c.last_name,
        c.first_name || ' ' || c.last_name      as full_name,
        c.email_address,
        c.phone_number,
        c.date_of_birth,
        date_part('year', age(c.date_of_birth))::int as age,
        c.nationality_code,
        c.city,
        c.postcode,
        c.kyc_status,
        k.verification_status                   as kyc_verification_status,
        k.risk_score,
        k.risk_tier,
        k.verified_at                           as kyc_verified_at,
        k.expires_at                            as kyc_expires_at,
        c._loaded_at,
        current_timestamp                       as dbt_updated_at
    from customers c
    left join latest_kyc k using (customer_number)
)
select * from final""",
        "compiled": """\
with customers as (
    select * from WAREHOUSE.STAGING.stg_customers
    where is_deleted = false
),
kyc as (
    select
        customer_number,
        verification_status,
        risk_score,
        risk_tier,
        verified_at,
        expires_at,
        row_number() over (
            partition by customer_number order by verified_at desc
        ) as rn
    from WAREHOUSE.STAGING.stg_kyc_verifications
),
latest_kyc as (
    select * from kyc where rn = 1
),
final as (
    select
        c.customer_id,
        c.customer_number,
        c.first_name,
        c.last_name,
        c.first_name || ' ' || c.last_name      as full_name,
        c.email_address,
        c.phone_number,
        c.date_of_birth,
        date_part('year', age(c.date_of_birth))::int as age,
        c.nationality_code,
        c.city,
        c.postcode,
        c.kyc_status,
        k.verification_status                   as kyc_verification_status,
        k.risk_score,
        k.risk_tier,
        k.verified_at                           as kyc_verified_at,
        k.expires_at                            as kyc_expires_at,
        c._loaded_at,
        current_timestamp                       as dbt_updated_at
    from customers c
    left join latest_kyc k using (customer_number)
)
select * from final""",
    },
    "dim_accounts": {
        "raw": """\
with accounts as (
    select * from {{ ref('stg_accounts') }}
),
customers as (
    select customer_id, full_name, risk_tier
    from {{ ref('dim_customers') }}
),
products as (
    select product_code, product_name, product_category, interest_rate_pct
    from {{ ref('dim_products') }}
),
final as (
    select
        a.account_id,
        a.account_number,
        a.customer_id,
        c.full_name                             as customer_name,
        c.risk_tier                             as customer_risk_tier,
        a.product_code,
        p.product_name,
        p.product_category,
        p.interest_rate_pct,
        a.branch_code,
        a.opened_date,
        a.closed_date,
        a.account_status,
        a.credit_limit,
        a.current_balance,
        a.currency_code,
        a.is_overdrawn,
        case
            when a.account_status = 'ACTIVE' and a.is_overdrawn then 'OVERDRAWN'
            when a.account_status = 'ACTIVE'                    then 'HEALTHY'
            when a.account_status = 'CLOSED'                    then 'CLOSED'
            else 'OTHER'
        end                                     as account_health,
        a._loaded_at,
        current_timestamp                       as dbt_updated_at
    from accounts a
    left join customers c using (customer_id)
    left join products p using (product_code)
)
select * from final""",
        "compiled": """\
with accounts as (
    select * from WAREHOUSE.STAGING.stg_accounts
),
customers as (
    select customer_id, full_name, risk_tier
    from WAREHOUSE.DIMENSIONS.dim_customers
),
products as (
    select product_code, product_name, product_category, interest_rate_pct
    from WAREHOUSE.DIMENSIONS.dim_products
),
final as (
    select
        a.account_id,
        a.account_number,
        a.customer_id,
        c.full_name                             as customer_name,
        c.risk_tier                             as customer_risk_tier,
        a.product_code,
        p.product_name,
        p.product_category,
        p.interest_rate_pct,
        a.branch_code,
        a.opened_date,
        a.closed_date,
        a.account_status,
        a.credit_limit,
        a.current_balance,
        a.currency_code,
        a.is_overdrawn,
        case
            when a.account_status = 'ACTIVE' and a.is_overdrawn then 'OVERDRAWN'
            when a.account_status = 'ACTIVE'                    then 'HEALTHY'
            when a.account_status = 'CLOSED'                    then 'CLOSED'
            else 'OTHER'
        end                                     as account_health,
        a._loaded_at,
        current_timestamp                       as dbt_updated_at
    from accounts a
    left join customers c using (customer_id)
    left join products p using (product_code)
)
select * from final""",
    },
    "dim_products": {
        "raw": """\
with source as (
    select * from {{ source('banking_raw', 'products') }}
),
renamed as (
    select
        product_code,
        product_name,
        upper(product_category)                 as product_category,
        upper(product_type)                     as product_type,
        cast(interest_rate_pct as numeric(6,4)) as interest_rate_pct,
        cast(annual_fee as numeric(10,2))       as annual_fee,
        cast(min_credit_limit as numeric(18,2)) as min_credit_limit,
        cast(max_credit_limit as numeric(18,2)) as max_credit_limit,
        is_active,
        cast(launched_date as date)             as launched_date
    from source
)
select * from renamed""",
        "compiled": """\
with source as (
    select * from WAREHOUSE.RAW.products
),
renamed as (
    select
        product_code,
        product_name,
        upper(product_category)                 as product_category,
        upper(product_type)                     as product_type,
        cast(interest_rate_pct as numeric(6,4)) as interest_rate_pct,
        cast(annual_fee as numeric(10,2))       as annual_fee,
        cast(min_credit_limit as numeric(18,2)) as min_credit_limit,
        cast(max_credit_limit as numeric(18,2)) as max_credit_limit,
        is_active,
        cast(launched_date as date)             as launched_date
    from source
)
select * from renamed""",
    },
    "dim_branches": {
        "raw": """\
with source as (
    select * from {{ source('banking_raw', 'branches') }}
),
renamed as (
    select
        branch_code,
        branch_name,
        upper(branch_type)                      as branch_type,
        region,
        city,
        postcode,
        cast(opened_date as date)               as opened_date,
        cast(closed_date as date)               as closed_date,
        is_active,
        sort_code
    from source
)
select * from renamed""",
        "compiled": """\
with source as (
    select * from WAREHOUSE.RAW.branches
),
renamed as (
    select
        branch_code,
        branch_name,
        upper(branch_type)                      as branch_type,
        region,
        city,
        postcode,
        cast(opened_date as date)               as opened_date,
        cast(closed_date as date)               as closed_date,
        is_active,
        sort_code
    from source
)
select * from renamed""",
    },
    "dim_date": {
        "raw": """\
{{ config(materialized='table') }}

with date_spine as (
    {{ dbt_utils.date_spine(
        datepart='day',
        start_date="cast('2015-01-01' as date)",
        end_date="cast('2030-01-01' as date)"
    ) }}
),
final as (
    select
        cast(date_day as date)                              as date_id,
        date_day,
        date_part('year',    date_day)::int                 as year,
        date_part('quarter', date_day)::int                 as quarter,
        date_part('month',   date_day)::int                 as month,
        to_char(date_day, 'Month')                          as month_name,
        date_part('week',    date_day)::int                 as week_of_year,
        date_part('day',     date_day)::int                 as day_of_month,
        date_part('dow',     date_day)::int                 as day_of_week,
        to_char(date_day, 'Day')                            as day_name,
        date_part('doy',     date_day)::int                 as day_of_year,
        date_trunc('month',   date_day)::date               as first_day_of_month,
        (date_trunc('month', date_day)
            + interval '1 month - 1 day')::date             as last_day_of_month,
        date_trunc('quarter', date_day)::date               as first_day_of_quarter,
        date_trunc('year',    date_day)::date               as first_day_of_year,
        date_part('dow', date_day) in (0, 6)                as is_weekend,
        to_char(date_day, 'YYYYMM')                         as year_month
    from date_spine
)
select * from final""",
        "compiled": """\
with date_spine as (
    select generate_series(
        '2015-01-01'::date,
        '2029-12-31'::date,
        interval '1 day'
    )::date as date_day
),
final as (
    select
        date_day                                            as date_id,
        date_day,
        date_part('year',    date_day)::int                 as year,
        date_part('quarter', date_day)::int                 as quarter,
        date_part('month',   date_day)::int                 as month,
        to_char(date_day, 'Month')                          as month_name,
        date_part('week',    date_day)::int                 as week_of_year,
        date_part('day',     date_day)::int                 as day_of_month,
        date_part('dow',     date_day)::int                 as day_of_week,
        to_char(date_day, 'Day')                            as day_name,
        date_part('doy',     date_day)::int                 as day_of_year,
        date_trunc('month',   date_day)::date               as first_day_of_month,
        (date_trunc('month', date_day)
            + interval '1 month - 1 day')::date             as last_day_of_month,
        date_trunc('quarter', date_day)::date               as first_day_of_quarter,
        date_trunc('year',    date_day)::date               as first_day_of_year,
        date_part('dow', date_day) in (0, 6)                as is_weekend,
        to_char(date_day, 'YYYYMM')                         as year_month
    from date_spine
)
select * from final""",
    },
    # ── FACTS ───────────────────────────────────────────────────────────────
    "fct_transactions": {
        "raw": """\
{{ config(materialized='table', sort='transaction_date', dist='account_id') }}

with transactions as (
    select * from {{ ref('stg_transactions') }}
),
accounts as (
    select account_id, customer_id, product_name, product_category, branch_code
    from {{ ref('dim_accounts') }}
),
final as (
    select
        t.transaction_id,
        t.account_id,
        a.customer_id,
        t.transaction_date,
        t.transaction_datetime,
        t.transaction_type,
        t.channel,
        t.amount,
        t.currency_code,
        t.direction,
        t.merchant_name,
        t.mcc,
        t.running_balance,
        t.is_flagged_fraud,
        a.product_name,
        a.product_category,
        a.branch_code,
        case
            when t.amount < 100   then 'MICRO'
            when t.amount < 1000  then 'SMALL'
            when t.amount < 10000 then 'MEDIUM'
            else                       'LARGE'
        end                                     as amount_band,
        t._loaded_at
    from transactions t
    inner join accounts a using (account_id)
)
select * from final""",
        "compiled": """\
with transactions as (
    select * from WAREHOUSE.STAGING.stg_transactions
),
accounts as (
    select account_id, customer_id, product_name, product_category, branch_code
    from WAREHOUSE.DIMENSIONS.dim_accounts
),
final as (
    select
        t.transaction_id,
        t.account_id,
        a.customer_id,
        t.transaction_date,
        t.transaction_datetime,
        t.transaction_type,
        t.channel,
        t.amount,
        t.currency_code,
        t.direction,
        t.merchant_name,
        t.mcc,
        t.running_balance,
        t.is_flagged_fraud,
        a.product_name,
        a.product_category,
        a.branch_code,
        case
            when t.amount < 100   then 'MICRO'
            when t.amount < 1000  then 'SMALL'
            when t.amount < 10000 then 'MEDIUM'
            else                       'LARGE'
        end                                     as amount_band,
        t._loaded_at
    from transactions t
    inner join accounts a using (account_id)
)
select * from final""",
    },
    "fct_loan_repayments": {
        "raw": """\
{{ config(materialized='table') }}

with loan_schedule as (
    select * from {{ ref('stg_loan_schedule') }}
),
accounts as (
    select account_id, customer_id, product_name, credit_limit, interest_rate_pct
    from {{ ref('dim_accounts') }}
),
final as (
    select
        l.loan_schedule_id,
        l.account_id,
        a.customer_id,
        l.due_date,
        l.paid_date,
        l.installment_number,
        l.principal_due,
        l.interest_due,
        l.principal_due + l.interest_due                    as total_due,
        l.principal_paid,
        l.interest_paid,
        l.principal_paid + l.interest_paid                  as total_paid,
        (l.principal_due  - coalesce(l.principal_paid, 0))
        + (l.interest_due - coalesce(l.interest_paid, 0))  as arrears_amount,
        l.repayment_status,
        case
            when l.repayment_status = 'PAID' then 0
            when l.paid_date is null and l.due_date < current_date
                then (current_date - l.due_date)
            else 0
        end                                                 as days_past_due,
        a.product_name,
        a.interest_rate_pct,
        l._loaded_at
    from loan_schedule l
    inner join accounts a using (account_id)
)
select * from final""",
        "compiled": """\
with loan_schedule as (
    select * from WAREHOUSE.STAGING.stg_loan_schedule
),
accounts as (
    select account_id, customer_id, product_name, credit_limit, interest_rate_pct
    from WAREHOUSE.DIMENSIONS.dim_accounts
),
final as (
    select
        l.loan_schedule_id,
        l.account_id,
        a.customer_id,
        l.due_date,
        l.paid_date,
        l.installment_number,
        l.principal_due,
        l.interest_due,
        l.principal_due + l.interest_due                    as total_due,
        l.principal_paid,
        l.interest_paid,
        l.principal_paid + l.interest_paid                  as total_paid,
        (l.principal_due  - coalesce(l.principal_paid, 0))
        + (l.interest_due - coalesce(l.interest_paid, 0))  as arrears_amount,
        l.repayment_status,
        case
            when l.repayment_status = 'PAID' then 0
            when l.paid_date is null and l.due_date < current_date
                then (current_date - l.due_date)
            else 0
        end                                                 as days_past_due,
        a.product_name,
        a.interest_rate_pct,
        l._loaded_at
    from loan_schedule l
    inner join accounts a using (account_id)
)
select * from final""",
    },
    "fct_payments": {
        "raw": """\
{{ config(materialized='table') }}

with transactions as (
    select * from {{ ref('stg_transactions') }}
    where transaction_type in (
        'PAYMENT', 'DIRECT_DEBIT', 'STANDING_ORDER', 'FASTER_PAYMENT'
    )
),
accounts as (
    select account_id, customer_id, product_name
    from {{ ref('dim_accounts') }}
),
final as (
    select
        t.transaction_id                        as payment_id,
        t.account_id,
        a.customer_id,
        t.transaction_date                      as payment_date,
        t.transaction_datetime                  as payment_datetime,
        t.transaction_type                      as payment_type,
        t.channel                               as payment_channel,
        t.amount                                as payment_amount,
        t.currency_code,
        t.direction,
        t.merchant_name                         as beneficiary_name,
        t.is_flagged_fraud,
        a.product_name,
        t._loaded_at
    from transactions t
    inner join accounts a using (account_id)
)
select * from final""",
        "compiled": """\
with transactions as (
    select * from WAREHOUSE.STAGING.stg_transactions
    where transaction_type in (
        'PAYMENT', 'DIRECT_DEBIT', 'STANDING_ORDER', 'FASTER_PAYMENT'
    )
),
accounts as (
    select account_id, customer_id, product_name
    from WAREHOUSE.DIMENSIONS.dim_accounts
),
final as (
    select
        t.transaction_id                        as payment_id,
        t.account_id,
        a.customer_id,
        t.transaction_date                      as payment_date,
        t.transaction_datetime                  as payment_datetime,
        t.transaction_type                      as payment_type,
        t.channel                               as payment_channel,
        t.amount                                as payment_amount,
        t.currency_code,
        t.direction,
        t.merchant_name                         as beneficiary_name,
        t.is_flagged_fraud,
        a.product_name,
        t._loaded_at
    from transactions t
    inner join accounts a using (account_id)
)
select * from final""",
    },
    # ── INTERMEDIATES ────────────────────────────────────────────────────────
    "int_customer_transactions_daily": {
        "raw": """\
with transactions as (
    select * from {{ ref('fct_transactions') }}
),
customers as (
    select customer_id, full_name, risk_tier
    from {{ ref('dim_customers') }}
),
daily_agg as (
    select
        t.customer_id,
        t.transaction_date,
        count(*)                                            as transaction_count,
        sum(case when t.direction = 'DEBIT'  then t.amount else 0 end) as total_debits,
        sum(case when t.direction = 'CREDIT' then t.amount else 0 end) as total_credits,
        sum(t.amount)                                       as total_amount,
        count(distinct t.account_id)                        as accounts_used,
        count(distinct t.channel)                           as channels_used,
        sum(t.is_flagged_fraud::int)                        as fraud_flag_count,
        max(t.amount)                                       as max_single_transaction,
        avg(t.amount)                                       as avg_transaction_amount,
        count(distinct t.mcc)                               as distinct_merchant_categories
    from transactions t
    group by t.customer_id, t.transaction_date
),
final as (
    select
        d.customer_id,
        c.full_name,
        c.risk_tier,
        d.transaction_date,
        d.transaction_count,
        d.total_debits,
        d.total_credits,
        d.total_amount,
        d.accounts_used,
        d.channels_used,
        d.fraud_flag_count,
        d.max_single_transaction,
        d.avg_transaction_amount,
        d.distinct_merchant_categories
    from daily_agg d
    left join customers c using (customer_id)
)
select * from final""",
        "compiled": """\
with transactions as (
    select * from WAREHOUSE.FACTS.fct_transactions
),
customers as (
    select customer_id, full_name, risk_tier
    from WAREHOUSE.DIMENSIONS.dim_customers
),
daily_agg as (
    select
        t.customer_id,
        t.transaction_date,
        count(*)                                            as transaction_count,
        sum(case when t.direction = 'DEBIT'  then t.amount else 0 end) as total_debits,
        sum(case when t.direction = 'CREDIT' then t.amount else 0 end) as total_credits,
        sum(t.amount)                                       as total_amount,
        count(distinct t.account_id)                        as accounts_used,
        count(distinct t.channel)                           as channels_used,
        sum(t.is_flagged_fraud::int)                        as fraud_flag_count,
        max(t.amount)                                       as max_single_transaction,
        avg(t.amount)                                       as avg_transaction_amount,
        count(distinct t.mcc)                               as distinct_merchant_categories
    from transactions t
    group by t.customer_id, t.transaction_date
),
final as (
    select
        d.customer_id,
        c.full_name,
        c.risk_tier,
        d.transaction_date,
        d.transaction_count,
        d.total_debits,
        d.total_credits,
        d.total_amount,
        d.accounts_used,
        d.channels_used,
        d.fraud_flag_count,
        d.max_single_transaction,
        d.avg_transaction_amount,
        d.distinct_merchant_categories
    from daily_agg d
    left join customers c using (customer_id)
)
select * from final""",
    },
    "int_loan_arrears": {
        "raw": """\
with repayments as (
    select * from {{ ref('fct_loan_repayments') }}
    where repayment_status != 'PAID'
),
accounts as (
    select account_id, customer_id, product_name, credit_limit
    from {{ ref('dim_accounts') }}
),
arrears as (
    select
        r.account_id,
        a.customer_id,
        a.product_name,
        a.credit_limit,
        count(*)                                            as missed_installments,
        sum(r.arrears_amount)                               as total_arrears,
        max(r.days_past_due)                                as max_days_past_due,
        min(r.due_date)                                     as earliest_missed_due_date,
        case
            when max(r.days_past_due) = 0   then 'CURRENT'
            when max(r.days_past_due) <= 30  then 'STAGE_1'
            when max(r.days_past_due) <= 90  then 'STAGE_2'
            else                                  'STAGE_3'
        end                                                 as ifrs9_stage,
        current_timestamp                                   as calculated_at
    from repayments r
    inner join accounts a using (account_id)
    group by r.account_id, a.customer_id, a.product_name, a.credit_limit
)
select * from arrears""",
        "compiled": """\
with repayments as (
    select * from WAREHOUSE.FACTS.fct_loan_repayments
    where repayment_status != 'PAID'
),
accounts as (
    select account_id, customer_id, product_name, credit_limit
    from WAREHOUSE.DIMENSIONS.dim_accounts
),
arrears as (
    select
        r.account_id,
        a.customer_id,
        a.product_name,
        a.credit_limit,
        count(*)                                            as missed_installments,
        sum(r.arrears_amount)                               as total_arrears,
        max(r.days_past_due)                                as max_days_past_due,
        min(r.due_date)                                     as earliest_missed_due_date,
        case
            when max(r.days_past_due) = 0   then 'CURRENT'
            when max(r.days_past_due) <= 30  then 'STAGE_1'
            when max(r.days_past_due) <= 90  then 'STAGE_2'
            else                                  'STAGE_3'
        end                                                 as ifrs9_stage,
        current_timestamp                                   as calculated_at
    from repayments r
    inner join accounts a using (account_id)
    group by r.account_id, a.customer_id, a.product_name, a.credit_limit
)
select * from arrears""",
    },
    # ── MARTS ────────────────────────────────────────────────────────────────
    "mart_customer_360": {
        "raw": """\
{{ config(materialized='table') }}

with customers as (
    select * from {{ ref('dim_customers') }}
),
accounts as (
    select
        customer_id,
        count(*)                                                        as total_accounts,
        count(case when account_status = 'ACTIVE' then 1 end)          as active_accounts,
        sum(current_balance)                                            as total_balance,
        sum(credit_limit)                                               as total_credit_limit,
        max(opened_date)                                                as latest_account_opened
    from {{ ref('dim_accounts') }}
    group by customer_id
),
txn_summary as (
    select
        customer_id,
        sum(transaction_count)                  as total_transactions_lifetime,
        sum(total_debits)                       as total_debits_lifetime,
        sum(total_credits)                      as total_credits_lifetime,
        max(transaction_date)                   as last_transaction_date,
        sum(fraud_flag_count)                   as total_fraud_flags
    from {{ ref('int_customer_transactions_daily') }}
    group by customer_id
),
loan_summary as (
    select
        customer_id,
        sum(total_due)                          as total_loan_exposure,
        sum(arrears_amount)                     as total_arrears,
        max(days_past_due)                      as max_days_past_due,
        count(distinct account_id)              as loan_accounts
    from {{ ref('fct_loan_repayments') }}
    group by customer_id
),
final as (
    select
        c.customer_id,
        c.customer_number,
        c.full_name,
        c.email_address,
        c.date_of_birth,
        c.age,
        c.nationality_code,
        c.city,
        c.kyc_status,
        c.risk_tier,
        a.total_accounts,
        a.active_accounts,
        a.total_balance,
        a.total_credit_limit,
        a.latest_account_opened,
        t.total_transactions_lifetime,
        t.total_debits_lifetime,
        t.total_credits_lifetime,
        t.last_transaction_date,
        t.total_fraud_flags,
        l.total_loan_exposure,
        l.total_arrears,
        l.max_days_past_due,
        l.loan_accounts,
        current_timestamp                       as dbt_updated_at
    from customers c
    left join accounts      a using (customer_id)
    left join txn_summary   t using (customer_id)
    left join loan_summary  l using (customer_id)
)
select * from final""",
        "compiled": """\
with customers as (
    select * from WAREHOUSE.DIMENSIONS.dim_customers
),
accounts as (
    select
        customer_id,
        count(*)                                                        as total_accounts,
        count(case when account_status = 'ACTIVE' then 1 end)          as active_accounts,
        sum(current_balance)                                            as total_balance,
        sum(credit_limit)                                               as total_credit_limit,
        max(opened_date)                                                as latest_account_opened
    from WAREHOUSE.DIMENSIONS.dim_accounts
    group by customer_id
),
txn_summary as (
    select
        customer_id,
        sum(transaction_count)                  as total_transactions_lifetime,
        sum(total_debits)                       as total_debits_lifetime,
        sum(total_credits)                      as total_credits_lifetime,
        max(transaction_date)                   as last_transaction_date,
        sum(fraud_flag_count)                   as total_fraud_flags
    from WAREHOUSE.INTERMEDIATE.int_customer_transactions_daily
    group by customer_id
),
loan_summary as (
    select
        customer_id,
        sum(total_due)                          as total_loan_exposure,
        sum(arrears_amount)                     as total_arrears,
        max(days_past_due)                      as max_days_past_due,
        count(distinct account_id)              as loan_accounts
    from WAREHOUSE.FACTS.fct_loan_repayments
    group by customer_id
),
final as (
    select
        c.customer_id,
        c.customer_number,
        c.full_name,
        c.email_address,
        c.date_of_birth,
        c.age,
        c.nationality_code,
        c.city,
        c.kyc_status,
        c.risk_tier,
        a.total_accounts,
        a.active_accounts,
        a.total_balance,
        a.total_credit_limit,
        a.latest_account_opened,
        t.total_transactions_lifetime,
        t.total_debits_lifetime,
        t.total_credits_lifetime,
        t.last_transaction_date,
        t.total_fraud_flags,
        l.total_loan_exposure,
        l.total_arrears,
        l.max_days_past_due,
        l.loan_accounts,
        current_timestamp                       as dbt_updated_at
    from customers c
    left join accounts      a using (customer_id)
    left join txn_summary   t using (customer_id)
    left join loan_summary  l using (customer_id)
)
select * from final""",
    },
    "mart_fraud_summary": {
        "raw": """\
{{ config(materialized='table') }}

with transactions as (
    select * from {{ ref('fct_transactions') }}
    where is_flagged_fraud = true
),
accounts as (
    select account_id, customer_id, product_name, product_category, branch_code
    from {{ ref('dim_accounts') }}
),
fraud_by_account as (
    select
        t.account_id,
        a.customer_id,
        a.product_name,
        a.product_category,
        a.branch_code,
        count(*)                                            as fraud_transaction_count,
        sum(t.amount)                                       as total_fraud_amount,
        avg(t.amount)                                       as avg_fraud_amount,
        max(t.amount)                                       as max_fraud_amount,
        min(t.transaction_date)                             as first_fraud_date,
        max(t.transaction_date)                             as latest_fraud_date,
        count(distinct t.channel)                           as fraud_channels,
        count(distinct t.mcc)                               as fraud_merchant_categories,
        count(distinct t.merchant_name)                     as distinct_merchants
    from transactions t
    inner join accounts a using (account_id)
    group by
        t.account_id, a.customer_id, a.product_name,
        a.product_category, a.branch_code
),
final as (
    select
        *,
        case
            when fraud_transaction_count >= 10 or total_fraud_amount >= 50000 then 'HIGH'
            when fraud_transaction_count >= 3  or total_fraud_amount >= 5000  then 'MEDIUM'
            else 'LOW'
        end                                                 as fraud_risk_level,
        current_timestamp                                   as dbt_updated_at
    from fraud_by_account
)
select * from final""",
        "compiled": """\
with transactions as (
    select * from WAREHOUSE.FACTS.fct_transactions
    where is_flagged_fraud = true
),
accounts as (
    select account_id, customer_id, product_name, product_category, branch_code
    from WAREHOUSE.DIMENSIONS.dim_accounts
),
fraud_by_account as (
    select
        t.account_id,
        a.customer_id,
        a.product_name,
        a.product_category,
        a.branch_code,
        count(*)                                            as fraud_transaction_count,
        sum(t.amount)                                       as total_fraud_amount,
        avg(t.amount)                                       as avg_fraud_amount,
        max(t.amount)                                       as max_fraud_amount,
        min(t.transaction_date)                             as first_fraud_date,
        max(t.transaction_date)                             as latest_fraud_date,
        count(distinct t.channel)                           as fraud_channels,
        count(distinct t.mcc)                               as fraud_merchant_categories,
        count(distinct t.merchant_name)                     as distinct_merchants
    from transactions t
    inner join accounts a using (account_id)
    group by
        t.account_id, a.customer_id, a.product_name,
        a.product_category, a.branch_code
),
final as (
    select
        *,
        case
            when fraud_transaction_count >= 10 or total_fraud_amount >= 50000 then 'HIGH'
            when fraud_transaction_count >= 3  or total_fraud_amount >= 5000  then 'MEDIUM'
            else 'LOW'
        end                                                 as fraud_risk_level,
        current_timestamp                                   as dbt_updated_at
    from fraud_by_account
)
select * from final""",
    },
    "mart_credit_risk": {
        "raw": """\
{{ config(materialized='table') }}

with accounts as (
    select * from {{ ref('dim_accounts') }}
    where product_category = 'LENDING'
),
customers as (
    select customer_id, full_name, risk_tier, kyc_status, age
    from {{ ref('dim_customers') }}
),
arrears as (
    select * from {{ ref('int_loan_arrears') }}
),
repayment_history as (
    select
        account_id,
        count(*)                                            as total_installments,
        count(case when repayment_status = 'PAID' then 1 end) as paid_installments,
        sum(total_paid)                                     as total_repaid,
        avg(days_past_due)                                  as avg_days_past_due
    from {{ ref('fct_loan_repayments') }}
    group by account_id
),
final as (
    select
        a.account_id,
        a.customer_id,
        c.full_name,
        c.risk_tier,
        c.kyc_status,
        a.product_name,
        a.credit_limit,
        a.current_balance,
        a.account_health,
        coalesce(ar.ifrs9_stage, 'CURRENT')                 as ifrs9_stage,
        coalesce(ar.total_arrears, 0)                       as total_arrears,
        coalesce(ar.max_days_past_due, 0)                   as max_days_past_due,
        coalesce(ar.missed_installments, 0)                 as missed_installments,
        rh.total_installments,
        rh.paid_installments,
        rh.total_repaid,
        rh.avg_days_past_due,
        round(
            coalesce(rh.paid_installments, 0)::numeric
            / nullif(rh.total_installments, 0) * 100, 2
        )                                                   as repayment_rate_pct,
        case coalesce(ar.ifrs9_stage, 'CURRENT')
            when 'CURRENT' then a.current_balance * 0.005
            when 'STAGE_1' then a.current_balance * 0.05
            when 'STAGE_2' then a.current_balance * 0.25
            when 'STAGE_3' then a.current_balance * 0.75
        end                                                 as ecl_provision,
        current_timestamp                                   as dbt_updated_at
    from accounts a
    left join customers        c  using (customer_id)
    left join arrears          ar using (account_id)
    left join repayment_history rh using (account_id)
)
select * from final""",
        "compiled": """\
with accounts as (
    select * from WAREHOUSE.DIMENSIONS.dim_accounts
    where product_category = 'LENDING'
),
customers as (
    select customer_id, full_name, risk_tier, kyc_status, age
    from WAREHOUSE.DIMENSIONS.dim_customers
),
arrears as (
    select * from WAREHOUSE.INTERMEDIATE.int_loan_arrears
),
repayment_history as (
    select
        account_id,
        count(*)                                            as total_installments,
        count(case when repayment_status = 'PAID' then 1 end) as paid_installments,
        sum(total_paid)                                     as total_repaid,
        avg(days_past_due)                                  as avg_days_past_due
    from WAREHOUSE.FACTS.fct_loan_repayments
    group by account_id
),
final as (
    select
        a.account_id,
        a.customer_id,
        c.full_name,
        c.risk_tier,
        c.kyc_status,
        a.product_name,
        a.credit_limit,
        a.current_balance,
        a.account_health,
        coalesce(ar.ifrs9_stage, 'CURRENT')                 as ifrs9_stage,
        coalesce(ar.total_arrears, 0)                       as total_arrears,
        coalesce(ar.max_days_past_due, 0)                   as max_days_past_due,
        coalesce(ar.missed_installments, 0)                 as missed_installments,
        rh.total_installments,
        rh.paid_installments,
        rh.total_repaid,
        rh.avg_days_past_due,
        round(
            coalesce(rh.paid_installments, 0)::numeric
            / nullif(rh.total_installments, 0) * 100, 2
        )                                                   as repayment_rate_pct,
        case coalesce(ar.ifrs9_stage, 'CURRENT')
            when 'CURRENT' then a.current_balance * 0.005
            when 'STAGE_1' then a.current_balance * 0.05
            when 'STAGE_2' then a.current_balance * 0.25
            when 'STAGE_3' then a.current_balance * 0.75
        end                                                 as ecl_provision,
        current_timestamp                                   as dbt_updated_at
    from accounts a
    left join customers        c  using (customer_id)
    left join arrears          ar using (account_id)
    left join repayment_history rh using (account_id)
)
select * from final""",
    },
}

# ---------------------------------------------------------------------------
# Column definitions  {model_name: [(col_name, pg_type, description, constraints)]}
# ---------------------------------------------------------------------------
COLUMNS = {
    "stg_customers": [
        ("customer_id",     "character varying(32)",  "MD5 surrogate key hashed from source customer_number.", ["not_null", "unique"]),
        ("customer_number", "character varying(20)",  "Natural key from core banking system (CB-YYYYNNNNNN).", ["not_null"]),
        ("first_name",      "character varying(100)", "Customer first name, lowercased.", []),
        ("last_name",       "character varying(100)", "Customer last name, lowercased.", []),
        ("email_address",   "character varying(255)", "Primary email, lowercased and trimmed.", []),
        ("phone_number",    "character varying(20)",  "Primary phone in E.164 format.", []),
        ("date_of_birth",   "date",                   "Date of birth for age eligibility checks.", []),
        ("nationality_code","character(2)",            "ISO 3166-1 alpha-2 nationality code.", []),
        ("city",            "character varying(100)", "City from registered address.", []),
        ("postcode",        "character varying(10)",  "Postcode for geo-segmentation.", []),
        ("kyc_status",      "character varying(20)",  "KYC status: PENDING, VERIFIED, REJECTED, EXPIRED.", []),
        ("is_deleted",      "boolean",                "TRUE if soft-deleted in source.", []),
        ("_loaded_at",      "timestamp without time zone", "Ingestion pipeline load timestamp.", []),
        ("_source_system",  "character varying(50)",  "Always 'CORE_BANKING' for this table.", []),
    ],
    "stg_accounts": [
        ("account_id",      "character varying(32)",  "MD5 surrogate key hashed from account_number.", ["not_null", "unique"]),
        ("account_number",  "character varying(16)",  "16-digit account number as on statements.", ["not_null"]),
        ("customer_id",     "character varying(32)",  "FK to stg_customers.", ["not_null"]),
        ("product_code",    "character varying(10)",  "Product code mapped to dim_products.", []),
        ("branch_code",     "character varying(10)",  "Branch code mapped to dim_branches.", []),
        ("opened_date",     "date",                   "Date the account was opened.", []),
        ("closed_date",     "date",                   "Date the account was closed, null if active.", []),
        ("account_status",  "character varying(20)",  "ACTIVE, CLOSED, SUSPENDED, DORMANT.", []),
        ("credit_limit",    "numeric(18,2)",           "Approved credit limit in account currency.", []),
        ("current_balance", "numeric(18,2)",           "Current ledger balance.", []),
        ("currency_code",   "character(3)",            "ISO 4217 currency code.", []),
        ("is_overdrawn",    "boolean",                "TRUE if balance below zero.", []),
        ("_loaded_at",      "timestamp without time zone", "Ingestion pipeline load timestamp.", []),
    ],
    "stg_transactions": [
        ("transaction_id",       "character varying(36)",  "UUID primary key from source.", ["not_null", "unique"]),
        ("account_id",           "character varying(32)",  "FK to stg_accounts.", ["not_null"]),
        ("transaction_date",     "date",                   "Calendar date of transaction.", []),
        ("transaction_datetime", "timestamp without time zone", "Full datetime of transaction.", []),
        ("transaction_type",     "character varying(30)",  "PURCHASE, ATM_WITHDRAWAL, TRANSFER, PAYMENT, etc.", []),
        ("channel",              "character varying(20)",  "ONLINE, MOBILE, BRANCH, ATM, POS.", []),
        ("amount",               "numeric(18,2)",           "Absolute transaction amount.", []),
        ("currency_code",        "character(3)",            "ISO 4217 currency code.", []),
        ("direction",            "character varying(6)",   "DEBIT or CREDIT.", []),
        ("merchant_name",        "character varying(200)", "Merchant or counterparty name.", []),
        ("mcc",                  "character varying(4)",   "Merchant Category Code (ISO 18245).", []),
        ("running_balance",      "numeric(18,2)",           "Account balance after this transaction.", []),
        ("is_flagged_fraud",     "boolean",                "TRUE if flagged by fraud detection.", []),
        ("_loaded_at",           "timestamp without time zone", "Ingestion pipeline load timestamp.", []),
    ],
    "stg_loan_schedule": [
        ("loan_schedule_id",  "character varying(36)",  "UUID PK from source loan schedule system.", ["not_null", "unique"]),
        ("account_id",        "character varying(32)",  "FK to stg_accounts.", ["not_null"]),
        ("due_date",          "date",                   "Date the installment is due.", []),
        ("paid_date",         "date",                   "Date the installment was paid; null if unpaid.", []),
        ("principal_due",     "numeric(18,2)",           "Principal component of the installment.", []),
        ("interest_due",      "numeric(18,2)",           "Interest component of the installment.", []),
        ("principal_paid",    "numeric(18,2)",           "Principal amount actually paid.", []),
        ("interest_paid",     "numeric(18,2)",           "Interest amount actually paid.", []),
        ("repayment_status",  "character varying(20)",  "PAID, PARTIAL, MISSED, PENDING.", []),
        ("installment_number","integer",                 "Sequential installment number starting at 1.", []),
        ("_loaded_at",        "timestamp without time zone", "Ingestion pipeline load timestamp.", []),
    ],
    "stg_kyc_verifications": [
        ("verification_id",    "character varying(36)",  "UUID PK from identity provider.", ["not_null", "unique"]),
        ("customer_number",    "character varying(20)",  "Natural key linking to stg_customers.", ["not_null"]),
        ("verification_status","character varying(20)",  "VERIFIED, PENDING, REJECTED, EXPIRED.", []),
        ("provider",           "character varying(50)",  "Identity provider name (e.g. ONFIDO, JUMIO).", []),
        ("verified_at",        "timestamp without time zone", "Timestamp of successful verification.", []),
        ("expires_at",         "timestamp without time zone", "KYC verification expiry timestamp.", []),
        ("risk_score",         "numeric(5,2)",            "Provider risk score 0–100.", []),
        ("risk_tier",          "character varying(10)",  "LOW, MEDIUM, HIGH derived from risk_score.", []),
        ("_loaded_at",         "timestamp without time zone", "Ingestion pipeline load timestamp.", []),
    ],
    "dim_customers": [
        ("customer_id",              "character varying(32)",  "Surrogate key, MD5 of customer_number.", ["not_null", "unique"]),
        ("customer_number",          "character varying(20)",  "Natural key from core banking.", ["not_null"]),
        ("first_name",               "character varying(100)", "First name.", []),
        ("last_name",                "character varying(100)", "Last name.", []),
        ("full_name",                "character varying(200)", "Concatenated full name.", []),
        ("email_address",            "character varying(255)", "Primary email address.", []),
        ("phone_number",             "character varying(20)",  "Primary phone in E.164 format.", []),
        ("date_of_birth",            "date",                   "Date of birth.", []),
        ("age",                      "integer",                "Age in years derived from date_of_birth.", []),
        ("nationality_code",         "character(2)",            "ISO 3166-1 alpha-2 nationality.", []),
        ("city",                     "character varying(100)", "City from registered address.", []),
        ("postcode",                 "character varying(10)",  "Postcode.", []),
        ("kyc_status",               "character varying(20)",  "KYC status from stg_customers.", []),
        ("kyc_verification_status",  "character varying(20)",  "Latest verification status from identity provider.", []),
        ("risk_score",               "numeric(5,2)",            "Latest KYC provider risk score.", []),
        ("risk_tier",                "character varying(10)",  "LOW, MEDIUM, HIGH risk tier.", []),
        ("kyc_verified_at",          "timestamp without time zone", "Timestamp of last successful verification.", []),
        ("kyc_expires_at",           "timestamp without time zone", "KYC expiry timestamp.", []),
        ("_loaded_at",               "timestamp without time zone", "Source load timestamp.", []),
        ("dbt_updated_at",           "timestamp without time zone", "dbt model last run timestamp.", []),
    ],
    "dim_accounts": [
        ("account_id",         "character varying(32)",  "Surrogate key.", ["not_null", "unique"]),
        ("account_number",     "character varying(16)",  "Display account number.", ["not_null"]),
        ("customer_id",        "character varying(32)",  "FK to dim_customers.", ["not_null"]),
        ("customer_name",      "character varying(200)", "Denormalised customer full name.", []),
        ("customer_risk_tier", "character varying(10)",  "Denormalised customer risk tier.", []),
        ("product_code",       "character varying(10)",  "FK to dim_products.", []),
        ("product_name",       "character varying(100)", "Denormalised product name.", []),
        ("product_category",   "character varying(30)",  "LENDING, DEPOSIT, CURRENT, SAVINGS.", []),
        ("interest_rate_pct",  "numeric(6,4)",            "Annual interest rate percentage.", []),
        ("branch_code",        "character varying(10)",  "FK to dim_branches.", []),
        ("opened_date",        "date",                   "Account opening date.", []),
        ("closed_date",        "date",                   "Account closure date; null if active.", []),
        ("account_status",     "character varying(20)",  "ACTIVE, CLOSED, SUSPENDED, DORMANT.", []),
        ("credit_limit",       "numeric(18,2)",           "Approved credit limit.", []),
        ("current_balance",    "numeric(18,2)",           "Current ledger balance.", []),
        ("currency_code",      "character(3)",            "ISO 4217 currency code.", []),
        ("is_overdrawn",       "boolean",                "TRUE if balance is negative.", []),
        ("account_health",     "character varying(20)",  "HEALTHY, OVERDRAWN, CLOSED, OTHER.", []),
        ("_loaded_at",         "timestamp without time zone", "Source load timestamp.", []),
        ("dbt_updated_at",     "timestamp without time zone", "dbt model last run timestamp.", []),
    ],
    "dim_products": [
        ("product_code",      "character varying(10)",  "Natural key from product catalogue.", ["not_null", "unique"]),
        ("product_name",      "character varying(100)", "Human-readable product name.", []),
        ("product_category",  "character varying(30)",  "LENDING, DEPOSIT, CURRENT, SAVINGS.", []),
        ("product_type",      "character varying(30)",  "Sub-type within category.", []),
        ("interest_rate_pct", "numeric(6,4)",            "Annual interest rate percentage.", []),
        ("annual_fee",        "numeric(10,2)",           "Annual fee charged to account holder.", []),
        ("min_credit_limit",  "numeric(18,2)",           "Minimum approved credit limit.", []),
        ("max_credit_limit",  "numeric(18,2)",           "Maximum approved credit limit.", []),
        ("is_active",         "boolean",                "FALSE if product is discontinued.", []),
        ("launched_date",     "date",                   "Date the product was launched.", []),
    ],
    "dim_branches": [
        ("branch_code",  "character varying(10)",  "Natural key from branch registry.", ["not_null", "unique"]),
        ("branch_name",  "character varying(100)", "Full branch name.", []),
        ("branch_type",  "character varying(20)",  "RETAIL, CORPORATE, DIGITAL, KIOSK.", []),
        ("region",       "character varying(50)",  "Geographic region.", []),
        ("city",         "character varying(100)", "City where branch is located.", []),
        ("postcode",     "character varying(10)",  "Branch postcode.", []),
        ("opened_date",  "date",                   "Branch opening date.", []),
        ("closed_date",  "date",                   "Closure date; null if still open.", []),
        ("is_active",    "boolean",                "FALSE if branch is closed.", []),
        ("sort_code",    "character(6)",            "UK bank sort code (digits only).", []),
    ],
    "dim_date": [
        ("date_id",               "date",                   "Primary key — the calendar date.", ["not_null", "unique"]),
        ("date_day",              "date",                   "Calendar date (same as date_id).", []),
        ("year",                  "integer",                "Calendar year.", []),
        ("quarter",               "integer",                "Quarter of year (1–4).", []),
        ("month",                 "integer",                "Month number (1–12).", []),
        ("month_name",            "character varying(10)",  "Full month name.", []),
        ("week_of_year",          "integer",                "ISO week number.", []),
        ("day_of_month",          "integer",                "Day within month (1–31).", []),
        ("day_of_week",           "integer",                "Day of week: 0=Sunday … 6=Saturday.", []),
        ("day_name",              "character varying(10)",  "Full day name.", []),
        ("day_of_year",           "integer",                "Day within year (1–366).", []),
        ("first_day_of_month",    "date",                   "First day of the month.", []),
        ("last_day_of_month",     "date",                   "Last day of the month.", []),
        ("first_day_of_quarter",  "date",                   "First day of the quarter.", []),
        ("first_day_of_year",     "date",                   "First day of the year.", []),
        ("is_weekend",            "boolean",                "TRUE for Saturday and Sunday.", []),
        ("year_month",            "character varying(6)",   "YYYYMM string for easy period grouping.", []),
    ],
    "fct_transactions": [
        ("transaction_id",       "character varying(36)",  "UUID PK from source.", ["not_null", "unique"]),
        ("account_id",           "character varying(32)",  "FK to dim_accounts.", ["not_null"]),
        ("customer_id",          "character varying(32)",  "Denormalised FK to dim_customers.", []),
        ("transaction_date",     "date",                   "Calendar date of transaction.", []),
        ("transaction_datetime", "timestamp without time zone", "Full datetime.", []),
        ("transaction_type",     "character varying(30)",  "Transaction classification.", []),
        ("channel",              "character varying(20)",  "ONLINE, MOBILE, BRANCH, ATM, POS.", []),
        ("amount",               "numeric(18,2)",           "Absolute amount.", []),
        ("currency_code",        "character(3)",            "ISO 4217 currency code.", []),
        ("direction",            "character varying(6)",   "DEBIT or CREDIT.", []),
        ("merchant_name",        "character varying(200)", "Merchant or counterparty.", []),
        ("mcc",                  "character varying(4)",   "Merchant Category Code.", []),
        ("running_balance",      "numeric(18,2)",           "Balance after this transaction.", []),
        ("is_flagged_fraud",     "boolean",                "TRUE if fraud flagged.", []),
        ("product_name",         "character varying(100)", "Denormalised product name.", []),
        ("product_category",     "character varying(30)",  "Denormalised product category.", []),
        ("branch_code",          "character varying(10)",  "Originating branch code.", []),
        ("amount_band",          "character varying(10)",  "MICRO <100, SMALL <1k, MEDIUM <10k, LARGE.", []),
        ("_loaded_at",           "timestamp without time zone", "Source load timestamp.", []),
    ],
    "fct_loan_repayments": [
        ("loan_schedule_id",  "character varying(36)",  "PK from loan schedule source.", ["not_null", "unique"]),
        ("account_id",        "character varying(32)",  "FK to dim_accounts.", ["not_null"]),
        ("customer_id",       "character varying(32)",  "Denormalised FK to dim_customers.", []),
        ("due_date",          "date",                   "Installment due date.", []),
        ("paid_date",         "date",                   "Actual payment date; null if unpaid.", []),
        ("installment_number","integer",                 "Installment sequence number.", []),
        ("principal_due",     "numeric(18,2)",           "Principal portion due.", []),
        ("interest_due",      "numeric(18,2)",           "Interest portion due.", []),
        ("total_due",         "numeric(18,2)",           "principal_due + interest_due.", []),
        ("principal_paid",    "numeric(18,2)",           "Principal actually paid.", []),
        ("interest_paid",     "numeric(18,2)",           "Interest actually paid.", []),
        ("total_paid",        "numeric(18,2)",           "principal_paid + interest_paid.", []),
        ("arrears_amount",    "numeric(18,2)",           "Outstanding unpaid amount.", []),
        ("repayment_status",  "character varying(20)",  "PAID, PARTIAL, MISSED, PENDING.", []),
        ("days_past_due",     "integer",                 "Days since due_date if unpaid; 0 otherwise.", []),
        ("product_name",      "character varying(100)", "Denormalised product name.", []),
        ("interest_rate_pct", "numeric(6,4)",            "Annual interest rate.", []),
        ("_loaded_at",        "timestamp without time zone", "Source load timestamp.", []),
    ],
    "fct_payments": [
        ("payment_id",       "character varying(36)",  "PK — transaction_id filtered to payments.", ["not_null", "unique"]),
        ("account_id",       "character varying(32)",  "FK to dim_accounts.", ["not_null"]),
        ("customer_id",      "character varying(32)",  "Denormalised FK to dim_customers.", []),
        ("payment_date",     "date",                   "Calendar date of payment.", []),
        ("payment_datetime", "timestamp without time zone", "Full datetime.", []),
        ("payment_type",     "character varying(30)",  "PAYMENT, DIRECT_DEBIT, STANDING_ORDER, FASTER_PAYMENT.", []),
        ("payment_channel",  "character varying(20)",  "Originating channel.", []),
        ("payment_amount",   "numeric(18,2)",           "Payment amount.", []),
        ("currency_code",    "character(3)",            "ISO 4217 currency code.", []),
        ("direction",        "character varying(6)",   "DEBIT or CREDIT.", []),
        ("beneficiary_name", "character varying(200)", "Payee or beneficiary name.", []),
        ("is_flagged_fraud", "boolean",                "TRUE if fraud flagged.", []),
        ("product_name",     "character varying(100)", "Denormalised product name.", []),
        ("_loaded_at",       "timestamp without time zone", "Source load timestamp.", []),
    ],
    "int_customer_transactions_daily": [
        ("customer_id",                  "character varying(32)",  "FK to dim_customers.", ["not_null"]),
        ("full_name",                    "character varying(200)", "Denormalised customer name.", []),
        ("risk_tier",                    "character varying(10)",  "Customer risk tier.", []),
        ("transaction_date",             "date",                   "Aggregation date.", ["not_null"]),
        ("transaction_count",            "bigint",                 "Number of transactions on this date.", []),
        ("total_debits",                 "numeric(18,2)",           "Sum of debit amounts.", []),
        ("total_credits",                "numeric(18,2)",           "Sum of credit amounts.", []),
        ("total_amount",                 "numeric(18,2)",           "Sum of all transaction amounts.", []),
        ("accounts_used",                "bigint",                 "Distinct accounts used.", []),
        ("channels_used",                "bigint",                 "Distinct channels used.", []),
        ("fraud_flag_count",             "bigint",                 "Transactions flagged as fraud.", []),
        ("max_single_transaction",       "numeric(18,2)",           "Largest single transaction.", []),
        ("avg_transaction_amount",       "numeric(18,2)",           "Mean transaction amount.", []),
        ("distinct_merchant_categories", "bigint",                 "Distinct MCCs transacted at.", []),
    ],
    "int_loan_arrears": [
        ("account_id",             "character varying(32)",  "FK to dim_accounts.", ["not_null", "unique"]),
        ("customer_id",            "character varying(32)",  "FK to dim_customers.", []),
        ("product_name",           "character varying(100)", "Denormalised product name.", []),
        ("credit_limit",           "numeric(18,2)",           "Account credit limit.", []),
        ("missed_installments",    "bigint",                 "Count of unpaid installments.", []),
        ("total_arrears",          "numeric(18,2)",           "Total outstanding arrears.", []),
        ("max_days_past_due",      "integer",                 "Worst days past due across installments.", []),
        ("earliest_missed_due_date","date",                  "Due date of oldest missed installment.", []),
        ("ifrs9_stage",            "character varying(10)",  "CURRENT, STAGE_1 (≤30 dpd), STAGE_2 (≤90 dpd), STAGE_3.", []),
        ("calculated_at",          "timestamp without time zone", "When this record was computed.", []),
    ],
    "mart_customer_360": [
        ("customer_id",                "character varying(32)",  "PK — FK to dim_customers.", ["not_null", "unique"]),
        ("customer_number",            "character varying(20)",  "Natural key.", []),
        ("full_name",                  "character varying(200)", "Customer full name.", []),
        ("email_address",              "character varying(255)", "Primary email.", []),
        ("date_of_birth",              "date",                   "Date of birth.", []),
        ("age",                        "integer",                "Age in years.", []),
        ("nationality_code",           "character(2)",            "ISO 3166-1 alpha-2.", []),
        ("city",                       "character varying(100)", "City.", []),
        ("kyc_status",                 "character varying(20)",  "KYC status.", []),
        ("risk_tier",                  "character varying(10)",  "Risk tier.", []),
        ("total_accounts",             "bigint",                 "Total accounts held.", []),
        ("active_accounts",            "bigint",                 "Currently active accounts.", []),
        ("total_balance",              "numeric(18,2)",           "Sum of balances across all accounts.", []),
        ("total_credit_limit",         "numeric(18,2)",           "Sum of credit limits.", []),
        ("latest_account_opened",      "date",                   "Most recently opened account date.", []),
        ("total_transactions_lifetime","bigint",                 "Lifetime transaction count.", []),
        ("total_debits_lifetime",      "numeric(18,2)",           "Lifetime debit total.", []),
        ("total_credits_lifetime",     "numeric(18,2)",           "Lifetime credit total.", []),
        ("last_transaction_date",      "date",                   "Date of most recent transaction.", []),
        ("total_fraud_flags",          "bigint",                 "Lifetime fraud-flagged transactions.", []),
        ("total_loan_exposure",        "numeric(18,2)",           "Sum of all loan installments due.", []),
        ("total_arrears",              "numeric(18,2)",           "Total outstanding arrears.", []),
        ("max_days_past_due",          "integer",                 "Worst dpd across all loans.", []),
        ("loan_accounts",              "bigint",                 "Number of loan accounts.", []),
        ("dbt_updated_at",             "timestamp without time zone", "dbt model last run timestamp.", []),
    ],
    "mart_fraud_summary": [
        ("account_id",               "character varying(32)",  "PK — FK to dim_accounts.", ["not_null", "unique"]),
        ("customer_id",              "character varying(32)",  "FK to dim_customers.", []),
        ("product_name",             "character varying(100)", "Product name.", []),
        ("product_category",         "character varying(30)",  "Product category.", []),
        ("branch_code",              "character varying(10)",  "Branch code.", []),
        ("fraud_transaction_count",  "bigint",                 "Total fraud-flagged transactions.", []),
        ("total_fraud_amount",       "numeric(18,2)",           "Total value of fraud transactions.", []),
        ("avg_fraud_amount",         "numeric(18,2)",           "Average fraud transaction value.", []),
        ("max_fraud_amount",         "numeric(18,2)",           "Largest single fraud transaction.", []),
        ("first_fraud_date",         "date",                   "Date of first fraud transaction.", []),
        ("latest_fraud_date",        "date",                   "Date of most recent fraud transaction.", []),
        ("fraud_channels",           "bigint",                 "Distinct channels used in fraud.", []),
        ("fraud_merchant_categories","bigint",                 "Distinct MCCs involved in fraud.", []),
        ("distinct_merchants",       "bigint",                 "Distinct merchants involved.", []),
        ("fraud_risk_level",         "character varying(10)",  "LOW, MEDIUM, HIGH.", []),
        ("dbt_updated_at",           "timestamp without time zone", "dbt model last run timestamp.", []),
    ],
    "mart_credit_risk": [
        ("account_id",          "character varying(32)",  "PK — FK to dim_accounts.", ["not_null", "unique"]),
        ("customer_id",         "character varying(32)",  "FK to dim_customers.", []),
        ("full_name",           "character varying(200)", "Customer full name.", []),
        ("risk_tier",           "character varying(10)",  "Customer risk tier.", []),
        ("kyc_status",          "character varying(20)",  "Customer KYC status.", []),
        ("product_name",        "character varying(100)", "Product name.", []),
        ("credit_limit",        "numeric(18,2)",           "Account credit limit.", []),
        ("current_balance",     "numeric(18,2)",           "Current outstanding balance.", []),
        ("account_health",      "character varying(20)",  "Account health status.", []),
        ("ifrs9_stage",         "character varying(10)",  "IFRS 9 classification: CURRENT, STAGE_1, STAGE_2, STAGE_3.", []),
        ("total_arrears",       "numeric(18,2)",           "Total arrears from int_loan_arrears.", []),
        ("max_days_past_due",   "integer",                 "Maximum days past due.", []),
        ("missed_installments", "bigint",                  "Count of missed installments.", []),
        ("total_installments",  "bigint",                  "Total installments in loan schedule.", []),
        ("paid_installments",   "bigint",                  "Installments with PAID status.", []),
        ("total_repaid",        "numeric(18,2)",           "Total amount repaid to date.", []),
        ("avg_days_past_due",   "numeric(10,2)",           "Average days past due across schedule.", []),
        ("repayment_rate_pct",  "numeric(5,2)",            "% of installments fully paid.", []),
        ("ecl_provision",       "numeric(18,2)",           "Expected Credit Loss provision per IFRS 9.", []),
        ("dbt_updated_at",      "timestamp without time zone", "dbt model last run timestamp.", []),
    ],
}

# ---------------------------------------------------------------------------
# Model metadata
# ---------------------------------------------------------------------------
LAYER_SCHEMA = {
    "stg_":   "STAGING",
    "dim_":   "DIMENSIONS",
    "fct_":   "FACTS",
    "int_":   "INTERMEDIATE",
    "mart_":  "MARTS",
}

MATERIALIZATIONS = {
    "stg_customers":                    "view",
    "stg_accounts":                     "view",
    "stg_transactions":                 "incremental",
    "stg_loan_schedule":                "view",
    "stg_kyc_verifications":            "view",
    "dim_customers":                    "table",
    "dim_accounts":                     "table",
    "dim_products":                     "table",
    "dim_branches":                     "table",
    "dim_date":                         "table",
    "fct_transactions":                 "table",
    "fct_loan_repayments":              "table",
    "fct_payments":                     "table",
    "int_customer_transactions_daily":  "table",
    "int_loan_arrears":                 "table",
    "mart_customer_360":                "table",
    "mart_fraud_summary":               "table",
    "mart_credit_risk":                 "table",
}

DESCRIPTIONS = {
    "stg_customers": "Staged customer records cleaned and renamed from the raw core banking extract. Applies type casting, deduplication via MD5 surrogate key, and preserves soft-delete flag. One row per customer. Single source of truth for downstream customer dimensions.",
    "stg_accounts":  "Staged account records from the core banking raw extract. Renames columns to snake_case, casts data types, and normalises account status codes. One row per account including closed accounts.",
    "stg_transactions": "Staged transaction ledger from the core banking raw extract. Loaded incrementally using merge strategy on transaction_id. Normalises channel and direction codes, casts amounts to numeric, and preserves fraud flags from the upstream detection system.",
    "stg_loan_schedule": "Staged loan repayment schedule from the loan origination system. One row per installment. Tracks due amounts, paid amounts, and repayment status for use in arrears and credit risk calculations.",
    "stg_kyc_verifications": "Staged Know Your Customer (KYC) verification events from the identity provider. One row per verification attempt. Downstream models use the latest verification per customer to derive kyc_status and risk_tier.",
    "dim_customers": "Customer dimension. One row per active customer (soft-deleted customers excluded). Enriched with the latest KYC verification outcome including risk tier and expiry date. Used as the primary customer lookup across all fact and mart models.",
    "dim_accounts":  "Account dimension. One row per account. Denormalised with customer risk tier and product details for convenient access in fact models. Derives account_health status flag.",
    "dim_products":  "Product catalogue dimension. One row per banking product (e.g. Flex Current Account, Premier Mortgage). Reference table for product names, categories, interest rates, and credit limit ranges.",
    "dim_branches":  "Branch dimension. One row per physical and digital branch. Includes region, sort code, and open/closed status. Used for geographic segmentation of transactions and accounts.",
    "dim_date":      "Date spine from 2015-01-01 to 2029-12-31. Generated using dbt_utils.date_spine. Includes calendar attributes, ISO week numbers, and is_weekend flag. Used for all time-based joins across the warehouse.",
    "fct_transactions": "Transaction fact table. One row per ledger transaction. Denormalised with account and customer IDs, product category, and amount band for easy slice-and-dice reporting. Source of truth for all transaction-level analytics.",
    "fct_loan_repayments": "Loan repayment fact table. One row per installment in the loan schedule. Computes arrears_amount and days_past_due for use in IFRS 9 staging and collections reporting.",
    "fct_payments":  "Payment fact table, a filtered subset of fct_transactions limited to outbound payment transaction types (PAYMENT, DIRECT_DEBIT, STANDING_ORDER, FASTER_PAYMENT). One row per payment event.",
    "int_customer_transactions_daily": "Intermediate aggregation of fct_transactions grouped by customer and calendar date. Used upstream by mart_customer_360 to compute lifetime transaction KPIs without re-scanning the full fact table.",
    "int_loan_arrears": "Intermediate model computing current arrears position and IFRS 9 stage per account. Reads only unpaid installments from fct_loan_repayments. One row per account with active arrears.",
    "mart_customer_360": "360-degree customer summary mart. One row per customer. Aggregates account balances, transaction KPIs, and loan exposure into a single wide table for CRM, marketing, and executive reporting.",
    "mart_fraud_summary": "Fraud summary mart. One row per account that has at least one fraud-flagged transaction. Provides fraud count, value, channel diversity, and a derived fraud_risk_level for the fraud operations team.",
    "mart_credit_risk": "Credit risk mart for IFRS 9 Expected Credit Loss reporting. One row per lending account. Combines arrears staging, repayment history, and ECL provision calculation. Consumed by the regulatory reporting pipeline.",
}

OWNERS = {
    "stg_":  "data-platform-team",
    "dim_":  "data-platform-team",
    "fct_":  "data-platform-team",
    "int_":  "analytics-engineering",
    "mart_": "analytics-engineering",
}

REFRESH = {
    "stg_":  "daily",
    "dim_":  "daily",
    "fct_":  "daily",
    "int_":  "daily",
    "mart_": "daily",
}

TAGS = {
    "stg_customers":                    ["staging", "customers", "pii"],
    "stg_accounts":                     ["staging", "accounts"],
    "stg_transactions":                 ["staging", "transactions", "incremental"],
    "stg_loan_schedule":                ["staging", "lending"],
    "stg_kyc_verifications":            ["staging", "kyc", "pii"],
    "dim_customers":                    ["dimensions", "customers", "pii"],
    "dim_accounts":                     ["dimensions", "accounts"],
    "dim_products":                     ["dimensions", "products"],
    "dim_branches":                     ["dimensions", "branches"],
    "dim_date":                         ["dimensions", "date_spine"],
    "fct_transactions":                 ["facts", "transactions", "core"],
    "fct_loan_repayments":              ["facts", "lending", "collections"],
    "fct_payments":                     ["facts", "payments"],
    "int_customer_transactions_daily":  ["intermediate", "transactions"],
    "int_loan_arrears":                 ["intermediate", "lending", "ifrs9"],
    "mart_customer_360":                ["mart", "crm", "customers"],
    "mart_fraud_summary":               ["mart", "fraud", "risk"],
    "mart_credit_risk":                 ["mart", "risk", "ifrs9", "regulatory"],
}

DEPENDS_ON = {
    "stg_customers":                    [],
    "stg_accounts":                     [],
    "stg_transactions":                 [],
    "stg_loan_schedule":                [],
    "stg_kyc_verifications":            [],
    "dim_customers":                    ["stg_customers", "stg_kyc_verifications"],
    "dim_accounts":                     ["stg_accounts", "dim_customers", "dim_products"],
    "dim_products":                     [],
    "dim_branches":                     [],
    "dim_date":                         [],
    "fct_transactions":                 ["stg_transactions", "dim_accounts"],
    "fct_loan_repayments":              ["stg_loan_schedule", "dim_accounts"],
    "fct_payments":                     ["stg_transactions", "dim_accounts"],
    "int_customer_transactions_daily":  ["fct_transactions", "dim_customers"],
    "int_loan_arrears":                 ["fct_loan_repayments", "dim_accounts"],
    "mart_customer_360":                ["dim_customers", "dim_accounts", "int_customer_transactions_daily", "fct_loan_repayments"],
    "mart_fraud_summary":               ["fct_transactions", "dim_accounts"],
    "mart_credit_risk":                 ["dim_accounts", "dim_customers", "int_loan_arrears", "fct_loan_repayments"],
}

SOURCE_DEPS = {
    "stg_customers":        [["banking_raw", "customers"], ["banking_raw", "kyc"]],
    "stg_accounts":         [["banking_raw", "accounts"]],
    "stg_transactions":     [["banking_raw", "transactions"]],
    "stg_loan_schedule":    [["banking_raw", "loan_schedule"]],
    "stg_kyc_verifications":[["banking_raw", "kyc"]],
    "dim_products":         [["banking_raw", "products"]],
    "dim_branches":         [["banking_raw", "branches"]],
}

# catalog: realistic row counts and byte sizes (None = view, no stats)
CATALOG_STATS = {
    "stg_customers":                    None,   # view
    "stg_accounts":                     None,
    "stg_transactions":                 {"row_count": 48_640_000, "num_bytes": 15_032_385_536},
    "stg_loan_schedule":                None,
    "stg_kyc_verifications":            None,
    "dim_customers":                    {"row_count": 245_000,    "num_bytes":  52_428_800},
    "dim_accounts":                     {"row_count": 412_000,    "num_bytes":  89_128_960},
    "dim_products":                     {"row_count": 28,         "num_bytes":  20_480},
    "dim_branches":                     {"row_count": 156,        "num_bytes":  51_200},
    "dim_date":                         {"row_count": 5_479,      "num_bytes":  2_097_152},
    "fct_transactions":                 {"row_count": 48_500_000, "num_bytes": 16_106_127_360},
    "fct_loan_repayments":              {"row_count": 3_200_000,  "num_bytes":   838_860_800},
    "fct_payments":                     {"row_count": 12_400_000, "num_bytes":  4_194_304_000},
    "int_customer_transactions_daily":  {"row_count": 18_500_000, "num_bytes":  5_368_709_120},
    "int_loan_arrears":                 {"row_count": 125_000,    "num_bytes":    31_457_280},
    "mart_customer_360":                {"row_count": 245_000,    "num_bytes":    68_157_440},
    "mart_fraud_summary":               {"row_count": 87_000,     "num_bytes":    20_971_520},
    "mart_credit_risk":                 {"row_count": 412_000,    "num_bytes":   104_857_600},
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def model_schema(name: str) -> str:
    for prefix, schema in LAYER_SCHEMA.items():
        if name.startswith(prefix):
            return schema
    return "PUBLIC"


def model_owner(name: str) -> str:
    for prefix, owner in OWNERS.items():
        if name.startswith(prefix):
            return owner
    return "data-platform-team"


def model_refresh(name: str) -> str:
    for prefix, freq in REFRESH.items():
        if name.startswith(prefix):
            return freq
    return "daily"


def unique_id(name: str) -> str:
    return f"model.{PROJECT}.{name}"


def source_unique_id(source: str, table: str) -> str:
    return f"source.{PROJECT}.{source}.{table}"


# ---------------------------------------------------------------------------
# Build manifest node
# ---------------------------------------------------------------------------
def build_manifest_node(name: str) -> dict:
    schema   = model_schema(name)
    mat      = MATERIALIZATIONS[name]
    deps     = DEPENDS_ON[name]
    src_deps = SOURCE_DEPS.get(name, [])
    uid      = unique_id(name)
    path     = f"{schema.lower()}/{name}.sql"

    # refs list for manifest (array of {name, package, version})
    refs = [{"name": d, "package": None, "version": None} for d in deps]

    # depends_on.nodes
    dep_nodes = [unique_id(d) for d in deps]
    dep_nodes += [source_unique_id(s[0], s[1]) for s in src_deps]

    # columns dict for manifest
    cols = {}
    for col_name, pg_type, desc, constraints in COLUMNS.get(name, []):
        col_constraints = [{"type": c, "expression": None, "name": None, "columns": None}
                           for c in constraints]
        cols[col_name] = {
            "name": col_name,
            "description": desc,
            "meta": {},
            "data_type": pg_type,
            "constraints": col_constraints,
            "docs": {"show": True},
            "tags": [],
        }

    # incremental_strategy only for incremental models
    inc_strategy = "merge" if mat == "incremental" else None
    unique_key   = "transaction_id" if mat == "incremental" else None

    return {
        "database": DATABASE,
        "schema": schema,
        "name": name,
        "resource_type": "model",
        "package_name": PROJECT,
        "path": path,
        "original_file_path": f"models/{path}",
        "unique_id": uid,
        "fqn": [PROJECT, schema.lower(), name],
        "alias": name,
        "checksum": {"name": "sha256", "checksum": sha256(SQL[name]["raw"])},
        "config": {
            "enabled": True,
            "alias": None,
            "schema": schema.lower(),
            "database": None,
            "tags": TAGS.get(name, []),
            "meta": {
                "owner": model_owner(name),
                "refresh_frequency": model_refresh(name),
            },
            "group": None,
            "materialized": mat,
            "incremental_strategy": inc_strategy,
            "persist_docs": {},
            "post-hook": [],
            "pre-hook": [],
            "quoting": {},
            "column_types": {},
            "full_refresh": None,
            "unique_key": unique_key,
            "on_schema_change": "ignore",
            "on_configuration_change": "apply",
            "grants": {},
            "packages": [],
            "docs": {"show": True, "node_color": None},
            "contract": {"enforced": False, "alias_types": True},
            "access": "protected",
        },
        "tags": TAGS.get(name, []),
        "description": DESCRIPTIONS.get(name, ""),
        "columns": cols,
        "meta": {
            "owner": model_owner(name),
            "refresh_frequency": model_refresh(name),
        },
        "group": None,
        "docs": {"show": True, "node_color": None},
        "patch_path": f"{PROJECT}://models/{schema.lower()}/schema.yml",
        "build_path": None,
        "deferred": False,
        "unrendered_config": {
            "schema": schema.lower(),
            "materialized": mat,
            **({"unique_key": unique_key, "incremental_strategy": inc_strategy}
               if mat == "incremental" else {}),
        },
        "created_at": 1711000000.0 + abs(hash(name)) % 100000,
        "relation_name": f"{DATABASE}.{schema}.{name}",
        "raw_code": SQL[name]["raw"],
        "compiled_code": SQL[name]["compiled"],
        "language": "sql",
        "refs": refs,
        "sources": src_deps,
        "metrics": [],
        "depends_on": {
            "macros": (["macro.dbt_utils.date_spine"] if name == "dim_date" else []),
            "nodes": dep_nodes,
        },
        "compiled_path": f"target/compiled/{PROJECT}/models/{path}",
        "contract": {"enforced": False, "alias_types": True, "checksum": None},
        "access": "protected",
        "constraints": [],
        "version": None,
        "latest_version": None,
        "deprecation_date": None,
    }


# ---------------------------------------------------------------------------
# Build sources section of manifest
# ---------------------------------------------------------------------------
SOURCES_META = {
    "banking_raw": {
        "description": "Raw tables landed by the ingestion pipeline from the core banking system and third-party providers. Loaded nightly via Fivetran into the RAW schema. Do not reference these tables directly in BI tools — use the staging models instead.",
        "tables": {
            "customers":    "Raw customer master records from the core banking system.",
            "accounts":     "Raw account records including current, savings, and lending accounts.",
            "transactions": "Raw ledger transactions. Partitioned by loaded_at for incremental ingestion.",
            "loan_schedule":"Raw loan repayment schedules from the loan origination system.",
            "kyc":          "Raw KYC verification events from the identity provider API.",
            "products":     "Raw product catalogue exported from the product management system.",
            "branches":     "Raw branch registry from the branch management system.",
        },
    }
}

def build_manifest_sources() -> dict:
    sources = {}
    for source_name, meta in SOURCES_META.items():
        for table_name, table_desc in meta["tables"].items():
            sid = source_unique_id(source_name, table_name)
            sources[sid] = {
                "unique_id": sid,
                "fqn": [PROJECT, "sources", source_name, table_name],
                "database": DATABASE,
                "schema": "RAW",
                "name": table_name,
                "resource_type": "source",
                "package_name": PROJECT,
                "path": f"models/sources/{source_name}.yml",
                "original_file_path": f"models/sources/{source_name}.yml",
                "source_name": source_name,
                "source_description": meta["description"],
                "loader": "fivetran",
                "identifier": table_name,
                "quoting": {"database": None, "schema": None, "identifier": None, "column": None},
                "loaded_at_field": "loaded_at",
                "freshness": {
                    "warn_after": {"count": 25, "period": "hour"},
                    "error_after": {"count": 49, "period": "hour"},
                    "filter": None,
                },
                "external": None,
                "description": table_desc,
                "columns": {},
                "meta": {"owner": "data-platform-team"},
                "source_meta": {},
                "tags": ["raw", source_name],
                "config": {
                    "enabled": True,
                    "tags": ["raw"],
                    "meta": {},
                    "quoting": {},
                    "persist_docs": {},
                    "docs": {"show": True, "node_color": None},
                    "freshness": {
                        "warn_after": {"count": 25, "period": "hour"},
                        "error_after": {"count": 49, "period": "hour"},
                    },
                },
                "patch_path": None,
                "unrendered_config": {},
                "relation_name": f"{DATABASE}.RAW.{table_name}",
                "created_at": 1711000000.0,
            }
    return sources


# ---------------------------------------------------------------------------
# Build parent/child maps
# ---------------------------------------------------------------------------
def build_parent_map(nodes: dict) -> dict:
    return {uid: node["depends_on"]["nodes"] for uid, node in nodes.items()}


def build_child_map(nodes: dict, sources: dict) -> dict:
    child_map: dict[str, list] = {uid: [] for uid in {**nodes, **sources}}
    for uid, node in nodes.items():
        for parent in node["depends_on"]["nodes"]:
            if parent in child_map:
                child_map[parent].append(uid)
    return child_map


# ---------------------------------------------------------------------------
# Build catalog node
# ---------------------------------------------------------------------------
def build_catalog_node(name: str) -> dict:
    schema = model_schema(name)
    mat    = MATERIALIZATIONS[name]
    stats  = CATALOG_STATS.get(name)

    cols = {}
    for idx, (col_name, pg_type, _desc, _constraints) in enumerate(COLUMNS.get(name, []), start=1):
        upper = col_name.upper()
        cols[upper] = {
            "type": pg_type.upper()
                    .replace("CHARACTER VARYING", "TEXT")
                    .replace("CHARACTER(", "CHAR(")
                    .replace("NUMERIC", "NUMERIC")
                    .replace("TIMESTAMP WITHOUT TIME ZONE", "TIMESTAMPTZ")
                    .replace("BIGINT", "INT8"),
            "index": idx,
            "name": upper,
            "comment": None,
        }

    has_stats = stats is not None
    stat_entries = {
        "has_stats": {
            "id": "has_stats",
            "label": "Has Stats?",
            "value": has_stats,
            "include": False,
            "description": "Indicates whether statistics are available for this table",
        }
    }
    if has_stats:
        stat_entries["row_count"] = {
            "id": "row_count",
            "label": "Row Count",
            "value": stats["row_count"],
            "include": True,
            "description": "Approximate number of rows in the table",
        }
        stat_entries["num_bytes"] = {
            "id": "num_bytes",
            "label": "Size (Bytes)",
            "value": stats["num_bytes"],
            "include": True,
            "description": "Approximate storage size in bytes",
        }
        stat_entries["last_modified"] = {
            "id": "last_modified",
            "label": "Last Modified",
            "value": "2024-03-21 10:00:00",
            "include": True,
            "description": "Timestamp of the most recent write",
        }

    return {
        "unique_id": unique_id(name),
        "metadata": {
            "type": "BASE TABLE" if mat in ("table", "incremental") else "VIEW",
            "schema": schema,
            "name": name.upper(),
            "database": DATABASE,
            "comment": None,
            "owner": "DBT_USER",
        },
        "columns": cols,
        "stats": stat_entries,
    }


# ---------------------------------------------------------------------------
# Assemble and write
# ---------------------------------------------------------------------------
def main():
    model_names = list(SQL.keys())  # 18 models in layer order

    # ── manifest ────────────────────────────────────────────────────────────
    nodes   = {unique_id(n): build_manifest_node(n) for n in model_names}
    sources = build_manifest_sources()

    manifest = {
        "metadata": {
            "dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v9/manifest.json",
            "dbt_version": "1.7.10",
            "generated_at": "2024-03-21T10:00:00.000000Z",
            "invocation_id": "b8f3a1c2-4d5e-6f7a-8b9c-0d1e2f3a4b5c",
            "env": {},
            "project_name": PROJECT,
            "project_id": sha256(PROJECT)[:32],
            "adapter_type": "postgres",
        },
        "nodes": nodes,
        "sources": sources,
        "exposures": {},
        "metrics": {},
        "groups": {},
        "selectors": {},
        "parent_map": build_parent_map(nodes),
        "child_map": build_child_map(nodes, sources),
        "group_map": {},
    }

    manifest_path = OUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"Wrote {manifest_path}  ({manifest_path.stat().st_size // 1024} KB)")

    # ── catalog ─────────────────────────────────────────────────────────────
    catalog_nodes = {unique_id(n): build_catalog_node(n) for n in model_names}

    # catalog sources (views, no stats)
    catalog_sources = {}
    for source_name, meta in SOURCES_META.items():
        for table_name in meta["tables"]:
            sid = source_unique_id(source_name, table_name)
            catalog_sources[sid] = {
                "unique_id": sid,
                "metadata": {
                    "type": "BASE TABLE",
                    "schema": "RAW",
                    "name": table_name.upper(),
                    "database": DATABASE,
                    "comment": None,
                    "owner": "FIVETRAN_USER",
                },
                "columns": {},   # raw tables — columns not documented
                "stats": {
                    "has_stats": {
                        "id": "has_stats",
                        "label": "Has Stats?",
                        "value": False,
                        "include": False,
                        "description": "Indicates whether statistics are available for this table",
                    }
                },
            }

    catalog = {
        "metadata": {
            "dbt_schema_version": "https://schemas.getdbt.com/dbt/catalog/v1.json",
            "dbt_version": "1.7.10",
            "generated_at": "2024-03-21T10:05:00.000000Z",
            "invocation_id": "b8f3a1c2-4d5e-6f7a-8b9c-0d1e2f3a4b5c",
            "env": {},
        },
        "nodes": catalog_nodes,
        "sources": catalog_sources,
        "errors": None,
    }

    catalog_path = OUT_DIR / "catalog.json"
    catalog_path.write_text(json.dumps(catalog, indent=2))
    print(f"Wrote {catalog_path}  ({catalog_path.stat().st_size // 1024} KB)")

    # quick sanity check
    print(f"\n{len(nodes)} model nodes, {len(sources)} source nodes")
    views  = [n for n in model_names if MATERIALIZATIONS[n] == "view"]
    tables = [n for n in model_names if MATERIALIZATIONS[n] in ("table", "incremental")]
    print(f"  Views: {views}")
    print(f"  Tables/Incremental: {tables}")


if __name__ == "__main__":
    main()
