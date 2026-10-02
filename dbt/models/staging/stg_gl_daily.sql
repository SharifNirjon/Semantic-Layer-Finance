select gl_date, gl_code, balance
from {{ source('raw', 'gl_daily_balances') }}
