FROM eclipse-temurin:21-jre-jammy AS java
FROM node:24-bookworm-slim
ENV JAVA_HOME=/opt/java/openjdk FIREBASE_EMULATORS_PATH=/opt/firebase/emulators \
    FIREBASE_CLI_DISABLE_UPDATE_CHECK=true XDG_CONFIG_HOME=/tmp/config
ENV PATH="${JAVA_HOME}/bin:${PATH}"
WORKDIR /app
COPY --from=java /opt/java/openjdk /opt/java/openjdk
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts \
    && node node_modules/firebase-tools/lib/bin/firebase.js setup:emulators:database \
    && mkdir -p /data && chown node:node /data
COPY database.rules.json ./
COPY deploy/firebase/firebase.json ./firebase.docker.json
COPY deploy/firebase/healthcheck.mjs ./healthcheck.mjs
USER node
WORKDIR /data
EXPOSE 9099 9000
HEALTHCHECK --interval=5s --timeout=3s --start-period=40s --retries=30 \
    CMD ["node", "/app/healthcheck.mjs"]
ENTRYPOINT ["node", "/app/node_modules/firebase-tools/lib/bin/firebase.js"]
CMD ["emulators:start", "--project", "demo-coursesphere", "--only", "auth,database", "--config", "/app/firebase.docker.json", "--import", "/data/state", "--export-on-exit", "/data/state"]
