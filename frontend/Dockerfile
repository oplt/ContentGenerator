FROM node:22-alpine

WORKDIR /app

COPY frontend/package*.json /app/
RUN npm ci

COPY frontend /app
RUN chown -R node:node /app

USER node

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
