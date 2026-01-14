#ARG BUILD_FROM
#FROM $BUILD_FROM

#RUN apk add --no-cache python3

#### ÄLÄ MUUTA TÄTÄ DOCKERFILEÄ ####
FROM python:3.11-slim

WORKDIR /app
COPY run.py /app/run.py

CMD ["python3", "/app/run.py"]
#COPY rootfs /
