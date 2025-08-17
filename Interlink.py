# main.py - Discord Bot with PostgreSQL + JSONBin.io for persistent token storage
import os
import json
import asyncio
import threading
import discord
import aiohttp
import requests
from discord.ext import commands
from flask import Flask, request
from dotenv import load_dotenv
from urllib.parse import urlparse
import time

# Try to import psycopg2, fallback to JSONBin if not available
try:
    import psycopg2
    HAS_PSYCOPG2 = True
    print("✅ psycopg2 imported successfully")
except ImportError:
    HAS_PSYCOPG2 = False
    print("⚠️ WARNING: psycopg2 not available, using JSONBin.io storage only")

# --- LOAD ENVIRONMENT VARIABLES ---
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')
DATABASE_URL = os.getenv('DATABASE_URL')

# JSONBin.io configuration
JSONBIN_API_KEY = os.getenv('JSONBIN_API_KEY')  # Thêm vào .env file
JSONBIN_BIN_ID = os.getenv('JSONBIN_BIN_ID')    # Thêm vào .env file

if not DISCORD_TOKEN:
    exit("LỖI: Không tìm thấy DISCORD_TOKEN")
if not CLIENT_ID:
    exit("LỖI: Không tìm thấy DISCORD_CLIENT_ID")
if not CLIENT_SECRET:
    exit("LỖI: Không tìm thấy DISCORD_CLIENT_SECRET")

# Kiểm tra JSONBin config
if not JSONBIN_API_KEY or not JSONBIN_BIN_ID:
    print("⚠️ WARNING: JSONBin.io config not found, will create new bin if needed")

# --- RENDER CONFIGURATION ---
PORT = int(os.getenv('PORT', 5000))
RENDER_URL = os.getenv('RENDER_EXTERNAL_URL', f'http://127.0.0.1:{PORT}')
REDIRECT_URI = f'{RENDER_URL}/callback'

# --- JSONBIN.IO FUNCTIONS ---
class JSONBinStorage:
    def __init__(self):
        self.api_key = JSONBIN_API_KEY
        self.bin_id = JSONBIN_BIN_ID
        self.base_url = "https://api.jsonbin.io/v3"
        
    def _get_headers(self):
        """Tạo headers cho requests"""
        return {
            "Content-Type": "application/json",
            "X-Master-Key": self.api_key,
            "X-Access-Key": self.api_key
        }
    
    def create_bin(self, data=None):
        """Tạo bin mới nếu chưa có"""
        if data is None:
            data = {}
        
        try:
            response = requests.post(
                f"{self.base_url}/b",
                json=data,
                headers=self._get_headers()
            )
            
            if response.status_code == 200:
                result = response.json()
                self.bin_id = result['metadata']['id']
                print(f"✅ Created new JSONBin: {self.bin_id}")
                print(f"🔑 Add this to your .env: JSONBIN_BIN_ID={self.bin_id}")
                return self.bin_id
            else:
                print(f"❌ Failed to create bin: {response.text}")
                return None
        except Exception as e:
            print(f"❌ JSONBin create error: {e}")
            return None
    
    def read_data(self):
        """Đọc dữ liệu từ JSONBin"""
        if not self.bin_id:
            print("⚠️ No bin ID, creating new bin...")
            self.create_bin()
            return {}
            
        try:
            response = requests.get(
                f"{self.base_url}/b/{self.bin_id}/latest",
                headers=self._get_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('record', {})
            elif response.status_code == 404:
                print("⚠️ Bin not found, creating new one...")
                self.create_bin()
                return {}
            else:
                print(f"❌ Failed to read from JSONBin: {response.status_code}")
                return {}
        except Exception as e:
            print(f"❌ JSONBin read error: {e}")
            return {}
    
    def write_data(self, data):
        """Ghi dữ liệu vào JSONBin"""
        if not self.bin_id:
            print("⚠️ No bin ID, creating new bin...")
            if not self.create_bin(data):
                return False
        
        try:
            response = requests.put(
                f"{self.base_url}/b/{self.bin_id}",
                json=data,
                headers=self._get_headers()
            )
            
            if response.status_code == 200:
                print("✅ Data saved to JSONBin successfully")
                return True
            else:
                print(f"❌ Failed to save to JSONBin: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"❌ JSONBin write error: {e}")
            return False
    
    def get_user_token(self, user_id):
        """Lấy token của user từ JSONBin"""
        data = self.read_data()
        user_data = data.get(str(user_id))
        
        if isinstance(user_data, dict):
            return user_data.get('access_token')
        return user_data
    
    def save_user_token(self, user_id, access_token, username=None):
        """Lưu token của user vào JSONBin"""
        data = self.read_data()
        
        data[str(user_id)] = {
            'access_token': access_token,
            'username': username,
            'updated_at': str(time.time())
        }
        
        return self.write_data(data)

# Khởi tạo JSONBin storage
jsonbin_storage = JSONBinStorage()

# --- DATABASE SETUP ---
def init_database():
    """Khởi tạo database và tạo bảng nếu chưa có"""
    if not DATABASE_URL or not HAS_PSYCOPG2:
        print("⚠️ WARNING: Không có DATABASE_URL hoặc psycopg2, sử dụng JSONBin.io")
        return False
    
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        cursor = conn.cursor()
        
        # Tạo bảng user_tokens nếu chưa có
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_tokens (
                user_id VARCHAR(50) PRIMARY KEY,
                access_token TEXT NOT NULL,
                username VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ Database initialized successfully")
        return True
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("📄 Falling back to JSONBin.io storage")
        return False

# --- DATABASE FUNCTIONS ---
def get_db_connection():
    """Tạo connection tới database"""
    if DATABASE_URL and HAS_PSYCOPG2:
        try:
            return psycopg2.connect(DATABASE_URL, sslmode='require')
        except Exception as e:
            print(f"Database connection error: {e}")
            return None
    return None

def get_user_access_token_db(user_id: str):
    """Lấy access token từ database"""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT access_token FROM user_tokens WHERE user_id = %s", (user_id,))
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            return result[0] if result else None
        except Exception as e:
            print(f"Database error: {e}")
            if conn:
                conn.close()
    return None

def save_user_token_db(user_id: str, access_token: str, username: str = None):
    """Lưu access token vào database"""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO user_tokens (user_id, access_token, username) 
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) 
                DO UPDATE SET 
                    access_token = EXCLUDED.access_token,
                    username = EXCLUDED.username,
                    updated_at = CURRENT_TIMESTAMP
            ''', (user_id, access_token, username))
            conn.commit()
            cursor.close()
            conn.close()
            print(f"✅ Saved token for user {user_id} to database")
            return True
        except Exception as e:
            print(f"Database error: {e}")
            if conn:
                conn.close()
    return False

# --- FALLBACK JSON FUNCTIONS (kept for compatibility) ---
def get_user_access_token_json(user_id: str):
    """Backup: Lấy token từ file JSON"""
    try:
        with open('tokens.json', 'r') as f:
            tokens = json.load(f)
            data = tokens.get(str(user_id))
            if isinstance(data, dict):
                return data.get('access_token')
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        return None

def save_user_token_json(user_id: str, access_token: str, username: str = None):
    """Backup: Lưu token vào file JSON"""
    try:
        try:
            with open('tokens.json', 'r') as f:
                tokens = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            tokens = {}
        
        tokens[user_id] = {
            'access_token': access_token,
            'username': username,
            'updated_at': str(time.time())
        }
        
        with open('tokens.json', 'w') as f:
            json.dump(tokens, f, indent=4)
        print(f"✅ Saved token for user {user_id} to JSON file")
        return True
    except Exception as e:
        print(f"JSON file error: {e}")
        return False

# --- UNIFIED TOKEN FUNCTIONS ---
def get_user_access_token(user_id: int):
    """Lấy access token (Ưu tiên: Database > JSONBin.io > JSON file)"""
    user_id_str = str(user_id)
    
    # Try database first
    token = get_user_access_token_db(user_id_str)
    if token:
        return token
    
    # Try JSONBin.io
    if JSONBIN_API_KEY:
        token = jsonbin_storage.get_user_token(user_id_str)
        if token:
            return token
    
    # Fallback to JSON file (for local development)
    return get_user_access_token_json(user_id_str)

def save_user_token(user_id: str, access_token: str, username: str = None):
    """Lưu access token (Database + JSONBin.io + JSON backup)"""
    success_db = save_user_token_db(user_id, access_token, username)
    success_jsonbin = False
    success_json = False
    
    # Try JSONBin.io
    if JSONBIN_API_KEY:
        success_jsonbin = jsonbin_storage.save_user_token(user_id, access_token, username)
    
    # Local JSON backup (for development)
    success_json = save_user_token_json(user_id, access_token, username)
    
    return success_db or success_jsonbin or success_json

# --- DISCORD BOT SETUP ---
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, owner_id=1386710352426959011, help_command=None)

# --- FLASK WEB SERVER SETUP ---
app = Flask(__name__)

# --- UTILITY FUNCTIONS ---
async def add_member_to_guild(guild_id: int, user_id: int, access_token: str):
    """Thêm member vào guild sử dụng Discord API trực tiếp"""
    url = f"https://discord.com/api/v10/guilds/{guild_id}/members/{user_id}"
    headers = {
        "Authorization": f"Bot {DISCORD_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "access_token": access_token
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.put(url, headers=headers, json=data) as response:
            if response.status == 201:
                return True, "Thêm thành công"
            elif response.status == 204:
                return True, "User đã có trong server"
            else:
                error_text = await response.text()
                return False, f"HTTP {response.status}: {error_text}"
                
# --- INTERACTIVE UI COMPONENTS ---

# Lớp này định nghĩa giao diện lựa chọn server
class ServerSelectView(discord.ui.View):
    def __init__(self, author: discord.User, target_user: discord.User, guilds: list[discord.Guild]):
        super().__init__(timeout=180)  # Giao diện sẽ hết hạn sau 180 giây
        self.author = author
        self.target_user = target_user
        self.guilds = guilds
        self.selected_guilds = []

        # Tạo menu thả xuống (Select)
        self.add_item(self.create_server_select())

    def create_server_select(self):
        # Tạo các lựa chọn cho menu, mỗi lựa chọn là một server
        options = [
            discord.SelectOption(
                label=guild.name, 
                value=str(guild.id), 
                emoji='🖥️', 
                description=f"{guild.member_count} thành viên"
            )
            for guild in self.guilds
        ]
        
        server_select = discord.ui.Select(
            placeholder="Chọn các server bạn muốn mời vào...",
            min_values=1,
            max_values=len(self.guilds), # Cho phép chọn nhiều server
            options=options
        )
        
        # Gắn hàm callback để xử lý khi người dùng chọn
        server_select.callback = self.on_server_select
        return server_select

    async def on_server_select(self, interaction: discord.Interaction):
        # Hàm này được gọi khi có lựa chọn trong menu
        # Chỉ chủ bot mới có thể tương tác
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Bạn không có quyền tương tác với menu này.", ephemeral=True)
            return

        # Lưu lại danh sách ID của các server đã chọn
        self.selected_guilds = [int(value) for value in interaction.data['values']]
        await interaction.response.defer() # Báo cho Discord biết bot đã nhận được tương tác

    @discord.ui.button(label="Summon", style=discord.ButtonStyle.green, emoji="✨")
    async def summon_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Hàm này được gọi khi nút "Summon" được bấm
        # Chỉ chủ bot mới có thể tương tác
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Bạn không có quyền sử dụng nút này.", ephemeral=True)
            return
        
        if not self.selected_guilds:
            await interaction.response.send_message("Bạn chưa chọn server nào cả!", ephemeral=True)
            return

        # Vô hiệu hóa giao diện sau khi bấm
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        
        await interaction.followup.send(f"✅ Đã nhận lệnh! Bắt đầu mời **{self.target_user.name}** vào **{len(self.selected_guilds)}** server đã chọn...")

        # Bắt đầu quá trình mời
        access_token = get_user_access_token(self.target_user.id)
        if not access_token:
            await interaction.followup.send(f"❌ Người dùng **{self.target_user.name}** chưa ủy quyền cho bot.")
            return

        success_count = 0
        fail_count = 0
        
        for guild_id in self.selected_guilds:
            guild = bot.get_guild(guild_id)
            if not guild: continue
            
            try:
                success, message = await add_member_to_guild(guild.id, self.target_user.id, access_token)
                if success:
                    print(f"👍 Thêm thành công {self.target_user.name} vào server {guild.name}")
                    success_count += 1
                else:
                    print(f"👎 Lỗi khi thêm vào {guild.name}: {message}")
                    fail_count += 1
            except Exception as e:
                print(f"👎 Lỗi không xác định khi thêm vào {guild.name}: {e}")
                fail_count += 1
        
        embed = discord.Embed(title=f"📊 Kết quả mời {self.target_user.name}", color=0x00ff00)
        embed.add_field(name="✅ Thành công", value=f"{success_count} server", inline=True)
        embed.add_field(name="❌ Thất bại", value=f"{fail_count} server", inline=True)
        await interaction.followup.send(embed=embed)
        
# --- DISCORD BOT EVENTS ---
@bot.event
async def on_ready():
    print(f'✅ Bot đăng nhập thành công: {bot.user.name}')
    print(f'🔗 Web server: {RENDER_URL}')
    print(f'🔑 Redirect URI: {REDIRECT_URI}')
    
    # Check storage status
    db_status = "Connected" if get_db_connection() else "Unavailable"
    jsonbin_status = "Connected" if JSONBIN_API_KEY else "Not configured"
    print(f'💾 Database: {db_status}')
    print(f'🌐 JSONBin.io: {jsonbin_status}')
    
    try:
        synced = await bot.tree.sync()
        print(f"✅ Đã đồng bộ {len(synced)} lệnh slash.")
    except Exception as e:
        print(f"❌ Không thể đồng bộ lệnh slash: {e}")
    print('------')

# --- DISCORD BOT COMMANDS ---
@bot.command(name='ping', help='Kiểm tra độ trễ kết nối của bot.')
async def ping(ctx):
    latency = round(bot.latency * 1000)
    await ctx.send(f'🏓 Pong! Độ trễ là {latency}ms.')

@bot.command(name='auth', help='Lấy link ủy quyền để bot có thể thêm bạn vào server.')
async def auth(ctx):
    auth_url = (
        f'https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}'
        f'&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify%20guilds.join'
    )
    embed = discord.Embed(
        title="🔓 Ủy quyền cho Bot",
        description=f"Nhấp vào link bên dưới để cho phép bot thêm bạn vào các server:",
        color=0x00ff00
    )
    embed.add_field(name="🔗 Link ủy quyền", value=f"[Nhấp vào đây]({auth_url})", inline=False)
    embed.add_field(name="📌 Lưu ý", value="Token sẽ được lưu an toàn vào cloud storage", inline=False)
    await ctx.send(embed=embed)

@bot.command(name='add_me', help='Thêm bạn vào tất cả các server của bot.')
async def add_me(ctx):
    user_id = ctx.author.id
    await ctx.send(f"✅ Bắt đầu quá trình thêm {ctx.author.mention} vào các server...")
    
    access_token = get_user_access_token(user_id)
    if not access_token:
        embed = discord.Embed(
            title="❌ Chưa ủy quyền",
            description="Bạn chưa ủy quyền cho bot. Hãy sử dụng lệnh `!auth` trước.",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    
    success_count = 0
    fail_count = 0
    
    for guild in bot.guilds:
        try:
            member = guild.get_member(user_id)
            if member:
                print(f"👍 {ctx.author.name} đã có trong server {guild.name}")
                success_count += 1
                continue
            
            success, message = await add_member_to_guild(guild.id, user_id, access_token)
            
            if success:
                print(f"👍 Thêm thành công {ctx.author.name} vào server {guild.name}: {message}")
                success_count += 1
            else:
                print(f"👎 Lỗi khi thêm vào {guild.name}: {message}")
                fail_count += 1
                
        except Exception as e:
            print(f"👎 Lỗi không xác định khi thêm vào {guild.name}: {e}")
            fail_count += 1
    
    embed = discord.Embed(title="📊 Kết quả", color=0x00ff00)
    embed.add_field(name="✅ Thành công", value=f"{success_count} server", inline=True)
    embed.add_field(name="❌ Thất bại", value=f"{fail_count} server", inline=True)
    await ctx.send(embed=embed)

@bot.command(name='check_token', help='Kiểm tra xem bạn đã ủy quyền chưa.')
async def check_token(ctx):
    user_id = ctx.author.id
    token = get_user_access_token(user_id)
    
    if token:
        embed = discord.Embed(
            title="✅ Đã ủy quyền", 
            description="Bot đã có token của bạn và có thể thêm bạn vào server",
            color=0x00ff00
        )
        embed.add_field(name="💾 Lưu trữ", value="Token được lưu an toàn trên cloud", inline=False)
    else:
        embed = discord.Embed(
            title="❌ Chưa ủy quyền", 
            description="Bạn chưa ủy quyền cho bot. Hãy sử dụng `!auth`",
            color=0xff0000
        )
    
    await ctx.send(embed=embed)

@bot.command(name='status', help='Kiểm tra trạng thái bot và storage.')
async def status(ctx):
    # Test database connection
    db_connection = get_db_connection()
    db_status = "✅ Connected" if db_connection else "❌ Unavailable"
    if db_connection:
        db_connection.close()
    
    # Test JSONBin connection
    jsonbin_status = "✅ Configured" if JSONBIN_API_KEY else "❌ Not configured"
    
    embed = discord.Embed(title="🤖 Trạng thái Bot", color=0x0099ff)
    embed.add_field(name="📊 Server", value=f"{len(bot.guilds)} server", inline=True)
    embed.add_field(name="👥 Người dùng", value=f"{len(bot.users)} user", inline=True)
    embed.add_field(name="💾 Database", value=db_status, inline=True)
    embed.add_field(name="🌐 JSONBin.io", value=jsonbin_status, inline=True)
    embed.add_field(name="🌍 Web Server", value=f"[Truy cập]({RENDER_URL})", inline=False)
    await ctx.send(embed=embed)
    
@bot.command(name='force_add', help='(Chủ bot) Thêm một người dùng bất kỳ vào tất cả các server.')
@commands.is_owner()
async def force_add(ctx, user_to_add: discord.User):
    """
    Lệnh chỉ dành cho chủ bot để thêm một người dùng bất kỳ vào các server.
    Cách dùng: !force_add <User_ID> hoặc !force_add @TênNgườiDùng
    """
    user_id = user_to_add.id
    await ctx.send(f"✅ Đã nhận lệnh! Bắt đầu quá trình thêm {user_to_add.mention} vào các server...")
    
    access_token = get_user_access_token(user_id)
    if not access_token:
        embed = discord.Embed(
            title="❌ Người dùng chưa ủy quyền",
            description=f"Người dùng {user_to_add.mention} chưa ủy quyền cho bot. Hãy yêu cầu họ sử dụng lệnh `!auth` trước.",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    
    success_count = 0
    fail_count = 0
    
    for guild in bot.guilds:
        try:
            member = guild.get_member(user_id)
            if member:
                print(f"👍 {user_to_add.name} đã có trong server {guild.name}")
                success_count += 1
                continue
            
            success, message = await add_member_to_guild(guild.id, user_id, access_token)
            
            if success:
                print(f"👍 Thêm thành công {user_to_add.name} vào server {guild.name}: {message}")
                success_count += 1
            else:
                print(f"👎 Lỗi khi thêm vào {guild.name}: {message}")
                fail_count += 1
                
        except Exception as e:
            print(f"👎 Lỗi không xác định khi thêm vào {guild.name}: {e}")
            fail_count += 1
    
    embed = discord.Embed(title=f"📊 Kết quả thêm {user_to_add.name}", color=0x00ff00)
    embed.add_field(name="✅ Thành công", value=f"{success_count} server", inline=True)
    embed.add_field(name="❌ Thất bại", value=f"{fail_count} server", inline=True)
    await ctx.send(embed=embed)

@force_add.error
async def force_add_error(ctx, error):
    if isinstance(error, commands.NotOwner):
        await ctx.send("🚫 Lỗi: Bạn không có quyền sử dụng lệnh này!")
    elif isinstance(error, commands.UserNotFound):
        await ctx.send(f"❌ Lỗi: Không tìm thấy người dùng được chỉ định.")
    else:
        print(f"Lỗi khi thực thi lệnh force_add: {error}")
        await ctx.send(f"Đã có lỗi xảy ra khi thực thi lệnh. Vui lòng kiểm tra console.")
        
@bot.command(name='invite', help='(Chủ bot) Mở giao diện để chọn server mời người dùng vào.')
@commands.is_owner()
async def invite(ctx, user_to_add: discord.User):
    """
    Mở một giao diện tương tác để chọn server mời người dùng.
    """
    if not user_to_add:
        await ctx.send("Không tìm thấy người dùng này.")
        return
        
    # Tạo giao diện (View) và truyền các thông tin cần thiết
    view = ServerSelectView(author=ctx.author, target_user=user_to_add, guilds=bot.guilds)
    
    embed = discord.Embed(
        title=f"💌 Mời {user_to_add.name}",
        description="Hãy chọn các server bạn muốn mời người này vào từ menu bên dưới, sau đó nhấn nút 'Summon'.",
        color=0x0099ff
    )
    embed.set_thumbnail(url=user_to_add.display_avatar.url)
    
    await ctx.send(embed=embed, view=view)

# --- SLASH COMMANDS ---
@bot.tree.command(name="help", description="Hiển thị thông tin về các lệnh của bot")
async def help_slash(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤖 Trợ giúp về lệnh của Interlink Bot",
        description="Dưới đây là danh sách các lệnh bạn có thể sử dụng:",
        color=discord.Color.blue()
    )
    
    embed.add_field(name="`!auth`", value="Gửi cho bạn link để ủy quyền cho bot.", inline=False)
    embed.add_field(name="`!add_me`", value="Tự thêm chính bạn vào tất cả các server sau khi đã ủy quyền.", inline=False)
    embed.add_field(name="`!check_token`", value="Kiểm tra xem bạn đã ủy quyền cho bot hay chưa.", inline=False)
    embed.add_field(name="`!status`", value="Kiểm tra trạng thái hoạt động của bot và các dịch vụ.", inline=False)
    embed.add_field(name="`!invite <User ID/@User>`", value="**(Chủ bot)** Mở giao diện để chọn server mời một người dùng.", inline=False)
    embed.add_field(name="`!force_add <User ID/@User>`", value="**(Chủ bot)** Thêm một người dùng vào TẤT CẢ các server.", inline=False)
    
    embed.set_footer(text="Bot được phát triển với sự hỗ trợ của AI. Token được lưu trên cloud storage.")
    
    await interaction.response.send_message(embed=embed, ephemeral=True) # ephemeral=True chỉ gửi cho người dùng lệnh

@bot.command(name='help', help='Hiển thị bảng trợ giúp về các lệnh.')
async def help(ctx):
    embed = discord.Embed(
        title="🤖 Bảng Lệnh Của Interlink Bot",
        description="Dưới đây là danh sách các lệnh bạn có thể sử dụng:",
        color=0x0099ff # Bạn có thể đổi màu ở đây
    )

    embed.add_field(name="`!auth`", value="Gửi link để bạn ủy quyền, cho phép bot thêm bạn vào server.", inline=False)
    embed.add_field(name="`!add_me`", value="Tự thêm chính bạn vào tất cả các server sau khi đã ủy quyền.", inline=False)
    embed.add_field(name="`!check_token`", value="Kiểm tra xem bạn đã ủy quyền cho bot hay chưa.", inline=False)
    embed.add_field(name="`!status`", value="Kiểm tra trạng thái hoạt động của bot và storage systems.", inline=False)

    # Chỉ hiển thị các lệnh của chủ bot cho chủ bot
    if await bot.is_owner(ctx.author):
        embed.add_field(name="👑 Lệnh Dành Cho Chủ Bot 👑", value="----------------------------------", inline=False)
        embed.add_field(name="`!invite <User ID/@User>`", value="Mở giao diện để chọn và mời một người dùng vào các server.", inline=False)
        embed.add_field(name="`!force_add <User ID/@User>`", value="Ép thêm một người dùng vào TẤT CẢ các server.", inline=False)

    embed.set_footer(text="Chọn một lệnh và bắt đầu! Token được lưu trên cloud storage.")
    embed.set_thumbnail(url=bot.user.display_avatar.url) # Thêm avatar của bot vào embed

    await ctx.send(embed=embed)

# --- ADDITIONAL JSONBIN MANAGEMENT COMMANDS ---
@bot.command(name='storage_info', help='(Chủ bot) Hiển thị thông tin về storage systems.')
@commands.is_owner()
async def storage_info(ctx):
    """Hiển thị thông tin chi tiết về các storage systems"""
    
    # Test Database
    db_connection = get_db_connection()
    if db_connection:
        try:
            cursor = db_connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM user_tokens")
            db_count = cursor.fetchone()[0]
            cursor.close()
            db_connection.close()
            db_info = f"✅ Connected ({db_count} tokens)"
        except:
            db_info = "❌ Connection Error"
    else:
        db_info = "❌ Not Available"
    
    # Test JSONBin
    if JSONBIN_API_KEY and JSONBIN_BIN_ID:
        try:
            data = jsonbin_storage.read_data()
            jsonbin_count = len(data) if isinstance(data, dict) else 0
            jsonbin_info = f"✅ Connected ({jsonbin_count} tokens)"
        except:
            jsonbin_info = "❌ Connection Error"
    else:
        jsonbin_info = "❌ Not Configured"
    
    embed = discord.Embed(title="💾 Storage Systems Info", color=0x0099ff)
    embed.add_field(name="🗃️ PostgreSQL Database", value=db_info, inline=False)
    embed.add_field(name="🌐 JSONBin.io", value=jsonbin_info, inline=False)
    
    if JSONBIN_BIN_ID:
        embed.add_field(name="📋 JSONBin Bin ID", value=f"`{JSONBIN_BIN_ID}`", inline=False)
    
    embed.add_field(name="ℹ️ Hierarchy", value="Database → JSONBin.io → Local JSON", inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name='migrate_tokens', help='(Chủ bot) Migrate tokens between storage systems.')
@commands.is_owner()
async def migrate_tokens(ctx, source: str = None, target: str = None):
    """
    Migrate tokens between storage systems
    Usage: !migrate_tokens <source> <target>
    Sources/Targets: db, jsonbin, json
    """
    
    if not source or not target:
        embed = discord.Embed(
            title="📦 Token Migration",
            description="Migrate tokens between storage systems",
            color=0x00ff00
        )
        embed.add_field(
            name="Usage", 
            value="`!migrate_tokens <source> <target>`\n\nValid options:\n• `db` - PostgreSQL Database\n• `jsonbin` - JSONBin.io\n• `json` - Local JSON file", 
            inline=False
        )
        embed.add_field(
            name="Examples", 
            value="`!migrate_tokens json jsonbin`\n`!migrate_tokens db jsonbin`", 
            inline=False
        )
        await ctx.send(embed=embed)
        return
    
    await ctx.send(f"🔄 Starting migration from {source} to {target}...")
    
    # Get source data
    source_data = {}
    if source == "db":
        conn = get_db_connection()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT user_id, access_token, username FROM user_tokens")
                rows = cursor.fetchall()
                for row in rows:
                    source_data[row[0]] = {
                        'access_token': row[1],
                        'username': row[2],
                        'updated_at': str(time.time())
                    }
                cursor.close()
                conn.close()
            except Exception as e:
                await ctx.send(f"❌ Database read error: {e}")
                return
    elif source == "jsonbin":
        try:
            source_data = jsonbin_storage.read_data()
        except Exception as e:
            await ctx.send(f"❌ JSONBin read error: {e}")
            return
    elif source == "json":
        try:
            with open('tokens.json', 'r') as f:
                source_data = json.load(f)
        except Exception as e:
            await ctx.send(f"❌ JSON file read error: {e}")
            return
    
    if not source_data:
        await ctx.send(f"❌ No data found in {source}")
        return
    
    # Write to target
    success_count = 0
    fail_count = 0
    
    for user_id, token_data in source_data.items():
        if isinstance(token_data, dict):
            access_token = token_data.get('access_token')
            username = token_data.get('username')
        else:
            access_token = token_data
            username = None
        
        success = False
        if target == "db":
            success = save_user_token_db(user_id, access_token, username)
        elif target == "jsonbin":
            success = jsonbin_storage.save_user_token(user_id, access_token, username)
        elif target == "json":
            success = save_user_token_json(user_id, access_token, username)
        
        if success:
            success_count += 1
        else:
            fail_count += 1
    
    embed = discord.Embed(title="📦 Migration Complete", color=0x00ff00)
    embed.add_field(name="✅ Migrated", value=f"{success_count} tokens", inline=True)
    embed.add_field(name="❌ Failed", value=f"{fail_count} tokens", inline=True)
    embed.add_field(name="📊 Total", value=f"{len(source_data)} tokens found", inline=True)
    
    await ctx.send(embed=embed)
    
# --- FLASK WEB ROUTES ---
@app.route('/')
def index():
    auth_url = (
        f'https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}'
        f'&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify%20guilds.join'
    )
    
    # Storage status for display
    db_status = "🟢 Connected" if get_db_connection() else "🔴 Unavailable"
    jsonbin_status = "🟢 Configured" if JSONBIN_API_KEY else "🔴 Not configured"
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Discord Bot Authorization</title>
        <style>
            body {{
                font-family: 'Segoe UI', Arial, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                text-align: center;
                padding: 30px;
                margin: 0;
            }}
            .container {{
                background: rgba(255, 255, 255, 0.1);
                backdrop-filter: blur(10px);
                border-radius: 20px;
                padding: 40px;
                max-width: 700px;
                margin: 0 auto;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            }}
            .btn {{
                background: linear-gradient(135deg, #7289da, #5865f2);
                color: white;
                padding: 15px 30px;
                border: none;
                border-radius: 10px;
                font-size: 18px;
                font-weight: 600;
                text-decoration: none;
                display: inline-block;
                margin: 20px;
                transition: all 0.3s ease;
                box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
            }}
            .btn:hover {{
                background: linear-gradient(135deg, #5865f2, #4752c4);
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(0, 0, 0, 0.3);
            }}
            .info-box {{
                background: rgba(255, 255, 255, 0.1);
                border-radius: 15px;
                padding: 20px;
                margin: 20px 0;
                border-left: 4px solid #00d4aa;
            }}
            .status-grid {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 15px;
                margin: 20px 0;
            }}
            .status-item {{
                background: rgba(255, 255, 255, 0.08);
                padding: 15px;
                border-radius: 10px;
                font-size: 14px;
            }}
            .commands {{
                text-align: left;
                background: rgba(0, 0, 0, 0.2);
                padding: 20px;
                border-radius: 10px;
                margin: 20px 0;
            }}
            .commands code {{
                background: rgba(255, 255, 255, 0.2);
                padding: 2px 6px;
                border-radius: 4px;
                font-family: 'Courier New', monospace;
            }}
            h1 {{ margin-top: 0; font-size: 2.5em; }}
            h3 {{ color: #00d4aa; margin-bottom: 10px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 Discord Bot Authorization</h1>
            <p style="font-size: 1.2em;">Chào mừng bạn đến với hệ thống ủy quyền Discord Bot!</p>
            
            <div class="info-box">
                <h3>☁️ Cloud Storage</h3>
                <p>Token của bạn sẽ được lưu an toàn trên cloud và không bị mất khi restart service</p>
                <div class="status-grid">
                    <div class="status-item">
                        <strong>🗃️ Database:</strong><br>{db_status}
                    </div>
                    <div class="status-item">
                        <strong>🌐 JSONBin.io:</strong><br>{jsonbin_status}
                    </div>
                </div>
            </div>
            
            <a href="{auth_url}" class="btn">🔑 Đăng nhập với Discord</a>
            
            <div class="commands">
                <h3>📋 Các lệnh bot:</h3>
                <p><code>!auth</code> - Lấy link ủy quyền</p>
                <p><code>!add_me</code> - Thêm bạn vào server</p>
                <p><code>!check_token</code> - Kiểm tra trạng thái token</p>
                <p><code>!status</code> - Trạng thái bot và storage</p>
                <hr style="border: 1px solid rgba(255,255,255,0.3); margin: 15px 0;">
                <p><strong>Lệnh chủ bot:</strong></p>
                <p><code>!invite &lt;User_ID&gt;</code> - Giao diện mời người dùng</p>
                <p><code>!force_add &lt;User_ID&gt;</code> - Thêm người dùng bất kỳ</p>
            </div>
            
            <div class="info-box">
                <h3>🔒 Bảo mật</h3>
                <p>• Token được mã hóa và lưu trữ an toàn<br>
                • Không lưu trữ mật khẩu Discord<br>
                • Chỉ sử dụng quyền cần thiết</p>
            </div>
        </div>
    </body>
    </html>
    '''

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return "❌ Lỗi: Không nhận được mã ủy quyền từ Discord.", 400

    token_url = 'https://discord.com/api/v10/oauth2/token'
    payload = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI,
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}

    token_response = requests.post(token_url, data=payload, headers=headers)
    if token_response.status_code != 200:
        return f"❌ Lỗi khi lấy token: {token_response.text}", 500
    
    token_data = token_response.json()
    access_token = token_data['access_token']

    user_info_url = 'https://discord.com/api/v10/users/@me'
    headers = {'Authorization': f'Bearer {access_token}'}
    user_response = requests.get(user_info_url, headers=headers)
    
    if user_response.status_code != 200:
        return "❌ Lỗi: Không thể lấy thông tin người dùng.", 500

    user_data = user_response.json()
    user_id = user_data['id']
    username = user_data['username']

    # Lưu token vào các storage systems
    success = save_user_token(user_id, access_token, username)
    
    # Determine storage info
    storage_methods = []
    if get_db_connection():
        storage_methods.append("PostgreSQL Database")
    if JSONBIN_API_KEY:
        storage_methods.append("JSONBin.io Cloud")
    if not storage_methods:
        storage_methods.append("Local JSON (fallback)")
    
    storage_info = " + ".join(storage_methods)

    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Ủy quyền thành công!</title>
        <style>
            body {{
                font-family: 'Segoe UI', Arial, sans-serif;
                background: linear-gradient(135deg, #00d4aa 0%, #667eea 100%);
                color: white;
                text-align: center;
                padding: 50px;
                margin: 0;
            }}
            .container {{
                background: rgba(255, 255, 255, 0.15);
                backdrop-filter: blur(15px);
                border-radius: 20px;
                padding: 40px;
                max-width: 600px;
                margin: 0 auto;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            }}
            .success-icon {{
                font-size: 4em;
                margin-bottom: 20px;
                animation: pulse 2s infinite;
            }}
            @keyframes pulse {{
                0% {{ transform: scale(1); }}
                50% {{ transform: scale(1.1); }}
                100% {{ transform: scale(1); }}
            }}
            .info-box {{
                background: rgba(255, 255, 255, 0.1);
                border-radius: 10px;
                padding: 15px;
                margin: 15px 0;
                border-left: 4px solid #00ff88;
            }}
            h1 {{ margin-top: 0; color: #00ff88; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="success-icon">✅</div>
            <h1>Thành công!</h1>
            <p style="font-size: 1.3em;">Cảm ơn <strong>{username}</strong>!</p>
            
            <div class="info-box">
                <strong>💾 Token đã được lưu vào:</strong><br>
                {storage_info}
            </div>
            
            <div class="info-box">
                <strong>🚀 Sử dụng ngay:</strong><br>
                Gõ <code>!add_me</code> trong Discord để vào server
            </div>
            
            <div class="info-box">
                <strong>🔒 Bảo mật:</strong><br>
                Token được lưu trữ an toàn trên cloud và không bị mất khi service restart
            </div>
        </div>
    </body>
    </html>
    '''

@app.route('/health')
def health():
    """Health check endpoint với thông tin chi tiết"""
    db_connection = get_db_connection()
    db_status = db_connection is not None
    if db_connection:
        db_connection.close()
    
    # Test JSONBin connection
    jsonbin_status = False
    if JSONBIN_API_KEY and JSONBIN_BIN_ID:
        try:
            test_data = jsonbin_storage.read_data()
            jsonbin_status = True
        except:
            jsonbin_status = False
    
    return {
        "status": "ok", 
        "bot_connected": bot.is_ready(),
        "storage": {
            "database_connected": db_status,
            "jsonbin_configured": JSONBIN_API_KEY is not None,
            "jsonbin_working": jsonbin_status,
            "has_psycopg2": HAS_PSYCOPG2
        },
        "servers": len(bot.guilds) if bot.is_ready() else 0,
        "users": len(bot.users) if bot.is_ready() else 0
    }

# --- THREADING FUNCTION ---
def run_flask():
    """Chạy Flask server"""
    app.run(host='0.0.0.0', port=PORT, debug=False)

# --- MAIN EXECUTION ---
if __name__ == '__main__':
    print("🚀 Đang khởi động Discord Bot + Web Server...")
    print(f"🔧 PORT: {PORT}")
    print(f"🔧 Render URL: {RENDER_URL}")
    
    # Initialize database
    database_initialized = init_database()
    
    # Test JSONBin connection
    if JSONBIN_API_KEY:
        print("🌐 Testing JSONBin.io connection...")
        try:
            test_data = jsonbin_storage.read_data()
            print(f"✅ JSONBin.io connected successfully")
            if isinstance(test_data, dict) and len(test_data) > 0:
                print(f"📊 Found {len(test_data)} existing tokens in JSONBin")
        except Exception as e:
            print(f"⚠️ JSONBin.io connection issue: {e}")
    else:
        print("⚠️ JSONBin.io not configured")
    
    try:
        # Start Flask server in separate thread
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        print(f"🌐 Web server started on port {PORT}")
        
        # Wait for Flask to start
        time.sleep(2)
        
        # Start Discord bot in main thread
        print("🤖 Starting Discord bot...")
        bot.run(DISCORD_TOKEN)
        
    except Exception as e:
        print(f"❌ Startup error: {e}")
        print("📄 Keeping web server alive...")
        while True:
            time.sleep(60)
