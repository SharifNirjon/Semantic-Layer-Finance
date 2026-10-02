FROM node:24-alpine AS build
ARG NPM_REGISTRY=https://registry.npmjs.org
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm config set registry ${NPM_REGISTRY} && npm install --no-audit --no-fund
COPY . .
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL} NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:24-alpine
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
