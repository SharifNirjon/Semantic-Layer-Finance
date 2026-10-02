FROM python:3.13-slim
ARG PIP_INDEX_URL=https://pypi.org/simple
COPY scripts/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} -r /tmp/requirements.txt
WORKDIR /app
COPY scripts /app/scripts
ENV PYTHONPATH=/app/scripts
CMD ["sh", "-c", "python scripts/generate_data.py --reference-date ${REFERENCE_DATE} && python scripts/load_raw.py && python scripts/data_quality_report.py"]
