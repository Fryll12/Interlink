# File: kvi_support.py (Phiên bản nâng cấp dùng Google Gemini MIỄN PHÍ)
import discord
import re
import os
import asyncio
import json
from typing import Optional, List, Dict
import google.generativeai as genai

# --- CẤU HÌNH ---
KARUTA_ID = 646937666251915264
KVI_CHANNELS_STR = os.getenv('KVI_CHANNELS', '')
KVI_CHANNELS = [int(ch.strip()) for ch in KVI_CHANNELS_STR.split(',') if ch.strip().isdigit()]
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')

# --- LOGIC CHÍNH ---
class KVIHelper:
    def __init__(self, bot):
        self.bot = bot
        try:
            if GOOGLE_API_KEY:
                genai.configure(api_key=GOOGLE_API_KEY)
                # Sử dụng gemini-1.5-flash, mô hình nhanh và miễn phí
                self.ai_model = genai.GenerativeModel('gemini-1.5-flash')
                print("✅ Kết nối thành công tới Google Gemini AI.")
            else:
                self.ai_model = None
                print("⚠️ Cảnh báo: Không tìm thấy GOOGLE_API_KEY.")
        except Exception as e:
            self.ai_model = None
            print(f"❌ Lỗi khi khởi tạo Google Gemini AI: {e}")

    def parse_karuta_embed(self, embed) -> Optional[Dict]:
        """Phân tích embed của Karuta để lấy thông tin."""
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
        """Sử dụng Google Gemini để phân tích."""
        if not self.ai_model:
            print("Lỗi: AI Model chưa được khởi tạo.")
            return None
        try:
            choices_text = "\n".join([f"{c['number']}. {c['text']}" for c in choices])
            prompt = (
                f"You are an expert anime character analyst. Analyze the personality of '{character}'. "
                f"Based on their personality, determine the most likely correct answer to the question: '{question}'.\n"
                f"Here are the choices:\n{choices_text}\n"
                f"Respond ONLY with a valid JSON object in the format: "
                f'{{"analysis":"brief analysis","percentages":[{{"choice":1,"percentage":_}},{{"choice":2,"percentage":_}}]}}'
            )
            
            print("[INTERLINK KVI] Đang phân tích với Google Gemini...")
            response = await self.ai_model.generate_content_async(prompt)
            
            # Xử lý response để lấy JSON
            result_text = response.text.strip().replace("```json", "").replace("```", "").strip()
            return json.loads(result_text)

        except Exception as e:
            print(f"❌ Lỗi khi gọi Google Gemini API: {e}")
            return None

    async def create_suggestion_embed(self, kvi_data: Dict, ai_result: Dict) -> discord.Embed:
        # Hàm này giữ nguyên, không cần thay đổi
        embed = discord.Embed(title="🤖 Interlink KVI Helper (Google AI)", color=0x4285F4) # Đổi màu cho đẹp
        description_lines = [
            f"**Character:** {kvi_data['character']}",
            f"**Question:** \"{kvi_data['question']}\"",
            "",
            "**AI Analysis:**",
            ai_result.get('analysis', 'Đang phân tích...'),
            "",
            "**Suggestions:**"
        ]
        
        percentages = sorted(ai_result.get('percentages', []), key=lambda x: x['percentage'], reverse=True)
        
        for item in percentages:
            choice_num = item['choice']
            percentage = item['percentage']
            emoji = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣'][choice_num - 1]
            choice_text = next((c['text'] for c in kvi_data['choices'] if c['number'] == choice_num), "")
            description_lines.append(f"{emoji} **{percentage}%** - {choice_text}")
        
        embed.description = "\n".join(description_lines)
        embed.set_footer(text="Powered by Google Gemini")
        return embed

    async def handle_kvi_message(self, message):
        if message.author.id != KARUTA_ID or message.channel.id not in KVI_CHANNELS or not message.embeds:
            return

        embed = message.embeds[0]
        description = embed.description or ""
        if "Your Affection Rating has" in description or "1️⃣" not in description:
            return
        
        print(f"\n[INTERLINK KVI] Phát hiện câu hỏi KVI trong kênh {message.channel.id}")
        
        kvi_data = self.parse_karuta_embed(embed) # Đổi sang hàm đồng bộ
        if not kvi_data:
            return
            
        ai_result = await self.analyze_with_ai(kvi_data["character"], kvi_data["question"], kvi_data["choices"])
        if not ai_result:
            return
            
        suggestion_embed = await self.create_suggestion_embed(kvi_data, ai_result)
        try:
            await message.channel.send(embed=suggestion_embed)
            print(f"✅ Đã gửi gợi ý từ Google Gemini.")
        except Exception as e:
            print(f"❌ Lỗi khi gửi embed gợi ý: {e}")

    async def handle_kvi_update(self, before, after):
        # Có thể gọi lại handle_kvi_message nếu cần xử lý update
        pass
