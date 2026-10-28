import asyncio
import ccxt.pro as ccxt
import requests
import pytz
from datetime import datetime

# --- НАСТРОЙКИ ТЕЛЕГРАМ ---
TELEGRAM_TOKEN = "ВАШ_ТОКЕН_БОТА"
TELEGRAM_CHAT_ID = "ВАШ_ID_АККАУНТА"

# --- НАСТРОЙКИ СКАНИРОВАНИЯ ---
TOP_N_COINS = 300
TIMEFRAMES = ['1h', '15m', '5m']

# Инициализируем биржу с поддержкой асинхронности
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})

def send_telegram_alert(text):
    """Синхронная отправка сообщения в Telegram"""
    url = f"https://telegram.org{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Ошибка отправки уведомления: {e}")

async def get_top_300_volumes():
    """Получение топ-300 фьючерсных монет по 24ч объему торгов"""
    try:
        await exchange.load_markets()
        tickers = await exchange.fetch_tickers()
        # Фильтруем только бессрочные фьючерсы к USDT
        futures = [t for t in tickers.values() if t['symbol'].endswith('/USDT:USDT') or t['symbol'].endswith('USDT')]
        # Сортируем по объему
        sorted_futures = sorted(futures, key=lambda x: x.get('quoteVolume', 0) or 0, reverse=True)
        top_symbols = [f['symbol'] for f in sorted_futures[:TOP_N_COINS]]
        return top_symbols
    except Exception as e:
        print(f"Ошибка получения топ монет: {e}")
        return []

def detect_sweep(candles):
    """Логика 1H: Поиск свипа ликвидности последних 20 свечей"""
    if len(candles) < 21:
        return False, None
    
    current_candle = candles[-2] # Последняя полностью закрытая свеча
    previous_candles = candles[-21:-2] # Предыдущие 20 свечей
    
    highest_prev = max(c[2] for c in previous_candles) # Самый высокий High
    lowest_prev = min(c[3] for c in previous_candles)  # Самый низкий Low
    
    # Бычий свип (цена уколола лоу тенью, но закрылась выше)
    if current_candle[3] < lowest_prev and current_candle[4] > lowest_prev:
        return 'BULLISH_SWEEP', lowest_prev
        
    # Медвежий свип (цена уколола хай тенью, но закрылась ниже)
    if current_candle[2] > highest_prev and current_candle[4] < highest_prev:
        return 'BEARISH_SWEEP', highest_prev
        
    return False, None

def detect_choch_and_fvg(candles):
    """Логика 15M: Поиск слома структуры (CHoCH) и свежего имбаланса (FVG)"""
    if len(candles) < 5:
        return False, None
        
    c1, c2, c3 = candles[-4], candles[-3], candles[-2]
    
    # Ищем Бычий FVG (Разрыв между High 1-й свечи и Low 3-й)
    if c3[3] > c1[2]:
        # Упрощенный CHoCH: Закрытие импульсной свечи выше хая первой
        if c2[4] > c1[2]:
            return 'BULLISH_SIGNAL', (c1[2], c3[3])
            
    # Ищем Медвежий FVG (Разрыв между Low 1-й свечи и High 3-й)
    if c3[2] < c1[3]:
        if c2[4] < c1[3]:
            return 'BEARISH_SIGNAL', (c3[2], c1[3])
            
    return False, None

async def scan_symbol(symbol):
    """Асинхронный анализ конкретной монеты по трем таймфреймам"""
    try:
        # Скачиваем свечи параллельно для экономии времени
        tasks = [
            exchange.fetch_ohlcv(symbol, '1h', limit=30),
            exchange.fetch_ohlcv(symbol, '15m', limit=15),
            exchange.fetch_ohlcv(symbol, '5m', limit=15)
        ]
        candles_1h, candles_15m, candles_5m = await asyncio.gather(*tasks)
        
        # Шаг 1: Ищем глобальный контекст на 1H (Свип)
        sweep_type, level = detect_sweep(candles_1h)
        if not sweep_type:
            return
            
        # Шаг 2: Ищем локальное подтверждение на 15M (Слом + FVG)
        signal_type, zone = detect_choch_and_fvg(candles_15m)
        if not signal_type:
            return
            
        # Шаг 3: Синхронизация направления (Бычий свип + Бычий слом ИЛИ Медвежий свип + Медвежий слом)
        if sweep_type == 'BULLISH_SWEEP' and signal_type == 'BULLISH_SIGNAL':
            # Локальный триггер на 5М (Ретест зоны или паттерн поглощения на 5М)
            trigger_price = candles_5m[-1][4]
            
            msg = (
                f"🔥 **СТРАТЕГИЯ А+ (Smart Money)**\n"
                f"🪙 Монета: `{symbol}`\n\n"
                f"🟩 **КОНТЕКСТ (1H):** Бычий Свип уровня {level:.4f}\n"
                f"⚡ **ПОДТВЕРЖДЕНИЕ (15M):** Слом структуры + FVG\n"
                f"🎯 **ВХОД (5M):** Ищите лонг на ретесте зоны `{zone[0]:.4f} - {zone[1]:.4f}`\n"
                f"💵 Текущая цена: `{trigger_price}`"
            )
            print(f"[!] СИГНАЛ ОТПРАВЛЕН: {symbol} LОNG")
            send_telegram_alert(msg)
            
        elif sweep_type == 'BEARISH_SWEEP' and signal_type == 'BEARISH_SIGNAL':
            trigger_price = candles_5m[-1][4]
            
            msg = (
                f"🔥 **СТРАТЕГИЯ А+ (Smart Money)**\n"
                f"🪙 Монета: `{symbol}`\n\n"
                f"🟥 **КОНТЕКСТ (1H):** Медвежий Свип уровня {level:.4f}\n"
                f"⚡ **ПОДТВЕРЖДЕНИЕ (15M):** Слом структуры + FVG\n"
                f"🎯 **ВХОД (5M):** Ищите шорт на ретесте зоны `{zone[0]:.4f} - {zone[1]:.4f}`\n"
                f"💵 Текущая цена: `{trigger_price}`"
            )
            print(f"[!] СИГНАЛ ОТПРАВЛЕН: {symbol} SHORT")
            send_telegram_alert(msg)

    except Exception as e:
        # Игнорируем временные ошибки сети биржи, чтобы не спамить в консоль
        pass

async def main():
    print("Получение списка ТОП-300 фьючерсных монет по объемам...")
    symbols = await get_top_300_volumes()
    print(f"Список сформирован. Запущено постоянное сканирование {len(symbols)} активов.")
    send_telegram_alert("🚀 *Бот-сканер Smart Money (Модель А+ для Топ-300 монет) успешно запущен!*")
    
    while True:
        start_time = time.time()
        
        # Сканируем монеты пачками по 15 штук параллельно, чтобы биржа не банила за Rate Limit
        chunk_size = 15
        for i in range(0, len(symbols), chunk_size):
            chunk = symbols[i:i+chunk_size]
            tasks = [scan_symbol(sym) for sym in chunk]
            await asyncio.gather(*tasks)
            await asyncio.sleep(0.5) # Пауза между пачками запросов
            
        execution_time = time.time() - start_time
        print(f"Круг сканирования топ-300 монет завершен за {execution_time:.2f} сек. Перезапуск...")
        
        # Обновляем список ТОП-300 раз в 3 часа, чтобы подтягивать новые волатильные монеты
        if datetime.now().hour % 3 == 0 and datetime.now().minute == 0:
            symbols = await get_top_300_volumes()

        await asyncio.sleep(10) # Общая пауза перед следующим полным кругом сканирования

if __name__ == "__main__":
    import time
    asyncio.run(main())
