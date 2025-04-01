ARG RELEASE_IMAGE
ARG BUILD_IMAGE
FROM ${RELEASE_IMAGE} AS release

FROM ${BUILD_IMAGE} AS builder
WORKDIR /libconnector
COPY --from=release /libconnector .
ARG PACKAGE_DIR
COPY ${PACKAGE_DIR} .
COPY README.md LICENSE MANIFEST.in .
ARG PYTHON_VERSION
ENV PY_VER=${PYTHON_VERSION}
ENV PY_ABI_TAG=cp${PY_VER}-cp${PY_VER}
RUN export PATH="/opt/python/${PY_ABI_TAG}/bin:$PATH" && \
    python3 -V && \
    libconnector=$(find . -type f -name "oss_*.cpython-${PY_VER}-x86_64-linux-gnu.so") && \
    chmod +x ${libconnector} && \
    echo -e "[build_ext]\nlibrary_path=${libconnector}" > setup.cfg && \
    cat setup.cfg && \
    python3 -u setup.py bdist_wheel && \
    auditwheel repair dist/oss*.whl -w repaired_wheel && \
    find . -type f -name "oss-connector-lib-*" -exec cp {} repaired_wheel/ \;

FROM scratch
COPY --from=builder /libconnector/repaired_wheel/oss* /
