{{ config(materialized='view') }}
{# GL balances. audit.gl_adjustments (delta in percent) injects a discrepancy into the latest month for the demo. #}
with latest as (select date_trunc('month', max(gl_date)) as m from {{ ref('stg_gl_daily') }})
select
    g.gl_date,
    g.gl_code,
    g.balance * (1 + coalesce(a.delta_pct, 0) / 100.0) as balance,
    g.gl_date = (date_trunc('month', g.gl_date) + interval '1 month - 1 day')::date as is_month_end
from {{ ref('stg_gl_daily') }} g
cross join latest
left join {{ source('raw', 'gl_adjustments') }} a
  on a.gl_code = g.gl_code and date_trunc('month', g.gl_date) = latest.m
