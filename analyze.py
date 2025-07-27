import yfinance as yf
import pandas as pd
from email_sender import send_email
from dotenv import load_dotenv
import numpy as np
from datetime import datetime
import os
import json

RSI_STATE_FILE = "rsi_state.json"
RSI_BUY_FILE = "rsi_buy_signals.json"

load_dotenv()


def compute_rsi(series, window=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1/window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/window, adjust=False).mean()

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def compute_srsi(rsi, window=14):
    min_rsi = rsi.rolling(window).min()
    max_rsi = rsi.rolling(window).max()
    range_rsi = max_rsi - min_rsi
    srsi = (rsi - min_rsi) / range_rsi.replace(0, pd.NA)
    return srsi * 100

def analyze_entry(rsi, srsi, price_vs_ma20, price_vs_ma50, pe_ratio, html_format=False):
    notes = []
    base_signal = "Hold"

    if rsi < 30 and srsi < 30 and price_vs_ma20 < 0:
        base_signal = "🔥 Strong Buy"
    elif rsi < 35 and srsi < 40 and price_vs_ma20 < 0:
        base_signal = "✅ Buy"
    elif rsi > 70 or srsi > 80:
        base_signal = "⚠️ Overbought — Consider Selling"
    elif 35 <= rsi <= 50:
        base_signal = "🤔 Watch (Neutral)"

    if price_vs_ma20 < -5 or price_vs_ma50 < -5:
        notes.append("📉 Price below MA — possible undervaluation")
    if price_vs_ma20 > 5 or price_vs_ma50 > 5:
        notes.append("📈 Price above MA — watch for overbought")

    if pe_ratio and pe_ratio < 15:
        notes.append("💰 Low P/E — undervalued?")
    elif pe_ratio and pe_ratio > 30:
        notes.append("🧨 High P/E — priced for perfection")

    # Combine
    if notes:
        separator = "<br>" if html_format else "\n"
        return f"{base_signal}{separator}" + separator.join(notes)
    else:
        return base_signal
    
def analyze_exit(rsi, price_vs_ma20, price_vs_ma50, previous_rsi=None):
    if previous_rsi is not None and (rsi - previous_rsi) > 42:
        return "🔻 Sell — RSI Jump > 42"
    if rsi > 70:
        return "🔻 Sell — RSI Overbought"
    if price_vs_ma20 > 12:
        return "🔻 Sell — Price above MA20"
    if price_vs_ma50 > 10:
        return "🔻 Sell — Price above MA50"
    return None
    
def log_trade_opportunity(data, filename="trade_log.csv"):
    log_cols = [
        'Date', 'Ticker', 'Price', 'RSI', 'SRSI',
        'MA20', 'MA50',
        'Price_vs_MA20(%)', 'Price_vs_MA50(%)',
        'PE_Ratio', 'Recommendation', 'Target1', 'Target2', 'StopLoss'
    ]

    entry = {
        **data,
        'Target1': round(data['MA20'], 2),
        'Target2': round(data['MA50'], 2),
        'StopLoss': round(data['Price'] * 0.975, 2)
    }

    df = pd.DataFrame([entry], columns=log_cols)

    if os.path.exists(filename):
        df.to_csv(filename, mode='a', index=False, header=False)
    else:
        df.to_csv(filename, mode='w', index=False, header=True)



def analyze_ticker(ticker):
    start_date = (pd.Timestamp.today() - pd.Timedelta(days=90)).strftime('%Y-%m-%d')
    end_date = pd.Timestamp.today().strftime('%Y-%m-%d')
    
    df = yf.download(ticker, start=start_date, end=end_date)[['Close']].copy()
    df.dropna(inplace=True)
    df.reset_index(inplace=True)
    df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
    df['Date'] = pd.to_datetime(df['Date'])

    df['RSI'] = compute_rsi(df['Close'])
    df['SRSI'] = compute_srsi(df['RSI'])
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA50'] = df['Close'].rolling(window=50).mean()
    df.dropna(subset=['RSI', 'SRSI', 'MA20', 'MA50'], inplace=True)

    latest = df.iloc[-1]

    try:
        info = yf.Ticker(ticker).info
        pe_ratio = info.get('trailingPE', None)
    except Exception:
        pe_ratio = None

    try:
        current_price = yf.Ticker(ticker).fast_info['last_price']
    except Exception:
        current_price = latest['Close']  

    recommendation = analyze_entry(
        latest['RSI'],
        latest['SRSI'],
        (current_price - latest['MA20']) / latest['MA20'] * 100,
        (current_price - latest['MA50']) / latest['MA50'] * 100,
        pe_ratio,
        html_format=True
    )

    previous_rsi = active_positions.get(ticker, None)

    exit_signal = analyze_exit(
        latest['RSI'],
        (current_price - latest['MA20']) / latest['MA20'] * 100,
        (current_price - latest['MA50']) / latest['MA50'] * 100,
        previous_rsi
    )

    return {
        'Ticker': ticker,
        'Date': datetime.now().strftime("%Y-%m-%d %H:%M"),
        'Price': current_price,
        'RSI': latest['RSI'],
        'SRSI': latest['SRSI'],
        'MA20': latest['MA20'],
        'MA50': latest['MA50'],
        'Price_vs_MA20(%)': (current_price - latest['MA20']) / latest['MA20'] * 100,
        'Price_vs_MA50(%)': (current_price - latest['MA50']) / latest['MA50'] * 100,
        'PE_Ratio': pe_ratio,
        'Recommendation': recommendation,
        'Sell_Signal': exit_signal

    }

def get_open_tickers(filename="positions.csv"):
    if not os.path.exists(filename):
        return []

    df = pd.read_csv(filename)
    open_tickers = df[df["status"] == "open"]["ticker"].unique().tolist()
    return open_tickers



# === Run analysis on desired tickers ===

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
        #'SQ'
    ]
    watchlist = get_open_tickers()
    already_in_positions = set(watchlist)

    results = []
    buy_opportunities = []

    if os.path.exists(RSI_STATE_FILE):
        with open(RSI_STATE_FILE, 'r') as f:
            active_positions = json.load(f)
    else:
        active_positions = {}

    if os.path.exists(RSI_BUY_FILE):
        with open(RSI_BUY_FILE, 'r') as f:
            rsi_at_buy = json.load(f)
    else:
        rsi_at_buy = {}
    
    active_positions = {k: float(v) for k, v in active_positions.items()}
    rsi_at_buy = {k: float(v) for k, v in rsi_at_buy.items()}



    TAKE_PROFIT_PCT = 0.20
    STOP_LOSS_PCT = 0.20

    for ticker in tickers:
        if ticker  in already_in_positions:
            continue

        try:
            result = analyze_ticker(ticker)
            if result:
                results.append(result)

            if result['Recommendation'].startswith("🔥") or result['Recommendation'].startswith("✅"):
                trade_result = result.copy()
                trade_result['Target1'] = round(result['Price'] * (1 + TAKE_PROFIT_PCT), 2)
                trade_result['StopLoss'] = round(result['Price'] * (1 - STOP_LOSS_PCT), 2)


                buy_opportunities.append(trade_result) 
                log_trade_opportunity(trade_result)    
                active_positions[ticker] = result['RSI']
                if ticker not in rsi_at_buy:
                    rsi_at_buy[ticker] = result['RSI']


        except Exception as e:
            print(f"❌ Error analyzing {ticker}: {e}")

    with open(RSI_STATE_FILE, 'w') as f:
        json.dump(active_positions, f, indent=2)

    with open(RSI_BUY_FILE, 'w') as f:
        json.dump(rsi_at_buy, f, indent=2)
    
    watchlist_results = [r for r in results if r['Ticker'] in watchlist]
    if watchlist_results:
        watchlist_df = pd.DataFrame(watchlist_results)
        watchlist_df['RSI_at_Buy'] = watchlist_df['Ticker'].apply(lambda x: rsi_at_buy.get(x, np.nan))
        watchlist_df['RSI_Jump'] = watchlist_df['RSI'] - watchlist_df['RSI_at_Buy']
        watchlist_df['RSI_Jump'] = watchlist_df['RSI_Jump'].round(2)
        watchlist_html = watchlist_df[['Ticker', 'Price', 'RSI', 'RSI_at_Buy', 'RSI_Jump', 'SRSI', 'PE_Ratio', 'Recommendation', 'Sell_Signal']].to_html(index=False, justify='center', border=1, escape=False)
        watchlist_section = f"<h3>🔍 Watchlist</h3>{watchlist_html}"
    else:
        watchlist_section = "<p>No watchlist data available.</p>"

    if results:
        df = pd.DataFrame(results)

        summary = "\n".join([
            f"{r['Ticker']}: {r['Recommendation']} | RSI: {r['RSI']:.2f}, SRSI: {r['SRSI']:.2f}"
            for r in results
        ])

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        if buy_opportunities:
            trades_df = pd.DataFrame(buy_opportunities)
            trades_html = trades_df[['Ticker', 'Price', 'RSI', 'SRSI', 'PE_Ratio', 'Recommendation', 'Target1', 'StopLoss']].to_html(index=False, justify='center', border=1, escape=False)
            trades_section = f"<h3>💸 Trade Opportunities</h3>{trades_html}"
        else:
            trades_section = "<p>No trade opportunities today.</p>"


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
            </style>
        </head>
        <body>
            <h2>📈 Daily Stock Analysis — {timestamp}</h2>
            {watchlist_section}
            <br>
            {trades_section}
        </body>
        </html>
        """
        send_email(
            subject = f"📊 Daily Stock Report — {timestamp}",
            body=html_body,
            recipient_email=os.environ["EMAIL_RECIPIENT"],
            is_html=True
        )
        print("✅ Email sent.")
    else:
        print("❌ No analysis results to send.")
