# Interlink.py (đã sửa lỗi)
import os
import json
import discord
import requests
import aiohttp # <--- LỖI 1: Thư viện này bị thiếu
import threading
from discord.ext import commands
from flask import Flask, request, redirect
from dotenv import load_dotenv

# --- CÀI ĐẶT BAN ĐẦU ---
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')
OWNER_ID = int(os.getenv('OWNER_ID', 0))

if not all([TOKEN, CLIENT_ID, CLIENT_SECRET, OWNER_ID]):
    exit("LỖI: Hãy chắc chắn DISCORD_TOKEN, CLIENT_ID, CLIENT_SECRET, và OWNER_ID đã được thiết lập trong file .env")

# ==============================================================================
# PHẦN 1: CODE CỦA BOT DISCORD
# ==============================================================================
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, owner_id=OWNER_ID)

def get_user_access_token(user_id: int):
    try:
        with open('tokens.json', 'r') as f:
            tokens = json.load(f)
            return tokens.get(str(user_id))
    except (FileNotFoundError, json.JSONDecodeError):
        return None

async def add_member_to_guild(guild_id: int, user_id: int, access_token: str):
    url = f"https://discord.com/api/v10/guilds/{guild_id}/members/{user_id}"
    headers = {
        "Authorization": f"Bot {TOKEN}",
        "Content-Type": "application/json"
    }
    data = {"access_token": access_token}
    
    async with aiohttp.ClientSession() as session:
        async with session.put(url, headers=headers, json=data) as response:
            if response.status in [201, 204]:
                return True, "Thành công hoặc đã có trong server"
            else:
                error_text = await response.text()
                return False, f"HTTP {response.status}: {error_text}"

@bot.event
async def on_ready():
    print(f'>>> Bot {bot.user.name} đã sẵn sàng!')

@bot.command(name='force_add', help='Thêm một người dùng vào tất cả các server.')
@commands.is_owner()
async def force_add(ctx, user_id_str: str):
    try:
        user_id = int(user_id_str)
    except ValueError:
        await ctx.send("⚠️ ID người dùng không hợp lệ. Vui lòng chỉ nhập số.")
        return
    await ctx.send(f"✅ Đã nhận lệnh! Bắt đầu quá trình thêm người dùng có ID `{user_id}`...")
    access_token = get_user_access_token(user_id)
    if not access_token:
        await ctx.send(f"❌ **Lỗi:** Không tìm thấy mã ủy quyền cho người dùng này.")
        return
    try:
        user_to_add = await bot.fetch_user(user_id)
    except discord.NotFound:
        await ctx.send(f"❌ Lỗi: Không tìm thấy người dùng có ID `{user_id}`.")
        return
    success_count = 0
    fail_count = 0
    for guild in bot.guilds:
        # LỖI 2: Không cần import aiohttp ở đây nữa vì đã import ở trên cùng
        success, message = await add_member_to_guild(guild.id, user_id, access_token)
        if success:
            print(f"👍 Thêm thành công {user_to_add.name} vào server {guild.name}: {message}")
            success_count += 1
        else:
            print(f"👎 Lỗi khi thêm vào {guild.name}: {message}")
            fail_count += 1
    await ctx.send(f"\n--- **HOÀN TẤT** --- \n✅ Thêm thành công vào **{success_count}** server.\n❌ Thất bại ở **{fail_count}** server.")

# ==============================================================================
# PHẦN 2: CODE CỦA WEB SERVER
# ==============================================================================
app = Flask(__name__)

@app.route('/')
def index():
    redirect_uri = os.environ.get('RENDER_EXTERNAL_URL', f'http://127.0.0.1:5000') + '/callback'
    auth_url = (
        f'https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}'
        f'&redirect_uri={redirect_uri}&response_type=code&scope=identify%20guilds.join'
    )
    return f'<h1>Chào mừng đến với trang ủy quyền!</h1><a href="{auth_url}">Đăng nhập với Discord</a>'

@app.route('/callback')
def callback():
    code = request.args.get('code')
    redirect_uri = os.environ.get('RENDER_EXTERNAL_URL', f'http://127.0.0.1:5000') + '/callback'
    # ... (phần còn lại của hàm callback giữ nguyên) ...
    token_url = 'https://discord.com/api/v10/oauth2/token'
    payload = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri,
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    token_response = requests.post(token_url, data=payload, headers=headers)
    token_data = token_response.json()
    access_token = token_data.get('access_token') # Dùng .get() để tránh lỗi nếu không có token
    if not access_token:
        return f"<h1>Lỗi</h1><p>Không thể lấy access token từ Discord. Phản hồi: {token_data}</p>"
    user_info_url = 'https://discord.com/api/v10/users/@me'
    headers = {'Authorization': f'Bearer {access_token}'}
    user_response = requests.get(user_info_url, headers=headers)
    user_data = user_response.json()
    user_id = user_data['id']
    username = user_data['username']
    try:
        with open('tokens.json', 'r') as f:
            tokens = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        tokens = {}
    tokens[user_id] = access_token
    with open('tokens.json', 'w') as f:
        json.dump(tokens, f, indent=4)
    return f'<h1>Thành công!</h1><p>Cảm ơn {username}, bạn đã ủy quyền thành công cho bot.</p>'

def run_flask():
    # Lấy cổng từ Render, nếu chạy ở local thì mặc định là 5000
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

# ==============================================================================
# PHẦN 3: CHẠY CẢ HAI
# ==============================================================================
if __name__ == "__main__":
    # Chạy web server trong một luồng (thread) riêng
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    print(">>> Web server đã khởi động trong luồng nền.")

    # Chạy bot trong luồng chính
    print(">>> Đang khởi động bot Discord...")
    bot.run(TOKEN)
