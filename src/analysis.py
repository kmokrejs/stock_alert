import yfinance as yf
import pandas as pd
from .indicators import compute_rsi, compute_srsi
from .logic import analyze_entry

def analyze_ticker(ticker, start_date='2024-10-01'):
    df = yf.download(ticker, start=start_date)[['Close']].copy()
    df.dropna(inplace=True)
    df.reset_index(inplace=True)
    df['Date'] = pd.to_datetime(df['Date'])

    df['RSI'] = compute_rsi(df['Close'])
    df['SRSI'] = compute_srsi(df['RSI'])
    df.dropna(subset=['RSI', 'SRSI'], inplace=True)

    latest = df.iloc[-1]
    recommendation = analyze_entry(latest['RSI'], latest['SRSI'])

    return {
        'Ticker': ticker,
        'Date': latest['Date'].date(),
        'Price': latest['Close'],
        'RSI': latest['RSI'],
        'SRSI': latest['SRSI'],
        'Recommendation': recommendation
    }
