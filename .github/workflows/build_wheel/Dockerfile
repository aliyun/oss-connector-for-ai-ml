ARG RELEASE_IMAGE
ARG BUILD_IMAGE
FROM ${RELEASE_IMAGE} AS release

FROM ${BUILD_IMAGE} AS builder
WORKDIR /libosstorchconnector
COPY --from=release /libosstorchconnector .
COPY . .
ARG PYTHON_VERSION
ENV PY_VER=${PYTHON_VERSION}
ENV PY_ABI_TAG=cp${PY_VER}-cp${PY_VER}
RUN export PATH="/opt/python/${PY_ABI_TAG}/bin:$PATH" && \
    python3 -V && \
    echo -e "[build_ext]\nlibrary_path=oss_connector.cpython-${PY_VER}-x86_64-linux-gnu.so" > setup.cfg && \
    python3 -u setup.py bdist_wheel && \
    auditwheel repair dist/osstorchconnector*.whl -w repaired_wheel

FROM scratch
COPY --from=builder /libosstorchconnector/repaired_wheel/osstorchconnector* /
