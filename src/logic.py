def analyze_entry(rsi, srsi):
    if rsi < 30 and srsi < 20:
        return "🔥 Strong Buy"
    elif rsi < 35 and srsi < 30:
        return "✅ Buy"
    elif 35 <= rsi <= 50 and srsi < 50:
        return "🤔 Watch (Neutral)"
    elif rsi > 70 or srsi > 80:
        return "⚠️ Overbought — Consider Selling"
    else:
        return "Hold"
