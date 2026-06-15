FROM node:20-alpine AS client-build
WORKDIR /app/client
COPY client/package.json client/package-lock.json* ./
RUN npm install
COPY client/ ./
RUN npm run build

FROM node:20-alpine
RUN apk add --no-cache curl
WORKDIR /app
COPY server/package.json server/package-lock.json* ./
RUN npm install --production
COPY server/ ./
COPY --from=client-build /app/client/dist ./public
ENV NODE_ENV=production
ENV PORT=3000
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:3000/api/health || exit 1
CMD ["node", "index.js"]
