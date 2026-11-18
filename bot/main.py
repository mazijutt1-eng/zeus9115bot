import asyncio
import logging
import os
from datetime import date
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv
from openai import AsyncOpenAI
import anthropic
import aiosqlite

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("zeus-ai")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}
DB = os.getenv("DATABASE_PATH", "zeus_ai.db")
FREE_LIMIT = int(os.getenv("FREE_DAILY_LIMIT", "20"))
PREMIUM_LIMIT = int(os.getenv("PREMIUM_DAILY_LIMIT", "300"))
MODELS = {"chatgpt":"ChatGPT", "gemini":"Gemini", "claude":"Claude", "deepseek":"DeepSeek", "perplexity":"Perplexity"}
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "chatgpt").lower()
dp = Dispatcher()

def main_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="🤖 Choose AI", callback_data="choose_ai")
    kb.button(text="👤 My Account", callback_data="account")
    kb.button(text="ℹ️ Help", callback_data="help")
    kb.adjust(1, 2)
    return kb.as_markup()

def model_keyboard():
    kb = InlineKeyboardBuilder()
    for key, label in MODELS.items():
        kb.button(text=label, callback_data=f"model:{key}")
    kb.adjust(2)
    return kb.as_markup()

async def db_init():
    async with aiosqlite.connect(DB) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY, model TEXT NOT NULL, premium INTEGER NOT NULL DEFAULT 0)")
        await db.execute("CREATE TABLE IF NOT EXISTS usage(user_id INTEGER NOT NULL, day TEXT NOT NULL, count INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id,day))")
        await db.commit()

async def user_get(uid):
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR IGNORE INTO users(user_id,model,premium) VALUES(?,?,0)", (uid, DEFAULT_MODEL if DEFAULT_MODEL in MODELS else "chatgpt"))
        await db.commit()
        cur = await db.execute("SELECT model,premium FROM users WHERE user_id=?", (uid,))
        return await cur.fetchone()

async def usage_get(uid, premium):
    today = date.today().isoformat()
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR IGNORE INTO usage(user_id,day,count) VALUES(?,?,0)", (uid,today))
        cur = await db.execute("SELECT count FROM usage WHERE user_id=? AND day=?", (uid,today))
        row = await cur.fetchone()
        await db.commit()
    return (row[0] if row else 0), (PREMIUM_LIMIT if premium else FREE_LIMIT)

async def usage_add(uid):
    today = date.today().isoformat()
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR IGNORE INTO usage(user_id,day,count) VALUES(?,?,0)", (uid,today))
        await db.execute("UPDATE usage SET count=count+1 WHERE user_id=? AND day=?", (uid,today))
        await db.commit()

def env(name):
    return os.getenv(name, "").strip()

async def ask_ai(model, prompt):
    compatible = {
        "chatgpt": (env("OPENAI_API_KEY"), env("OPENAI_BASE_URL") or None, env("OPENAI_MODEL") or "gpt-4o-mini"),
        "gemini": (env("GEMINI_API_KEY"), "https://generativelanguage.googleapis.com/v1beta/openai/", env("GEMINI_MODEL") or "gemini-2.0-flash"),
        "deepseek": (env("DEEPSEEK_API_KEY"), "https://api.deepseek.com", env("DEEPSEEK_MODEL") or "deepseek-chat"),
        "perplexity": (env("PERPLEXITY_API_KEY"), "https://api.perplexity.ai", env("PERPLEXITY_MODEL") or "sonar"),
    }
    if model == "claude":
        key = env("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("Claude API key is not configured.")
        client = anthropic.AsyncAnthropic(api_key=key)
        result = await client.messages.create(model=env("CLAUDE_MODEL") or "claude-3-5-haiku-latest", max_tokens=1200, messages=[{"role":"user","content":prompt}])
        return "\n".join(x.text for x in result.content if getattr(x,"type","") == "text")
    if model not in compatible:
        raise RuntimeError("Unknown AI model.")
    key, base_url, model_name = compatible[model]
    if not key:
        raise RuntimeError(f"{MODELS[model]} API key is not configured.")
    client = AsyncOpenAI(api_key=key, base_url=base_url)
    result = await client.chat.completions.create(model=model_name, messages=[{"role":"user","content":prompt}], temperature=0.7)
    return result.choices[0].message.content or "No response received."

@dp.message(CommandStart())
async def start(message: Message):
    await user_get(message.from_user.id)
    await message.answer("👑 <b>Welcome to ZEUS AI!</b>\nOne bot, multiple AI assistants.\nChoose an AI, then send a message.", reply_markup=main_keyboard(), parse_mode="HTML")

@dp.message(Command("menu"))
async def menu(message: Message):
    await message.answer("👑 <b>ZEUS AI Menu</b>", reply_markup=main_keyboard(), parse_mode="HTML")

@dp.message(Command("id"))
async def show_id(message: Message):
    await message.answer(f"Your Telegram user ID: <code>{message.from_user.id}</code>", parse_mode="HTML")

@dp.callback_query(F.data == "choose_ai")
async def choose_ai(call: CallbackQuery):
    await call.message.edit_text("Select your AI assistant:", reply_markup=model_keyboard())
    await call.answer()

@dp.callback_query(F.data.startswith("model:"))
async def choose_model(call: CallbackQuery):
    model = call.data.split(":",1)[1]
    if model not in MODELS:
        await call.answer("Invalid model", show_alert=True)
        return
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR IGNORE INTO users(user_id,model,premium) VALUES(?,?,0)", (call.from_user.id, model))
        await db.execute("UPDATE users SET model=? WHERE user_id=?", (model,call.from_user.id))
        await db.commit()
    await call.message.edit_text(f"Selected: <b>{MODELS[model]}</b>\nNow send your question.", parse_mode="HTML", reply_markup=main_keyboard())
    await call.answer("AI selected")

@dp.callback_query(F.data == "account")
async def account(call: CallbackQuery):
    model, premium = await user_get(call.from_user.id)
    used, limit = await usage_get(call.from_user.id, bool(premium))
    await call.message.edit_text(f"👤 <b>Your ZEUS AI Account</b>\nPlan: {'Premium' if premium else 'Free'}\nSelected AI: {MODELS.get(model,model)}\nToday's usage: {used}/{limit}", parse_mode="HTML", reply_markup=main_keyboard())
    await call.answer()

@dp.callback_query(F.data == "help")
async def help_menu(call: CallbackQuery):
    await call.message.edit_text("Tap Choose AI, select a provider, then send your question. Use /menu to return.", reply_markup=main_keyboard())
    await call.answer()

@dp.message(Command("premium"))
async def premium(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Premium access is managed by the administrator.")
        return
    parts = (message.text or "").split()
    if len(parts) != 3 or parts[2] not in {"on","off"}:
        await message.answer("Usage: /premium USER_ID on OR /premium USER_ID off")
        return
    try:
        uid = int(parts[1])
    except ValueError:
        await message.answer("USER_ID must be a number.")
        return
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR IGNORE INTO users(user_id,model,premium) VALUES(?, 'chatgpt', 0)", (uid,))
        await db.execute("UPDATE users SET premium=? WHERE user_id=?", (1 if parts[2]=="on" else 0,uid))
        await db.commit()
    await message.answer("Premium setting updated.")

@dp.message(F.text)
async def chat(message: Message):
    model, premium_flag = await user_get(message.from_user.id)
    used, limit = await usage_get(message.from_user.id, bool(premium_flag))
    if used >= limit:
        await message.answer(f"Daily limit reached ({limit}). Try again tomorrow.")
        return
    status = await message.answer(f"⏳ Asking {MODELS.get(model,model)}...")
    try:
        answer = await ask_ai(model, message.text)
        await usage_add(message.from_user.id)
        for i in range(0, len(answer), 4000):
            await message.answer(answer[i:i+4000])
        await status.delete()
    except Exception:
        log.exception("AI request failed")
        await status.edit_text("⚠️ AI request failed. Check provider API key and Railway logs.")

async def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing. Add it in Railway Variables.")
    await db_init()
    bot = Bot(TOKEN)
    log.info("Starting ZEUS AI Telegram bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
