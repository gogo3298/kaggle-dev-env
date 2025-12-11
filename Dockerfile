ARG BASE_IMAGE=gcr.io/kaggle-images/python

FROM ${BASE_IMAGE}

RUN pip install --no-cache-dir \
    hydra-core
