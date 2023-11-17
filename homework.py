import logging
import os
import time
from http import HTTPStatus

import requests
import telegram
from dotenv import load_dotenv

from exeptions import EmptyResponseFromApiError

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


def custom_logger(name):
    """Создаёт настраиваемый изолированный logger."""
    formatter = logging.Formatter(fmt=(
        '[%(asctime)s] '
        '[%(levelname)s] '
        '[%(funcName)s:%(lineno)d] '
        '[%(message)s]'
    ))
    # Создание логов в файле.
    log_file = __file__ + '.log'
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)
    # Создание логов в консоли.
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    # Определение логов.
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


logger = custom_logger(__name__)


def check_tokens():
    """Проверка доступности переменных окружения."""
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID,
    }
    all_tokens = True
    for name, token in tokens.items():
        if token:
            logger.debug(
                f'Переменная окружения {name} = {token} поступила корректно.'
            )
        else:
            logger.critical(
                'Отсутствует обязательная переменная окружения '
                f'{name} = {token}.'
            )
            all_tokens = False
    if not all_tokens:
        raise SystemExit(
            'Программа принудительно остановлена из-за отсутствия '
            'обязательных переменных окружения.'
        )


def get_api_answer(timestamp):
    """Делает запрос к эндпоинту API-сервиса."""
    requests_parametrs = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {'from_date': timestamp},
    }
    logger.debug(
        'Отправлен запрос API {url}. Параметры: headers = {headers}, '
        'params = {params}.'.format(**requests_parametrs)
    )
    try:
        response = requests.get(**requests_parametrs)
    except requests.RequestException:
        raise ConnectionError(
            'Сбой в работе программы: Во время подключения к эндпоинту {url} '
            'произошла непредвиденная ошибка: headers = {headers}, '
            'params = {params}.'.format(**requests_parametrs)
        )
    if response.status_code != HTTPStatus.OK:
        raise requests.HTTPError(
            'Ошибка HTTP: {status_code}. Причина: {reason}. '
            'Текст ответа: {text}.'.format(**response)
        )
    logger.debug('Запрос к эндпоинту API-сервиса прошёл успешно.')
    return response.json()


def check_response(response):
    """Проверяет ответ API на соответствие документации Python."""
    if not isinstance(response, dict):
        raise TypeError('Тип данных не соответствует типу "dict".')
    homeworks = response.get('homeworks')
    if 'homeworks' not in response:
        raise EmptyResponseFromApiError('Пришёл пустой ответ от API.')
    if not isinstance(homeworks, list):
        raise TypeError('Тип данных не соответствует типу "list".')
    logger.debug('Ресурс API соответствует документации Python.')
    return homeworks


def parse_status(homework):
    """Извлекает из информации о домашней работе статус этой работы."""
    for key in ('status', 'homework_name'):
        if key not in homework:
            raise KeyError(
                f'В словаре отсутствует запрошенный ключ: {key}.'
            )
    if homework.get('status') not in HOMEWORK_VERDICTS:
        raise ValueError(
            f'Неожиданное принятое значение: {homework.get("status")}'
        )
    homework_name = homework.get('homework_name')
    verdict = HOMEWORK_VERDICTS.get(homework.get('status'))
    return (
        f'Изменился статус проверки работы "{homework_name}". {verdict}'
    )


def send_message(bot, message):
    """Отправка сообщения в чат Телеграм."""
    try:
        logger.debug(f'Попытка отправки сообщения: {message}')
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(f'Сообщение отправлено: {message}')
        return True
    except telegram.error.TelegramError as tg_e:
        logger.error(f'Ошибка при отправке сообщения: {tg_e}')
        return False


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = 0
    homeworks_status_dict = {}
    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if homeworks:
                first_homework = homeworks[0]
                verdict = parse_status(first_homework)
            else:
                verdict = 'Нет новых статусов.'
            if verdict != homeworks_status_dict.get('verdict'):
                if send_message(bot, verdict):
                    homeworks_status_dict['verdict'] = verdict
                    timestamp = response.get('current_date', timestamp)
            else:
                logger.info(f'Нет изменений в статусе: {verdict}')
        except EmptyResponseFromApiError as error:
            logger.error(f'Пришёл пустой ответ от API. {error}')
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            if verdict != homeworks_status_dict.get('verdict'):
                send_message(bot, message)
                homeworks_status_dict['verdict'] = verdict
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
