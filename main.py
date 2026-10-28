import telebot
import requests
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# Данные для подключения
API_TOKEN = '9092035955:AAGgezhvmZtyOY-2mpGntUQ4ReWh4Cvs8BQ'
FIXED_RISK = 5.0  # Риск $5

bot = telebot.TeleBot(API_TOKEN)
subscribed_chats = set()
user_data = {}

# Хранилища для уникальности триггеров
last_triggered = {
    '5': {},
    '15': {},
    '60': {}
}

class HealthCheckServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"All-time Scan Engine Active")

def run_health_server():
    import os
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckServer)
    print(f"🌍 Сервер контроля запущен на порту {port}...")
    server.serve_forever()

def get_active_market_symbols():
    try:
        url = "https://bybit.com"
        resp = requests.get(url, timeout=10).json()
        if resp.get('retCode') == 0 and 'result' in resp and 'list' in resp['result']:
            return [t['symbol'] for t in resp['result']['list'] if t['symbol'].endswith('USDT') and 'DELE' not in t['symbol']]
    except Exception as e:
        print(f"Ошибка получения списка рынка: {e}")
    return []

def check_timeframe_signals(tf_interval, label):
    print(f"📡 Запущен сканер таймфрейма {label}...")
    
    while True:
        try:
            symbols = get_active_market_symbols()
            if not symbols:
                time.sleep(15)
                continue
                
            for symbol in symbols:
                try:
                    url = f"https://bybit.com{symbol}&interval={tf_interval}&limit=3"
                    k_resp = requests.get(url, timeout=5).json()
                    
                    if k_resp.get('retCode') != 0 or not k_resp.get('result') or not k_resp['result'].get('list'):
                        time.sleep(0.1)
                        continue
                        
                    klines = k_resp['result']['list']
                    if len(klines) < 3:
                        time.sleep(0.1)
                        continue

                    # Правильный разбор индексов Bybit свечей (от новых к старым)
                    current_candle = klines[0]
                    prev_candle = klines[1]
                    older_candle = klines[2]

                    current_ts = int(current_candle[0])
                    
                    p_high = float(prev_candle[2])
                    p_low = float(prev_candle[3])
                    p_close = float(prev_candle[4])
                    
                    o_high = float(older_candle[2])
                    o_low = float(older_candle[3])

                    if symbol not in last_triggered[tf_interval]:
                        last_triggered[tf_interval][symbol] = 0

                    if current_ts <= last_triggered[tf_interval][symbol]:
                        time.sleep(0.1)
                        continue

                    signal_type = None
                    entry_price = 0.0
                    stop_loss = 0.0

                    # Логика ложного пробоя
                    if p_high > o_high and p_close < o_high:
                        signal_type = f"ШОРТ 🔴 (Свип хая на {label})"
                        entry_price = p_close
                        stop_loss = p_high + (p_high * 0.0004)

                    elif p_low < o_low and p_close > o_low:
                        signal_type = f"ЛОНГ 🟢 (Свип лоя на {label})"
                        entry_price = p_close
                        stop_loss = p_low - (p_low * 0.0004)

                    if signal_type and subscribed_chats:
                        last_triggered[tf_interval][symbol] = current_ts
                        stop_dist = abs(entry_price - stop_loss)

                        if stop_dist > 0:
                            pos_size = FIXED_RISK / stop_dist
                            total_val = pos_size * entry_price
                            tp = entry_price + (stop_dist * 2) if "ЛОНГ" in signal_type else entry_price - (stop_dist * 2)

                            alert_text = (
                                f"⚡ **SMC МЕГА-РАДАР (ВЕСЬ МАРКЕТ)** ⚡\n\n"
                                f"🪙 **Монета:** #{symbol}\n"
                                f"⏱️ **Таймфрейм:** {label}\n"
                                f"📊 **Сигнал:** {signal_type}\n\n"
                                f"🗺️ *Анализ:* Зафиксирован ложный пробой экстремума. Кит собрал стопы толпы и защищает ценовой диапазон.\n\n"
                                f"⚔️ **Математика сделки (Риск ${FIXED_RISK:.2f}):**\n"
                                f"🔹 Вход (Рыночный): `{entry_price}`\n"
                                f"🛑 Стоп-Лосс: `{stop_loss:.5f}`\n"
                                f"🎯 Тейк-Профит (1:2): `{tp:.5f}`\n\n"
                                f"💰 **Объем позиции:** `{pos_size:.2f}` монет\n"
                                f"💎 Стоимость позиции: ${total_val:.2f}\n"
                                f"🧱 **Необходимая маржа:**\n"
                                f"• Плечо 10х: ${total_val/10:.2f}\n"
                                f"• Плечо 20х: ${total_val/20:.2f}\n\n"
                                f"⚠️ *Внимание: Перед открытием ордера убедитесь в наличии слома структуры на младшем графике!*"
                            )

                            for chat_id in subscribed_chats:
                                try:
                                    bot.send_message(chat_id, alert_text, parse_mode="Markdown")
                                except Exception:
                                    pass
                    
                    time.sleep(0.1)
                except Exception:
                    time.sleep(0.1)
                    continue
                    
            time.sleep(5)
        except Exception:
            time.sleep(10)

@bot.message_handler(commands=['start'])
def cmd_start(message):
    uid = message.chat.id
    subscribed_chats.add(uid)
    
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    btn_calc = telebot.types.KeyboardButton("📊 Ручной калькулятор")
    btn_status = telebot.types.KeyboardButton("📡 Статус 3-ТФ Радара")
    markup.add(btn_calc, btn_status)
    
    welcome = (
        "🚀 **Глобальный 3-ТФ Мега-Радар запущен в облаке 24/7!**\n\n"
        "🔥 Зона поиска: **Весь фьючерсный рынок Bybit (350-500 монет)**.\n"
        "⏱️ Таймфреймы отслеживания: **5 Минут, 15 Минут, 1 Час**.\n\n"
        "Я непрерывно ищу следы маркетмейкеров. Сигналы будут приходить в этот чат автоматически."
    )
    bot.send_message(uid, welcome, reply_markup=markup)

@bot.message_handler(func=lambda msg: msg.text == "📡 Статус 3-ТФ Радара")
def cmd_status(message):
    bot.send_message(
        message.chat.id, 
        f"📡 **Мульти-таймфрейм сканер Bybit активен**\n"
        f"🌍 Охват: Весь фьючерсный рынок (все USDT-пары)\n"
        f"⏱️ Сетка анализа: 5М | 15М | 1Ч одновременно\n"
        f"📉 Алгоритм: Импульсный свип ликвидности\n"
        f"🧮 Параметры: Риск строго ${FIXED_RISK:.2f} на сделку."
    )

@bot.message_handler(func=lambda msg: msg.text == "📊 Ручной калькулятор")
def start_manual_calc(message):
    msg = bot.send_message(message.chat.id, "Введите цену **ВХОДА**:")
    bot.register_next_step_handler(msg, process_manual_entry)

def process_manual_entry(message):
    try:
        uid = message.from_user.id
        user_data[uid] = {'entry': float(message.text.replace(',', '.'))}
        msg = bot.send_message(message.chat.id, "Введите цену **СТОП-ЛОССА**:")
        bot.register_next_step_handler(msg, process_manual_stop)
    except Exception:
        bot.send_message(message.chat.id, "Ошибка. Введите число.")

def process_manual_stop(message):
    try:
        uid = message.from_user.id
        stop = float(message.text.replace(',', '.'))
        entry = user_data[uid]['entry']
        stop_distance = abs(entry - stop)
        
        pos_size = FIXED_RISK / stop_distance
        total_val = pos_size * entry
        tp = entry + (stop_distance * 2) if entry > stop else entry - (stop_distance * 2)
        
        res = (
            f"📊 **Ручной Расчет (Риск ${FIXED_RISK}):**\n"
            f"🔹 Вход: `{entry}` | Стоп: `{stop}`\n"
            f"🎯 Тейк (1:2): `{tp:.4f}`\n\n"
            f"💰 Объем: `{pos_size:.2f}` монет (${total_val:.2f})\n"
            f"🧱 Маржа: 10х = `${total_val/10:.2f}` | 20х = `${total_val/20:.2f}`"
        )
        bot.send_message(message.chat.id, res, parse_mode="Markdown")
    except Exception:
        bot.send_message(message.chat.id, "Ошибка в расчете.")

if __name__ == '__main__':
    threading.Thread(target=check_timeframe_signals, args=('5', '5 минут'), daemon=True).start()
    threading.Thread(target=check_timeframe_signals, args=('15', '15 минут'), daemon=True).start()
    threading.Thread(target=check_timeframe_signals, args=('60', '1 час'), daemon=True).start()
    
    threading.Thread(target=run_health_server, daemon=True).start()
    bot.infinity_polling()
