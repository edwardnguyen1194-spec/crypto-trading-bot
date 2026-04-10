const crypto = require('crypto');
const https = require('https');

const BASE_URL = 'https://fapi.bitunix.com';
const WS_URL = 'wss://fapi.bitunix.com/private';
const WS_PUBLIC_URL = 'wss://fapi.bitunix.com/public';

class BitunixClient {
  constructor(apiKey, secretKey) {
    this.apiKey = apiKey;
    this.secretKey = secretKey;
    this.baseUrl = BASE_URL;
  }

  _sha256(str) {
    return crypto.createHash('sha256').update(str, 'utf8').digest('hex');
  }

  _generateNonce() {
    return crypto.randomBytes(16).toString('hex');
  }

  _sign(queryParams = '', body = '') {
    const nonce = this._generateNonce();
    const timestamp = Date.now().toString();
    const digest = this._sha256(nonce + timestamp + this.apiKey + queryParams + body);
    const sign = this._sha256(digest + this.secretKey);
    return { nonce, timestamp, sign };
  }

  _sortParams(params) {
    return Object.keys(params)
      .sort()
      .map(k => `${k}${params[k]}`)
      .join('');
  }

  async _request(method, path, params = {}, body = null) {
    const queryStr = method === 'GET' && Object.keys(params).length > 0
      ? this._sortParams(params)
      : '';
    const bodyStr = body ? JSON.stringify(body) : '';
    const { nonce, timestamp, sign } = this._sign(queryStr, bodyStr);

    const queryString = method === 'GET' && Object.keys(params).length > 0
      ? '?' + Object.entries(params).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&')
      : '';

    const url = new URL(path + queryString, this.baseUrl);

    const options = {
      method,
      hostname: url.hostname,
      path: url.pathname + url.search,
      headers: {
        'Content-Type': 'application/json',
        'api-key': this.apiKey,
        'nonce': nonce,
        'timestamp': timestamp,
        'sign': sign,
      },
    };

    return new Promise((resolve, reject) => {
      const req = https.request(options, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
          try {
            const parsed = JSON.parse(data);
            if (parsed.code !== 0) {
              reject(new Error(`Bitunix API Error ${parsed.code}: ${parsed.msg}`));
            } else {
              resolve(parsed.data);
            }
          } catch (e) {
            reject(new Error(`Parse error: ${data}`));
          }
        });
      });
      req.on('error', reject);
      if (bodyStr) req.write(bodyStr);
      req.end();
    });
  }

  // ─── Market Data ───
  async getTickers() {
    return this._request('GET', '/api/v1/futures/market/tickers');
  }

  async getTicker(symbol) {
    return this._request('GET', '/api/v1/futures/market/tickers', { symbol });
  }

  async getKlines(symbol, interval, limit = 200) {
    return this._request('GET', '/api/v1/futures/market/kline', {
      symbol, interval, limit: limit.toString(),
    });
  }

  async getDepth(symbol, limit = 20) {
    return this._request('GET', '/api/v1/futures/market/depth', {
      symbol, limit: limit.toString(),
    });
  }

  async getTradingPairs() {
    return this._request('GET', '/api/v1/futures/market/trading_pairs');
  }

  async getFundingRate(symbol) {
    return this._request('GET', '/api/v1/futures/market/funding_rate', { symbol });
  }

  // ─── Account ───
  async getAccount() {
    return this._request('GET', '/api/v1/futures/account/get_single_account');
  }

  async getLeverageAndMarginMode(symbol) {
    return this._request('GET', '/api/v1/futures/account/get_leverage_margin_mode', { symbol });
  }

  async changeLeverage(symbol, leverage, positionSide = 'BOTH') {
    return this._request('POST', '/api/v1/futures/account/change_leverage', {}, {
      symbol, leverage: leverage.toString(), positionSide,
    });
  }

  async changeMarginMode(symbol, marginMode) {
    return this._request('POST', '/api/v1/futures/account/change_margin_mode', {}, {
      symbol, marginMode,
    });
  }

  // ─── Trading ───
  async placeOrder({ symbol, side, orderType, qty, price, tradeSide = 'OPEN', effect = 'GTC', tpPrice, slPrice, tpStopType = 'LAST_PRICE', slStopType = 'LAST_PRICE', reduceOnly = false, clientId }) {
    const body = { symbol, side, orderType, qty: qty.toString(), tradeSide };

    if (orderType === 'LIMIT' && price) {
      body.price = price.toString();
      body.effect = effect;
    }
    if (clientId) body.clientId = clientId;
    if (reduceOnly) body.reduceOnly = true;
    if (tpPrice) {
      body.tpPrice = tpPrice.toString();
      body.tpStopType = tpStopType;
      body.tpOrderType = 'MARKET';
    }
    if (slPrice) {
      body.slPrice = slPrice.toString();
      body.slStopType = slStopType;
      body.slOrderType = 'MARKET';
    }

    return this._request('POST', '/api/v1/futures/trade/place_order', {}, body);
  }

  async batchOrder(orders) {
    return this._request('POST', '/api/v1/futures/trade/batch_order', {}, { orderList: orders });
  }

  async cancelOrder(symbol, orderId) {
    return this._request('POST', '/api/v1/futures/trade/cancel_orders', {}, {
      symbol, orderIdList: [orderId],
    });
  }

  async cancelAllOrders(symbol) {
    return this._request('POST', '/api/v1/futures/trade/cancel_all_orders', {}, { symbol });
  }

  async closeAllPositions(symbol) {
    return this._request('POST', '/api/v1/futures/trade/close_all_position', {}, { symbol });
  }

  async flashClosePosition(symbol, positionId) {
    return this._request('POST', '/api/v1/futures/trade/flash_close_position', {}, {
      symbol, positionId,
    });
  }

  async modifyOrder(symbol, orderId, qty, price) {
    return this._request('POST', '/api/v1/futures/trade/modify_order', {}, {
      symbol, orderId, qty: qty.toString(), price: price.toString(),
    });
  }

  // ─── Positions ───
  async getPendingPositions(symbol) {
    return this._request('GET', '/api/v1/futures/position/get_pending_positions', { symbol });
  }

  async getHistoryPositions(symbol, pageNum = 1, pageSize = 20) {
    return this._request('GET', '/api/v1/futures/position/get_history_positions', {
      symbol, pageNum: pageNum.toString(), pageSize: pageSize.toString(),
    });
  }

  async getPositionTiers(symbol) {
    return this._request('GET', '/api/v1/futures/position/get_position_tiers', { symbol });
  }

  // ─── Orders ───
  async getPendingOrders(symbol) {
    return this._request('GET', '/api/v1/futures/trade/get_pending_orders', { symbol });
  }

  async getHistoryOrders(symbol, pageNum = 1, pageSize = 20) {
    return this._request('GET', '/api/v1/futures/trade/get_history_orders', {
      symbol, pageNum: pageNum.toString(), pageSize: pageSize.toString(),
    });
  }

  async getOrderDetail(symbol, orderId) {
    return this._request('GET', '/api/v1/futures/trade/get_order_detail', { symbol, orderId });
  }

  // ─── TP/SL ───
  async placeTpSlOrder({ symbol, positionId, tpPrice, slPrice, tpStopType = 'LAST_PRICE', slStopType = 'LAST_PRICE' }) {
    const body = { symbol, positionId };
    if (tpPrice) {
      body.tpPrice = tpPrice.toString();
      body.tpStopType = tpStopType;
      body.tpOrderType = 'MARKET';
    }
    if (slPrice) {
      body.slPrice = slPrice.toString();
      body.slStopType = slStopType;
      body.slOrderType = 'MARKET';
    }
    return this._request('POST', '/api/v1/futures/tp_sl/place_tp_sl_order', {}, body);
  }

  // ─── WebSocket auth params ───
  getWsAuthParams() {
    const nonce = this._generateNonce();
    const timestamp = Date.now().toString();
    const params = `apiKey${this.apiKey}nonce${nonce}timestamp${timestamp}`;
    const digest = this._sha256(nonce + timestamp + this.apiKey + params);
    const sign = this._sha256(digest + this.secretKey);
    return { apiKey: this.apiKey, nonce, timestamp, sign };
  }
}

module.exports = { BitunixClient, BASE_URL, WS_URL, WS_PUBLIC_URL };
