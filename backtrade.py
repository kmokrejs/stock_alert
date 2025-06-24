import backtrader as bt
import yfinance as yf
import pandas as pd

class FractionalDollarSizer(bt.Sizer):
    params = (('amount', 1000),)

    def _getsizing(self, comminfo, cash, data, isbuy):
        if isbuy:
            price = data.close[0]
            size = self.p.amount / price  # Float division (fractional shares)
            return size  # ⚠️ Returns a float
        else:
            return self.broker.getposition(data).size




class StochasticRSI(bt.Indicator):
    lines = ('stochrsi',)
    params = (('rsi_period', 14), ('stoch_period', 14))

    def __init__(self):
        rsi = bt.indicators.RSI(self.data, period=self.p.rsi_period)
        min_rsi = bt.indicators.Lowest(rsi, period=self.p.stoch_period)
        max_rsi = bt.indicators.Highest(rsi, period=self.p.stoch_period)
        self.lines.stochrsi = (rsi - min_rsi) / (max_rsi - min_rsi + 1e-9) * 100



class RSISRSIStrategy(bt.Strategy):

    def __init__(self):
        self.rsi = bt.indicators.RSI(self.data.close, period=14)
        self.srsi = StochasticRSI(self.data, rsi_period=14, stoch_period=14)
        self.ma20 = bt.indicators.SimpleMovingAverage(self.data.close, period=20)
        self.ma50 = bt.indicators.SimpleMovingAverage(self.data.close, period=50)

        self.order = None
        self.buy_price = None
        self.trades = []
        self.bar_executed = 0
        self.hold_days = 10
        self.srsi_extreme_bars = 0


    def next(self):
        if self.order:
            return

        if not self.position:
            if self.rsi[0] < 30 and self.srsi[0] < 30 and self.data.close[0] < self.ma20[0]:
                self.buy_price = self.data.close[0]
                self.buy_rsi = self.rsi[0]
                self.bar_executed = len(self)
                self.order = self.buy()

        else:
            hold_time = len(self) - self.bar_executed
            rsi_jump = self.rsi[0] - self.buy_rsi
            price = self.data.close[0]
            price_vs_ma20 = (price - self.ma20[0]) / self.ma20[0] * 100
            price_vs_ma50 = (price - self.ma50[0]) / self.ma50[0] * 100

            stop_loss_pct = 0.20
            take_profit_pct = 0.07

            stop_loss_triggered = price < self.buy_price * (1 - stop_loss_pct)
            take_profit_triggered = price > self.buy_price * (1 + take_profit_pct)

            if self.srsi[0] > 80:
                self.srsi_extreme_bars += 1
            else:
                self.srsi_extreme_bars = 0 

            sell_signal = (
                self.rsi[0] > 70 or
                rsi_jump > 15 or
                price_vs_ma20 > 5 or
                price_vs_ma50 > 5
            )

            # Determine reason
            if stop_loss_triggered:
                exit_reason = "Stop Loss"
            elif take_profit_triggered:
                exit_reason = "Take Profit"
            elif self.rsi[0] > 70:
                exit_reason = "RSI Overbought"
            elif rsi_jump > 15:
                exit_reason = "RSI Jump"
            elif price_vs_ma20 > 5:
                exit_reason = "Price > MA20"
            elif price_vs_ma50 > 5:
                exit_reason = "Price > MA50"
            else:
                exit_reason = "Unknown"

            if sell_signal or stop_loss_triggered or take_profit_triggered:
                sell_price = price
                pnl = sell_price - self.buy_price
                self.trades.append({
                    'Entry Date': self.data.datetime.date(-hold_time),
                    'Exit Date': self.data.datetime.date(0),
                    'Buy Price': self.buy_price,
                    'Sell Price': sell_price,
                    'PnL': pnl,
                    'Stopped Out': stop_loss_triggered,
                    'Profit Taken': take_profit_triggered,
                    'Exit Reason': exit_reason

                })
                self.order = self.sell()
                self.srsi_extreme_bars = 0


    def notify_order(self, order):
        if order.status in [order.Completed, order.Canceled, order.Margin]:
            self.order = None

    def stop(self):
        if self.trades:
            df = pd.DataFrame(self.trades)
            df['Win'] = df['PnL'] > 0
      


if __name__ == '__main__':
    tickers = [
        'AAPL', 'MSFT', 'NVDA', 'AMD', 'GOOGL', 'META',
        'JPM', 'GS', 'BAC', 'JNJ', 'PFE', 'UNH', 'LLY',
        'AMZN', 'DIS', 'HD', 'COST', 'DE', 'GE', 'XOM', 'CVX',
        'DAL', 'EXPE', 'SPY', 'QQQ', 'XLK', 'XLF', 'SHOP', 'NET', 'ZS', 'SCHW', 'PYPL',
        'MRK', 'BMY', 'ABBV', 'TMO', 'IBB',
        'TGT', 'WMT', 'ULTA', 'MCD',
        'NOC', 'RTX', 'LMT', 'FCX',
        'IWM', 'XLV', 'XLE', 'ARKK',
        #'SQ'
    ]

    finalPnL = 0
    all_trades = []
    open_positions = []

    for ticker in tickers:
        df = yf.download(ticker, start='2025-01-01', end='2025-06-24', auto_adjust=True)

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.index.name = 'datetime'  

        if df.empty:
            print(f"⚠️ No data for {ticker}, skipping.")
            continue

        data = bt.feeds.PandasData(dataname=df, name=ticker)

        cerebro = bt.Cerebro()
        cerebro.addstrategy(RSISRSIStrategy)
        cerebro.adddata(data)
        cerebro.addsizer(FractionalDollarSizer, amount=100)
        cerebro.broker.set_coc(True)
        cerebro.broker.set_cash(10000)
        
        strategies = cerebro.run()
        strategy = strategies[0]

        pnl = sum([t['PnL'] for t in strategy.trades])
        finalPnL += pnl

        position = cerebro.broker.getposition(data)
        if position.size > 0:
            open_positions.append({
                'Ticker': ticker,
                'Size': position.size,
                'Price': position.price,
                'Value': position.size * position.price
            })

        if strategy.trades:
            df = pd.DataFrame(strategy.trades)
            df['Ticker'] = ticker
            all_trades.append(df)

    print(f"\n💰 Final Total PnL across all tickers: {finalPnL:.2f}")

    print("\n📈 Open positions summary:")
    print(open_positions)

    if all_trades:
        final_df = pd.concat(all_trades, ignore_index=True)
        final_df.to_csv("backtest_results.csv", index=False)
