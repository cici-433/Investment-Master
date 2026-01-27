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
                "book_value": info.get('bookValue'),
                "dividend_yield": self._get_best_dividend_yield(info)
            }
            return pe_data
        except Exception:
            pass
        return None

    def calculate_graham(self, ticker, info=None):
        """
        格雷厄姆成长股估值公式 (V = EPS * (8.5 + 2g))
        """
        try:
            if not info:
                stock = yf.Ticker(ticker)
                info = stock.info
            
            eps = info.get('trailingEps')
            if not eps:
                return {"error": "缺少 EPS 数据"}
            
            # 获取增长率，如果没有则尝试计算或使用默认保守值
            # 这里尝试使用 earningsGrowth (季度同比增长) 或 revenueGrowth
            # 更严谨应该用分析师预估，这里做简化处理
            g = 0
            if info.get('earningsGrowth'):
                g = info.get('earningsGrowth') * 100 # 转换为百分比
            elif info.get('revenueGrowth'):
                g = info.get('revenueGrowth') * 100
            
            # 限制 g 的范围，防止异常值 (例如亏损转盈导致的巨大增长率)
            # 格雷厄姆公式通常适用于 0-20% 的稳健增长
            g = max(0, min(g, 25)) 
            
            # 原始公式
            intrinsic_value = eps * (8.5 + 2 * g)
            
            # 修正公式 (考虑利率，当前AAA利率约 4.5% - 5.0%)
            # V = (EPS * (8.5 + 2g) * 4.4) / Y
            current_aaa_yield = 4.5 # 假设值
            intrinsic_value_adj = (eps * (8.5 + 2 * g) * 4.4) / current_aaa_yield
            
            return {
                "eps": eps,
                "growth_rate": round(g, 2),
                "intrinsic_value": round(intrinsic_value, 2),
                "intrinsic_value_adj": round(intrinsic_value_adj, 2),
                "formula": "V = EPS * (8.5 + 2g)"
            }
        except Exception as e:
            return {"error": f"Graham 计算出错: {e}"}

    def calculate_peg(self, ticker, info=None):
        """
        PEG 估值法 (PEG = PE / Growth)
        """
        try:
            if not info:
                stock = yf.Ticker(ticker)
                info = stock.info
                
            pe = info.get('trailingPE')
            if not pe:
                pe = info.get('forwardPE')
            
            if not pe:
                return {"error": "缺少 PE 数据"}
                
            # 获取增长率 (优先使用 pegRatio 字段如果存在，否则手动计算)
            peg = info.get('pegRatio')
            growth_rate = 0
            
            if peg:
                # 反推 implied growth rate
                # PEG = PE / g => g = PE / PEG
                growth_rate = pe / peg
            else:
                # 尝试手动获取增长率
                if info.get('earningsGrowth'):
                    growth_rate = info.get('earningsGrowth') * 100
                elif info.get('revenueGrowth'):
                    growth_rate = info.get('revenueGrowth') * 100
                
                # 避免分母为0
                if growth_rate <= 0:
                    return {"error": "增长率为负或为零，不适用 PEG", "pe": pe, "growth_rate": growth_rate}
                    
                peg = pe / growth_rate
            
            result_type = "合理"
            if peg < 0.8:
                result_type = "低估 (买入)"
            elif peg > 1.5:
                result_type = "高估 (卖出)"
                
            return {
                "pe": round(pe, 2),
                "growth_rate": round(growth_rate, 2),
                "peg": round(peg, 2),
                "result_type": result_type
            }
        except Exception as e:
            return {"error": f"PEG 计算出错: {e}"}

    def calculate_ddm(self, ticker, info=None):
        """
        股息贴现模型 (Gordon Growth Model)
        P = D1 / (r - g)
        """
        try:
            if not info:
                stock = yf.Ticker(ticker)
                info = stock.info
                
            # 1. 获取股息
            dividend_rate = info.get('dividendRate') # 年化股息金额
            if not dividend_rate:
                 # 尝试用 yield * price 计算
                 price = info.get('currentPrice') or info.get('previousClose')
                 d_yield = self._get_best_dividend_yield(info)
                 if price and d_yield:
                     dividend_rate = price * d_yield
            
            if not dividend_rate:
                return {"error": "无分红数据，不适用 DDM 模型"}
                
            # 2. 假设参数
            # r: 股权要求回报率 (Cost of Equity)，通常 8% - 12%
            # g: 股息增长率，通常 2% - 5% (保守估计)
            r = 0.09 # 9%
            g = 0.03 # 3%
            
            # 如果 g >= r，模型失效 (分母为负)
            if g >= r:
                return {"error": "增长率假设过高 (>=回报率)，模型失效"}
            
            # D1 = D0 * (1+g)
            d1 = dividend_rate * (1 + g)
            
            intrinsic_value = d1 / (r - g)
            
            return {
                "dividend_rate": round(dividend_rate, 2),
                "cost_of_equity": r,
                "growth_rate": g,
                "intrinsic_value": round(intrinsic_value, 2),
                "formula": "P = D1 / (r - g)"
            }
        except Exception as e:
            return {"error": f"DDM 计算出错: {e}"}

    def calculate_tang(self, ticker, info=None):
        """
        老唐估值法
        核心逻辑：三年后以 25 倍市盈率卖出能赚 100% (即翻倍) 的位置买入。
        买点 = (三年后净利润 * 合理PE) / 2
        如果是高杠杆企业，打七折。
        """
        try:
            if not info:
                stock = yf.Ticker(ticker)
                info = stock.info
            
            # 1. 获取当前利润 (Net Income)
            # 使用 trailingEarnings (TTM)
            net_income = info.get('netIncomeToCommon')
            if not net_income:
                # 尝试用 EPS * Shares
                eps = info.get('trailingEps')
                shares = info.get('sharesOutstanding')
                if eps and shares:
                    net_income = eps * shares
            
            if not net_income:
                 return {"error": "缺少净利润数据"}

            # 2. 预估增长率 (g)
            # 优先使用 earningsGrowth, 其次 revenueGrowth, 默认 0
            g = 0
            if info.get('earningsGrowth'):
                g = info.get('earningsGrowth')
            elif info.get('revenueGrowth'):
                g = info.get('revenueGrowth')
            
            # 限制增长率范围，避免过于激进
            g = max(0, min(g, 0.25)) # 0% - 25%

            # 3. 估算三年后净利润
            future_profit = net_income * ((1 + g) ** 3)
            
            # 4. 合理 PE (默认为 25)
            rational_pe = 25
            
            # 5. 三年后合理市值
            future_market_cap = future_profit * rational_pe
            
            # 6. 买点计算 (三年后合理市值的一半)
            buy_point_cap = future_market_cap / 2
            
            # 7. 高杠杆调整 (打七折)
            # 判断高杠杆：资产负债率 (Total Debt / Total Assets) > ? 或者 Debt/Equity > ?
            # 这里简单使用 debtToEquity > 100 (即 1:1) 作为高杠杆警戒线，或者直接查看行业
            # 更加保守的策略：如果是银行、保险、地产等，通常认为是高杠杆。
            # 这里实现一个基于 debtToEquity 的动态判断
            is_high_leverage = False
            dte = info.get('debtToEquity')
            if dte and dte > 100:
                is_high_leverage = True
                buy_point_cap = buy_point_cap * 0.7
            
            # 8. 转换为股价
            shares = info.get('sharesOutstanding')
            if not shares:
                return {"error": "缺少股本数据"}
                
            buy_price = buy_point_cap / shares
            
            # 9. 卖点计算 (当年 50 倍 PE)
            # 这里的“当年”指当前 TTM
            sell_cap = net_income * 50
            sell_price = sell_cap / shares
            
            return {
                "current_profit": net_income,
                "growth_rate": g,
                "future_profit_3y": future_profit,
                "rational_pe": rational_pe,
                "future_market_cap": future_market_cap,
                "buy_price": round(buy_price, 2),
                "sell_price": round(sell_price, 2),
                "is_high_leverage": is_high_leverage,
                "leverage_ratio": dte,
                "formula": "买点 = (3年后利润 x 25) / 2" + (" x 0.7 (高杠杆)" if is_high_leverage else "")
            }

        except Exception as e:
            return {"error": f"老唐估值法计算出错: {e}"}

    def _get_best_dividend_yield(self, info):
        """
        尝试获取最准确的股息率。
        A股数据源在 yfinance 中经常不一致，有的只有 trailingAnnualDividendRate，有的只有 dividendYield。
        策略：计算 TTM 股息率和 Forward 股息率，取两者中较大且合理的值。
        """
        try:
            price = info.get('currentPrice') or info.get('previousClose')
            if not price:
                return None
                
            # 1. 计算 TTM 股息率 (基于过去一年实际支付)
            t_rate = info.get('trailingAnnualDividendRate')
            t_yield = 0.0
            if t_rate:
                t_yield = t_rate / price
                
            # 2. 获取 Forward/Indicated 股息率 (数据源直接提供)
            d_yield_raw = info.get('dividendYield')
            d_yield = 0.0
            if d_yield_raw:
                # 处理百分比格式 (e.g. 7.92 -> 0.0792)
                if d_yield_raw > 1:
                    d_yield = d_yield_raw / 100.0
                else:
                    d_yield = d_yield_raw
            
            # 3. 决策逻辑
            # 取最大值，通常能覆盖数据缺失的情况 (例如 600036 TTM=0 但 Yield=7.9%; 002027 TTM=5.2% 但 Yield=2%)
            best_yield = max(t_yield, d_yield)
            
            return best_yield if best_yield > 0 else None
            
        except Exception:
            return None

    def _process_dividend_yield(self, val):
        # Deprecated, replaced by _get_best_dividend_yield
        if val is None:
            return None
        if val > 1:
            return val / 100.0
        return val

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
        市赚率 (PR) 估值法 - 包含三个变种公式
        1. 标准公式: PR = PE / (ROE * 100)
        2. 修正公式 (含分红): PR = (PE * N) / (ROE * 100)
        3. PB推导公式: PR = PB / (ROE * ROE * 100)
        """
        try:
            if not info:
                stock = yf.Ticker(ticker)
                info = stock.info
            
            # 1. 获取基础数据
            pe = info.get('trailingPE')
            roe = info.get('returnOnEquity') # 0.15
            pb = info.get('priceToBook')
            dpr = info.get('payoutRatio')    # 0.40
            
            if not (pe and roe):
                return {"error": "缺少必要数据 (PE/ROE)"}
            
            # ROE 必须转换为百分比数值参与计算 (例如 15% -> 15)
            roe_val = roe * 100
            
            # --- 公式 1: 标准市赚率 ---
            # PR1 = PE / ROE
            pr1 = pe / roe_val
            
            # --- 公式 2: 修正市赚率 (含分红) ---
            # 默认 N=1 
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
            
            # PR2 = N * PE / ROE
            pr2 = n * (pe / roe_val)
            
            # --- 公式 3: PB 推导市赚率 ---
            # PR3 = PB / (ROE^2 * 100)
            # 推导: 若 PR=1, 则 PE=100*ROE. 又 PB=PE*ROE, 故 PB=100*ROE^2.
            # 这里的 ROE 是小数 (0.15), 还是整数 (15)?
            # 之前的公式是 PE / (ROE_val).
            # PB = PE * ROE(小数).
            # PR = PE / ROE_val = (PB/ROE_decimal) / (ROE_decimal * 100) = PB / (ROE_decimal^2 * 100)
            # 或者 PR = PB / (ROE_val * ROE_decimal) ? 
            # 让我们代入: ROE=0.15, ROE_val=15.
            # PR = PB / (15 * 0.15) = PB / 2.25.
            # 如果 PR=1, PB=2.25. (符合 ROE=15% 时 PB=2.25 合理)
            pr3 = 0
            if pb:
                pr3 = pb / (roe_val * roe)
            
            # 4. 估值结论 (以 PR2 修正值为准)
            result_type = "合理/持有"
            main_pr = pr2
            
            if main_pr < 0.6:
                result_type = "严重低估 (买入)"
            elif main_pr > 1.0:
                result_type = "高估 (卖出)"
            
            return {
                "pe": pe,
                "roe": roe,
                "pb": pb,
                "dpr": dpr,
                "n_factor": n,
                "pr_value": round(main_pr, 3), # 保持兼容
                "pr_1": round(pr1, 3),
                "pr_2": round(pr2, 3),
                "pr_3": round(pr3, 3),
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
