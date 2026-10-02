FROM python:3.13-slim
ARG PIP_INDEX_URL=https://pypi.org/simple
WORKDIR /srv
COPY mcp-server/requirements.txt .
RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} -r requirements.txt
COPY mcp-server/app ./app
ENV MCP_TRANSPORT=http MCP_PORT=8765
EXPOSE 8765
CMD ["python", "-m", "app"]
