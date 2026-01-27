# Investment Master (投资大师)

这是一个辅助投资的工具集，旨在帮助用户进行选股、估值以及行业和公司分析。它利用 `yfinance` 获取实时市场数据。

## 功能

- **选股助手**: 
  - 支持对指定股票列表进行筛选（基于 PE 和 ROE）。
  - 若未提供列表，提供模拟数据演示。
- **估值工具**: 
  - 获取实时股价和市盈率 (PE)。
  - 提供简化的 DCF (现金流折现) 估值模型参考。
- **分析报告**: 
  - 自动获取公司基本信息、行业分类和业务简介。
  - 生成标准化的分析报告框架。

## 安装

需要 Python 3.8+。

1. 创建虚拟环境 (可选但推荐):
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Mac/Linux
   # venv\Scripts\activate   # Windows
   ```

2. 安装依赖:
   ```bash
   pip install -r requirements.txt
   ```

## 使用

运行主程序：

```bash
python main.py
```

按提示输入操作：
- **选股**: 输入股票代码列表（如 `AAPL, MSFT, GOOG`）进行筛选。
- **估值**: 输入单个股票代码（如 `NVDA`）查看估值。
- **分析**: 输入代码获取公司简报。
