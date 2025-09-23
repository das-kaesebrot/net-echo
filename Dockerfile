FROM python:3.12-alpine AS build

COPY Pipfile .
COPY Pipfile.lock .

# generate the requirements file
RUN python3 -m pip install pipenv && \
    pipenv requirements > requirements.txt

FROM python:3.12-alpine AS base
ENV PYTHONUNBUFFERED=true

ARG APP_ROOT=/usr/local/bin/net-test
ARG APP_VERSION

RUN adduser -u 1101 -D net-test
RUN mkdir -pv ${APP_ROOT}
RUN chown -R 1101:1101 ${APP_ROOT}

WORKDIR ${APP_ROOT}

COPY --from=build requirements.txt .
RUN python3 -m pip install -r requirements.txt

COPY --chown=1101:1101 resources resources
COPY --chown=1101:1101 main.py main.py

USER net-test

ENV APP_VERSION=${APP_VERSION}

CMD [ "/usr/bin/env", "python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0" ]
