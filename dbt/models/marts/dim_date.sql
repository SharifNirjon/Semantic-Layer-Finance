select
    d::date as date_day,
    date_trunc('month', d)::date as month_start,
    (date_trunc('month', d) + interval '1 month - 1 day')::date as month_end,
    to_char(d, 'YYYY') || '-Q' || to_char(d, 'Q') as quarter,
    extract(year from d)::int as year,
    to_char(d, 'YYYY-MM') as month_label,
    extract(isodow from d)::int in (5, 6) as is_weekend,
    d::date = (date_trunc('month', d) + interval '1 month - 1 day')::date as is_month_end
from generate_series(
    date '2018-01-01',
    (select max(month_end) from {{ ref('stg_account_snapshots') }}),
    interval '1 day') as d
