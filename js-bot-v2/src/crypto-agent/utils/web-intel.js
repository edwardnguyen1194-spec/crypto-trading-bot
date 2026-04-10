const https = require('https');

/**
 * Web Intelligence - fetches crypto news, fear & greed index, trending data
 */
class WebIntel {
  constructor() {
    this.cache = {};
    this.cacheTTL = 300000; // 5 min cache
  }

  async _fetch(url) {
    return new Promise((resolve, reject) => {
      https.get(url, { headers: { 'User-Agent': 'CryptoAgent/1.0' } }, (res) => {
        let data = '';
        res.on('data', d => data += d);
        res.on('end', () => {
          try { resolve(JSON.parse(data)); }
          catch { resolve(data); }
        });
      }).on('error', reject);
    });
  }

  _getCached(key) {
    const cached = this.cache[key];
    if (cached && Date.now() - cached.time < this.cacheTTL) return cached.data;
    return null;
  }

  _setCache(key, data) {
    this.cache[key] = { data, time: Date.now() };
  }

  /**
   * Fear & Greed Index
   */
  async getFearGreed() {
    const cached = this._getCached('feargreed');
    if (cached) return cached;
    try {
      const data = await this._fetch('https://api.alternative.me/fng/?limit=1');
      const result = {
        value: parseInt(data.data[0].value),
        label: data.data[0].value_classification,
        timestamp: data.data[0].timestamp,
      };
      this._setCache('feargreed', result);
      return result;
    } catch {
      return { value: 50, label: 'Neutral', error: true };
    }
  }

  /**
   * CoinGecko trending coins
   */
  async getTrending() {
    const cached = this._getCached('trending');
    if (cached) return cached;
    try {
      const data = await this._fetch('https://api.coingecko.com/api/v3/search/trending');
      const coins = (data.coins || []).slice(0, 5).map(c => ({
        name: c.item.name,
        symbol: c.item.symbol,
        rank: c.item.market_cap_rank,
      }));
      this._setCache('trending', coins);
      return coins;
    } catch {
      return [];
    }
  }

  /**
   * BTC dominance and global market data
   */
  async getGlobalData() {
    const cached = this._getCached('global');
    if (cached) return cached;
    try {
      const data = await this._fetch('https://api.coingecko.com/api/v3/global');
      const result = {
        btcDominance: data.data.market_cap_percentage.btc.toFixed(1),
        ethDominance: data.data.market_cap_percentage.eth.toFixed(1),
        totalMarketCap: (data.data.total_market_cap.usd / 1e12).toFixed(2) + 'T',
        totalVolume24h: (data.data.total_volume.usd / 1e9).toFixed(1) + 'B',
        marketCapChange24h: data.data.market_cap_change_percentage_24h_usd.toFixed(2),
      };
      this._setCache('global', result);
      return result;
    } catch {
      return null;
    }
  }

  /**
   * CoinGecko price data with 24h change for specific coins
   */
  async getCoinData(ids = 'bitcoin,ethereum,solana,ripple') {
    const cached = this._getCached('coindata');
    if (cached) return cached;
    try {
      const data = await this._fetch(
        `https://api.coingecko.com/api/v3/simple/price?ids=${ids}&vs_currencies=usd&include_24hr_change=true&include_24hr_vol=true&include_market_cap=true`
      );
      this._setCache('coindata', data);
      return data;
    } catch {
      return null;
    }
  }

  /**
   * Get full market intel summary
   */
  async getMarketIntel() {
    const [fearGreed, trending, global, coinData] = await Promise.all([
      this.getFearGreed(),
      this.getTrending(),
      this.getGlobalData(),
      this.getCoinData(),
    ]);

    let summary = 'MARKET INTELLIGENCE (live from internet):\n';

    if (fearGreed) {
      summary += `Fear & Greed Index: ${fearGreed.value}/100 (${fearGreed.label})\n`;
    }

    if (global) {
      summary += `Global Market Cap: $${global.totalMarketCap} (${global.marketCapChange24h}% 24h)\n`;
      summary += `24h Volume: $${global.totalVolume24h}\n`;
      summary += `BTC Dominance: ${global.btcDominance}% | ETH: ${global.ethDominance}%\n`;
    }

    if (coinData) {
      const coins = { bitcoin: 'BTC', ethereum: 'ETH', solana: 'SOL', ripple: 'XRP' };
      for (const [id, sym] of Object.entries(coins)) {
        const c = coinData[id];
        if (c) {
          summary += `${sym}: $${c.usd.toLocaleString()} (${c.usd_24h_change?.toFixed(2)}% 24h) | Vol: $${(c.usd_24h_vol / 1e9).toFixed(1)}B | MCap: $${(c.usd_market_cap / 1e9).toFixed(0)}B\n`;
        }
      }
    }

    if (trending && trending.length > 0) {
      summary += `Trending: ${trending.map(t => t.symbol).join(', ')}\n`;
    }

    return summary;
  }

  /**
   * Get BTC/ETH long/short ratio and open interest from Binance (free)
   */
  async getLongShortRatio(symbol = 'BTCUSDT') {
    const cached = this._getCached('lsr_' + symbol);
    if (cached) return cached;
    try {
      const data = await this._fetch(
        `https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol=${symbol}&period=1h&limit=1`
      );
      if (data && data[0]) {
        const result = {
          symbol,
          longAccount: (parseFloat(data[0].longAccount) * 100).toFixed(1),
          shortAccount: (parseFloat(data[0].shortAccount) * 100).toFixed(1),
          longShortRatio: parseFloat(data[0].longShortRatio).toFixed(2),
        };
        this._setCache('lsr_' + symbol, result);
        return result;
      }
    } catch { }
    return null;
  }

  /**
   * Get open interest from Binance
   */
  async getOpenInterest(symbol = 'BTCUSDT') {
    const cached = this._getCached('oi_' + symbol);
    if (cached) return cached;
    try {
      const data = await this._fetch(
        `https://fapi.binance.com/fapi/v1/openInterest?symbol=${symbol}`
      );
      if (data && data.openInterest) {
        const result = { symbol, openInterest: parseFloat(data.openInterest) };
        this._setCache('oi_' + symbol, result);
        return result;
      }
    } catch { }
    return null;
  }

  /**
   * Get top liquidations data
   */
  async getFundingRates() {
    const cached = this._getCached('funding');
    if (cached) return cached;
    try {
      const data = await this._fetch('https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT');
      if (data) {
        const result = {
          symbol: data.symbol,
          fundingRate: (parseFloat(data.lastFundingRate) * 100).toFixed(4),
          nextFundingTime: new Date(data.nextFundingTime).toLocaleTimeString(),
          markPrice: parseFloat(data.markPrice).toFixed(2),
        };
        this._setCache('funding', result);
        return result;
      }
    } catch { }
    return null;
  }

  /**
   * Full advanced market intel including on-chain / derivatives data
   */
  async getAdvancedIntel() {
    const [basic, btcLSR, ethLSR, btcOI, funding] = await Promise.all([
      this.getMarketIntel(),
      this.getLongShortRatio('BTCUSDT'),
      this.getLongShortRatio('ETHUSDT'),
      this.getOpenInterest('BTCUSDT'),
      this.getFundingRates(),
    ]);

    let intel = basic;

    intel += '\nDERIVATIVES DATA:\n';
    if (btcLSR) {
      intel += `BTC Long/Short: ${btcLSR.longAccount}% long / ${btcLSR.shortAccount}% short (ratio: ${btcLSR.longShortRatio})\n`;
    }
    if (ethLSR) {
      intel += `ETH Long/Short: ${ethLSR.longAccount}% long / ${ethLSR.shortAccount}% short (ratio: ${ethLSR.longShortRatio})\n`;
    }
    if (btcOI) {
      intel += `BTC Open Interest: ${btcOI.openInterest.toLocaleString()} BTC\n`;
    }
    if (funding) {
      intel += `BTC Funding Rate: ${funding.fundingRate}% | Next: ${funding.nextFundingTime}\n`;
      intel += `BTC Mark Price: $${funding.markPrice}\n`;
    }

    // Add pro trading knowledge context
    intel += '\nTRADING WISDOM (use these in your analysis):\n';
    intel += '- High funding rate (>0.03%) = overleveraged longs, expect a flush down\n';
    intel += '- Negative funding = shorts paying longs, bullish squeeze incoming\n';
    intel += '- Long/Short ratio >60% on one side = crowded trade, fade it\n';
    intel += '- Rising OI + rising price = new money entering (strong trend)\n';
    intel += '- Rising OI + falling price = shorts opening (bearish pressure)\n';
    intel += '- Falling OI + rising price = short squeeze (not sustainable)\n';
    intel += '- Fear & Greed <25 = extreme fear, historically great buy zone\n';
    intel += '- Fear & Greed >75 = extreme greed, consider taking profits\n';
    intel += '- BTC dominance rising = altcoins will bleed, focus on BTC\n';
    intel += '- BTC dominance falling = alt season starting, rotate to alts\n';

    return intel;
  }
}

module.exports = { WebIntel };
