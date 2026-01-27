import yfinance as yf
import random

class Valuator:
    def __init__(self):
        pass

    def get_current_price(self, ticker):
        """
        获取当前股价，如果获取失败则返回None或模拟值
        """
        try:
            stock = yf.Ticker(ticker)
            # 尝试获取实时价格，如果市场关闭可能是 previousClose
            price = stock.info.get('currentPrice') or stock.info.get('previousClose')
            if price:
                return price
        except Exception as e:
            print(f"获取 {ticker} 价格失败: {e}")
        
        return None

    def calculate_pe(self, ticker):
        """
        获取市盈率详情
        """
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            pe_data = {
                "trailing_pe": info.get('trailingPE'),
                "forward_pe": info.get('forwardPE'),
                "trailing_eps": info.get('trailingEps'),
                "forward_eps": info.get('forwardEps'),
                "sector": info.get('sector', 'Unknown'),
                "price_to_book": info.get('priceToBook'),
                "return_on_equity": info.get('returnOnEquity'),
                "book_value": info.get('bookValue')
            }
            return pe_data
        except Exception:
            pass
        return None

    def calculate_pb_roe(self, ticker, info=None):
        """
        根据 ROE-PB 锚定法计算估值
        """
        try:
            if not info:
                stock = yf.Ticker(ticker)
                info = stock.info
            
            current_pb = info.get('priceToBook')
            roe = info.get('returnOnEquity') # 小数，例如 0.15
            bps = info.get('bookValue')     # 每股净资产
            price = info.get('currentPrice') or info.get('previousClose')
            
            if not (roe and bps and price):
                return {"error": "缺少必要数据 (ROE/BPS/Price)"}
                
            # ROE 锚定法 (公式法: PB = ROE / 7)
            # 使用 7 作为保守分母因子
            roe_percent = roe * 100
            target_pb = roe_percent / 7.0
            
            fair_value = target_pb * bps
            margin = ((fair_value - price) / fair_value) * 100
            
            # 计算买入区间 (7折 - 8折)
            buy_pb_low = target_pb * 0.7
            buy_pb_high = target_pb * 0.8
            buy_price_low = buy_pb_low * bps
            buy_price_high = buy_pb_high * bps

            # 计算卖出区间 (120% - 130%)
            sell_pb_low = target_pb * 1.2
            sell_pb_high = target_pb * 1.3
            sell_price_low = sell_pb_low * bps
            sell_price_high = sell_pb_high * bps
            
            return {
                "current_roe": roe,
                "current_pb": current_pb,
                "bps": bps,
                "target_pb": round(target_pb, 2),
                "fair_value": round(fair_value, 2),
                "margin": round(margin, 2),
                "buy_range_pb": (round(buy_pb_low, 2), round(buy_pb_high, 2)),
                "buy_range_price": (round(buy_price_low, 2), round(buy_price_high, 2)),
                "sell_range_pb": (round(sell_pb_low, 2), round(sell_pb_high, 2)),
                "sell_range_price": (round(sell_price_low, 2), round(sell_price_high, 2))
            }
            
        except Exception as e:
            return {"error": f"PB 计算出错: {e}"}

    def calculate_pr(self, ticker, info=None):
        """
        市赚率 (PR) 估值法
        PR = N * PE / (ROE * 100)
        """
        try:
            if not info:
                stock = yf.Ticker(ticker)
                info = stock.info
            
            # 1. 获取基础数据
            pe = info.get('trailingPE')
            roe = info.get('returnOnEquity') # 0.15
            dpr = info.get('payoutRatio')    # 0.40
            
            if not (pe and roe):
                return {"error": "缺少必要数据 (PE/ROE)"}
            
            # ROE 必须转换为百分比数值参与计算 (例如 15% -> 15)
            # 这里的公式 PR = PE / ROE，通常 ROE 是指 15 这种整数概念，还是 0.15？
            # 根据 "低于1低估" 判断：
            # 如果 PE=15, ROE=15%(0.15).
            # 方式A: 15 / 0.15 = 100 (太大)
            # 方式B: 15 / 15 = 1.0 (合理)
            # 所以 ROE 应该取百分比的数值 (15)。
            roe_val = roe * 100
            
            # 2. 计算修正系数 N
            # 默认 N=1 (如果缺少分红数据，暂时按标准处理或保守处理？这里按 N=1 处理但提示)
            n = 1.0
            dpr_val = 0
            
            if dpr is not None:
                dpr_val = dpr
                if dpr_val >= 0.50:
                    n = 1.0
                elif dpr_val <= 0.25:
                    n = 2.0
                else:
                    # 25% < dpr < 50%
                    # n = 0.5 / dpr
                    n = 0.50 / dpr_val
            else:
                # 缺少分红数据，保守起见或者提示
                n = 1.0 # 假设
            
            # 3. 计算 PR
            # PR = N * PE / ROE
            pr = n * (pe / roe_val)
            
            # 4. 估值结论
            result_type = "合理/持有"
            if pr < 0.6:
                result_type = "严重低估 (买入)"
            elif pr > 1.0:
                result_type = "高估 (卖出)"
            
            return {
                "pe": pe,
                "roe": roe,
                "dpr": dpr,
                "n_factor": n,
                "pr_value": round(pr, 3),
                "result_type": result_type
            }
            
        except Exception as e:
            return {"error": f"PR 计算出错: {e}"}

    def calculate_dcf(self, ticker):
        """
        简化的 DCF 估值模型，返回详细计算步骤
        """
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # 尝试获取自由现金流
            fcf = info.get('freeCashflow')
            if not fcf:
                # 尝试计算 FCF = Operating Cashflow - CapEx
                ocf = info.get('operatingCashflow')
                capex = info.get('capitalExpenditures') # 注意：有时候是负数，有时候是正数，yfinance通常返回负数
                
                # yfinance API 变动较大，如果拿不到直接数据，这里做一个模拟逻辑以便展示流程
                # 仅用于演示：如果没有FCF，假设 FCF 为市值的 3% (粗略假设)
                market_cap = info.get('marketCap')
                if market_cap:
                    fcf = market_cap * 0.03
                    print(f"Warning: 无法直接获取 {ticker} 的 FCF，使用市值 3% 进行模拟演示: {fcf}")
                else:
                    return {"error": "无法获取基础财务数据 (FCF/MarketCap)"}

            # 假设参数 (实际应用中应基于历史增长率预测)
            growth_rate = 0.05
            wacc = 0.10
            terminal_growth = 0.02
            years = 5
            
            steps = []
            present_value_sum = 0
            current_fcf = fcf
            
            for i in range(1, years + 1):
                projected_fcf = current_fcf * (1 + growth_rate)
                discount_factor = 1 / ((1 + wacc) ** i)
                pv = projected_fcf * discount_factor
                
                steps.append({
                    "year": i,
                    "fcf": projected_fcf,
                    "discount_factor": discount_factor,
                    "present_value": pv
                })
                
                present_value_sum += pv
                current_fcf = projected_fcf
                
            # 终值计算
            terminal_value = current_fcf * (1 + terminal_growth) / (wacc - terminal_growth)
            terminal_pv = terminal_value / ((1 + wacc) ** years)
            
            total_enterprise_value = present_value_sum + terminal_pv
            
            # 股权价值 (简化：假设无净债务或已包含在EV调整中，这里直接用EV近似)
            # 实际应: Equity Value = Enterprise Value + Cash - Debt
            equity_value = total_enterprise_value
            
            shares = info.get('sharesOutstanding', 1)
            fair_value = equity_value / shares
            
            return {
                "parameters": {
                    "initial_fcf": fcf,
                    "growth_rate": growth_rate,
                    "wacc": wacc,
                    "terminal_growth": terminal_growth,
                    "years": years
                },
                "steps": steps,
                "terminal_value": {
                    "future_value": terminal_value,
                    "present_value": terminal_pv
                },
                "result": {
                    "sum_pv_cash_flows": present_value_sum,
                    "total_equity_value": equity_value,
                    "shares_outstanding": shares,
                    "fair_value_per_share": round(fair_value, 2)
                }
            }
            
        except Exception as e:
            return {"error": f"计算过程出错: {e}"}
