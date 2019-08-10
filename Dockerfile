FROM python:3-alpine

COPY / /cfdnsupdater/

RUN cd /cfdnsupdater \
    && python3 setup.py install \
    && cd / \
    && rm -rf cfdnsupdater

ENTRYPOINT [ "updatecfdns" ]