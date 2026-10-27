FROM node:24-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG VITE_USE_FIREBASE_EMULATORS=false
ENV VITE_USE_FIREBASE_EMULATORS=${VITE_USE_FIREBASE_EMULATORS}
RUN case "$VITE_USE_FIREBASE_EMULATORS" in true|false) ;; *) exit 1 ;; esac \
    && npm run build

FROM nginx:stable-alpine
ARG VITE_USE_FIREBASE_EMULATORS=false
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY nginx.emulator.conf /tmp/nginx.emulator.conf
COPY nginx.runtime.conf /etc/nginx/nginx.conf
RUN if [ "$VITE_USE_FIREBASE_EMULATORS" = true ]; then \
      cp /tmp/nginx.emulator.conf /etc/nginx/conf.d/default.conf; \
    fi && rm /tmp/nginx.emulator.conf
USER 101:101
EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD wget -q -O /dev/null http://127.0.0.1:3000/
ENTRYPOINT ["nginx", "-g", "daemon off;"]
