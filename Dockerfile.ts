FROM node

WORKDIR /app
COPY ts /app
RUN yarn install

EXPOSE 50051
CMD npx ts-node server.ts

