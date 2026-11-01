# Build both React apps (npm workspaces), then serve them with one nginx:
#   :8080 front office (customers + advisors), :8081 back office (managers).
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
COPY shared/package.json shared/
COPY front-office/package.json front-office/
COPY back-office/package.json back-office/
RUN npm ci
COPY . .
ENV VITE_FRONT_OFFICE_URL=http://localhost:8080     VITE_BACK_OFFICE_URL=http://localhost:8081
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/front-office/dist /usr/share/nginx/front-office
COPY --from=build /app/back-office/dist /usr/share/nginx/back-office
EXPOSE 8080 8081
