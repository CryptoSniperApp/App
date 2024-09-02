FROM node:alpine

WORKDIR /app
COPY ts /app
RUN yarn install
# RUN apk --no-cache add netcat-openbsd

EXPOSE 50051
CMD npx ts-node server.ts

