{# Campaign cost is allocated evenly across targeted customers so it sums back to the campaign cost under any slice. #}
select
    r.response_id,
    r.campaign_id,
    c.campaign_name,
    c.campaign_channel,
    c.target_segment,
    (date_trunc('month', c.start_date) + interval '1 month - 1 day')::date as month_end,
    r.customer_id,
    d.customer_key,
    d.branch_id,
    d.branch_name,
    d.region,
    d.segment,
    r.responded::int as responded,
    (r.converted_product is not null)::int as converted,
    r.converted_product,
    c.cost / count(*) over (partition by r.campaign_id) as allocated_cost
from {{ ref('stg_campaign_responses') }} r
join {{ ref('stg_campaigns') }} c using (campaign_id)
join {{ ref('dim_customer') }} d
  on d.customer_id = r.customer_id and c.start_date >= d.valid_from and c.start_date < d.valid_to
