
def compute_rsi(series, window=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window).mean()
    avg_loss = loss.rolling(window).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def compute_srsi(rsi, window=14):
    min_rsi = rsi.rolling(window).min()
    max_rsi = rsi.rolling(window).max()
    return ((rsi - min_rsi) / (max_rsi - min_rsi)) * 100
