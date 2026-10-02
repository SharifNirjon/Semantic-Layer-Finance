FROM python:3.13-slim
ARG PIP_INDEX_URL=https://pypi.org/simple
WORKDIR /srv
COPY api/requirements.txt .
RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} -r requirements.txt
COPY api/app ./app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
