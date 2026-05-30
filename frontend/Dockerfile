# Multi-stage build for the Valeraup frontend.
#
# Stage 1 (build): install deps and produce the static Vite bundle.
# Stage 2 (runtime): serve the bundle with nginx (tiny, no Node at runtime).
#
# Note: VITE_API_BASE_URL is baked in at build time because Vite inlines
# import.meta.env.* into the bundle. Override with a build-arg per environment.

# ---- Stage 1: build ----
FROM node:22-alpine AS build
WORKDIR /app

# Install dependencies first to leverage Docker layer caching.
COPY package.json package-lock.json* ./
RUN npm install

# Copy the rest of the source and build.
COPY . .

ARG VITE_API_BASE_URL=http://localhost:8000/api
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build

# ---- Stage 2: runtime ----
FROM nginx:1.27-alpine AS runtime

# SPA-aware nginx config (history fallback to index.html).
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Static assets produced by the build stage.
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
