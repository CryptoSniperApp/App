FROM python:3.12

WORKDIR /app
COPY pyproject.toml /app/

RUN pip install poetry
RUN poetry config virtualenvs.create false

RUN poetry install --no-root --no-interaction --no-ansi

COPY . /app/

ENTRYPOINT python solana_snipping/main.py