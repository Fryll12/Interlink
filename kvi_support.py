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
        """Phân tích embed của Karuta để lấy thông tin"""
        try:
            description = embed.description or ""

            # Tìm tên nhân vật
            char_match = re.search(r"Character · \*\*([^\*]+)\*\*", description)
            character_name = char_match.group(1).strip() if char_match else None

            # Tìm câu hỏi trong dấu ngoặc kép
            question_match = re.search(r'"([^"]+)"', description)
            question = question_match.group(1).strip() if question_match else None

            # Tìm tất cả các dòng bắt đầu bằng emoji 1️⃣-5️⃣ và lấy nội dung
            choice_lines = re.findall(r'^(1️⃣|2️⃣|3️⃣|4️⃣|5️⃣)\s+(.+)$', description, re.MULTILINE)

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

            # Kiểm tra dữ liệu
            if not character_name or not question or len(choices) < 2:
                print(f"[PARSER] Thiếu dữ liệu - Character: {character_name}, Question: {bool(question)}, Choices: {len(choices)}")
                return None

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
        """Kiểm tra xem có phải tin nhắn KVI không"""
        try:
            description = embed.description or ""

            # Kiểm tra có "Visit Character" trong embed
            if "**Visit Character **" not in description:
                return False

            # Kiểm tra có emoji lựa chọn
            if not re.search(r'(1️⃣|2️⃣|3️⃣|4️⃣|5️⃣)', description):
                return False

            # Kiểm tra có câu hỏi trong dấu ngoặc kép
            if not re.search(r'"([^"]+)"', description):
                return False

            return True

        except Exception as e:
            print(f"❌ [KVI_CHECK] Lỗi: {e}")
            return False

    async def handle_kvi_message(self, message):
        print(f"\n[DEBUG] Step 1: Bot nhìn thấy tin nhắn từ '{message.author.name}'.")

        # Chỉ xử lý tin nhắn từ Karuta
        if message.author.id != KARUTA_ID:
            return

        try:
            await asyncio.sleep(1)
            message = await message.channel.fetch_message(message.id)
        except Exception as e:
            print(f"❌ [DEBUG] Lỗi tải tin nhắn: {e}")
            return

        # Kiểm tra có embed không
        if not message.embeds:
            return
        print("[DEBUG] Step 2: Tin nhắn Karuta có embed.")

        embed = message.embeds[0]

        # Kiểm tra có phải KVI không
        if not self.is_kvi_message(embed):
            print("[DEBUG] Thoát: Không phải tin nhắn KVI.")
            return
        print("[DEBUG] Step 3: Đây là câu hỏi KVI hợp lệ.")

        # Phân tích embed
        kvi_data = self.parse_karuta_embed(embed)
        if not kvi_data:
            print("[DEBUG] Thoát: Phân tích embed thất bại.")
            return
        print(f"[DEBUG] Step 4: Phân tích embed thành công - Character: {kvi_data['character']}")

        # Kiểm tra trùng lặp
        session = self.kvi_sessions.get(message.channel.id, {})
        if session.get("message_id") == message.id and session.get("last_question") == kvi_data["question"]:
            print("[DEBUG] Thoát: Bỏ qua sự kiện trùng lặp.")
            return
        print("[DEBUG] Step 5: Cập nhật session.")

        self.kvi_sessions[message.channel.id] = {
            "message_id": message.id,
            "last_question": kvi_data["question"]
        }

        # Gọi AI để phân tích
        print("[DEBUG] Step 6: Gọi AI để phân tích...")
        ai_result = await self.analyze_with_ai(kvi_data["character"], kvi_data["question"], kvi_data["choices"])
        if not ai_result:
            print("[DEBUG] Thoát: AI phân tích thất bại.")
            return

        # Tạo embed gợi ý
        print("[DEBUG] Step 7: Tạo embed gợi ý...")
        suggestion_embed = await self.create_suggestion_embed(kvi_data, ai_result)

        try:
            await message.channel.send(embed=suggestion_embed)
            print("[DEBUG] Step 8: ✅ Gửi gợi ý thành công!")
        except Exception as e:
            print(f"❌ [DEBUG] Step 8: Lỗi gửi tin nhắn: {e}")
