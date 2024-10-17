FROM node:alpine

WORKDIR /app

COPY ts/package.json .
RUN yarn install

COPY ts /app
COPY .env /app/.env
EXPOSE 50051

CMD ts-node server.ts

