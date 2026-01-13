ARG BUILD_FROM
FROM $BUILD_FROM

# Install Python and dependencies
RUN apk add --no-cache python3 py3-pip && \
    pip3 install --no-cache-dir paho-mqtt requests

# Copy application
WORKDIR /app
COPY run.py /app/run.py

# Copy s6 service definition
COPY rootfs /