FROM node:alpine

WORKDIR /app

COPY ts/package.json .
RUN npm install

COPY ts /app
COPY .env /app/.env
EXPOSE 50051

CMD npx ts-node server.ts

