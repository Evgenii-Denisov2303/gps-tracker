# Optional isolated APK build; SDK license acceptance is part of this build.
FROM gradle:8.11.1-jdk17 AS builder
USER root
RUN apt-get update && apt-get install -y --no-install-recommends curl unzip && rm -rf /var/lib/apt/lists/*
ENV ANDROID_HOME=/opt/android-sdk
RUN mkdir -p /opt/android-sdk/cmdline-tools && \
    curl -fL https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip -o /tmp/sdk.zip && \
    unzip -q /tmp/sdk.zip -d /opt/android-sdk/cmdline-tools && \
    mv /opt/android-sdk/cmdline-tools/cmdline-tools /opt/android-sdk/cmdline-tools/latest && rm /tmp/sdk.zip
RUN yes | /opt/android-sdk/cmdline-tools/latest/bin/sdkmanager --licenses >/dev/null
RUN /opt/android-sdk/cmdline-tools/latest/bin/sdkmanager 'platforms;android-35' 'build-tools;35.0.0'
WORKDIR /project
COPY . .
RUN --mount=type=cache,target=/root/.gradle --mount=type=secret,id=android_debug_keystore \
    if [ -f /run/secrets/android_debug_keystore ]; then \
      mkdir -p /root/.android && cp /run/secrets/android_debug_keystore /root/.android/debug.keystore; \
    fi && gradle --no-daemon testDebugUnitTest lintDebug assembleDebug
FROM scratch AS export
COPY --from=builder /project/app/build/outputs/apk/debug/app-debug.apk /fleet-tracker-debug.apk
COPY --from=builder /project/app/build/reports/lint-results-debug.html /lint-results.html
COPY --from=builder /project/app/build/test-results/testDebugUnitTest /unit-test-results
