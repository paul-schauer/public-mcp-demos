FROM node:18-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
EXPOSE 8080
CMD ["npx", "-y", "supergateway", "--stdio", "node", "build/index.js", "--port", "$PORT", "--ssePath", "/sse", "--messagePath", "/message", "--cors", "--healthEndpoint", "/healthz"]