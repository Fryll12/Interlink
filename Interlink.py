# main.py - Discord Bot with PostgreSQL for persistent token storage
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

# Try to import psycopg2, fallback to JSON if not available
try:
    import psycopg2
    HAS_PSYCOPG2 = True
    print("✅ psycopg2 imported successfully")
except ImportError:
    HAS_PSYCOPG2 = False
    print("⚠️ WARNING: psycopg2 not available, using JSON storage only")

# --- LOAD ENVIRONMENT VARIABLES ---
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')
DATABASE_URL = os.getenv('DATABASE_URL')

if not DISCORD_TOKEN:
    exit("LỖI: Không tìm thấy DISCORD_TOKEN")
if not CLIENT_ID:
    exit("LỖI: Không tìm thấy DISCORD_CLIENT_ID")
if not CLIENT_SECRET:
    exit("LỖI: Không tìm thấy DISCORD_CLIENT_SECRET")

# --- RENDER CONFIGURATION ---
PORT = int(os.getenv('PORT', 5000))
RENDER_URL = os.getenv('RENDER_EXTERNAL_URL', f'http://127.0.0.1:{PORT}')
REDIRECT_URI = f'{RENDER_URL}/callback'

# --- DATABASE SETUP ---
def init_database():
    """Khởi tạo database và tạo bảng nếu chưa có"""
    if not DATABASE_URL or not HAS_PSYCOPG2:
        print("⚠️ WARNING: Không có DATABASE_URL hoặc psycopg2, sử dụng file JSON backup")
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
        print("🔄 Falling back to JSON file storage")
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

# --- FALLBACK JSON FUNCTIONS ---
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
    """Lấy access token (ưu tiên database, fallback JSON)"""
    user_id_str = str(user_id)
    
    # Try database first
    token = get_user_access_token_db(user_id_str)
    if token:
        return token
    
    # Fallback to JSON
    return get_user_access_token_json(user_id_str)

def save_user_token(user_id: str, access_token: str, username: str = None):
    """Lưu access token (database + JSON backup)"""
    success_db = save_user_token_db(user_id, access_token, username)
    success_json = save_user_token_json(user_id, access_token, username)
    return success_db or success_json

# --- DISCORD BOT SETUP ---
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, owner_id=1386710352426959011)

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

# --- DISCORD BOT EVENTS ---
@bot.event
async def on_ready():
    print(f'✅ Bot đăng nhập thành công: {bot.user.name}')
    print(f'🔗 Web server: {RENDER_URL}')
    print(f'🔑 Redirect URI: {REDIRECT_URI}')
    db_status = "Connected" if get_db_connection() else "JSON Fallback"
    print(f'💾 Database: {db_status}')
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
        title="🔐 Ủy quyền cho Bot",
        description=f"Nhấp vào link bên dưới để cho phép bot thêm bạn vào các server:",
        color=0x00ff00
    )
    embed.add_field(name="🔗 Link ủy quyền", value=f"[Nhấp vào đây]({auth_url})", inline=False)
    embed.add_field(name="📝 Lưu ý", value="Token sẽ được lưu an toàn và không mất khi restart", inline=False)
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
    else:
        embed = discord.Embed(
            title="❌ Chưa ủy quyền", 
            description="Bạn chưa ủy quyền cho bot. Hãy sử dụng `!auth`",
            color=0xff0000
        )
    
    await ctx.send(embed=embed)

@bot.command(name='status', help='Kiểm tra trạng thái bot và database.')
async def status(ctx):
    # Test database connection
    db_connection = get_db_connection()
    db_status = "✅ Connected" if db_connection else "❌ JSON Fallback"
    if db_connection:
        db_connection.close()
    
    embed = discord.Embed(title="🤖 Trạng thái Bot", color=0x0099ff)
    embed.add_field(name="📊 Server", value=f"{len(bot.guilds)} server", inline=True)
    embed.add_field(name="👥 Người dùng", value=f"{len(bot.users)} user", inline=True)
    embed.add_field(name="💾 Database", value=db_status, inline=True)
    embed.add_field(name="🌐 Web Server", value=f"[Truy cập]({RENDER_URL})", inline=False)
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
        
# --- FLASK WEB ROUTES ---
@app.route('/')
def index():
    auth_url = (
        f'https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}'
        f'&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify%20guilds.join'
    )
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Discord Bot Authorization</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                text-align: center;
                padding: 50px;
            }}
            .container {{
                background: rgba(255, 255, 255, 0.1);
                border-radius: 15px;
                padding: 30px;
                max-width: 600px;
                margin: 0 auto;
            }}
            .btn {{
                background: #7289da;
                color: white;
                padding: 15px 30px;
                border: none;
                border-radius: 5px;
                font-size: 18px;
                text-decoration: none;
                display: inline-block;
                margin: 20px;
                transition: background 0.3s;
            }}
            .btn:hover {{
                background: #5865f2;
            }}
            .info {{
                background: rgba(255, 255, 255, 0.05);
                border-radius: 10px;
                padding: 15px;
                margin: 20px 0;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 Discord Bot Authorization</h1>
            <p>Chào mừng bạn đến với hệ thống ủy quyền Discord Bot!</p>
            
            <div class="info">
                <h3>💾 Persistent Storage</h3>
                <p>Token của bạn sẽ được lưu an toàn và không bị mất khi restart service</p>
            </div>
            
            <a href="{auth_url}" class="btn">🔐 Đăng nhập với Discord</a>
            
            <div class="info">
                <h3>📋 Các lệnh bot:</h3>
                <p><code>!force_add &lt;User_ID&gt;</code> - (Chủ bot) Thêm người dùng bất kỳ</p>
                <p><code>!auth</code> - Lấy link ủy quyền</p>
                <p><code>!add_me</code> - Thêm bạn vào server</p>
                <p><code>!check_token</code> - Kiểm tra trạng thái token</p>
                <p><code>!status</code> - Trạng thái bot</p>
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

    # Lưu token vào database + JSON backup
    success = save_user_token(user_id, access_token, username)
    storage_info = "database và file backup" if success else "chỉ file backup"

    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Ủy quyền thành công!</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                text-align: center;
                padding: 50px;
            }}
            .container {{
                background: rgba(255, 255, 255, 0.1);
                border-radius: 15px;
                padding: 30px;
                max-width: 600px;
                margin: 0 auto;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>✅ Thành công!</h1>
            <p>Cảm ơn <strong>{username}</strong>!</p>
            <p>🎉 Token đã được lưu vào {storage_info}</p>
            <p>📝 Sử dụng <code>!add_me</code> trong Discord để vào server</p>
            <p>🔒 Token sẽ không bị mất khi service restart</p>
        </div>
    </body>
    </html>
    '''

@app.route('/health')
def health():
    """Health check endpoint"""
    db_connection = get_db_connection()
    db_status = db_connection is not None
    if db_connection:
        db_connection.close()
    
    return {
        "status": "ok", 
        "bot_connected": bot.is_ready(),
        "database_connected": db_status,
        "has_psycopg2": HAS_PSYCOPG2
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
        print("🔄 Keeping web server alive...")
        while True:
            time.sleep(60)

