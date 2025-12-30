import os
from datetime import date, datetime
import pandas as pd
import ta
import yfinance as yf

from email_sender import send_email


def fetch_data(ticker: str, start_date: str, end_date: str) -> pd.DataFrame | None:
    """Fetch historical stock data using yfinance"""
    try:
        df = yf.download(ticker, start=start_date, end=end_date, auto_adjust=True, progress=False)
        if df.empty:
            return None

        df = df[['High', 'Low', 'Close']].copy()
        df.reset_index(inplace=True)
        df.columns = ['Date', 'High', 'Low', 'Close']
        df['Date'] = pd.to_datetime(df['Date'])
        df.set_index('Date', inplace=True)
        return df
    except Exception as e:
        print(f"❌ Failed to fetch data for {ticker}: {e}")
        return None

def check_near_buy_signal(df: pd.DataFrame, rsi_threshold=35, srsi_threshold=30):
    df = df.dropna()
    if df.empty:
        return False, {}

    latest = df.iloc[-1]
    close = float(latest['Close'])
    rsi = float(latest['RSI'])
    srsi = float(latest['SRSI'])
    ma20 = float(latest['MA20'])
    atr = float(latest['ATR'])
    atr_pct = (atr / close) * 100 if close else None

    # "Near buy" (not as strict as BUY)
    if rsi < rsi_threshold and srsi < srsi_threshold and close < ma20:
        return True, {
            'date': latest.name,
            'close': close,
            'rsi': rsi,
            'srsi': srsi,
            'ma20': ma20,
            'atr': atr,
            'atr_pct': atr_pct,
        }
    return False, {}


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None
    try:
        df = df.copy()
        df['RSI'] = ta.momentum.RSIIndicator(df['Close'], window=14).rsi()

        df['SRSI'] = ta.momentum.StochRSIIndicator(df['Close']).stochrsi_k() * 100

        df['MA20'] = ta.trend.SMAIndicator(df['Close'], window=20).sma_indicator()

        df['ATR'] = ta.volatility.AverageTrueRange(
            high=df['High'],
            low=df['Low'],
            close=df['Close'],
            window=14
        ).average_true_range()

        return df
    except Exception as e:
        print(f"❌ Failed to compute indicators: {e}")
        return None


def check_buy_signal(df: pd.DataFrame):
    df = df.dropna()
    if df.empty:
        return False, {}

    latest = df.iloc[-1]
    close = float(latest['Close'])
    rsi = float(latest['RSI'])
    srsi = float(latest['SRSI'])
    ma20 = float(latest['MA20'])
    atr = float(latest['ATR'])
    atr_pct = (atr / close) * 100 if close else None

    if rsi < 30 and srsi < 30 and close < ma20:
        return True, {
            'date': latest.name,
            'close': close,
            'entry_rsi': rsi,
            'srsi': srsi,
            'ma20': ma20,
            'atr': atr,
            'atr_pct': atr_pct,
        }
    return False, {}

def get_spy_trend_status(end_date: str):
    """
    Returns (is_bullish, spy_close, spy_ma200).
    Bullish if SPY Close > MA200.
    """
    # Need enough history for MA200
    start_date = (pd.Timestamp(end_date) - pd.Timedelta(days=400)).strftime('%Y-%m-%d')

    spy_df = fetch_data("SPY", start_date, end_date)
    if spy_df is None or spy_df.empty:
        return None, None, None

    spy_df = spy_df.copy()
    spy_df['MA200'] = spy_df['Close'].rolling(200).mean()
    spy_df = spy_df.dropna()

    if spy_df.empty:
        return None, None, None

    latest = spy_df.iloc[-1]
    spy_close = float(latest['Close'])
    spy_ma200 = float(latest['MA200'])
    return spy_close > spy_ma200, spy_close, spy_ma200


def send_signals_email(buy_signals: list[tuple[str, dict]], near_buy_signals: list[tuple[str, dict]], spy_status):
    if not buy_signals and not near_buy_signals:
        print("📭 No signals to email.")
        return

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    subject = f"📈 Stock Signals — {timestamp}"

    is_bullish, spy_close, spy_ma200 = spy_status
    if is_bullish is None:
        spy_line = "SPY trend: (could not fetch)"
    else:
        icon = "✅" if is_bullish else "⚠️"
        regime = "Bullish" if is_bullish else "Bearish"
        spy_line = f"{icon} SPY trend: <b>{regime}</b> (Close: {spy_close:.2f} vs MA200: {spy_ma200:.2f})"

    def to_df(signals, signal_type: str):
        rows = []
        for ticker, info in signals:
            price = info['close']
            ma20 = info['ma20']
            rows.append({
                "Ticker": ticker,
                "Price": round(price, 2),
                "RSI": round(info.get("entry_rsi", info.get("rsi")), 2),
                "SRSI": round(info["srsi"], 2),
                "MA20": round(ma20, 2),
                "ATR(14)": round(info["atr"], 2),
                "ATR%": round(info["atr_pct"], 2),
                "Price vs MA20 (%)": round((price - ma20) / ma20 * 100, 2),
                "Signal": signal_type,
            })
        return pd.DataFrame(rows)

    sections = []

    if buy_signals:
        buy_df = to_df(buy_signals, "🔥 Strong Buy")
        buy_html = buy_df.to_html(index=False, justify="center", border=1, escape=False)
        sections.append(f"<h3>💸 Trade Opportunities</h3>{buy_html}")
    else:
        sections.append("<h3>💸 Trade Opportunities</h3><p>No buy signals today.</p>")

    if near_buy_signals:
        near_df = to_df(near_buy_signals, "👀 Close to Buy")
        near_html = near_df.to_html(index=False, justify="center", border=1, escape=False)
        sections.append(f"<h3>👀 Close to Buy (RSI < 35 & SRSI < 30)</h3>{near_html}")
    else:
        sections.append("<h3>👀 Close to Buy (RSI < 35 & SRSI < 30)</h3><p>No near-buy candidates today.</p>")

    html_body = f"""
    <html>
    <head>
        <style>
            table {{
                border-collapse: collapse;
                width: 100%;
            }}
            th, td {{
                border: 1px solid #ddd;
                padding: 8px;
                text-align: center;
            }}
            th {{
                background-color: #f2f2f2;
            }}
            h2, h3 {{
                font-family: Arial, sans-serif;
            }}
            p {{
                font-family: Arial, sans-serif;
            }}
        </style>
    </head>
    <body>
        <h2>📈 Daily Stock Signals — {timestamp}</h2>
        <p>{spy_line}</p>
        {"<br>".join(sections)}
    </body>
    </html>
    """
    print(html_body)
    # send_email(
    #     subject=subject,
    #     body=html_body,
    #     recipient_email=os.environ["EMAIL_RECIPIENT"],
    #     is_html=True
    # )

    print("✅ Signal email sent.")



if __name__ == "__main__":
    tickers = [
        'AAPL', 'MSFT', 'NVDA', 'AMD', 'GOOGL', 'META',
        'JPM', 'GS', 'BAC', 'JNJ', 'PFE', 'UNH', 'LLY',
        'AMZN', 'DIS', 'HD', 'COST', 'DE', 'GE', 'XOM', 'CVX',
        'DAL', 'EXPE', 'SPY', 'QQQ', 'XLK', 'XLF', 'SHOP', 'NET', 'ZS', 'SCHW', 'PYPL',
        'MRK', 'BMY', 'ABBV', 'TMO', 'IBB',
        'TGT', 'WMT', 'ULTA', 'MCD',
        'NOC', 'RTX', 'LMT', 'FCX',
        'IWM', 'XLV', 'XLE', 'ARKK',
    ]

    start_date = "2025-01-01"
    end_date = date.today().isoformat()

    buy_signals: list[tuple[str, dict]] = []
    near_buy_signals: list[tuple[str, dict]] = []

    print("\n🔍 Analyzing tickers for signals...")
    for ticker in tickers:
        df = fetch_data(ticker, start_date, end_date)
        if df is None:
            continue

        df = compute_indicators(df)
        if df is None:
            continue

        buy_signal, buy_info = check_buy_signal(df)
        if buy_signal:
            buy_signals.append((ticker, buy_info))
            continue  

        near_signal, near_info = check_near_buy_signal(df, rsi_threshold=35, srsi_threshold=30)
        if near_signal:
            near_buy_signals.append((ticker, near_info))

    spy_status = get_spy_trend_status(end_date)
    send_signals_email(buy_signals, near_buy_signals, spy_status)
