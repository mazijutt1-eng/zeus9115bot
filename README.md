# ZEUS AI Telegram Bot

Python Telegram bot with ChatGPT, Gemini, Claude, DeepSeek and Perplexity model selection, daily free/premium quotas and admin premium commands.

## Deploy to Railway
1. Create a Railway project and deploy this GitHub repository.
2. Railway will build using the included Dockerfile.
3. Add environment variables in Railway:
   - TELEGRAM_BOT_TOKEN (required; get it from @BotFather)
   - ADMIN_IDS (your numeric Telegram user ID; use /id after first start)
   - API keys for providers you want to enable: OPENAI_API_KEY, GEMINI_API_KEY, ANTHROPIC_API_KEY, DEEPSEEK_API_KEY, PERPLEXITY_API_KEY
4. Redeploy and check logs for "Starting ZEUS AI Telegram bot...".

Set DATABASE_PATH to a path on an attached persistent Railway volume, such as /data/zeus_ai.db, if you want user plans and usage counters to survive redeploys.

## Commands
- /start and /menu: open the bot menu
- /id: show your Telegram numeric user ID
- /premium USER_ID on|off: admin-only premium control

Each AI provider may charge separately for API use. A ChatGPT subscription does not include OpenAI API credits. Premium is manually assigned; no payment gateway is included. Keep tokens and API keys in Railway Variables, never in GitHub.
