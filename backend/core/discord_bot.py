import asyncio
import io
import base64
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

try:
    import discord
    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False


class DiscordSentinelBot:
    """
    2-Way Discord Remote Control Bot for CUA-Sentinel.
    Handles inbound user prompts, !price, !cua screenshot, !link, and outbound alert notifications.
    Protected by User ID Whitelisting.
    """

    def __init__(self, task_queue=None, governance=None):
        self.task_queue = task_queue
        self.governance = governance
        self.client: Optional[Any] = None
        self.bot_task: Optional[asyncio.Task] = None
        self.token: str = ""
        self.allowed_user_id: str = ""
        self.target_channel_id: str = ""

    def start_bot(self, token: str, allowed_user_id: str = "", target_channel_id: str = ""):
        if not DISCORD_AVAILABLE:
            logger.warning("discord.py library is not installed. Discord bot service disabled.")
            return

        if not token:
            logger.info("No Discord bot token provided. Bot disabled.")
            return

        self.token = token
        self.allowed_user_id = str(allowed_user_id).strip()
        self.target_channel_id = str(target_channel_id).strip()

        intents = discord.Intents.default()
        intents.message_content = True
        self.client = discord.Client(intents=intents, allowed_mentions=discord.AllowedMentions.none())

        @self.client.event
        async def on_ready():
            logger.info(f"Discord Sentinel Bot online as {self.client.user} (ID: {self.client.user.id})")

        @self.client.event
        async def on_message(message):
            # Fail-closed User Whitelist Guard
            if message.author.bot or not self.allowed_user_id or str(message.author.id) != self.allowed_user_id:
                return

            content = message.content.strip()
            if not content:
                return

            logger.info(f"Discord Bot received command from {message.author}: {content}")

            # 1. Command: !help
            if content.lower() == "!help":
                help_embed = discord.Embed(
                    title="🤖 CUA-Sentinel Discord Commands",
                    description="Your 24/7 Governed Personal Assistant & Desktop Operations Engine",
                    color=0x38bdf8
                )
                help_embed.add_field(name="!price <symbol>", value="Fetch live stock or crypto quote (e.g. `!price NVDA` or `!price BTC`)", inline=False)
                help_embed.add_field(name="!link <url>", value="Bookmark & RAG index web page link", inline=False)
                help_embed.add_field(name="!remind <time> <prompt>", value="Schedule background reminder (e.g. `!remind 15m Check email for tracking`)", inline=False)
                help_embed.add_field(name="!digest", value="Generate & post Daily Operations Digest (Portfolio, Gmail, Tech Radar)", inline=False)
                help_embed.add_field(name="!web <prompt>", value="Run AI Deep Research with live web search", inline=False)
                help_embed.add_field(name="<Any text prompt>", value="Direct AI chat (local model)", inline=False)
                await message.channel.send(embed=help_embed)
                return

            # 1.4 Command: !digest
            if content.lower().startswith("!digest"):
                async with message.channel.typing():
                    try:
                        from core.digest_engine import DigestEngine
                        de = DigestEngine()
                        res = await de.generate_digest()
                        embed = discord.Embed(title="📊 Daily Operations Digest", description=res["full_markdown"][:2000], color=0x38bdf8)
                        await message.channel.send(embed=embed)
                    except Exception as d_err:
                        await message.channel.send(f"❌ Could not generate digest: {d_err}", suppress_embeds=True)
                return

            # 1.5 Command: !remind / !schedule <time> <prompt>
            if content.lower().startswith("!remind") or content.lower().startswith("!schedule"):
                parts = content.split(maxsplit=2)
                if len(parts) >= 3:
                    time_offset = parts[1]
                    prompt_text = parts[2]
                    try:
                        from core.scheduler_engine import SchedulerEngine
                        se = SchedulerEngine()
                        job = se.add_reminder(name=f"Discord Reminder: {prompt_text[:30]}", time_str=time_offset, prompt=prompt_text)
                        if job:
                            embed = discord.Embed(title="⏰ Background Reminder Scheduled", color=0x38bdf8)
                            embed.add_field(name="Trigger Time", value=f"`{job['run_at']}` (in {time_offset})", inline=False)
                            embed.add_field(name="Prompt", value=prompt_text, inline=False)
                            await message.channel.send(embed=embed)
                        else:
                            await message.channel.send("❌ Invalid time format. Use e.g. `10s`, `15m`, `2h`, `1d`.", suppress_embeds=True)
                    except Exception as s_err:
                        await message.channel.send(f"❌ Could not schedule reminder: {s_err}", suppress_embeds=True)
                else:
                    await message.channel.send("Usage: `!remind <time> <prompt>` (e.g. `!remind 15m Check order status`)", suppress_embeds=True)
                return

            # 2. Command: !price <symbol>
            if content.lower().startswith("!price"):
                parts = content.split()
                symbol = parts[1].upper() if len(parts) > 1 else "NVDA"
                async with message.channel.typing():
                    from tools.finance_tools import FinanceTools
                    finance = FinanceTools()
                    quote = await finance.fetch_ticker_quote(symbol)
                    await finance.close()

                    if quote.get("price"):
                        change = quote.get("change_24h_pct", 0)
                        color = 0x10b981 if change >= 0 else 0xf87171
                        embed = discord.Embed(title=f"📈 {quote['name']} ({quote['symbol']})", color=color)
                        embed.add_field(name="Price", value=f"${quote['price']:,.2f} {quote.get('currency', 'USD')}", inline=True)
                        embed.add_field(name="24h Shift", value=f"{change:+.2f}%", inline=True)
                        embed.set_footer(text=f"Timestamp: {quote.get('timestamp')}")
                        await message.channel.send(embed=embed)
                    else:
                        await message.channel.send(f"❌ Could not fetch market quote for symbol `{symbol}`.", suppress_embeds=True)
                return

            # 3. Command: !link <url>
            if content.lower().startswith("!link"):
                parts = content.split()
                if len(parts) > 1:
                    url = parts[1]
                    async with message.channel.typing():
                        from tools.link_manager import LinkManager
                        lm = LinkManager()
                        added = lm.add_link(url)
                        crawled = await lm.crawl_and_process(added["link_id"])
                        await lm.close()

                        embed = discord.Embed(title="🔖 URL Bookmarked & RAG Indexed", url=url, color=0x10b981)
                        embed.add_field(name="Title", value=crawled.get("title", "Indexed Web Page"), inline=False)
                        embed.add_field(name="Summary", value=crawled.get("summary", "Summary created")[:500], inline=False)
                        await message.channel.send(embed=embed)
                    return

            # 4. Default: Direct AI Prompting & Task Dispatch (requires !web for live web crawl)
            use_web = False
            prompt_text = content
            if content.lower().startswith("!web "):
                use_web = True
                prompt_text = content[5:].strip()

            async with message.channel.typing():
                if self.task_queue:
                    task_id = self.task_queue.enqueue(
                        workflow_type="ENDPOINT",
                        title=f"Discord Chat: {prompt_text[:50]}",
                        input_payload={"prompt": prompt_text, "use_web": use_web},
                        priority=0
                    )
                    await message.channel.send(f"⏳ *Processing request... (Task `{task_id}`)*", suppress_embeds=True)

                    # Wait for task completion
                    completed = False
                    for _ in range(45):
                        await asyncio.sleep(2)
                        t = self.task_queue.get_task(task_id)
                        if t and t.get("status") == "COMPLETED":
                            result = t.get("result_payload", {})
                            resp_text = result.get("response") or result.get("answer") or "Task completed."

                            # Truncate response if exceeds Discord 2000 limit
                            if len(resp_text) > 1900:
                                chunk = resp_text[:1900] + "\n\n*(Full report available via download)*"
                            else:
                                chunk = resp_text

                            await message.channel.send(f"🤖 **Sentinel Response:**\n\n{chunk}", suppress_embeds=True)
                            completed = True
                            return
                        elif t and t.get("status") == "FAILED":
                            await message.channel.send(f"❌ Task failed: {t.get('error_message')}", suppress_embeds=True)
                            completed = True
                            return

                    if not completed:
                        t = self.task_queue.get_task(task_id)
                        status = t.get("status") if t else "UNKNOWN"
                        if status == "WAITING_APPROVAL":
                            await message.channel.send(
                                f"⚠️ Task `{task_id}` requires HITL approval in CUA-Sentinel dashboard before proceeding.",
                                suppress_embeds=True
                            )
                        else:
                            await message.channel.send(
                                f"⏳ Request still in progress (Task `{task_id}`, status: `{status}`). Check the web dashboard.",
                                suppress_embeds=True
                            )
                        return
                else:
                    await message.channel.send("❌ Task Queue is currently offline.", suppress_embeds=True)

        loop = asyncio.get_event_loop()
        self.bot_task = loop.create_task(self.client.start(token))
        logger.info("Discord Bot task scheduled.")

    async def send_notification(self, channel_id: str, title: str, description: str, color: int = 0x38bdf8) -> bool:
        """
        Outbound alert dispatcher to specific Discord Channel ID.
        """
        if not self.client or not self.client.is_ready():
            return False

        try:
            target_id = int(channel_id or self.target_channel_id)
            channel = self.client.get_channel(target_id)
            if not channel:
                channel = await self.client.fetch_channel(target_id)

            if channel:
                embed = discord.Embed(title=title, description=description, color=color)
                await channel.send(embed=embed)
                return True
        except Exception as e:
            logger.error(f"Failed sending Discord bot notification: {e}")

        return False

    def stop_bot(self):
        if self.client and not self.client.is_closed():
            asyncio.create_task(self.client.close())
            logger.info("Discord Bot service stopped.")
