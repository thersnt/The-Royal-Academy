import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import time 
import os
from utils import load_data, PROFILE_FILE

DB_NAME = 'school_data.db'
STAFF_ROLE_NAME = 'Student Council'       
START_ROLE_NAME = 'newbie'              
WELCOME_CHANNEL_ID = 1441105584056303780 
STAFF_ALERT_CHANNEL_ID = 1441128039416201246

AFFILIATION_ROLES = {
    "ourea": "Ourea", 
    "gaia": "Gaia", 
    "salacia": "Salacia", 
    "noblia": "Noblia", 
    "ordinaria": "Ordinaria", 
    "professor": "Professor",
    "royalstaff": "Royal Staff"
}

LAST_JOIN_TIME = 0.0
LAST_JOIN_MEMBER_ID = 0

class Roles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = os.path.join(os.getcwd(), DB_NAME)

    async def cog_load(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''CREATE TABLE IF NOT EXISTS applications (user_id INTEGER PRIMARY KEY, application_text TEXT, submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            await db.execute('''CREATE TABLE IF NOT EXISTS user_data (user_id INTEGER PRIMARY KEY, is_approved BOOLEAN DEFAULT 0)''')
            await db.commit()

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if member.bot: return
        global LAST_JOIN_TIME, LAST_JOIN_MEMBER_ID
        if member.id == LAST_JOIN_MEMBER_ID and time.time() - LAST_JOIN_TIME < 1.0: return
        LAST_JOIN_MEMBER_ID, LAST_JOIN_TIME = member.id, time.time()
        
        role = discord.utils.get(member.guild.roles, name=START_ROLE_NAME)
        if role: await member.add_roles(role)
        
        ch = member.guild.get_channel(WELCOME_CHANNEL_ID) 
        if ch: await ch.send(f'**ยินดีต้อนรับ** {member.mention} ✨\nกรุณาส่งประวัติด้วยคำสั่ง `/apply`')

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT OR IGNORE INTO user_data (user_id) VALUES (?)", (member.id,))
            await db.commit()
    
    @app_commands.command(name='apply')
    async def apply(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ApplicationModal(self.bot, self.db_path))

class ApplicationModal(discord.ui.Modal, title='ใบสมัคร'):
    def __init__(self, bot, db):
        super().__init__()
        self.bot = bot
        self.db = db
        self.text = discord.ui.TextInput(label='ประวัติ', style=discord.TextStyle.paragraph, min_length=50, max_length=1500, required=True)
        self.add_item(self.text)

    async def on_submit(self, interaction):
        await interaction.response.defer(ephemeral=True) 
        async with aiosqlite.connect(self.db) as db:
            async with db.execute("SELECT 1 FROM applications WHERE user_id=?", (interaction.user.id,)) as c:
                if await c.fetchone(): return await interaction.followup.send("❌ ส่งไปแล้ว", ephemeral=True)
            await db.execute("INSERT INTO applications (user_id, application_text) VALUES (?, ?)", (interaction.user.id, self.text.value))
            await db.commit()

        ch = self.bot.get_channel(STAFF_ALERT_CHANNEL_ID)
        if ch:
            embed = discord.Embed(title="🚨 ใบสมัครใหม่", color=discord.Color.red())
            embed.add_field(name="User", value=interaction.user.mention)
            embed.add_field(name="Data", value=self.text.value[:1000])
            await ch.send(embed=embed, view=AffiliationView(interaction.user.id, self.db))
        await interaction.followup.send("✅ ส่งแล้ว", ephemeral=True)

class AffiliationView(discord.ui.View):
    def __init__(self, uid, db):
        super().__init__(timeout=None)
        self.uid = uid
        self.db = db
        for k, n in AFFILIATION_ROLES.items(): self.add_item(self.btn(k, n))
        self.add_item(self.reject_btn())

    def btn(self, k, n):
        b = discord.ui.Button(label=n, style=discord.ButtonStyle.secondary, custom_id=f"affil_{k}_{self.uid}")
        b.callback = self.approve
        return b

    def reject_btn(self):
        b = discord.ui.Button(label="❌ ปฏิเสธ", style=discord.ButtonStyle.danger, custom_id=f"reject_{self.uid}")
        b.callback = self.reject
        return b

    async def approve(self, interaction):
        await interaction.response.defer()
        try: _, k, uid = interaction.data['custom_id'].split('_'); uid = int(uid)
        except: return
        
        m = interaction.guild.get_member(uid)
        if not m: return await interaction.followup.send("❌ ไม่พบผู้เล่น", ephemeral=True)
        
        r = discord.utils.get(interaction.guild.roles, name=AFFILIATION_ROLES[k])
        if r: await m.add_roles(r)
        nr = discord.utils.get(interaction.guild.roles, name=START_ROLE_NAME)
        if nr: await m.remove_roles(nr)
        
        async with aiosqlite.connect(self.db) as db:
            await db.execute("UPDATE user_data SET is_approved=1 WHERE user_id=?", (uid,))
            await db.execute("DELETE FROM applications WHERE user_id=?", (uid,))
            await db.commit()
        await interaction.message.edit(content=f"✅ อนุมัติ {m.mention} -> {AFFILIATION_ROLES[k]}", view=None, embeds=[])

    async def reject(self, interaction):
        await interaction.response.defer()
        uid = int(interaction.data['custom_id'].split('_')[1])
        async with aiosqlite.connect(self.db) as db:
            await db.execute("DELETE FROM applications WHERE user_id=?", (uid,))
            await db.commit()
        await interaction.message.edit(content="🛑 ปฏิเสธแล้ว", view=None, embeds=[])

async def setup(bot):
    await bot.add_cog(Roles(bot))
