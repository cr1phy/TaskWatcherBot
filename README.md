# TaskWatcherBot

Telegram-бот для автоматического мониторинга домашних заданий из CloudText. Собирает статистику по ученикам, отправляет уведомления в группы и заполняет Google Sheets.

## Возможности

- Автоматическая авторизация в CloudText по email/паролю
- Привязка учеников через deep link (`/start`)
- Персональная статистика по ДЗ (`/stats`)
- Еженедельные уведомления в группы и в ЛС
- Автоматическое заполнение Google Sheets таблиц
- Панель владельца для управления

## Установка на VPS

### Требования

- Docker + Docker Compose
- Домен не требуется (polling)

### 1. Google OAuth

Бот использует Google Sheets для выгрузки таблиц. Нужны OAuth-креденшлы:

1. Перейдите в [Google Cloud Console](https://console.cloud.google.com/)
2. Создайте проект или выберите существующий
3. Включите **Google Sheets API** и **Google Drive API**
4. Перейдите в **Credentials** → **Create Credentials** → **OAuth 2.0 Client ID**
5. Тип: **Desktop application**
6. Скачайте JSON-файл, переименуйте в `credentials.json`
7. Положите `credentials.json` в корень проекта

### 2. Папка Google Drive

1. Создайте папку в Google Drive для таблиц
2. Скопируйте ID папки из URL: `https://drive.google.com/drive/folders/ЭТОТ_ID`
3. Это значение для `SPREADSHEETS_FOLDER_ID`

### 3. CloudText

Вам нужны:
- **URL вашей организации**: например `https://alo.cloudtext.ru`
  (если без организации — `https://cloudtext.ru`)
- **Email и пароль** от аккаунта с премиум-подпиской

### 4. Telegram API

1. Перейдите на [my.telegram.org/apps](https://my.telegram.org/apps)
2. Создайте приложение
3. Запишите **API ID** и **API Hash**

Это нужно для Telethon (парсинг участников групп).

### 5. Бот и владелец

1. Создайте бота через [@BotFather](https://t.me/BotFather)
2. Запишите **Bot Token**
3. Узнайте свой Telegram ID (например через [@userinfobot](https://t.me/userinfobot))

### 6. Конфигурация

Скопируйте `example.env` в `.env` и заполните:

```env
# CloudText
CLOUDTEXT_BASE_URL=https://your-school.cloudtext.ru
CLOUDTEXT_EMAIL=teacher@example.com
CLOUDTEXT_PASSWORD=your_password

# Telegram
BOT_TOKEN=123456:ABC-DEF
OWNER_TGID=your_telegram_id

# Telegram API (для Telethon)
TG_API_ID=12345678
TG_API_HASH=abcdef1234567890
TG_SESSION=session

# Database
DB_URL=postgresql://bot:bot@postgres/bot
REDIS_URL=redis://redis

# Google Sheets
GSHEETS_CREDS_FILE=mycreds.json
SPREADSHEETS_FOLDER_ID=your_folder_id
```

### 7. Авторизация

Перед первым запуском в Docker нужно авторизоваться в Google и Telegram **локально**, т.к. Docker не имеет доступа к браузеру и интерактивному вводу.

```bash
# Установить зависимости
uv sync

# Google OAuth — откроется браузер
uv run scripts/auth_gsheets.py

# Telethon — сканируйте QR
uv run scripts/auth_telethon.py
```

После этого появятся файлы:
- `authorized_user.json` (или в `%APPDATA%\gspread\` на Windows)
- `session.session`

Скопируйте `authorized_user.json` в корень проекта:
```bash
# Linux/macOS
cp ~/.config/gspread/authorized_user.json ./authorized_user.json

# Windows
copy %APPDATA%\gspread\authorized_user.json .\authorized_user.json
```

### 8. Запуск

```bash
docker compose up -d
```

Проверьте логи:
```bash
docker compose logs -f bot
```

Вы должны увидеть:
```
cloudtext_authenticated  email=...
✅ Теперь бот готов.цц
```

## Использование

### Для владельца

1. Напишите боту `/start` — увидите панель
2. Добавьте бота в Telegram-группу с названием «Группа N» (например «Информатика | Группа 1»)
3. Бот автоматически привяжется и отправит кнопку «Привязаться» ученикам
4. `/links` — получить ссылки для всех групп
5. `/create_sheets` — создать Google Sheets таблицы
6. `/parse_users` — посмотреть, сколько учеников привязалось

### Для учеников

1. Нажать кнопку «Привязаться» в группе (или перейти по ссылке от преподавателя)
2. Ввести своё ФИО как в CloudText
3. `/stats` — посмотреть свою статистику

### Автоматические действия

- **Понедельник 10:00** — уведомление в группы + личные напоминания
- **Воскресенье 03:00** — обновление Google Sheets таблиц

## Ограничения

- CloudText не предоставляет публичный API. Бот использует внутренние эндпоинты через cookie-авторизацию. При обновлении CloudText интеграция может сломаться.
- Журнал CloudText не возвращает ID учеников — привязка работает **по совпадению ФИО**. При дубликатах имён персональная статистика **невозможна**.
- Google OAuth токен может протухнуть — в этом случае повторите шаг 7.

## Структура проекта

```
app/
├── bootstrap.py          # Запуск бота, шедулер
├── config.py             # Переменные окружения
├── container.py          # DI-контейнер
├── middleware.py          # PrivateOnly, Owner, Logging
├── states.py             # FSM состояния
├── handlers/
│   ├── linking.py        # /start, привязка, /unlink, /help
│   ├── owner.py          # /admin, /links, /create_sheets
│   └── stats.py          # /stats
├── jobs/
│   ├── notify.py         # Еженедельные уведомления
│   └── sheets.py         # Обновление таблиц
├── models/
│   ├── cloudtext/        # API клиент, модели, парсинг
│   ├── gsheets/          # Google Sheets клиент, filler
│   └── db/               # Pydantic модели для БД
├── dao/                  # Data Access Objects
└── services/             # UserService, GroupRegistry
```
