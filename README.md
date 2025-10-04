# 🤖 Bot Interlink

Discord Bot với web interface để thêm users vào multiple servers.

## Features
- 🔐 OAuth2 authentication
- 💾 PostgreSQL persistent storage 
- 🌐 Web interface
- 🤖 Discord bot commands

## 📖 Commands

#### ### Tính năng cho Người dùng
- `!auth` - Lấy link ủy quyền cá nhân cho bot.
- `!add_me` - Tự động tham gia tất cả server của bot.
- `!check_token` - Kiểm tra trạng thái ủy quyền của bạn.
- `!ping` - Kiểm tra độ trễ kết nối của bot.
- `!help` - Hiển thị danh sách tất cả các lệnh.
- `!track` - Bắt đầu theo dõi một kênh để cảnh báo nếu không hoạt động.
- `!untrack` - Ngừng theo dõi một kênh.
---
#### ### Lệnh Quản trị (Chỉ dành cho Chủ Bot)
- `!status` - Xem trạng thái bot, số server và hệ thống lưu trữ.
- `!roster` - Hiển thị danh sách tất cả tài khoản đã ủy quyền.
- `!roster_move` - Thay đổi thứ tự của tài khoản trong roster.
- `!remove` - Xóa dữ liệu của một người dùng khỏi hệ thống.
- `!force_add` - Ép thêm một người dùng vào tất cả server.
- `!setupadmin` - Tạo và cấp vai trò Admin cho thành viên trên tất cả server.
- `!deploy` - Mở giao diện mời nhiều người dùng vào nhiều server.
- `!invite` - Mở giao diện mời một người dùng vào nhiều server.
- `!invitebot` - Lấy link mời cho một hoặc nhiều bot khác.
- `!create` - Mở giao diện tạo kênh hàng loạt trên nhiều server.
- `!getid` - Tìm ID kênh bằng tên trên nhiều server.
- `!storage_info` - Xem thông tin chi tiết về các hệ thống lưu trữ.
- `!migrate_tokens` - Di chuyển dữ liệu token giữa các hệ thống lưu trữ.

## Setup
1. Create Discord Application
2. Deploy to Render
3. Set environment variables
4. Setup PostgreSQL database

## Environment Variables
- `DISCORD_TOKEN`
- `DISCORD_CLIENT_ID` 
- `DISCORD_CLIENT_SECRET`
- `DATABASE_URL`
- `JSONBIN_API_KEY`
- `JSONBIN_BIN_ID`
