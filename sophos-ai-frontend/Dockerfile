FROM node:18-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci --silent

COPY public/ ./public/
COPY src/ ./src/

ARG REACT_APP_API_URL
ENV REACT_APP_API_URL=$REACT_APP_API_URL

RUN npm run build

FROM nginx:alpine

RUN apk add --no-cache curl

COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
