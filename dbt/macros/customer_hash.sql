{% macro customer_hash(column) -%}
    left(encode(sha256(convert_to('{{ var("customer_hash_salt") }}:' || {{ column }}::text, 'UTF8')), 'hex'), 16)
{%- endmacro %}
