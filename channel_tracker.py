# channel_tracker.py
# Module (Cog) để theo dõi hoạt động của các kênh Discord.
# Phiên bản 3: Hỗ trợ cấu hình ngưỡng không hoạt động theo phút.

import discord
from discord.ext import commands, tasks
import psycopg2
import os
from datetime import datetime, timedelta, timezone

# --- Các hàm tương tác với Database (Synchronous) ---
DATABASE_URL = os.getenv('DATABASE_URL')

def db_connect():
    """Kết nối tới database."""
    try:
        return psycopg2.connect(DATABASE_URL, sslmode='require')
    except Exception as e:
        print(f"[Tracker] Lỗi kết nối database: {e}")
        return None

def init_tracker_db():
    """Tạo bảng 'tracked_channels' nếu chưa tồn tại."""
    conn = db_connect()
    if conn:
        try:
            with conn.cursor() as cur:
                # Thêm cột notification_channel_id để lưu kênh gửi thông báo
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS tracked_channels (
                        channel_id BIGINT PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        user_id BIGINT NOT NULL,
                        notification_channel_id BIGINT NOT NULL,
                        added_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                conn.commit()
            print("[Tracker] Bảng 'tracked_channels' trong database đã sẵn sàng.")
        finally:
            conn.close()

def db_add_channel(channel_id, guild_id, user_id, notification_channel_id):
    """Thêm một kênh vào database để theo dõi."""
    conn = db_connect()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO tracked_channels (channel_id, guild_id, user_id, notification_channel_id) VALUES (%s, %s, %s, %s) ON CONFLICT (channel_id) DO UPDATE SET user_id = EXCLUDED.user_id, notification_channel_id = EXCLUDED.notification_channel_id;",
                    (channel_id, guild_id, user_id, notification_channel_id)
                )
                conn.commit()
        finally:
            conn.close()

def db_remove_channel(channel_id):
    """Xóa một kênh khỏi database."""
    conn = db_connect()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM tracked_channels WHERE channel_id = %s;", (channel_id,))
                conn.commit()
        finally:
            conn.close()

def db_get_all_tracked():
    """Lấy danh sách tất cả các kênh đang được theo dõi."""
    conn = db_connect()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT channel_id, guild_id, user_id, notification_channel_id FROM tracked_channels;")
                results = cur.fetchall()
                return results
        finally:
            conn.close()
    return []

# Chạy khởi tạo bảng một lần khi bot load module này
init_tracker_db()

# --- Các thành phần UI (Views, Modals) ---

class TrackByIDModal(discord.ui.Modal, title="Theo dõi bằng ID Kênh"):
    """Modal để người dùng nhập ID của kênh muốn theo dõi."""
    channel_id_input = discord.ui.TextInput(
        label="ID của kênh cần theo dõi",
        placeholder="Dán ID của kênh văn bản vào đây...",
        required=True,
        min_length=17,
        max_length=20
    )

    async def on_submit(self, interaction: discord.Interaction):
        bot = interaction.client
        try:
            channel_id = int(self.channel_id_input.value)
        except ValueError:
            return await interaction.response.send_message("ID kênh không hợp lệ. Vui lòng chỉ nhập số.", ephemeral=True)

        channel_to_track = bot.get_channel(channel_id)
        if not isinstance(channel_to_track, discord.TextChannel):
            return await interaction.response.send_message("Không tìm thấy kênh văn bản với ID này, hoặc bot không có quyền truy cập.", ephemeral=True)
        
        # Thêm kênh vào database, lưu luôn ID kênh hiện tại để gửi thông báo
        await bot.loop.run_in_executor(
            None, db_add_channel, channel_to_track.id, channel_to_track.guild.id, interaction.user.id, interaction.channel_id
        )

        embed = discord.Embed(
            title="🛰️ Bắt đầu theo dõi",
            description=f"Thành công! Bot sẽ theo dõi kênh {channel_to_track.mention} trong server **{channel_to_track.guild.name}**.",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Cảnh báo sẽ được gửi về kênh này nếu kênh không hoạt động.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class TrackByNameModal(discord.ui.Modal):
    """Modal để người dùng nhập tên kênh sau khi đã chọn server."""
    def __init__(self, guild: discord.Guild):
        super().__init__(title=f"Tìm kênh trong '{guild.name}'")
        self.guild = guild

        self.channel_name_input = discord.ui.TextInput(
            label="Tên kênh cần theo dõi (không có #)",
            placeholder="Ví dụ: general, announcements, v.v.",
            required=True
        )
        self.add_item(self.channel_name_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        bot = interaction.client
        channel_name = self.channel_name_input.value.strip().lower().replace('-', ' ')
        
        found_channel = discord.utils.get(self.guild.text_channels, name=channel_name)
        
        if not found_channel:
            return await interaction.response.send_message(f"Không tìm thấy kênh nào có tên `{self.channel_name_input.value}` trong server **{self.guild.name}**.", ephemeral=True)

        # Thêm kênh vào database, lưu kênh hiện tại để gửi thông báo
        await bot.loop.run_in_executor(
            None, db_add_channel, found_channel.id, found_channel.guild.id, interaction.user.id, interaction.channel_id
        )

        embed = discord.Embed(
            title="🛰️ Bắt đầu theo dõi",
            description=f"Thành công! Bot sẽ theo dõi kênh {found_channel.mention} trong server **{self.guild.name}**.",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Cảnh báo sẽ được gửi về kênh này nếu kênh không hoạt động.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class TrackByNameView(discord.ui.View):
    """View chứa dropdown để chọn server."""
    def __init__(self, author_id: int, bot: commands.Bot):
        super().__init__(timeout=300)
        self.author_id = author_id
        
        server_options = [
            discord.SelectOption(label=guild.name, value=str(guild.id), emoji="🖥️")
            for guild in bot.guilds if guild.get_member(self.author_id)
        ]
        
        if server_options:
            self.add_item(discord.ui.Select(placeholder="Bước 1: Chọn server...", options=server_options[:25]))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Bạn không phải người dùng lệnh này!", ephemeral=True)
            return False
        return True

    @discord.ui.select()
    async def server_select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        selected_guild_id = int(select.values[0])
        guild = interaction.client.get_guild(selected_guild_id)
        if guild:
            await interaction.response.send_modal(TrackByNameModal(guild=guild))
        else:
            await interaction.response.send_message("Không tìm thấy server này.", ephemeral=True)


class TrackInitialView(discord.ui.View):
    """View ban đầu với hai lựa chọn: theo dõi bằng ID hoặc Tên."""
    def __init__(self, author_id: int, bot: commands.Bot):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.bot = bot

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Bạn không phải người dùng lệnh này!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Theo dõi bằng ID Kênh", style=discord.ButtonStyle.primary, emoji="🆔")
    async def track_by_id(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TrackByIDModal())

    @discord.ui.button(label="Theo dõi bằng Tên Kênh", style=discord.ButtonStyle.secondary, emoji="📝")
    async def track_by_name(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = TrackByNameView(author_id=self.author_id, bot=self.bot)
        embed = discord.Embed(
            title="Theo dõi bằng Tên Kênh",
            description="Sử dụng menu bên dưới để chọn server chứa kênh bạn muốn theo dõi.",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)


# --- Cog chính ---

class ChannelTracker(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Đọc ngưỡng theo PHÚT. Mặc định là 7 ngày (7 * 24 * 60 = 10080 phút)
        self.inactivity_threshold_minutes = int(os.getenv('INACTIVITY_THRESHOLD_MINUTES', 7 * 24 * 60))
        self.check_activity.start()

    def cog_unload(self):
        self.check_activity.cancel()

    @tasks.loop(minutes=30) # Chạy kiểm tra mỗi 30 phút
    async def check_activity(self):
        print(f"[{datetime.now()}] [Tracker] Bắt đầu kiểm tra kênh không hoạt động...")
        
        tracked_channels_data = await self.bot.loop.run_in_executor(None, db_get_all_tracked)
        
        for channel_id, guild_id, user_id, notification_channel_id in tracked_channels_data:
            notification_channel = self.bot.get_channel(notification_channel_id)
            if not notification_channel:
                print(f"[Tracker] LỖI: Không tìm thấy kênh thông báo {notification_channel_id} cho kênh {channel_id}. Đang xóa...")
                await self.bot.loop.run_in_executor(None, db_remove_channel, channel_id)
                continue

            channel_to_track = self.bot.get_channel(channel_id)
            if not channel_to_track:
                print(f"[Tracker] Kênh {channel_id} không còn tồn tại. Đang xóa...")
                await self.bot.loop.run_in_executor(None, db_remove_channel, channel_id)
                continue
            
            try:
                last_message = await channel_to_track.fetch_message(channel_to_track.last_message_id) if channel_to_track.last_message_id else None
                
                last_activity_time = last_message.created_at if last_message else channel_to_track.created_at
                time_since_activity = datetime.now(timezone.utc) - last_activity_time
                
                # So sánh với ngưỡng theo PHÚT
                if time_since_activity > timedelta(minutes=self.inactivity_threshold_minutes):
                    user_to_notify = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                    
                    embed = discord.Embed(
                        title="⚠️ Cảnh báo Kênh không hoạt động",
                        # Cập nhật thông báo để hiển thị theo phút
                        description=f"Kênh {channel_to_track.mention} trong server **{channel_to_track.guild.name}** đã không có tin nhắn mới trong hơn **{self.inactivity_threshold_minutes}** phút.",
                        color=discord.Color.orange()
                    )
                    embed.add_field(name="Lần hoạt động cuối", value=f"<t:{int(last_activity_time.timestamp())}:R>", inline=False)
                    embed.set_footer(text=f"Kênh này được thiết lập theo dõi bởi {user_to_notify.display_name if user_to_notify else f'User ID: {user_id}'}")

                    mention = user_to_notify.mention if user_to_notify else f"<@{user_id}>"
                    await notification_channel.send(content=f"Thông báo cho {mention}:", embed=embed)
                    
                    await self.bot.loop.run_in_executor(None, db_remove_channel, channel_id)
            
            except discord.Forbidden:
                print(f"[Tracker] Lỗi quyền: Bot không thể đọc lịch sử kênh {channel_to_track.name} ({channel_id}). Đang xóa...")
                await self.bot.loop.run_in_executor(None, db_remove_channel, channel_id)
            except Exception as e:
                print(f"[Tracker] Lỗi không xác định khi kiểm tra kênh {channel_id}: {e}")

    @check_activity.before_loop
    async def before_check_activity(self):
        await self.bot.wait_until_ready()

    @commands.command(name='track', help='Theo dõi hoạt động của một kênh.')
    async def track(self, ctx: commands.Context):
        embed = discord.Embed(
            title="🛰️ Thiết lập Theo dõi Kênh",
            description="Chọn phương thức bạn muốn dùng để xác định kênh cần theo dõi.",
            color=discord.Color.blue()
        )
        view = TrackInitialView(author_id=ctx.author.id, bot=self.bot)
        await ctx.send(embed=embed, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(ChannelTracker(bot))

