{{ config(indexes=[{'columns': ['month_end', 'branch_id']}]) }}
{# Loan-month grain. Provisioning rule (demo, simplified): Standard 1%, SMA 5%, Substandard 20%, Doubtful 50%, Bad-Loss 100%. #}
select
    s.loan_id,
    {{ customer_hash('s.loan_id') }} as loan_key,
    s.month_end,
    l.customer_id,
    c.branch_id,
    c.branch_name,
    c.region,
    c.segment,
    p.product_name,
    l.sector,
    s.classification,
    s.days_past_due,
    case
        when s.days_past_due = 0 then 'Current'
        when s.days_past_due < 30 then '1-29 days'
        when s.days_past_due < 60 then '30-59 days'
        when s.days_past_due < 90 then '60-89 days'
        when s.days_past_due < 180 then '90-179 days'
        else '180+ days'
    end as aging_bucket,
    s.outstanding,
    s.classification in ('Substandard', 'Doubtful', 'Bad-Loss') as is_npl,
    case when s.classification in ('Substandard', 'Doubtful', 'Bad-Loss') then s.outstanding else 0 end as npl_balance,
    s.outstanding * case s.classification
        when 'Standard' then 0.01 when 'SMA' then 0.05 when 'Substandard' then 0.20
        when 'Doubtful' then 0.50 else 1.00 end as provision_amount,
    case when date_trunc('month', l.disbursed_date) = date_trunc('month', s.month_end) then l.principal else 0 end
        as disbursed_amount
from {{ ref('stg_loan_snapshots') }} s
join {{ ref('stg_loans') }} l using (loan_id)
join {{ ref('dim_product') }} p on p.product_id = l.product_id
join {{ ref('dim_customer') }} c
  on c.customer_id = l.customer_id and s.month_end >= c.valid_from and s.month_end < c.valid_to
