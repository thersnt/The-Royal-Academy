import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from aiohttp import web # นำเข้า web server

# โหลด Token (รองรับทั้ง .env และ Environment Variable ของ Render)
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# ตั้งค่า Intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

class RoyalBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents, help_command=None)

    async def setup_hook(self):
        # โหลดไฟล์ระบบต่างๆ (Cogs)
        extensions = [
            'cogs.roles',
            'cogs.profile',
            'cogs.economy',
            'cogs.shop',
            'cogs.inventory',
            'cogs.clubs',
            'cogs.school_activities',
            'cogs.rp_system',
            'cogs.features',
            'cogs.data_cleanup'
        ]
        
        for ext in extensions:
            try:
                await self.load_extension(ext)
                print(f"✅ Loaded extension: {ext}")
            except Exception as e:
                print(f"❌ Failed to load {ext}: {e}")

        # --- 🌐 RENDER KEEP-ALIVE ---
        # สร้าง Web Server จำลองเพื่อให้ Render ตรวจจับว่า App ทำงานอยู่ (Bind Port)
        app = web.Application()
        async def home(request):
            return web.Response(text="🤖 The Royal Academy Bot is Online!")
        
        app.router.add_get('/', home)
        runner = web.AppRunner(app)
        await runner.setup()
        
        # ดึง Port จาก Environment Variable (Render จะส่งค่า PORT มาให้)
        port = int(os.getenv("PORT", 8080))
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        print(f"🌐 Web server started on port {port} (Render Ready)")

    async def on_ready(self):
        print(f'✨ Logged in as {self.user} (ID: {self.user.id})')
        print('🏰 The Royal Academy System is Online!')
        try:
            synced = await self.tree.sync()
            print(f"🌳 Synced {len(synced)} slash commands")
        except Exception as e:
            print(f"⚠️ Sync failed: {e}")

bot = RoyalBot()

if __name__ == '__main__':
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Error: DISCORD_TOKEN not found. Please check your Render Environment Variables.")
