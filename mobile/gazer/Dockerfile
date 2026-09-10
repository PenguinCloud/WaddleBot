# syntax=docker/dockerfile:1.7
#
# Gazer Mobile 2.0 toolchain image. Every mobile-* make target in the
# repo-root Makefile runs inside this image -- nothing in mobile/gazer is
# ever built, linted, tested, or packaged with the host's Flutter/Android
# SDK. Single stage: this image ships no runtime app of its own, it *is*
# the build tool, so there is no separate "runtime" half to split into a
# second stage.
FROM ubuntu@sha256:33ceb71981b602c1a7443a53469e4dba065f7503eab3078a2d7a57a2ab987517

LABEL org.opencontainers.image.title="gazer-toolchain" \
      org.opencontainers.image.description="Flutter 3.47.2 + Android SDK 36 + Temurin 17 toolchain for mobile/gazer" \
      org.opencontainers.image.source="https://github.com/penguintechinc/waddlebot"

ARG DEBIAN_FRONTEND=noninteractive

# --- Base OS packages (rarely changes -> keep first for cache reuse) ------
# cmake here satisfies the spec's "CMake 3.28+ system or download" pin
# (Ubuntu 24.04's repo cmake is 3.28.x); clang/ninja are pre-installed now
# so the same image serves M2/M3's native libuvc bridge without a rebuild.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        gnupg \
        unzip \
        xz-utils \
        cmake \
        ninja-build \
        clang \
        python3 \
        python3-venv \
        file \
    && rm -rf /var/lib/apt/lists/*

# --- Temurin 17 (Eclipse Adoptium apt repo; GPG key pinned by fingerprint) -
# Fingerprint verified 2026-09-07 by downloading
# https://packages.adoptium.net/artifactory/api/gpg/key/public and running
# `gpg --show-keys --with-fingerprint --with-colons` on the result; this is
# Eclipse Adoptium's Temurin apt signing key fingerprint.
ENV ADOPTIUM_GPG_FPR="3B04D753C9050D9A5D343F39843C48A565F8F04B"
RUN curl -fsSL https://packages.adoptium.net/artifactory/api/gpg/key/public -o /tmp/adoptium.asc \
    && ACTUAL_FPR=$(gpg --show-keys --with-fingerprint --with-colons /tmp/adoptium.asc | awk -F: '/^fpr:/ {print $10; exit}') \
    && if [ "$ACTUAL_FPR" != "$ADOPTIUM_GPG_FPR" ]; then \
         echo "Adoptium GPG key fingerprint mismatch: got $ACTUAL_FPR, expected $ADOPTIUM_GPG_FPR -- ABORT" >&2; \
         exit 1; \
       fi \
    && gpg --dearmor -o /usr/share/keyrings/adoptium.gpg /tmp/adoptium.asc \
    && rm /tmp/adoptium.asc \
    && echo "deb [signed-by=/usr/share/keyrings/adoptium.gpg] https://packages.adoptium.net/artifactory/deb $(awk -F= '/^VERSION_CODENAME/{print $2}' /etc/os-release) main" > /etc/apt/sources.list.d/adoptium.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends temurin-17-jdk \
    && rm -rf /var/lib/apt/lists/*
ENV JAVA_HOME=/usr/lib/jvm/temurin-17-jdk-amd64
ENV PATH="${JAVA_HOME}/bin:${PATH}"

# --- Security scanners for mobile-security (osv-scanner, gitleaks, semgrep) -
# Installed here as root, before appuser exists, so mobile-security never
# needs root at runtime. This image is amd64-only today (matches the host
# this toolchain builds on) -- linux_amd64/linux_x64 assets are selected
# explicitly; no arm64 branch is added until a genuine multi-arch need
# exists (see devops-containers.md Multi-Arch Builds).

# osv-scanner v2.5.1 (latest stable release as of 2026-09-11, verified via
# `gh release list --repo google/osv-scanner`) -- linux_amd64 binary,
# sha256 independently verified against the release's own
# osv-scanner_SHA256SUMS file (re-downloaded and hashed directly, not just
# read from the checksums file).
ENV OSV_SCANNER_VERSION="2.5.1"
ENV OSV_SCANNER_SHA256="f9f25499a2c8cc367b3af45df2ea7eeca7fbccceab9c35079968f4b3652194be"
RUN curl -fsSL "https://github.com/google/osv-scanner/releases/download/v${OSV_SCANNER_VERSION}/osv-scanner_linux_amd64" -o /tmp/osv-scanner \
    && echo "${OSV_SCANNER_SHA256}  /tmp/osv-scanner" | sha256sum -c - \
    && install -m 0755 /tmp/osv-scanner /usr/local/bin/osv-scanner \
    && rm /tmp/osv-scanner

# gitleaks v8.30.1 (latest stable release as of 2026-09-11, verified via
# `gh release list --repo gitleaks/gitleaks`) -- linux_x64 tarball, sha256
# independently verified against the release's own
# gitleaks_8.30.1_checksums.txt file (re-downloaded and hashed directly).
ENV GITLEAKS_VERSION="8.30.1"
ENV GITLEAKS_SHA256="551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"
RUN curl -fsSL "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" -o /tmp/gitleaks.tar.gz \
    && echo "${GITLEAKS_SHA256}  /tmp/gitleaks.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/gitleaks.tar.gz -C /tmp gitleaks \
    && install -m 0755 /tmp/gitleaks /usr/local/bin/gitleaks \
    && rm -f /tmp/gitleaks.tar.gz /tmp/gitleaks

# semgrep 1.176.1 (latest stable on PyPI as of 2026-09-11, verified via
# https://pypi.org/pypi/semgrep/json) -- installed into its own venv (not
# system python3, which stays free for other tooling) and symlinked onto
# PATH. Exact version pinned; `pip install semgrep` with no pin is
# forbidden by critical-rules.md Dependency Pinning.
ENV SEMGREP_VERSION="1.176.1"
RUN python3 -m venv /opt/semgrep \
    && /opt/semgrep/bin/pip install --no-cache-dir "semgrep==${SEMGREP_VERSION}" \
    && ln -s /opt/semgrep/bin/semgrep /usr/local/bin/semgrep

# --- Non-root user (UID 1000) ----------------------------------------------
# ubuntu:24.04 ships a stock "ubuntu" user/group already at uid/gid 1000 --
# remove it first (missing-user/-group is not an error here: this RUN's
# shell has no `set -e`, so `;`-joined statements continue past a non-zero
# exit) so appuser can claim uid:gid 1000, matching the host uid used by the
# mobile-* make targets' `docker run --user $(id -u):$(id -g)`.
RUN userdel -r ubuntu 2>/dev/null; getent group ubuntu >/dev/null && groupdel ubuntu; groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash appuser

# --- Flutter 3.47.2 (sha256-verified tarball) ------------------------------
ENV FLUTTER_SDK_SHA256="447878859d01ca9bfdb99a85f245af07ed8a15fedcd9d189c4749e8e92d1f185"
RUN curl -fsSL https://storage.googleapis.com/flutter_infra_release/releases/stable/linux/flutter_linux_3.47.2-stable.tar.xz -o /tmp/flutter.tar.xz \
    && echo "${FLUTTER_SDK_SHA256}  /tmp/flutter.tar.xz" | sha256sum -c - \
    && tar -xJf /tmp/flutter.tar.xz -C /opt \
    && rm /tmp/flutter.tar.xz \
    && chown -R appuser:appuser /opt/flutter
ENV PATH="/opt/flutter/bin:${PATH}"

# --- Android cmdline-tools (sha256-verified zip; independently re-verified
# as Task 1 Step 4 before this pin was trusted) -----------------------------
ENV ANDROID_SDK_ROOT=/opt/android-sdk
ENV ANDROID_HOME="${ANDROID_SDK_ROOT}"
ENV ANDROID_NDK_HOME="${ANDROID_SDK_ROOT}/ndk/28.2.13676358"
ENV CMDLINE_TOOLS_SHA256="4e4c464f145a7512b57d088ac6c278c03c9eea610886b35a5e0804e74eedf583"
RUN mkdir -p "${ANDROID_SDK_ROOT}/cmdline-tools" \
    && curl -fsSL https://dl.google.com/android/repository/commandlinetools-linux-15859902_latest.zip -o /tmp/cmdline-tools.zip \
    && echo "${CMDLINE_TOOLS_SHA256}  /tmp/cmdline-tools.zip" | sha256sum -c - \
    && unzip -q /tmp/cmdline-tools.zip -d "${ANDROID_SDK_ROOT}/cmdline-tools" \
    && mv "${ANDROID_SDK_ROOT}/cmdline-tools/cmdline-tools" "${ANDROID_SDK_ROOT}/cmdline-tools/latest" \
    && rm /tmp/cmdline-tools.zip \
    && chown -R appuser:appuser "${ANDROID_SDK_ROOT}"
ENV PATH="${ANDROID_SDK_ROOT}/cmdline-tools/latest/bin:${ANDROID_SDK_ROOT}/platform-tools:${ANDROID_SDK_ROOT}/build-tools/36.0.0:${PATH}"

# --- SDK packages (root-installed: sdkmanager writes under $ANDROID_SDK_ROOT
# as root and licenses are accepted as root too -- appuser only needs read
# access to run the SDK tools later; do not chmod the SDK world-writable) ---
# Two separate RUN layers -- not chained with `&&` -- so writer E's Task 21 can find and modify
# the package-install invocation on its own (it appends "system-images;android-34;google_apis;
# x86_64" and "emulator" to this exact list for the integration-test emulator). cmdline-tools is
# deliberately NOT re-listed as an sdkmanager package here: it was already unpacked directly at
# ${ANDROID_SDK_ROOT}/cmdline-tools/latest above, which IS the "cmdline-tools;latest" package as
# far as sdkmanager is concerned -- asking sdkmanager to install it again is redundant.
RUN yes | sdkmanager --sdk_root="${ANDROID_SDK_ROOT}" --licenses > /dev/null

# cmake;3.22.1, platforms;android-34, platforms;android-35 added by Task 2 (2026-09-09):
# transitive Flutter plugins pulled in by the spec-pinned pubspec.yaml dependency graph each
# compile against a DIFFERENT platform than this app's own compileSdk=36, and Gradle cannot
# substitute a different platform for what a subproject's own build.gradle declares:
#   - cmake;3.22.1: the :jni native module (transitively via device_info_plus, part of the
#     package:jni/jnigen ecosystem) runs `configureCMakeDebug`, which needs this exact CMake
#     version -- without it: "Failed to install the following SDK components: cmake;3.22.1".
#   - platforms;android-34: file_picker 8.3.7 (transitively via flutter_libs) declares
#     compileSdk 34 in its own plugin build.gradle -- without it, its `extractDebugAnnotations`
#     task fails the same way ("Failed to install ... platforms;android-34").
#   - platforms;android-35: permission_handler_android 13.0.1 (pinned directly in
#     pubspec.yaml -- see its comment there for why 14.x/13.0.2+ are unusable: they need
#     platforms;android-37, which does not exist yet in the Android SDK repository)
#     declares compileSdkVersion 35 in its own plugin build.gradle.
RUN sdkmanager --sdk_root="${ANDROID_SDK_ROOT}" \
      "platforms;android-34" \
      "platforms;android-35" \
      "platforms;android-36" \
      "build-tools;36.0.0" \
      "ndk;28.2.13676358" \
      "platform-tools" \
      "cmake;3.22.1"

# --- Switch to appuser before any flutter invocation ------------------------
# /opt/flutter is chown'd to appuser (above); git refuses to operate inside a
# repo it doesn't own ("dubious ownership") when the effective uid differs,
# so every flutter command from here on runs as appuser. ENV HOME is set
# explicitly rather than left to the USER-by-name default because the
# mobile-* make targets invoke `docker run --user $(id -u):$(id -g)` with the
# HOST uid/gid at runtime, which has no /etc/passwd entry to derive HOME
# from -- an explicit ENV HOME persists regardless of that runtime --user
# override, so $HOME/.gitconfig (holding the safe.directory exception below)
# and the gazer-pub-cache / gazer-gradle named volumes always resolve to the
# same path both at build time and at every mobile-* invocation.
ENV HOME=/home/appuser
USER appuser

RUN git config --global --add safe.directory /opt/flutter \
    && flutter config --no-analytics \
    && flutter precache --android

USER root
RUN mkdir -p /work && chown appuser:appuser /work
WORKDIR /work
USER appuser

# No ENTRYPOINT: every mobile-* make target passes its full command as the
# container CMD (`docker run ... gazer-toolchain:3.47.2 <cmd>`). This CMD
# only matters for `docker run gazer-toolchain:3.47.2` with no arguments.
CMD ["bash", "-lc", "flutter --version"]
