import logging
import os
import sys
import time
from http import HTTPStatus

import requests
import telegram

from dotenv import load_dotenv

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(stream=sys.stdout),
    ]
)
logger = logging.getLogger(__name__)


def check_tokens():
    """Проверка доступности переменных окружения."""
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID,
    }
    for key, value in tokens.items():
        if value is not None:
            logger.debug(
                f'Переменная окружения "{key}" поступила корректно.'
            )
        else:
            logger.critical(
                f'Отсутствует обязательная переменная окружения: "{key}".'
            )
            raise SystemExit('Программа принудительно остановлена.')


def get_api_answer(timestamp):
    """Делает запрос к эндпоинту API-сервиса."""
    try:
        response = requests.get(
            url=ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp}
        )
    except requests.exceptions.RequestException as error:
        logger.error(f'Ошибка запроса. {error}')
    else:
        if response.status_code != HTTPStatus.OK:
            raise requests.HTTPError('Код ответа не соответствует ожидаемому.')
        logger.debug('Запрос к эндпоинту API-сервиса прошёл успешно.')
        return response.json()


def check_response(response):
    """Проверяет ответ API на соответствие документации Python."""
    if not isinstance(response, dict):
        raise TypeError('Тип данных не соответствует типу "dict".')
    if 'homeworks' not in response:
        raise KeyError('В словаре отсутствует запрошенный ключ.')
    if not isinstance(response['homeworks'], list):
        raise TypeError('Тип данных не соответствует типу "list".')
    logger.debug('Ресурс API соответствует документации Python.')
    return response['homeworks']


def parse_status(homework):
    """Извлекает из информации о домашней работе статус этой работы."""
    for key in ('status', 'homework_name'):
        if key not in homework:
            raise KeyError(
                f'В словаре отсутствует запрошенный ключ: "{key}".'
            )
    if homework.get('status') not in HOMEWORK_VERDICTS:
        raise KeyError(
            f'В словаре отсутствует запрошеный ключ:"{homework.get("status")}"'
        )
    homework_name = homework.get('homework_name')
    verdict = HOMEWORK_VERDICTS.get(homework.get('status'))
    return (
        f'Изменился статус проверки работы "{homework_name}". {verdict}'
    )


def send_message(bot, message):
    """Отправка сообщения в чат Телеграм."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug('Сообщение отправлено')
    except telegram.error.TelegramError:
        logger.error('Сообщение не доставлено')


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            for homework in homeworks:
                message = parse_status(homework)
                send_message(bot, message)
        except requests.exceptions.RequestException as error:
            message = f'Сбой в работе программы: {error}'
            send_message(bot, message)
            logger.error(message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
