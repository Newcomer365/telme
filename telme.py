import requests
import configparser
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from datetime import datetime
import logging
import time
import asyncio
from threading import Lock

logging.basicConfig(filename='bot.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

config = configparser.ConfigParser()
config.read('config.ini')

bot_token = config.get('telegram', 'bot_token')
chat_id = config.get('telegram', 'chat_id')
bscscan_api_key = config.get('bscscan', 'api_key')

ADDRESS = '0xeba6ad75e46406cc6b6ce9c8ac6c431fef493e5b'
BSC_SCAN_URL = 'https://api.bscscan.com/api'

monitoring_job_eth = None
monitoring_job_web = None
alert_triggered = False
last_alert_time = datetime.min
latest_checked_block = None
web_monitoring_lock = Lock()

def get_eth_price():
    while True:
        try:
            url = "https://www.okx.com/api/v5/market/ticker?instId=ETH-USDT"
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            data = r.json()
            if data.get('code') == '0':
                return int(float(data['data'][0]['last']))
        except:
            pass
        time.sleep(5)

def get_latest_block():
    try:
        r = requests.get(BSC_SCAN_URL, params={'module': 'proxy', 'action': 'eth_blockNumber', 'apikey': bscscan_api_key}, timeout=10)
        r.raise_for_status()
        return int(r.json()['result'], 16)
    except:
        return -1

def get_new_event_count(from_block, to_block):
    offset = 1000
    page = 1
    total = 0
    while True:
        params = {
            'module': 'logs',
            'action': 'getLogs',
            'address': ADDRESS,
            'fromBlock': from_block,
            'toBlock': to_block,
            'page': page,
            'offset': offset,
            'apikey': bscscan_api_key
        }
        try:
            r = requests.get(BSC_SCAN_URL, params=params, timeout=10)
            r.raise_for_status()
            logs = r.json().get('result', [])
            total += len(logs)
            if len(logs) < offset:
                break
            page += 1
            time.sleep(0.2)
        except:
            break
    return total

async def check_event_count(context: ContextTypes.DEFAULT_TYPE):
    global latest_checked_block
    with web_monitoring_lock:
        try:
            latest_block = get_latest_block()
            if latest_block == -1:
                return
            if latest_checked_block is None:
                latest_checked_block = latest_block
                return
            from_block = latest_checked_block + 1
            to_block = latest_block
            if from_block > to_block:
                return
            event_count = get_new_event_count(from_block, to_block)
            if event_count > 0:
                confirmed = True
                for _ in range(3):
                    await asyncio.sleep(15)
                    if get_new_event_count(from_block, to_block) == 0:
                        confirmed = False
                        break
                if confirmed:
                    await context.bot.send_message(chat_id=chat_id, text="TG")
            latest_checked_block = to_block
        except:
            pass

async def send_price_alert(context: ContextTypes.DEFAULT_TYPE):
    global alert_triggered, last_alert_time
    now = datetime.now()
    if alert_triggered and (now - last_alert_time).seconds < 1800:
        return
    price = get_eth_price()
    if price is None:
        return
    if price > 5000:
        await context.bot.send_message(chat_id=chat_id, text="up")
        alert_triggered = True
        last_alert_time = now
    elif price < 3000:
        await context.bot.send_message(chat_id=chat_id, text="down")
        alert_triggered = True
        last_alert_time = now
    else:
        alert_triggered = False

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price = get_eth_price()
    if price is None:
        await update.message.reply_text("Failed to fetch data, please try again later.")
    else:
        await update.message.reply_text(str(price))

async def start_eth_monitoring(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global monitoring_job_eth
    job_queue = context.application.job_queue
    if monitoring_job_eth:
        monitoring_job_eth.schedule_removal()
    monitoring_job_eth = job_queue.run_repeating(send_price_alert, interval=5, first=0)
    await update.message.reply_text("monitoring started")

async def start_web_monitoring(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global monitoring_job_web, latest_checked_block
    job_queue = context.application.job_queue
    latest_block = get_latest_block()
    if latest_block == -1:
        await update.message.reply_text("Failed to get latest block")
        return
    latest_checked_block = latest_block
    if monitoring_job_web:
        monitoring_job_web.schedule_removal()
    monitoring_job_web = job_queue.run_repeating(check_event_count, interval=60, first=30)
    await update.message.reply_text(f"{latest_checked_block}")

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    eth_status = "Started" if monitoring_job_eth else "Not started"
    web_status = "Started" if monitoring_job_web else "Not started"
    await update.message.reply_text(f"/h help\n/p Instant query\n/s {eth_status}\n/w {web_status}")

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    if text == 'p':
        await price(update, context)
    elif text == 's':
        await start_eth_monitoring(update, context)
    elif text == 'w':
        await start_web_monitoring(update, context)
    elif text == 'h':
        await help(update, context)
    else:
        await update.message.reply_text("Unknown command. Try h for help.")

def main():
    while True:
        try:
            app = Application.builder().token(bot_token).build()
            app.add_handler(CommandHandler("p", price))
            app.add_handler(CommandHandler("s", start_eth_monitoring))
            app.add_handler(CommandHandler("w", start_web_monitoring))
            app.add_handler(CommandHandler("h", help))
            app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
            app.run_polling()
        except:
            time.sleep(5)

if __name__ == '__main__':
    main()
