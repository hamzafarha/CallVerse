# Build both React apps (npm workspaces), then serve them with one nginx:
#   :8080 front office (customers + advisors), :8081 back office (managers).
# Stage 1 (build): install the packages and build both apps into static files (dist/).
FROM node:20-alpine AS build
WORKDIR /app
# Copy the package files first: Docker reuses the cached npm install while they do not change.
COPY package.json package-lock.json ./
COPY shared/package.json shared/
COPY front-office/package.json front-office/
COPY back-office/package.json back-office/
RUN npm ci
COPY . .
# The links between the two apps point to the nginx ports.
ENV VITE_FRONT_OFFICE_URL=http://localhost:8080     VITE_BACK_OFFICE_URL=http://localhost:8081
RUN npm run build

# Stage 2 (serve): a small nginx image with only the built files (no Node.js).
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/front-office/dist /usr/share/nginx/front-office
COPY --from=build /app/back-office/dist /usr/share/nginx/back-office
EXPOSE 8080 8081
