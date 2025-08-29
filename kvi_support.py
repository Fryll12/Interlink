import discord
import re
import os
import asyncio
import json
from typing import Optional, List, Dict
import aiohttp

# --- CẤU HÌNH ---
KARUTA_ID = 646937666251915264
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

class KVIHelper:
    def __init__(self, bot):
        self.bot = bot
        self.api_key = GEMINI_API_KEY
        self.http_session = None
        self.kvi_sessions = {}
        if not self.api_key:
            print("⚠️ [KVI] Cảnh báo: Không tìm thấy GEMINI_API_KEY.")

    async def async_setup(self):
        """Tạo HTTP session sau khi bot sẵn sàng"""
        if not self.http_session or self.http_session.closed:
            self.http_session = aiohttp.ClientSession()
            print("✅ [KVI] HTTP session đã sẵn sàng.")

    def parse_karuta_embed(self, embed) -> Optional[Dict]:
        """Phân tích embed của Karuta để lấy thông tin (đã cải tiến)"""
        try:
            description = embed.description or ""
            title = embed.title or ""
            
            print(f"[DEBUG] parse_karuta_embed: Tiêu đề embed: {title}")
            print(f"[DEBUG] parse_karuta_embed: Đoạn mô tả (500 ký tự đầu):\n{description[:500]}...")

            # Tìm tên nhân vật - Ưu tiên từ tiêu đề trước
            character_name = None
            
            # Cách 1: Tìm trong tiêu đề (dạng "**Tên Nhân Vật**")
            title_match = re.search(r'\*\*([^\*]+)\*\*', title)
            if title_match:
                character_name = title_match.group(1).strip()
                print(f"[DEBUG] parse_karuta_embed: Tìm thấy tên nhân vật trong tiêu đề: {character_name}")
            
            # Cách 2: Tìm trong mô tả (dạng "Character · **Tên**")
            if not character_name:
                char_match = re.search(r'Character[^\*]*\*\*([^\*]+)\*\*', description, re.IGNORECASE)
                if char_match:
                    character_name = char_match.group(1).strip()
                    print(f"[DEBUG] parse_karuta_embed: Tìm thấy tên nhân vật trong mô tả: {character_name}")
            
            # Cách 3: Tên đầu tiên trong ngoặc kép
            if not character_name:
                name_in_quotes = re.search(r'"([^"]+)"', description)
                if name_in_quotes:
                    character_name = name_in_quotes.group(1).strip()
                    print(f"[DEBUG] parse_karuta_embed: Tìm thấy tên nhân vật trong ngoặc kép: {character_name}")

            # Tìm câu hỏi trong dấu ngoặc kép
            question_match = re.search(r'"([^"]+)"', description)
            question = question_match.group(1).strip() if question_match else None
            print(f"[DEBUG] parse_karuta_embed: Câu hỏi tìm thấy: {question}")

            # Tìm tất cả các dòng bắt đầu bằng emoji 1️⃣-5️⃣
            choice_lines = re.findall(r'^(1️⃣|2️⃣|3️⃣|4️⃣|5️⃣)\s+(.+)$', description, re.MULTILINE)
            print(f"[DEBUG] parse_karuta_embed: Số dòng lựa chọn tìm thấy: {len(choice_lines)}")

            # Mapping emoji -> số
            emoji_to_number = {
                '1️⃣': 1, '2️⃣': 2, '3️⃣': 3, '4️⃣': 4, '5️⃣': 5
            }

            choices = []
            for emoji, text in choice_lines:
                if emoji in emoji_to_number:
                    choices.append({
                        "number": emoji_to_number[emoji],
                        "text": text.strip()
                    })

            print(f"[DEBUG] parse_karuta_embed: Số lựa chọn hợp lệ: {len(choices)}")

            # Kiểm tra dữ liệu tối thiểu
            if not question:
                print("[DEBUG] parse_karuta_embed: THẤT BẠI - Không tìm thấy câu hỏi")
                return None
                
            if len(choices) < 2:
                print(f"[DEBUG] parse_karuta_embed: THẤT BẠI - Chỉ có {len(choices)} lựa chọn (cần >=2)")
                return None

            # Nếu không tìm thấy tên nhân vật, sử dụng "Unknown Character"
            if not character_name:
                character_name = "Unknown Character"
                print("[DEBUG] parse_karuta_embed: Sử dụng tên mặc định: Unknown Character")

            print("[DEBUG] parse_karuta_embed: THÀNH CÔNG - Dữ liệu đầy đủ")
            return {"character": character_name, "question": question, "choices": choices}

        except Exception as e:
            print(f"❌ [PARSER] Lỗi: {e}")
            return None

    async def analyze_with_ai(self, character: str, question: str, choices: List[Dict]) -> Optional[Dict]:
        """Phân tích bằng Google Gemini"""
        if not self.api_key:
            return None

        if not self.http_session or self.http_session.closed:
            await self.async_setup()

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.api_key}"

        choices_text = "\n".join([f"{c['number']}. {c['text']}" for c in choices])
        prompt = (
            f"Phân tích tính cách '{character}' và trả lời câu hỏi: '{question}'\n"
            f"Lựa chọn:\n{choices_text}\n"
            f'JSON: {{"analysis":"phân tích ngắn","percentages":[{{"choice":1,"percentage":50}}]}}'
        )

        payload = {"contents": [{"parts": [{"text": prompt}]}]}

        try:
            async with self.http_session.post(url, json=payload, timeout=8) as response:
                if response.status == 200:
                    data = await response.json()
                    result_text = data["candidates"][0]["content"]["parts"][0]["text"]
                    result_text = result_text.strip().replace("```json", "").replace("```", "").strip()
                    return json.loads(result_text)
                else:
                    error_text = await response.text()
                    print(f"❌ [AI] Lỗi API ({response.status}): {error_text}")
                    return None
        except Exception as e:
            print(f"❌ [AI] Lỗi: {e}")
            return None

    async def create_suggestion_embed(self, kvi_data: Dict, ai_result: Dict) -> discord.Embed:
        """Tạo embed gợi ý"""
        embed = discord.Embed(
            title="🎯 KVI Helper",
            color=0x00ff88,
            description=f"**{kvi_data['character']}**\n*{kvi_data['question']}*"
        )

        percentages = sorted(ai_result.get('percentages', []), key=lambda x: x.get('percentage', 0), reverse=True)

        # Mapping emoji theo số thứ tự
        emoji_map = {1: '1️⃣', 2: '2️⃣', 3: '3️⃣', 4: '4️⃣', 5: '5️⃣'}
        available_choices = {c['number']: c['text'] for c in kvi_data['choices']}

        suggestions = []
        for item in percentages[:min(3, len(available_choices))]:
            choice_num = item.get('choice')
            percentage = item.get('percentage')
            if choice_num is None or percentage is None or choice_num not in available_choices:
                continue

            emoji = emoji_map.get(choice_num, f"{choice_num}️⃣")
            if percentage >= 50:
                suggestions.append(f"{emoji} **{percentage}%** ⭐")
            else:
                suggestions.append(f"{emoji} {percentage}%")

        if suggestions:
            embed.add_field(name="💡 Gợi ý", value="\n".join(suggestions), inline=False)

        analysis = ai_result.get('analysis', '')[:80]
        if analysis:
            embed.add_field(name="📝 Phân tích", value=analysis, inline=False)

        embed.set_footer(text=f"🤖 Gemini AI • {len(available_choices)} lựa chọn")
        return embed

    def is_kvi_message(self, embed) -> bool:
        """Kiểm tra xem có phải tin nhắn KVI không (đã đơn giản hóa)"""
        try:
            description = embed.description or ""
            print(f"[DEBUG] is_kvi_message: Kiểm tra nội dung embed...")

            # Điều kiện 1: Phải có emoji lựa chọn
            if not re.search(r'(1️⃣|2️⃣|3️⃣|4️⃣|5️⃣)', description):
                print("[DEBUG] is_kvi_message: THẤT BẠI - Không tìm thấy emoji lựa chọn")
                return False

            # Điều kiện 2: Phải có câu hỏi trong dấu ngoặc kép
            if not re.search(r'"([^"]+)"', description):
                print("[DEBUG] is_kvi_message: THẤT BẠI - Không tìm thấy câu hỏi trong ngoặc kép")
                return False

            print("[DEBUG] is_kvi_message: THÀNH CÔNG - Tất cả điều kiện đạt")
            return True

        except Exception as e:
            print(f"❌ [KVI_CHECK] Lỗi: {e}")
            return False

    async def handle_kvi_message(self, message):
        print(f"\n[DEBUG] Step 1: Bot nhìn thấy tin nhắn từ '{message.author.name}' (ID: {message.author.id}).")
    
        # Chỉ xử lý tin nhắn từ Karuta
        if message.author.id != KARUTA_ID:
            return
    
        # Cơ chế thử lại tải tin nhắn
        max_retries = 3
        retry_delay = 3  # Tăng từ 1 lên 3 giây
        
        for attempt in range(1, max_retries + 1):
            try:
                print(f"[DEBUG] Step 2.{attempt}: Đợi {retry_delay} giây trước khi tải lại tin nhắn...")
                await asyncio.sleep(retry_delay)
                
                # Tải lại tin nhắn từ Discord
                refreshed_message = await message.channel.fetch_message(message.id)
                print(f"[DEBUG] Step 2.{attempt}: Tải lại tin nhắn thành công")
                
                # Kiểm tra embed
                if not refreshed_message.embeds:
                    print(f"[DEBUG] Step 2.{attempt}: THẤT BẠI - Tin nhắn không có embed")
                    if attempt < max_retries:
                        print(f"[DEBUG] Step 2.{attempt}: Thử lại lần {attempt + 1}...")
                        continue
                    else:
                        print("[DEBUG] Step 2: THẤT BẠI - Đã thử 3 lần, tin nhắn vẫn không có embed")
                        return
                else:
                    print(f"[DEBUG] Step 2.{attempt}: THÀNH CÔNG - Tin nhắn có {len(refreshed_message.embeds)} embed")
                    message = refreshed_message  # Cập nhật message với phiên bản có embed
                    break
                    
            except discord.NotFound:
                print(f"[DEBUG] Step 2.{attempt}: Lỗi - Tin nhắn không tồn tại hoặc đã bị xóa")
                return
            except discord.Forbidden:
                print(f"[DEBUG] Step 2.{attempt}: Lỗi - Bot không có quyền đọc tin nhắn")
                return
            except discord.HTTPException as e:
                print(f"[DEBUG] Step 2.{attempt}: Lỗi HTTP {e.status}: {e.text}")
                if attempt < max_retries:
                    print(f"[DEBUG] Step 2.{attempt}: Thử lại lần {attempt + 1}...")
                    continue
                else:
                    print("[DEBUG] Step 2: THẤT BẠI - Đã thử 3 lần, không thể tải tin nhắn")
                    return
            except Exception as e:
                print(f"[DEBUG] Step 2.{attempt}: Lỗi không xác định: {e}")
                if attempt < max_retries:
                    print(f"[DEBUG] Step 2.{attempt}: Thử lại lần {attempt + 1}...")
                    continue
                else:
                    print("[DEBUG] Step 2: THẤT BẠI - Đã thử 3 lần, vẫn gặp lỗi")
                    return
    
        embed = message.embeds[0]
    
        # Kiểm tra có phải KVI không
        if not self.is_kvi_message(embed):
            print("[DEBUG] Step 3: THẤT BẠI - Không phải tin nhắn KVI")
            return
        print("[DEBUG] Step 3: THÀNH CÔNG - Đây là câu hỏi KVI hợp lệ")
    
        # Phân tích embed
        kvi_data = self.parse_karuta_embed(embed)
        if not kvi_data:
            print("[DEBUG] Step 4: THẤT BẠI - Phân tích embed thất bại")
            return
        print(f"[DEBUG] Step 4: THÀNH CÔNG - Phân tích embed thành công - Character: {kvi_data['character']}")
    
        # Kiểm tra trùng lặp
        session = self.kvi_sessions.get(message.channel.id, {})
        if session.get("message_id") == message.id and session.get("last_question") == kvi_data["question"]:
            print("[DEBUG] Step 5: THÀNH CÔNG - Bỏ qua sự kiện trùng lặp")
            return
        print("[DEBUG] Step 5: Cập nhật session")
    
        self.kvi_sessions[message.channel.id] = {
            "message_id": message.id,
            "last_question": kvi_data["question"]
        }
    
        # Gọi AI để phân tích
        print("[DEBUG] Step 6: Gọi AI để phân tích...")
        ai_result = await self.analyze_with_ai(kvi_data["character"], kvi_data["question"], kvi_data["choices"])
        if not ai_result:
            print("[DEBUG] Step 6: THẤT BẠI - AI phân tích thất bại")
            return
    
        # Tạo embed gợi ý
        print("[DEBUG] Step 7: Tạo embed gợi ý...")
        suggestion_embed = await self.create_suggestion_embed(kvi_data, ai_result)
    
        try:
            await message.channel.send(embed=suggestion_embed)
            print("[DEBUG] Step 8: THÀNH CÔNG - Gửi gợi ý thành công!")
        except Exception as e:
            print(f"❌ [DEBUG] Step 8: THẤT BẠI - Lỗi gửi tin nhắn: {e}")
