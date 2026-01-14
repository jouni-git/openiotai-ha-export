ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache \
    python3 \
    py3-requests \
    py3-paho-mqtt

COPY rootfs /
