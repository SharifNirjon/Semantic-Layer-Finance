{# Fails (returns rows) when marts deposits or loans differ from the GL by more than var('recon_tolerance'). #}
with marts as (
    select month_end, sum(deposit_balance) as deposits, sum(loan_balance) as loans
    from {{ ref('fct_account_snapshot') }} group by 1
),
gl as (
    select gl_date as month_end,
           sum(case when gl_code = 'DEPOSITS' then balance end) as deposits,
           sum(case when gl_code = 'LOANS' then balance end) as loans
    from {{ ref('fct_gl_daily') }} where is_month_end group by 1
)
select m.month_end, m.deposits as marts_deposits, g.deposits as gl_deposits, m.loans as marts_loans, g.loans as gl_loans
from marts m join gl g using (month_end)
where abs(m.deposits - g.deposits) / g.deposits > {{ var('recon_tolerance') }}
   or abs(m.loans - g.loans) / g.loans > {{ var('recon_tolerance') }}
