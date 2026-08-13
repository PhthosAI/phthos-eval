FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE CHANGELOG.md ./
COPY src ./src
COPY schema ./schema
COPY examples/live/config.json /etc/phthos-eval/config.json
RUN pip install --no-cache-dir .
ENV PHTHOS_EVAL_LIVE_CONFIG=/etc/phthos-eval/config.json
ENV PHTHOS_EVAL_DATA_DIR=/data
ENV PHTHOS_EVAL_SAMPLE_RATE=0.05
ENV PHTHOS_EVAL_LIVE_HOST=0.0.0.0
EXPOSE 8765
CMD ["phthos-eval", "live", "--host", "0.0.0.0", "--port", "8765"]
