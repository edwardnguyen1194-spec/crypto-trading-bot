FROM node:20-slim

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install --omit=dev

# Copy source
COPY src ./src

# Create data directory for state persistence
RUN mkdir -p /app/data

# Expose dashboard port
EXPOSE 3456

# Start dashboard (which also starts the trading bot via /start command)
CMD ["node", "src/crypto-agent/dashboard/server.js"]
