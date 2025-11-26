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
            await db.execute('''
                CREATE TABLE IF NOT EXISTS applications (
                    user_id INTEGER PRIMARY KEY,
                    application_text TEXT,
                    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS user_data ( 
                    user_id INTEGER PRIMARY KEY, 
                    is_approved BOOLEAN DEFAULT 0
                )
            ''')
            await db.commit()

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if member.bot: return

        global LAST_JOIN_TIME, LAST_JOIN_MEMBER_ID
        current_time = time.time()
        
        if member.id == LAST_JOIN_MEMBER_ID and current_time - LAST_JOIN_TIME < 1.0:
            return
            
        LAST_JOIN_MEMBER_ID = member.id
        LAST_JOIN_TIME = current_time
        
        try:
            role = discord.utils.get(member.guild.roles, name=START_ROLE_NAME)
            if role: await member.add_roles(role)
        
            welcome_channel = member.guild.get_channel(WELCOME_CHANNEL_ID) 
            if welcome_channel:
                await welcome_channel.send(f'**ยินดีต้อนรับ** {member.mention} สู่โรงเรียนแห่งนี้! ✨\nกรุณาส่งประวัติของคุณด้วยคำสั่ง `/apply` เพื่อเข้าสังกัดค่ะ')

            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("INSERT OR IGNORE INTO user_data (user_id) VALUES (?)", (member.id,))
                await db.commit()
            
        except Exception as e:
            print(f"Error in on_member_join: {e}")
    
    @app_commands.command(name='apply')
    async def submit_application_slash(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ApplicationModal(self.bot, self.db_path))

class ApplicationModal(discord.ui.Modal, title='ส่งประวัติการสมัครเข้าสังกัด'):
    def __init__(self, bot, db_path):
        super().__init__()
        self.bot = bot
        self.db_path = db_path
        self.application_text = discord.ui.TextInput(label='ประวัติและรายละเอียด', style=discord.TextStyle.paragraph, placeholder='กรุณาใส่ประวัติโดยละเอียด (50+ ตัวอักษร)', required=True, min_length=50, max_length=1500)
        self.add_item(self.application_text)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True) 
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT application_text FROM applications WHERE user_id = ?", (interaction.user.id,)) as cursor:
                if await cursor.fetchone(): return await interaction.followup.send("❌ คุณส่งใบสมัครไปแล้ว", ephemeral=True)
            await db.execute("INSERT INTO applications (user_id, application_text) VALUES (?, ?)", (interaction.user.id, self.application_text.value))
            await db.commit()

        alert_channel = self.bot.get_channel(STAFF_ALERT_CHANNEL_ID)
        if alert_channel:
            embed = discord.Embed(title="🚨 ใบสมัครใหม่!", color=discord.Color.red())
            embed.add_field(name="ผู้สมัคร", value=f"{interaction.user.mention}", inline=False)
            embed.add_field(name="ประวัติ", value=self.application_text.value[:1024], inline=False)
            await alert_channel.send(content=f"📝 ใบสมัครจาก {interaction.user.mention}", embed=embed, view=AffiliationView(interaction.user.id, self.db_path))
        
        await interaction.followup.send("✅ **ส่งประวัติสำเร็จ!**", ephemeral=True)

class AffiliationView(discord.ui.View):
    def __init__(self, target_user_id, db_path):
        super().__init__(timeout=None)
        self.target_user_id = target_user_id
        self.db_path = db_path
        for key, name in AFFILIATION_ROLES.items(): self.add_item(self.create_button(key, name))
        self.add_item(self.create_reject_button())

    def create_button(self, key, name):
        btn = discord.ui.Button(label=name, style=discord.ButtonStyle.secondary, custom_id=f"affil_{key}_{self.target_user_id}")
        btn.callback = self.approve_callback
        return btn

    def create_reject_button(self):
        btn = discord.ui.Button(label="❌ ปฏิเสธ", style=discord.ButtonStyle.danger, custom_id=f"reject_{self.target_user_id}")
        btn.callback = self.reject_callback
        return btn

    async def approve_callback(self, interaction: discord.Interaction):
        await interaction.response.defer() 
        try: _, key, uid = interaction.data['custom_id'].split('_'); uid = int(uid)
        except: return
        
        member = interaction.guild.get_member(uid)
        if not member: return await interaction.followup.send("❌ ไม่พบผู้เล่น", ephemeral=True)
            
        role_name = AFFILIATION_ROLES[key]
        role = discord.utils.get(interaction.guild.roles, name=role_name)
        if role: await member.add_roles(role)
        
        newbie = discord.utils.get(interaction.guild.roles, name=START_ROLE_NAME)
        if newbie: await member.remove_roles(newbie)
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE user_data SET is_approved = 1 WHERE user_id = ?", (uid,))
            await db.execute("DELETE FROM applications WHERE user_id = ?", (uid,))
            await db.commit()
            
        await interaction.message.edit(content=f"✅ มอบยศ **{role_name}** ให้ {member.mention} แล้ว", view=None, embeds=[])

    async def reject_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        uid = int(interaction.data['custom_id'].split('_')[1])
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM applications WHERE user_id = ?", (uid,))
            await db.commit()
        
        member = interaction.guild.get_member(uid)
        await interaction.message.edit(content=f"🛑 ปฏิเสธแล้ว", view=None, embeds=[])
        if member: 
            try: await member.send("❌ ประวัติไม่ผ่านการพิจารณา กรุณาส่งใหม่")
            except: pass

async def setup(bot):
    await bot.add_cog(Roles(bot))
