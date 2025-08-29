# File: kvi_support.py (Fixed version)
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

# Biến toàn cục để lưu trữ session
kvi_sessions = {}

class KVIHelper:
    def __init__(self, bot):
        self.bot = bot
        self.api_key = GEMINI_API_KEY
        self.http_session = None
        if not self.api_key:
            print("⚠️ [KVI] Cảnh báo: Không tìm thấy GEMINI_API_KEY.")

    async def async_setup(self):
        """Tạo HTTP session sau khi bot sẵn sàng"""
        self.http_session = aiohttp.ClientSession()
        print("✅ [KVI] Aiohttp client session đã được tạo.")

    def parse_karuta_embed(self, embed) -> Optional[Dict]:
        """Phân tích embed của Karuta để lấy thông tin"""
        description = embed.description or ""
        
        # Tìm tên nhân vật
        char_match = re.search(r"Character · \*\*([^\*]+)\*\*", description)
        character_name = char_match.group(1).strip() if char_match else None
    
        # Tìm câu hỏi trong dấu ngoặc kép
        question_match = re.search(r'[""]([^""]+)[""]', description)
        question = question_match.group(1).strip() if question_match else None
        
        # Tìm các lựa chọn
        choice_lines = re.findall(r'^(1️⃣|2️⃣|3️⃣|4️⃣|5️⃣)\s+(.+)$', description, re.MULTILINE)
        choices = [{"number": int(emoji[0]), "text": text.strip()} for emoji, text in choice_lines]
        
        if not all([character_name, question, choices]):
            return None
            
        return {"character": character_name, "question": question, "choices": choices}

    async def analyze_with_ai(self, character: str, question: str, choices: List[Dict]) -> Optional[Dict]:
        """Phân tích bằng AI để đưa ra gợi ý"""
        if not self.api_key:
            return None
        
        if not self.http_session:
            await self.async_setup()

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.api_key}"
        
        choices_text = "\n".join([f"{c['number']}. {c['text']}" for c in choices])
        prompt = (
            f"Phân tích tính cách nhân vật '{character}' và dự đoán câu trả lời phù hợp nhất cho câu hỏi: '{question}'.\n"
            f"Lựa chọn:\n{choices_text}\n"
            f"Trả lời bằng JSON: "
            f'{{"analysis":"phân tích ngắn gọn","percentages":[{{"choice":1,"percentage":_}},{{"choice":2,"percentage":_}}]}}'
        )

        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }

        try:
            async with self.http_session.post(url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    result_text = data["candidates"][0]["content"]["parts"][0]["text"]
                    result_text = result_text.strip().replace("```json", "").replace("```", "").strip()
                    return json.loads(result_text)
                else:
                    return None
        except Exception as e:
            print(f"❌ [GEMINI] Lỗi: {e}")
            return None

    async def create_suggestion_embed(self, kvi_data: Dict, ai_result: Dict) -> discord.Embed:
        """Tạo embed gợi ý đẹp và ngắn gọn"""
        embed = discord.Embed(
            title="🎯 KVI Helper", 
            color=0x00ff88,
            description=f"**{kvi_data['character']}**\n*{kvi_data['question']}*"
        )
        
        percentages = sorted(ai_result.get('percentages', []), key=lambda x: x.get('percentage', 0), reverse=True)
        
        suggestions = []
        for item in percentages:
            choice_num = item.get('choice')
            percentage = item.get('percentage')
            if choice_num is None or percentage is None: 
                continue

            emoji = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣'][choice_num - 1]
            choice_text = next((c['text'] for c in kvi_data['choices'] if c['number'] == choice_num), "")
            
            if percentage >= 50:
                suggestions.append(f"{emoji} **{percentage}%** ⭐")
            else:
                suggestions.append(f"{emoji} {percentage}%")
        
        embed.add_field(
            name="💡 Gợi ý", 
            value="\n".join(suggestions[:3]), 
            inline=False
        )
        
        analysis = ai_result.get('analysis', '')
        if len(analysis) > 100:
            analysis = analysis[:100] + "..."
        
        embed.add_field(
            name="🔍 Phân tích", 
            value=analysis, 
            inline=False
        )
        
        embed.set_footer(text="🤖 Powered by Gemini AI")
        return embed

    async def handle_kvi_message(self, message):
        """Xử lý tin nhắn KVI từ tất cả kênh"""
        global kvi_sessions
    
        # Chỉ xử lý tin nhắn từ Karuta có embed
        if message.author.id != KARUTA_ID or not message.embeds:
            return
    
        embed = message.embeds[0]
        description = embed.description or ""
        
        # Bỏ qua tin nhắn không phải KVI
        if "Your Affection Rating has" in description or "1️⃣" not in description:
            return
    
        # Phân tích embed
        kvi_data = self.parse_karuta_embed(embed)
        if not kvi_data:
            return
    
        # Kiểm tra session để tránh spam
        session = kvi_sessions.get(message.channel.id, {})
        
        if session.get("message_id") == message.id and session.get("last_question") == kvi_data["question"]:
            return
    
        # Cập nhật session
        kvi_sessions[message.channel.id] = {
            "message_id": message.id,
            "last_question": kvi_data["question"]
        }
            
        # Phân tích bằng AI
        ai_result = await self.analyze_with_ai(kvi_data["character"], kvi_data["question"], kvi_data["choices"])
        if not ai_result:
            return
            
        # Gửi gợi ý
        suggestion_embed = await self.create_suggestion_embed(kvi_data, ai_result)
        try:
            await message.channel.send(embed=suggestion_embed)
            print(f"✅ [KVI] Đã gửi gợi ý cho {kvi_data['character']}")
        except Exception as e:
            print(f"❌ [KVI] Lỗi gửi embed: {e}")
