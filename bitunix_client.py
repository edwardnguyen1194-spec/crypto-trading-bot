"""
Bitunix Futures API Client
Direct REST API integration - no CCXT dependency
"""

import time
import hmac
import hashlib
import json
import requests
from typing import Optional
import config


class BitunixClient:
    def __init__(self, api_key: str = "", api_secret: str = ""):
        self.api_key = api_key or config.API_KEY
        self.api_secret = api_secret or config.API_SECRET
        self.base_url = config.BASE_URL
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def _sign(self, timestamp: str, nonce: str, body: str = "") -> str:
        """Generate HMAC-SHA256 signature for Bitunix API auth."""
        # Bitunix signing: sha256(nonce + timestamp + api_key + body_digest)
        if body:
            body_digest = hashlib.sha256(body.encode()).hexdigest()
        else:
            body_digest = ""

        sign_str = nonce + str(timestamp) + self.api_key + body_digest
        signature = hmac.new(
            self.api_secret.encode(),
            sign_str.encode(),
            hashlib.sha256
        ).hexdigest()
        return signature

    def _request(self, method: str, endpoint: str, params: dict = None,
                 body: dict = None, signed: bool = False) -> dict:
        """Make API request with optional authentication."""
        url = f"{self.base_url}{endpoint}"

        headers = {}
        if signed:
            timestamp = str(int(time.time()))
            nonce = hashlib.md5(str(time.time_ns()).encode()).hexdigest()
            body_str = json.dumps(body) if body else ""

            signature = self._sign(timestamp, nonce, body_str)
            headers.update({
                "api-key": self.api_key,
                "sign": signature,
                "timestamp": timestamp,
                "nonce": nonce,
            })

        try:
            if method == "GET":
                resp = self.session.get(url, params=params, headers=headers, timeout=10)
            else:
                resp = self.session.post(url, json=body, headers=headers, timeout=10)

            resp.raise_for_status()
            data = resp.json()

            if data.get("code") != 0:
                raise Exception(f"Bitunix API error: {data.get('msg', 'Unknown')} (code={data.get('code')})")

            return data.get("data", data)

        except requests.exceptions.RequestException as e:
            raise Exception(f"Request failed: {e}")

    # === Public Market Data ===

    def get_tickers(self, symbols: list = None) -> list:
        """Get futures tickers."""
        params = {}
        if symbols:
            params["symbols"] = ",".join(symbols)
        return self._request("GET", "/api/v1/futures/market/tickers", params=params)

    def get_ticker(self, symbol: str) -> dict:
        """Get ticker for a specific symbol."""
        data = self._request("GET", "/api/v1/futures/market/tickers",
                             params={"symbols": symbol})
        if isinstance(data, list):
            for t in data:
                if t.get("symbol") == symbol:
                    return t
        return data

    def get_klines(self, symbol: str, interval: str, limit: int = 200) -> list:
        """
        Get candlestick/kline data.
        interval: 1m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M
        Returns list of dicts with open, high, low, close, quoteVol, baseVol, time
        """
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": min(limit, 200),
        }
        return self._request("GET", "/api/v1/futures/market/kline", params=params)

    def get_funding_rate(self, symbol: str) -> dict:
        """Get current funding rate for a symbol."""
        return self._request("GET", "/api/v1/futures/market/get_funding_rate",
                             params={"symbol": symbol})

    def get_depth(self, symbol: str, limit: int = 20) -> dict:
        """Get order book depth."""
        return self._request("GET", "/api/v1/futures/market/get_depth",
                             params={"symbol": symbol, "limit": limit})

    # === Private Account ===

    def get_account(self) -> dict:
        """Get futures account info."""
        return self._request("GET", "/api/v1/futures/account/get_single_account",
                             signed=True)

    def change_leverage(self, symbol: str, leverage: int, side: str = "BOTH") -> dict:
        """Set leverage for a trading pair."""
        body = {
            "symbol": symbol,
            "leverage": str(leverage),
            "positionSide": side,  # BOTH for one-way mode
        }
        return self._request("POST", "/api/v1/futures/account/change_leverage",
                             body=body, signed=True)

    # === Trading ===

    def place_order(self, symbol: str, side: str, qty: str,
                    order_type: str = "MARKET", price: str = None,
                    stop_loss: str = None, take_profit: str = None,
                    reduce_only: bool = False) -> dict:
        """
        Place a futures order.
        side: BUY or SELL
        order_type: MARKET or LIMIT
        """
        body = {
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": qty,
            "tradeSide": "OPEN" if not reduce_only else "CLOSE",
        }
        if price and order_type == "LIMIT":
            body["price"] = price
        if stop_loss:
            body["stopLoss"] = stop_loss
        if take_profit:
            body["takeProfit"] = take_profit

        return self._request("POST", "/api/v1/futures/trade/place_order",
                             body=body, signed=True)

    def close_position(self, symbol: str, side: str, qty: str) -> dict:
        """Close a position by placing an opposite order."""
        close_side = "SELL" if side == "BUY" else "BUY"
        body = {
            "symbol": symbol,
            "side": close_side,
            "orderType": "MARKET",
            "qty": qty,
            "tradeSide": "CLOSE",
        }
        return self._request("POST", "/api/v1/futures/trade/place_order",
                             body=body, signed=True)

    def get_open_orders(self, symbol: str = None) -> list:
        """Get all open orders."""
        params = {}
        if symbol:
            params["symbol"] = symbol
        return self._request("GET", "/api/v1/futures/trade/get_pending_orders",
                             params=params, signed=True)

    def cancel_order(self, symbol: str, order_id: str) -> dict:
        """Cancel an open order."""
        body = {"symbol": symbol, "orderId": order_id}
        return self._request("POST", "/api/v1/futures/trade/cancel_order",
                             body=body, signed=True)

    # === Positions ===

    def get_positions(self, symbol: str = None) -> list:
        """Get all open positions."""
        params = {}
        if symbol:
            params["symbol"] = symbol
        return self._request("GET", "/api/v1/futures/position/get_pending_positions",
                             params=params, signed=True)

    def get_history_positions(self, symbol: str = None) -> list:
        """Get closed position history."""
        params = {}
        if symbol:
            params["symbol"] = symbol
        return self._request("GET", "/api/v1/futures/position/get_history_positions",
                             params=params, signed=True)

    # === Helpers ===

    @staticmethod
    def _convert_interval(interval: str) -> str:
        """Convert interval string to Bitunix kline type."""
        mapping = {
            "1m": "1", "3m": "3", "5m": "5", "15m": "15",
            "30m": "30", "1h": "60", "2h": "120", "4h": "240",
            "1d": "1D", "1w": "1W",
        }
        return mapping.get(interval, interval)
