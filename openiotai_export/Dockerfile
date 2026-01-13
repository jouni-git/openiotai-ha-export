ARG BUILD_FROM
FROM $BUILD_FROM

# Install Python and required libraries
RUN apk add --no-cache python3 py3-pip && \
    pip3 install --no-cache-dir paho-mqtt requests

# Create app directory
WORKDIR /app

# Copy application code
COPY run.py /app/run.py

# Run the add-on
CMD ["python3", "/app/run.py"]
