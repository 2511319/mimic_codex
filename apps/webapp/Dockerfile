FROM node:20-alpine as build
WORKDIR /app
COPY apps/webapp/package*.json ./
RUN npm ci
COPY apps/webapp .
RUN npm run build

FROM node:20-alpine as runtime
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/dist ./dist

# Лёгкий http-сервер для раздачи статики
RUN npm i -g http-server@14

EXPOSE 4173
CMD ["http-server", "dist", "-p", "4173", "-a", "0.0.0.0", "--silent", "--cors"]
