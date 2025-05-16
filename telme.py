import requests
import configparser
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from datetime import datetime
import logging
import time
import asyncio

logging.basicConfig(
    filename='bot.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

config = configparser.ConfigParser()
config.read('config.ini')

bot_token       = config.get('telegram', 'bot_token')
chat_id         = config.get('telegram', 'chat_id')
bscscan_api_key = config.get('bscscan',  'api_key')

monitoring_job_eth  = None
monitoring_job_web  = None
previous_count      = None
alert_triggered     = False
last_alert_time     = datetime.min

ADDRESS      = '0xeba6ad75e46406cc6b6ce9c8ac6c431fef493e5b'
BSC_SCAN_URL = 'https://api.bscscan.com/api'


def get_eth_price():
    while True:
        try:
            url = "https://www.okx.com/api/v5/market/ticker?instId=ETH-USDT"
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            data = r.json()
            if data.get('code') == '0':
                return int(float(data['data'][0]['last']))
        except Exception:
            pass
        time.sleep(5)


async def send_price_alert(context: ContextTypes.DEFAULT_TYPE) -> None:
    global alert_triggered, last_alert_time
    now = datetime.now()
    if alert_triggered and (now - last_alert_time).seconds < 600:
        return

    price = get_eth_price()
    if price is None:
        return

    if price > 3000:
        await context.bot.send_message(chat_id=chat_id, text="up")
        alert_triggered = True
        last_alert_time = now
    elif price < 2000:
        await context.bot.send_message(chat_id=chat_id, text="down")
        alert_triggered = True
        last_alert_time = now
    else:
        alert_triggered = False


async def price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    price = get_eth_price()
    if price is None:
        await update.message.reply_text("Failed to fetch data, please try again later.")
    else:
        await update.message.reply_text(str(price))


def get_event_count() -> int:
    page = 1
    offset = 1000
    total = 0

    while True:
        params = {
            'module': 'logs',
            'action': 'getLogs',
            'address': ADDRESS,
            'fromBlock': 0,
            'toBlock': 'latest',
            'page': page,
            'offset': offset,
            'apikey': bscscan_api_key
        }
        r = requests.get(BSC_SCAN_URL, params=params, timeout=20)
        r.raise_for_status()
        resp = r.json()
        logs = resp.get('result', [])
        if not logs:
            break
        total += len(logs)
        if len(logs) < offset:
            break
        page += 1
        time.sleep(0.2)

    return total


async def check_event_count(context: ContextTypes.DEFAULT_TYPE) -> None:
    global previous_count
    try:
        current = get_event_count()
    except Exception as e:
        logging.error(f"Error fetching event count: {e}")
        return

    if previous_count is None:
        previous_count = current
        return

    if current != previous_count:
        original_previous = previous_count
        confirmed = True

        for _ in range(3):
            await asyncio.sleep(15)
            try:
                retry_current = get_event_count()
                if retry_current == original_previous:
                    confirmed = False
                    break
            except Exception:
                confirmed = False
                break

        if confirmed:
            await context.bot.send_message(chat_id=chat_id, text="TG")
            previous_count = current


async def start_eth_monitoring(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global monitoring_job_eth
    job_queue = context.application.job_queue
    if monitoring_job_eth:
        monitoring_job_eth.schedule_removal()
    monitoring_job_eth = job_queue.run_repeating(send_price_alert, interval=5, first=0)
    await update.message.reply_text("s")


async def start_web_monitoring(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global monitoring_job_web, previous_count
    job_queue = context.application.job_queue
    try:
        initial_count = get_event_count()
    except Exception as e:
        await update.message.reply_text(f"Failed to fetch event count: {e}")
        return

    if monitoring_job_web:
        monitoring_job_web.schedule_removal()
    previous_count = initial_count
    monitoring_job_web = job_queue.run_repeating(check_event_count, interval=30, first=30)
    await update.message.reply_text(str(previous_count))


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    eth_status = "Started" if monitoring_job_eth else "Not started"
    web_status = "Started" if monitoring_job_web else "Not started"
    await update.message.reply_text(
        "/h help\n"
        "/p Instant query\n"
        f"/s {eth_status}\n"
        f"/w {web_status}"
    )


def main():
    while True:
        try:
            app = Application.builder().token(bot_token).build()
            app.add_handler(CommandHandler("p", price))
            app.add_handler(CommandHandler("s", start_eth_monitoring))
            app.add_handler(CommandHandler("w", start_web_monitoring))
            app.add_handler(CommandHandler("h", help))
            app.run_polling()
        except Exception:
            continue


if __name__ == '__main__':
    main()
