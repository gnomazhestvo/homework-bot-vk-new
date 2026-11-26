import os
import random
import sys
import time
from http import HTTPStatus

import requests
import vk_api
from dotenv import load_dotenv

from exceptions import ApiAnswerError


load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
VK_TOKEN = os.getenv('VK_TOKEN')
VK_USER_ID = os.getenv('VK_USER_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверяет доступность необходимых переменных окружения."""
    tokens = {
        'Токен сервиса Практикум.Домашка': PRACTICUM_TOKEN,
        'Токен VK': VK_TOKEN,
        'Адрес получателя информации (VK ID)': VK_USER_ID,
    }

    missing_tokens = [name for name, value in tokens.items() if not value]
    if missing_tokens:
        sys.exit(
            f'Отсутствует необходимый токен: {", ".join(missing_tokens)}.'
        )


def send_message(vk, message):
    """Отправка сообщений пользователю."""
    vk.messages.send(
        user_id=VK_USER_ID,
        message=message,
        random_id=random.randint(0, 100000),
    )


def get_api_answer(timestamp):
    """Получает данные от API."""
    payload = {'from_date': timestamp}
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=payload,
            timeout=10
        )
    except requests.RequestException as error:
        raise ApiAnswerError(f'Не удалось обратиться к API: {error}')
    if response.status_code != HTTPStatus.OK:
        raise ApiAnswerError(
            f'Ошибка ответа сервера: {response.status_code}.'
        )
    return response.json()


# TODO: подробнее описать docstring.
def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError(f'Сервер вернул {type(response)} вместо dict.')
    if 'homeworks' not in response:
        raise KeyError('Отсутствуют данные о Домашках в ответе сервера.')
    homeworks = response.get('homeworks')
    if not isinstance(homeworks, list):
        raise TypeError(
            f'Сервер вернул {type(homeworks)} вместо list списка Домашек.'
        )
    return homeworks


def parse_status(homework):
    """Обрабатывает статус Домашки и возвращает ответ."""
    if 'homework_name' not in homework:
        raise KeyError('В ответе API нет ключа homework_name.')
    homework_name = homework.get('homework_name')
    status = homework.get('status')
    if status not in HOMEWORK_VERDICTS:
        raise KeyError(f'Некорректный ответ сервера: статус - {status}.')
    verdict = HOMEWORK_VERDICTS.get(status)

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    check_tokens()
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    timestamp = int(time.time())
    last_message = ''

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if homeworks:
                message = parse_status(homeworks[0])
                if message != last_message:
                    send_message(vk, message)
                    last_message = message
            timestamp = response.get('current_date', timestamp)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            if message != last_message:
                send_message(vk, message)
                last_message = message
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
