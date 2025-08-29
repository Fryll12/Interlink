# === KVI SUPPORT MODULE FOR INTERLINK BOT (FINAL VERSION) ===
import discord
import re
import os
import asyncio
import json
from typing import Optional, List, Dict
from openai import AsyncOpenAI

# Cấu hình
KARUTA_ID = 646937666251915264
KVI_CHANNELS_STR = os.getenv('KVI_CHANNELS', '')
KVI_CHANNELS = [int(ch.strip()) for ch in KVI_CHANNELS_STR.split(',') if ch.strip().isdigit()]
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Trạng thái theo dõi KVI cho từng kênh
kvi_sessions = {}

class KVIHelper:
    def __init__(self, bot):
        self.bot = bot
        if OPENAI_API_KEY:
            self.ai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        else:
            self.ai_client = None
            print("⚠️ Cảnh báo: Không có OpenAI API key. Bot sẽ chạy ở chế độ gợi ý ngẫu nhiên.")

    async def parse_karuta_embed(self, embed) -> Optional[Dict]:
        """Phân tích embed của Karuta để lấy thông tin KVI"""
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
            
        print(f"✅ Phân tích thành công: Nhân vật {character_name}")
        return {
            "character": character_name,
            "question": question,
            "choices": choices,
        }

    async def analyze_with_ai(self, character: str, question: str, choices: List[Dict]) -> Optional[Dict]:
        """Sử dụng AI để phân tích hoặc fallback sang chế độ ngẫu nhiên."""
        
        # --- Chế độ AI thật (khi có API key) ---
        if self.ai_client:
            try:
                choices_text = "\n".join([f"{choice['number']}. {choice['text']}" for choice in choices])
                prompt = f"""
                You are an expert anime/manga character analyst.
                Character: {character}
                Question: "{question}"
                Choices:
                {choices_text}
                Analyze and respond ONLY with a valid JSON object in the format:
                {{"analysis": "brief analysis", "percentages": [{{"choice": 1, "percentage": X}}, {{"choice": 2, "percentage": Y}}]}}
                """

                print("[INTERLINK KVI] Đang phân tích với OpenAI...")
                response = await self.ai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "You are an expert anime character analyst. Respond accurately in the requested JSON format."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=500,
                    temperature=0.7
                )
                
                result_text = response.choices[0].message.content.strip()
                result_json = json.loads(result_text)
                print(f"✅ [OpenAI] Phân tích thành công cho {character}")
                return result_json
            except Exception as e:
                print(f"❌ [OpenAI] Lỗi API: {e}. Chuyển sang chế độ ngẫu nhiên.")
        
        # --- Chế độ miễn phí (khi không có API key hoặc API lỗi) ---
        print("⚠️ Chuyển sang chế độ gợi ý ngẫu nhiên (MIỄN PHÍ).")
        import random
        percentages_list = []
        num_choices = len(choices)
        remaining = 100
        for i in range(num_choices - 1):
            p = random.randint(1, remaining - (num_choices - 1 - i))
            percentages_list.append(p)
            remaining -= p
        percentages_list.append(remaining)
        random.shuffle(percentages_list)

        return {
            "analysis": "Chế độ miễn phí: Gợi ý được tạo ngẫu nhiên.",
            "percentages": [{"choice": c["number"], "percentage": p} for c, p in zip(choices, percentages_list)]
        }

    async def create_suggestion_embed(self, kvi_data: Dict, ai_result: Dict) -> discord.Embed:
        """Tạo embed gợi ý."""
        embed = discord.Embed(title="🤖 Interlink KVI Helper", color=0x00ff88)
        
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
            reasoning = item.get('reasoning', '')
            
            emoji = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣'][choice_num - 1]
            choice_text = next((c['text'] for c in kvi_data['choices'] if c['number'] == choice_num), "")
            
            line = f"{emoji} **{percentage}%** - {choice_text}"
            if reasoning:
                line += f"\n  ↳ *{reasoning}*"
            description_lines.append(line)
            
        embed.description = "\n".join(description_lines)
        embed.set_footer(text="Powered by Interlink AI")
        return embed

    async def handle_kvi_message(self, message):
        """Xử lý tin nhắn KVI từ Karuta."""
        if (message.author.id != KARUTA_ID or 
            message.channel.id not in KVI_CHANNELS or 
            not message.embeds):
            return

        embed = message.embeds[0]
        description = embed.description or ""
        
        if "Your Affection Rating has" in description or "1️⃣" not in description:
            return

        session_key = f"{message.channel.id}_{message.id}"
        if session_key in kvi_sessions:
            return
        
        kvi_sessions[session_key] = True

        print(f"\n[INTERLINK KVI] Phát hiện câu hỏi KVI trong kênh {message.channel.id}")
        
        kvi_data = await self.parse_karuta_embed(embed)
        if not kvi_data:
            return
            
        ai_result = await self.analyze_with_ai(kvi_data["character"], kvi_data["question"], kvi_data["choices"])
        if not ai_result:
            return
            
        suggestion_embed = await self.create_suggestion_embed(kvi_data, ai_result)
        try:
            await message.channel.send(embed=suggestion_embed)
        except Exception as e:
            print(f"❌ Lỗi khi gửi embed gợi ý: {e}")
