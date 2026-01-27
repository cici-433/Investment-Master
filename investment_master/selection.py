import yfinance as yf

class StockSelector:
    def __init__(self):
        pass

    def select(self, criteria, tickers=None):
        """
        根据标准筛选股票。
        如果提供了 tickers 列表，则实时获取数据进行筛选。
        否则返回模拟数据。
        """
        if tickers:
            print(f"正在筛选 {len(tickers)} 只股票...")
            results = []
            for ticker in tickers:
                try:
                    stock = yf.Ticker(ticker)
                    info = stock.info
                    pe = info.get('trailingPE')
                    roe = info.get('returnOnEquity')
                    
                    # 简单的筛选逻辑
                    if pe and roe:
                        if criteria.get('min_pe', 0) <= pe <= criteria.get('max_pe', 999) and \
                           roe >= (criteria.get('min_roe', 0) / 100):
                            results.append({
                                "symbol": ticker,
                                "name": info.get('shortName'),
                                "pe": round(pe, 2),
                                "roe": round(roe * 100, 2)
                            })
                except Exception:
                    continue
            return results

        # 模拟返回
        print(f"未提供股票列表，返回模拟演示数据 (标准: {criteria})")
        return [
            {"symbol": "600519.SS", "name": "贵州茅台", "pe": 30, "roe": 25},
            {"symbol": "000858.SZ", "name": "五粮液", "pe": 25, "roe": 20},
            {"symbol": "AAPL", "name": "Apple Inc.", "pe": 28, "roe": 35}
        ]
