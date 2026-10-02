FROM python:3.13-slim
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} "dbt-core==1.10.23" "dbt-postgres==1.10.2"
WORKDIR /dbt
ENV DBT_PROFILES_DIR=/dbt
ENTRYPOINT ["dbt"]
CMD ["build"]
