# Установка сервера

## 1. VPS и поддомен

Для первого испытания: Linux VPS, например Ubuntu 24.04 LTS, ориентир 2 vCPU,
2 ГБ RAM и 20 ГБ диска. Фактическую нагрузку и рост БД нужно контролировать.
Хостинг оплачивается владельцем напрямую; этот проект ничего не покупает.

Можно использовать **поддомен имеющегося домена**, например `gps.ваш-домен.ru`.
Основной сайт остаётся на прежнем хостинге. В DNS добавьте только A-запись `gps`
на IPv4 нового VPS. Если IPv6 на VPS не настроен, не добавляйте AAAA-запись.
Не меняйте A/CNAME основного сайта, www или почтовые MX-записи.

## 2. Docker и исходники

Установите Docker Engine и Compose plugin по официальной инструкции для ОС:
https://docs.docker.com/engine/install/ubuntu/ .
Проверьте `docker version` и `docker compose version`.
Скачайте исходники на VPS, например в `/opt/gps-tracker`:

```sh
git clone https://github.com/Evgenii-Denisov2303/gps-tracker.git /opt/gps-tracker
```

Создайте новую `.env`, не переносите настройки от локального теста.
Откройте входящие TCP 80/443 и SSH; не открывайте наружу 5432 или 8000.
UDP 443 необязателен для HTTP/3. Не выполняйте локальный compose override на публичном VPS.

## 3. Настройки и HTTPS

```sh
cd /opt/gps-tracker
umask 077
cp .env.example .env
```

В `.env` замените:

```dotenv
DOMAIN=gps.your-domain.ru
PUBLIC_ORIGIN=https://gps.your-domain.ru
COOKIE_SECURE=true
POSTGRES_PASSWORD=случайная_HEX_строка_без_пробелов
TIMEZONE=Europe/Moscow
```

Сгенерировать HEX: `openssl rand -hex 32`.
DOMAIN без схемы и пути, PUBLIC_ORIGIN без завершающего `/`.
Пароль БД включается в URL подключения, поэтому пример специально использует HEX без URL-спецсимволов.
Если БД уже создана, смена POSTGRES_PASSWORD в `.env` сама по себе не меняет пароль внутри PostgreSQL.

```sh
docker compose -f docker-compose.yml -f compose.production.yml up -d --build
docker compose -f docker-compose.yml -f compose.production.yml ps
docker compose -f docker-compose.yml -f compose.production.yml logs --tail=100 api caddy
docker compose -f docker-compose.yml -f compose.production.yml exec api python -m app.cli admin owner
```

Caddy получает и продлевает сертификат автоматически. Если не получилось, проверьте
DNS, доступность портов, системное время и журнал Caddy. Не отключайте проверку сертификата в Android.
Миграции Alembic применяются перед стартом API. База и API не доступны напрямую из интернета.
Для первой установки используйте пустую БД; не переносите локальные тестовые точки и учётные записи.

## 4. Регистрация

1. Откройте HTTPS-адрес, войдите под созданным владельцем.
2. Добавьте машину: название и при необходимости номер.
3. «Устройства» → название телефона → «Выдать токен».
4. Сохраните токен и HTTPS-адрес в Android-приложении. ID машины оно не вводит:
   сервер определяет машину по токену, подмена vehicle_id запрещена.
5. Проверьте первую точку, отключение интернета, выгрузку очереди и потерю связи.

## 5. Доступ другу только для просмотра

Создание отдельного зрителя или смена его пароля:

```sh
docker compose exec api python -m app.cli viewer friend
```

Пароль вводится скрыто, минимум 12 символов. Команда также отзывает старые сессии этого аккаунта.
Передавайте зрителю только адрес сайта, его логин и пароль. Пароль `owner` и токены трекеров ему не нужны.
Зритель видит все автомобили и их историю; ограничения по отдельным автомобилям пока не предусмотрены.
Названия аккаунтов должны различаться: команда `viewer owner` изменит роль владельца на просмотр.
Команда `admin имя` явно назначает полный доступ, поэтому не используйте её для пароля зрителя.

## 6. Резервное копирование

Пример для Linux, из каталога проекта; имя копии выбирайте уникальным:

```sh
mkdir -p backups
chmod 700 backups
docker compose exec -T db pg_dump -U tracker -d tracker -Fc > backups/tracker-2026-10-03.dump
```

Также сохраните `.env` и ключ подписи APK отдельно в защищённом месте.
Не кладите резервные копии в Git или публичную директорию сайта. Храните внешнюю копию.
Регулярность, срок хранения и место хранения определяет владелец.

Проверка восстановления без изменения рабочей БД:

```sh
docker compose exec db createdb -U tracker tracker_restore_test
docker compose exec -T db pg_restore -U tracker -d tracker_restore_test --no-owner < backups/tracker-2026-10-03.dump
docker compose exec db psql -U tracker -d tracker_restore_test -c 'SELECT count(*) FROM location_points;'
```

Для рабочего восстановления сначала остановите API, сделайте копию текущей БД,
восстановите дамп в отдельную БД и проверьте его. Переключение рабочей БД выполняйте осознанно;
не запускайте `pg_restore --clean` поверх работающей системы.

## 7. Обновления и обслуживание

Перед обновлением — резервная копия БД и `.env`, затем загрузка новой версии исходников
и `docker compose -f docker-compose.yml -f compose.production.yml up -d --build`.
После — health, вход, текущая точка, история, очередь на телефоне.
Следите за диском: `docker system df`, `docker compose logs --tail=100 api`.
Логи контейнеров ограничены по размеру. Автоматической политики удаления точек нет.

Явная очистка точек старше 180 дней (необратима без копии):
`docker compose exec api python -m app.cli prune --days 180`.

Сброс пароля: `docker compose exec api python -m app.cli admin owner`.
Это отзывает сессии владельца. Потерянный телефон: отозвать токен в кабинете,
выдать новый токен новому устройству; историю это не удаляет.
