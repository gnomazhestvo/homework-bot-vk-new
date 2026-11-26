import logging
import os
import sys
import time
from http import HTTPStatus

import requests
import vk_api
from dotenv import load_dotenv
from vk_api.utils import get_random_id

from exceptions import ApiAnswerError


load_dotenv()
logger = logging.getLogger(__name__)

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
VK_TOKEN = os.getenv('VK_TOKEN')
VK_USER_ID = os.getenv('VK_USER_ID')

RETRY_PERIOD = 600
TIMEOUT = 10
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

LOGGING_FORMAT = '%(asctime)s [%(levelname)s] %(message)s'


def check_tokens():
    """Проверяет доступность необходимых переменных окружения.

    В случае отсутствия необходимой переменной добавляет ее в список и
    в сообщение об ошибке. Работа скрипта завершается.
    """
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'VK_TOKEN': VK_TOKEN,
        'VK_USER_ID': VK_USER_ID,
    }

    missing_tokens = [name for name, value in tokens.items() if not value]
    if missing_tokens:
        error_message = (
            'Отсутствует обязательная переменная'
            f' окружения: {", ".join(missing_tokens)}.'
        )
        logger.critical(error_message)
        sys.exit(error_message)


def send_message(vk, message):
    """Отправляет сообщение пользователю в VK и пишет результат в лог.

    При неудавшейся попытке отправки сообщения возвращает False.
    """
    try:
        vk.messages.send(
            user_id=VK_USER_ID,
            message=message,
            random_id=get_random_id(),
        )
    except Exception as error:
        logger.error(f'Не удалось отправить сообщение в VK: {error}.')
        return False
    logger.debug(f'Сообщение отправлено пользователю: "{message}".')
    return True


def get_api_answer(timestamp):
    """Получает данные от API.

    Делает запрос к API Практикум.Домашки с меткой времени timestamp.
    Возвращает ответ (словарь).
    Если запрос не удался или код ответа не 200, выбрасывает ApiAnswerError.
    """
    payload = {'from_date': timestamp}
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=payload,
            timeout=TIMEOUT,
        )
    except requests.RequestException as error:
        raise ApiAnswerError(
            f'Не удалось обратиться к API: {error}'
        ) from error
    if response.status_code != HTTPStatus.OK:
        raise ApiAnswerError(
            f'Эндпоинт недоступен: {response.status_code} ({ENDPOINT}).'
        )
    try:
        response = response.json()
    except Exception as error:
        raise ApiAnswerError(f'API вернул не JSON: {error}.')
    return response


def check_response(response):
    """Проверяет ответ API на соответствие документации.

    - ответ должен быть словарем;
    - в словаре должны быть ключи 'homeworks' и 'current_date';
    - значением homeworks является список домашек.
    """
    if not isinstance(response, dict):
        raise TypeError(f'Сервер вернул {type(response)} вместо dict.')
    for key in ('homeworks', 'current_date'):
        if key not in response:
            raise KeyError(f'В ответе API нет ключа {key}.')
    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError(
            f'Сервер вернул {type(homeworks)} вместо list списка Домашек.'
        )
    return homeworks


def parse_status(homework):
    """Обрабатывает статус Домашки и возвращает ответ.

    Получает на вход одну Домашку из ответа API, возвращает текст сообщения
    в зависимости от статуса ее проверки.
    """
    for key in ('homework_name', 'status'):
        if key not in homework:
            raise KeyError(f'В ответе API нет ключа {key}.')
    homework_name = homework['homework_name']
    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        raise KeyError(f'Некорректный ответ сервера: статус - {status}.')
    verdict = HOMEWORK_VERDICTS.get(status)

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота.

    Раз в RETRY_PERIOD запрашивает у API статусы домашних работ, изменившиеся
    с момента timestamp. После успешной доставки сообщения в VK смещает
    timestamp на current_date из ответа.
    """
    logger.info('Бот запущен.')

    check_tokens()
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    timestamp = int(time.time())
    logger.debug(f'timestamp: {timestamp}.')
    last_message = ''

    while True:
        message = None
        new_timestamp = timestamp
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            new_timestamp = response['current_date']
            if homeworks:
                message = parse_status(homeworks[0])
            else:
                logger.debug('Новых статусов нет.')
                timestamp = new_timestamp

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)

        if message and message != last_message and send_message(vk, message):
            last_message = message
            timestamp = new_timestamp

        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOGGING_FORMAT))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    main()
