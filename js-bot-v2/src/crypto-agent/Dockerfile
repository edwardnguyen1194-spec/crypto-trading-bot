FROM node:20-slim

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci --only=production

# Copy source
COPY src/crypto-agent ./src/crypto-agent

# Expose dashboard port
EXPOSE 3456

# Start dashboard (includes trading bot)
CMD ["node", "src/crypto-agent/dashboard/server.js"]
