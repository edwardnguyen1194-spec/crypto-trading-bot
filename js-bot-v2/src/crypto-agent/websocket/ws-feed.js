const WebSocket = require('ws');
const EventEmitter = require('events');

const WS_PUBLIC_URL = 'wss://fapi.bitunix.com/public/';
const WS_PRIVATE_URL = 'wss://fapi.bitunix.com/private/';

class BitunixWebSocket extends EventEmitter {
  constructor(client) {
    super();
    this.client = client;
    this.publicWs = null;
    this.privateWs = null;
    this.reconnectDelay = 5000;
    this.maxReconnectDelay = 60000;
    this.pingInterval = null;
    this.subscriptions = new Set();
    this.isConnected = { public: false, private: false };
  }

  async connectPublic(symbols) {
    return new Promise((resolve, reject) => {
      this.publicWs = new WebSocket(WS_PUBLIC_URL);

      this.publicWs.on('open', () => {
        console.log('[WS] Public feed connected');
        this.isConnected.public = true;

        // Subscribe to channels
        for (const symbol of symbols) {
          this._subscribe(this.publicWs, 'ticker', symbol);
          this._subscribe(this.publicWs, 'kline_1m', symbol);
          this._subscribe(this.publicWs, 'kline_5m', symbol);
          this._subscribe(this.publicWs, 'depth5', symbol);
          this._subscribe(this.publicWs, 'trade', symbol);
        }

        this._startPing(this.publicWs, 'public');
        resolve();
      });

      this.publicWs.on('message', (data) => {
        try {
          const msg = JSON.parse(data.toString());
          this._handlePublicMessage(msg);
        } catch (e) {
          // ping/pong or non-JSON
        }
      });

      this.publicWs.on('close', () => {
        console.log('[WS] Public feed disconnected');
        this.isConnected.public = false;
        this._reconnect('public', symbols);
      });

      this.publicWs.on('error', (err) => {
        console.error('[WS] Public error:', err.message);
        reject(err);
      });
    });
  }

  async connectPrivate() {
    return new Promise((resolve, reject) => {
      this.privateWs = new WebSocket(WS_PRIVATE_URL);

      this.privateWs.on('open', () => {
        console.log('[WS] Private feed connected');
        this.isConnected.private = true;

        // Authenticate
        const auth = this.client.getWsAuthParams();
        this.privateWs.send(JSON.stringify({
          op: 'login',
          args: [auth],
        }));

        setTimeout(() => {
          this._subscribe(this.privateWs, 'order', '');
          this._subscribe(this.privateWs, 'position', '');
          this._subscribe(this.privateWs, 'balance', '');
          resolve();
        }, 1000);

        this._startPing(this.privateWs, 'private');
      });

      this.privateWs.on('message', (data) => {
        try {
          const msg = JSON.parse(data.toString());
          this._handlePrivateMessage(msg);
        } catch (e) {
          // ping/pong
        }
      });

      this.privateWs.on('close', () => {
        console.log('[WS] Private feed disconnected');
        this.isConnected.private = false;
        this._reconnect('private');
      });

      this.privateWs.on('error', (err) => {
        console.error('[WS] Private error:', err.message);
      });
    });
  }

  _subscribe(ws, channel, symbol) {
    const sub = { channel, symbol };
    ws.send(JSON.stringify({ op: 'subscribe', args: [sub] }));
    this.subscriptions.add(JSON.stringify(sub));
  }

  _handlePublicMessage(msg) {
    if (!msg.ch) return;

    const channel = msg.ch;
    if (channel.includes('ticker')) {
      this.emit('ticker', msg.data);
    } else if (channel.includes('kline')) {
      this.emit('kline', { interval: channel.split('_')[1], data: msg.data });
    } else if (channel.includes('depth')) {
      this.emit('depth', msg.data);
    } else if (channel.includes('trade')) {
      this.emit('trade', msg.data);
    }
  }

  _handlePrivateMessage(msg) {
    if (!msg.ch) return;

    const channel = msg.ch;
    if (channel.includes('order')) {
      this.emit('order_update', msg.data);
    } else if (channel.includes('position')) {
      this.emit('position_update', msg.data);
    } else if (channel.includes('balance')) {
      this.emit('balance_update', msg.data);
    }
  }

  _startPing(ws, type) {
    const interval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send('ping');
      }
    }, 20000);

    ws.on('close', () => clearInterval(interval));
  }

  _reconnect(type, symbols) {
    console.log(`[WS] Reconnecting ${type} in ${this.reconnectDelay / 1000}s...`);
    setTimeout(() => {
      if (type === 'public' && symbols) {
        this.connectPublic(symbols).catch(() => {});
      } else if (type === 'private') {
        this.connectPrivate().catch(() => {});
      }
    }, this.reconnectDelay);
    this.reconnectDelay = Math.min(this.reconnectDelay * 1.5, this.maxReconnectDelay);
  }

  disconnect() {
    if (this.publicWs) this.publicWs.close();
    if (this.privateWs) this.privateWs.close();
  }
}

module.exports = { BitunixWebSocket };
