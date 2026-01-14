ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache python3

WORKDIR /app
COPY run.py /app/run.py

COPY rootfs /
