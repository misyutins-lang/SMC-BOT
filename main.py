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
last_triggered_time = {}

# Фейковый веб-сервер, чтобы Render Free тариф не выключал бота
class HealthCheckServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_health_server():
    # Render выдает порт динамически через переменную среды, либо используем стандартный 10000
    import os
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckServer)
    print(f"🌍 Фейковый веб-сервер запущен на порту {port}...")
    server.serve_forever()

def scan_market_unlimited():
    print("🚀 Глобальный многопоточный сканер рынка успешно запущен...")
    while True:
        try:
            url = "https://bybit.com"
            response = requests.get(url, timeout=10).json()
            if response.get('retCode') != 0 or 'result' not in response or 'list' not in response['result']:
                time.sleep(15)
                continue

            tickers_list = response['result']['list']
            # Фильтруем только активные USDT пары (весь топ-рынка)
            usdt_pairs = [t['symbol'] for t in tickers_list if t['symbol'].endswith('USDT') and 'DELE' not in t['symbol']]
            active_list = usdt_pairs[:120]  # Оптимальный список топ-120 монет

            for symbol in active_list:
                try:
                    kline_url = f"https://bybit.com{symbol}&interval=60&limit=3"
                    k_resp = requests.get(kline_url, timeout=5).json()
                    
                    if k_resp.get('retCode') != 0 or not k_resp.get('result') or not k_resp['result'].get('list'):
                        continue
                        
                    klines = k_resp['result']['list']
                    if len(klines) < 3:
                        continue

                    # Разбор свечей (Bybit возвращает от новых к старым)
                    current_candle = klines[0]
                    prev_candle = klines[1]
                    older_candle = klines[2]

                    p_high = float(prev_candle[2])
                    p_low = float(prev_candle[3])
                    p_close = float(prev_candle[4])
                    o_high = float(older_candle[2])
                    o_low = float(older_candle[3])
                    current_timestamp = int(current_candle[0])

                    if symbol not in last_triggered_time:
                        last_triggered_time[symbol] = 0

                    if current_timestamp <= last_triggered_time[symbol]:
                        continue

                    signal_type = None
                    entry_price = 0.0
                    stop_loss = 0.0

                    # СТРАТЕГИЯ КИТОВ (ЛОЖНЫЙ ПРОБОЙ)
                    if p_high > o_high and p_close < o_high:
                        signal_type = "ШОРТ 🔴 (Снятие ликвидности сверху)"
                        entry_price = p_close
                        stop_loss = p_high + (p_high * 0.0005)

                    elif p_low < o_low and p_close > o_low:
                        signal_type = "ЛОНГ 🟢 (Снятие ликвидности снизу)"
                        entry_price = p_close
                        stop_loss = p_low - (p_low * 0.0005)

                    if signal_type and subscribed_chats:
                        last_triggered_time[symbol] = current_timestamp
                        stop_distance = abs(entry_price - stop_loss)

                        if stop_distance > 0:
                            position_size = FIXED_RISK / stop_distance
                            total_value = position_size * entry_price
                            take_profit = entry_price + (stop_distance * 2) if "ЛОНГ" in signal_type else entry_price - (stop_distance * 2)

                            alert_text = (
                                f"⚡ **SMC МЕГА-РАДАР ТОР-100+** ⚡\n\n"
                                f"🪙 **Монета:** #{symbol}\n"
                                f"📊 **Направление:** {signal_type}\n"
                                f"🗺️ *Этап 1-2:* Импульсный свип пула ликвидности на часовике. Кит собрал стопы толпы и защищает уровень.\n\n"
                                f"⚔️ **Этап 3 (Расчет риска на ${FIXED_RISK:.2f}):**\n"
                                f"🔹 Вход (Рыночный): `{entry_price}`\n"
                                f"🛑 Стоп-Лосс: `{stop_loss:.5f}`\n"
                                f"🎯 Минимальный Тейк (1:2): `{take_profit:.5f}`\n\n"
                                f"💰 **Объем позиции:** `{position_size:.2f}` монет\n"
                                f"💎 Стоимость позиции: ${total_value:.2f}\n"
                                f"🧱 **Необходимая маржа:**\n"
                                f"• Плечо 10х: ${total_value/10:.2f}\n"
                                f"• Плечо 20х: ${total_value/20:.2f}\n\n"
                                f"⚠️ *Внимание: Проверьте слом структуры на LTF (1М/5М) перед входом!*"
                            )

                            for chat_id in subscribed_chats:
                                try:
                                    bot.send_message(chat_id, alert_text, parse_mode="Markdown")
                                except Exception:
                                    pass
                    time.sleep(0.3)
                except Exception:
                    continue
        except Exception:
            time.sleep(10)

@bot.message_handler(commands=['start'])
def cmd_start(message):
    uid = message.chat.id
    subscribed_chats.add(uid)
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    btn_calc = telebot.types.KeyboardButton("📊 Ручной калькулятор")
    btn_status = telebot.types.KeyboardButton("📡 Статус мега-радара")
    markup.add(btn_calc, btn_status)
    
    welcome = (
        "🚀 **SMC Мега-Радар активирован в облаке Render 24/7!**\n\n"
        "🔥 Я непрерывно сканирую топ рынка Bybit (более 100 монет). Сигналы придут автоматически в этот чат, как только закроется свеча со свипом."
    )
    bot.send_message(uid, welcome, reply_markup=markup)

@bot.message_handler(func=lambda msg: msg.text == "📡 Статус мега-радара")
def cmd_status(message):
    bot.send_message(message.chat.id, f"📡 **Мега-радар работает автономно**\n🧮 Параметры: Риск строго ${FIXED_RISK:.2f} на стоп.")

if __name__ == '__main__':
    # Запускаем фейковый веб-сервер для обмана Render
    threading.Thread(target=run_health_server, daemon=True).start()
    # Запускаем сканер Bybit
    threading.Thread(target=scan_market_unlimited, daemon=True).start()
    bot.infinity_polling()
