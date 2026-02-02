
# -*- coding: utf-8 -*-

# Hikka module to explore bot functionalities.
#
# Usage:
#   .gbot <bot_username> - Explores the specified bot and provides a summary.

import logging
import asyncio
import re
from telethon import events
from telethon.tl.types import Message, ReplyInlineMarkup, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton
from telethon.tl.functions.messages import DeleteHistoryRequest
from .. import loader, utils

logger = logging.getLogger(__name__)

# --- Configuration ---
BOT_EXPLORATION_TIMEOUT = 60  # Total timeout for bot exploration
MAX_BUTTON_CLICKS = 3       # Max number of buttons to click to explore deeper
MAX_MESSAGES_TO_COLLECT = 10 # Max messages to collect from bot during exploration

@loader.tds
class BotExplorerMod(loader.Module):
    """
    🤖 Модуль для исследования функционала Telegram-ботов.
    """
    strings = {
        "name": "BotExplorer",
        "usage": "✨ **Используйте:** `.gbot <username_бота>`\n"
                 "👉 **Пример:** `.gbot @BotFather`",
        "invalid_username": "❌ **Некорректный юзернейм бота!**\n"
                            "Пожалуйста, введите действительный юзернейм (например, `@BotFather`).",
        "exploring_bot": "🔍 **Исследую бота** `{bot_username}`...\n"
                         "⏳ Это может занять до {timeout} секунд. Пожалуйста, ожидайте...",
        "bot_not_found": "❌ **Бот `{bot_username}` не найден или недоступен.**",
        "exploration_failed": "🚫 **Не удалось полностью исследовать бота `{bot_username}`.**\n"
                              "Возможно, он не отвечает или требует специфического взаимодействия.",
        "report_template": """
┏ 🤖 **Отчет по боту** `{bot_username}`
┣ 🆔 **ID бота:** `{bot_id}`
┣ 👤 **Имя бота:** `{bot_name}`
┣ 📝 **Основное приветствие:**
{welcome_message}
┣ 💬 **Найденные команды:**
{commands_list}
┣ ⌨️ **Найденные кнопки (Reply/Inline):**
{buttons_list}
┗ 💡 _Это лишь поверхностное исследование. Некоторые функции могли быть не обнаружены._
""",
        "no_welcome_message": "  _Не удалось получить._",
        "no_commands_found": "  _Команды не найдены._",
        "no_buttons_found": "  _Кнопки не найдены._",
        "history_cleared": "✅ История с ботом `{bot_username}` очищена.",
        "error_clearing_history": "❌ Ошибка при очистке истории с ботом `{bot_username}`: {error}",
    }

    def __init__(self):
        self.config = loader.ModuleConfig() # Пока без настроек, но можно добавить

    async def client_ready(self, client, db):
        self.db = db
        self.client = client

    async def _clear_bot_history(self, bot_entity):
        """Очищает историю чата с ботом."""
        try:
            bot_input_peer = await self.client.get_input_entity(bot_entity)
            await self.client(DeleteHistoryRequest(
                peer=bot_input_peer,
                max_id=0,
                just_clear=True
            ))
            logger.info(self.strings("history_cleared").format(bot_username=bot_entity.username))
        except Exception as e:
            logger.error(self.strings("error_clearing_history").format(bot_username=bot_entity.username, error=e))

    async def _get_bot_response(self, conv, timeout):
        """
        Ожидает и возвращает ответ от бота, включая текст и кнопки.
        """
        try:
            resp = await conv.get_response(timeout=timeout)
            return resp
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            logger.error(f"Error getting response from bot: {e}")
            return None

    async def _extract_commands_from_text(self, text: str) -> list:
        """Извлекает команды из текста сообщения."""
        commands = set()
        # Ищем команды, начинающиеся с /
        found = re.findall(r'/(?P<command>[a-zA-Z0-9_]+)', text)
        for cmd in found:
            # Исключаем команды, которые могут быть частью URL или других не командных структур
            if not re.match(r'^[a-zA-Z0-9_]+$', cmd):
                continue
            commands.add(f"/{cmd}")
        return sorted(list(commands))

    async def gbotcmd(self, message: Message):
        """
        🤖 Исследует функционал указанного Telegram-бота.
        """
        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, self.strings("usage"))
            return

        bot_username_raw = args.strip()
        if not bot_username_raw.startswith('@'):
            bot_username_raw = '@' + bot_username_raw

        if not re.match(r'^@[a-zA-Z0-9_]{5,32}$', bot_username_raw):
            await utils.answer(message, self.strings("invalid_username"))
            return

        await utils.answer(message, self.strings("exploring_bot").format(
            bot_username=bot_username_raw, timeout=BOT_EXPLORATION_TIMEOUT
        ))

        bot_entity = None
        try:
            bot_entity = await self.client.get_entity(bot_username_raw)
            if not bot_entity.bot:
                await utils.answer(message, f"❌ `{bot_username_raw}` не является ботом.")
                return
        except Exception:
            await utils.answer(message, self.strings("bot_not_found").format(bot_username=bot_username_raw))
            return

        bot_id = bot_entity.id
        bot_name = bot_entity.first_name

        welcome_message = self.strings("no_welcome_message")
        found_commands = set()
        found_buttons = set()
        
        # Список сообщений, которые мы получили от бота во время исследования
        collected_messages_text = []

        try:
            async with self.client.conversation(bot_entity, timeout=BOT_EXPLORATION_TIMEOUT) as conv:
                # 1. Отправляем /start
                await conv.send_message("/start")
                resp = await self._get_bot_response(conv, BOT_EXPLORATION_TIMEOUT / 3) # Даем треть таймаута
                
                if resp:
                    collected_messages_text.append(resp.text)
                    welcome_message = resp.text.strip()
                    found_commands.update(await self._extract_commands_from_text(resp.text))
                    
                    if resp.reply_markup:
                        if isinstance(resp.reply_markup, ReplyInlineMarkup):
                            for row in resp.reply_markup.rows:
                                for button in row.buttons:
                                    if isinstance(button, InlineKeyboardButton):
                                        found_buttons.add(f"[Inline] {button.text}")
                        elif isinstance(resp.reply_markup, ReplyKeyboardMarkup):
                            for row in resp.reply_markup.rows:
                                for button in row.buttons:
                                    if isinstance(button, KeyboardButton):
                                        found_buttons.add(f"[Reply] {button.text}")

                # 2. Отправляем /help
                await conv.send_message("/help")
                resp = await self._get_bot_response(conv, BOT_EXPLORATION_TIMEOUT / 3)
                
                if resp:
                    collected_messages_text.append(resp.text)
                    found_commands.update(await self._extract_commands_from_text(resp.text))
                    if resp.reply_markup:
                        if isinstance(resp.reply_markup, ReplyInlineMarkup):
                            for row in resp.reply_markup.rows:
                                for button in row.buttons:
                                    if isinstance(button, InlineKeyboardButton):
                                        found_buttons.add(f"[Inline] {button.text}")
                        elif isinstance(resp.reply_markup, ReplyKeyboardMarkup):
                            for row in resp.reply_markup.rows:
                                for button in row.buttons:
                                    if isinstance(button, KeyboardButton):
                                        found_buttons.add(f"[Reply] {button.text}")

                # 3. Попробуем нажать на несколько кнопок (если есть)
                clicked_buttons_count = 0
                messages_collected_count = len(collected_messages_text)

                # Собираем все найденные кнопки, которые можно нажать
                all_possible_buttons = []
                if resp and resp.reply_markup:
                    if isinstance(resp.reply_markup, ReplyInlineMarkup):
                        for row in resp.reply_markup.rows:
                            for button in row.buttons:
                                if isinstance(button, InlineKeyboardButton) and button.text not in [b.split('] ')[1] for b in found_buttons if b.startswith('[Inline]')]:
                                    all_possible_buttons.append(button)
                    elif isinstance(resp.reply_markup, ReplyKeyboardMarkup):
                        for row in resp.reply_markup.rows:
                            for button in row.buttons:
                                if isinstance(button, KeyboardButton) and button.text not in [b.split('] ')[1] for b in found_buttons if b.startswith('[Reply]')]:
                                    all_possible_buttons.append(button)

                # Выбираем несколько для клика
                buttons_to_click = all_possible_buttons[:MAX_BUTTON_CLICKS]

                for button in buttons_to_click:
                    if messages_collected_count >= MAX_MESSAGES_TO_COLLECT:
                        break

                    try:
                        if isinstance(button, InlineKeyboardButton):
                            # Для inline кнопок нужно использовать click()
                            await button.click(conv.dialog) # conv.dialog - это peer (entity) бота
                        elif isinstance(button, KeyboardButton):
                            # Для reply кнопок нужно отправить текст кнопки
                            await conv.send_message(button.text)
                        
                        resp_after_click = await self._get_bot_response(conv, BOT_EXPLORATION_TIMEOUT / (MAX_BUTTON_CLICKS + 3))
                        if resp_after_click:
                            collected_messages_text.append(resp_after_click.text)
                            found_commands.update(await self._extract_commands_from_text(resp_after_click.text))
                            if resp_after_click.reply_markup:
                                if isinstance(resp_after_click.reply_markup, ReplyInlineMarkup):
                                    for row in resp_after_click.reply_markup.rows:
                                        for btn in row.buttons:
                                            if isinstance(btn, InlineKeyboardButton):
                                                found_buttons.add(f"[Inline] {btn.text}")
                                elif isinstance(resp_after_click.reply_markup, ReplyKeyboardMarkup):
                                    for row in resp_after_click.reply_markup.rows:
                                        for btn in row.buttons:
                                            if isinstance(btn, KeyboardButton):
                                                found_buttons.add(f"[Reply] {btn.text}")
                            messages_collected_count += 1
                        clicked_buttons_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to click button '{button.text}' for {bot_username_raw}: {e}")
                        # Если кнопка вызвала ошибку, пропускаем ее и идем дальше

        except asyncio.TimeoutError:
            logger.warning(f"Bot exploration for {bot_username_raw} timed out.")
        except Exception as e:
            logger.error(f"Error during bot exploration for {bot_username_raw}: {e}")
            await utils.answer(message, self.strings("exploration_failed").format(bot_username=bot_username_raw))
            return
        finally:
            if bot_entity:
                await self._clear_bot_history(bot_entity)

        # Формирование отчета
        commands_list_str = "\n".join([f"    - `{cmd}`" for cmd in sorted(list(found_commands))]) \
                            if found_commands else self.strings("no_commands_found")
        
        buttons_list_str = "\n".join([f"    - `{btn}`" for btn in sorted(list(found_buttons))]) \
                           if found_buttons else self.strings("no_buttons_found")

        # Ограничиваем приветственное сообщение, чтобы не было слишком длинным
        if len(welcome_message) > 500:
            welcome_message = welcome_message[:497] + "..."
        welcome_message = "\n".join([f"  {line}" for line in welcome_message.split('\n')])


        final_report = self.strings("report_template").format(
            bot_username=bot_username_raw,
            bot_id=bot_id,
            bot_name=bot_name,
            welcome_message=welcome_message,
            commands_list=commands_list_str,
            buttons_list=buttons_list_str,
        )

        await utils.answer(message, final_report)

