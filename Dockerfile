FROM python:3-alpine

RUN apk add --no-cache tini

COPY / /cfdnsupdater/

RUN cd /cfdnsupdater \
    && python3 setup.py install \
    && cd / \
    && rm -rf cfdnsupdater

ENTRYPOINT [ "/sbin/tini", "--", "updatecfdns" ]
