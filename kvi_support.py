# File: kvi_support.py (Phiên bản Google Gemini - Sửa lỗi và tối ưu hóa)
import discord
import re
import os
import asyncio
import json
from typing import Optional, List, Dict
import aiohttp # Sử dụng aiohttp để gọi API bất đồng bộ

# --- CẤU HÌNH ---
KARUTA_ID = 646937666251915264
KVI_CHANNELS_STR = os.getenv('KVI_CHANNELS', '')
KVI_CHANNELS = [int(ch.strip()) for ch in KVI_CHANNELS_STR.split(',') if ch.strip().isdigit()]
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY') # Đổi tên biến môi trường cho nhất quán

# --- LOGIC CHÍNH ---
# Dán toàn bộ class này vào kvi_support.py, thay thế cho class cũ

class KVIHelper:
    def __init__(self, bot):
        self.bot = bot
        self.api_key = GEMINI_API_KEY
        # THAY ĐỔI 1: Khởi tạo là None, sẽ tạo sau
        self.http_session = None
        if not self.api_key:
            print("⚠️ [KVI] Cảnh báo: Không tìm thấy GEMINI_API_KEY.")

    async def async_setup(self):
        """
        Hàm này sẽ được gọi sau khi bot đã sẵn sàng.
        Nó tạo ra ClientSession một cách an toàn.
        """
        self.http_session = aiohttp.ClientSession()
        print("✅ [KVI] Aiohttp client session đã được tạo.")

    def parse_karuta_embed(self, embed) -> Optional[Dict]:
        # ... (Hàm này giữ nguyên, không cần thay đổi) ...
        description = embed.description or ""
        char_match = re.search(r"Character · \*\*([^\*]+)\*\*", description)
        character_name = char_match.group(1).strip() if char_match else None
        question_match = re.search(r'"([^"]*)"', description)
        question = question_match.group(1).strip() if question_match else None
        choices = []
        choice_lines = re.findall(r'^\d️⃣\s+(.+)$', description, re.MULTILINE)
        for i, choice in enumerate(choice_lines, 1):
            choices.append({"number": i, "text": choice.strip()})
        
        if not all([character_name, question, choices]):
            return None
        return {"character": character_name, "question": question, "choices": choices}

    async def analyze_with_ai(self, character: str, question: str, choices: List[Dict]) -> Optional[Dict]:
        # ... (Hàm này giữ nguyên, không cần thay đổi) ...
        if not self.api_key:
            print("Lỗi: AI Model chưa được cấu hình vì thiếu API key.")
            return None
        
        # THAY ĐỔI 2: Đảm bảo session đã được tạo
        if not self.http_session:
            await self.async_setup()

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.api_key}"
        
        choices_text = "\n".join([f"{c['number']}. {c['text']}" for c in choices])
        prompt = (
            f"You are an expert anime character analyst. Analyze the personality of '{character}'. "
            f"Based on their personality, determine the most likely correct answer to the question: '{question}'.\n"
            f"Choices:\n{choices_text}\n"
            f"Respond ONLY with a valid JSON object in the format: "
            f'{{"analysis":"brief analysis","percentages":[{{"choice":1,"percentage":_}},{{"choice":2,"percentage":_}}]}}'
        )

        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }

        try:
            print("[INTERLINK KVI] Đang gửi yêu cầu tới Google Gemini...")
            async with self.http_session.post(url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    result_text = data["candidates"][0]["content"]["parts"][0]["text"]
                    result_text = result_text.strip().replace("```json", "").replace("```", "").strip()
                    print("✅ [GEMINI] Phân tích thành công!")
                    return json.loads(result_text)
                else:
                    error_text = await response.text()
                    print(f"❌ [GEMINI] Lỗi API ({response.status}): {error_text}")
                    return None
        except Exception as e:
            print(f"❌ [GEMINI] Lỗi kết nối hoặc xử lý: {e}")
            return None

    async def create_suggestion_embed(self, kvi_data: Dict, ai_result: Dict) -> discord.Embed:
        # ... (Hàm này giữ nguyên, không cần thay đổi) ...
        embed = discord.Embed(title="🤖 Interlink KVI Helper (Google AI)", color=0x4285F4)
        description_lines = [
            f"**Character:** {kvi_data['character']}",
            f"**Question:** \"{kvi_data['question']}\"",
            "",
            "**AI Analysis:**",
            ai_result.get('analysis', 'Đang phân tích...'),
            "",
            "**Suggestions:**"
        ]
        
        percentages = sorted(ai_result.get('percentages', []), key=lambda x: x.get('percentage', 0), reverse=True)
        
        for item in percentages:
            choice_num = item.get('choice')
            percentage = item.get('percentage')
            if choice_num is None or percentage is None: continue

            emoji = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣'][choice_num - 1]
            choice_text = next((c['text'] for c in kvi_data['choices'] if c['number'] == choice_num), "")
            description_lines.append(f"{emoji} **{percentage}%** - {choice_text}")
        
        embed.description = "\n".join(description_lines)
        embed.set_footer(text="Powered by Google Gemini")
        return embed

    async def handle_kvi_message(self, message):
        # Dòng này sẽ in ra mỗi khi có tin nhắn mới trong server
        print(f"\n[DEBUG] Step 1: Bot nhìn thấy tin nhắn từ '{message.author.name}' trong kênh #{message.channel.name}.")
    
        # Kiểm tra xem có phải tin nhắn của Karuta không
        if message.author.id != KARUTA_ID:
            return 
        print("[DEBUG] Step 2: Tin nhắn này là của Karuta.")
    
        # Kiểm tra xem tin nhắn có ở trong kênh KVI đã cài đặt không
        if message.channel.id not in KVI_CHANNELS:
            print(f"[DEBUG] LỖI: Tin nhắn ở sai kênh ({message.channel.id}). Các kênh hợp lệ: {KVI_CHANNELS}")
            return
        print("[DEBUG] Step 3: Tin nhắn ở trong kênh KVI hợp lệ.")
    
        # Kiểm tra xem tin nhắn có chứa embed không
        if not message.embeds:
            return
        print("[DEBUG] Step 4: Tin nhắn có chứa embed.")
    
        embed = message.embeds[0]
        description = embed.description or ""
    
        # Bỏ qua nếu là tin nhắn kết quả
        if "Your Affection Rating has" in description:
            return
        print("[DEBUG] Step 5: Đây không phải là tin nhắn kết quả.")
        
        # Bỏ qua nếu không phải tin nhắn câu hỏi
        if "1️⃣" not in description:
            return
        print("[DEBUG] Step 6: Đây là tin nhắn câu hỏi KVI!")
        
        kvi_data = self.parse_karuta_embed(embed)
        if not kvi_data:
            print("[DEBUG] LỖI: Phân tích embed thất bại.")
            return
        print("[DEBUG] Step 7: Phân tích embed thành công.")
            
        ai_result = await self.analyze_with_ai(kvi_data["character"], kvi_data["question"], kvi_data["choices"])
        if not ai_result:
            print("[DEBUG] LỖI: Phân tích AI thất bại hoặc không trả về kết quả.")
            return
        print("[DEBUG] Step 8: Phân tích AI thành công.")
            
        suggestion_embed = await self.create_suggestion_embed(kvi_data, ai_result)
        try:
            await message.channel.send(embed=suggestion_embed)
            print("✅✅✅ [DEBUG] Step 9: Gửi gợi ý thành công! ✅✅✅")
        except Exception as e:
            print(f"❌ [DEBUG] LỖI CUỐI CÙNG: Không thể gửi tin nhắn gợi ý. Lỗi quyền: {e}")
