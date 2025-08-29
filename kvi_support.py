# === KVI SUPPORT MODULE FOR INTERLINK BOT ===
import discord
import re
import os
import asyncio
from typing import Optional, List, Tuple, Dict
import google.generativeai as genai
import aiohttp
import json

# Cấu hình
KARUTA_ID = 646937666251915264
KVI_CHANNELS = os.getenv('KVI_CHANNELS', '').split(',')  # Nhập nhiều kênh cách nhau bởi dấu phẩy
KVI_CHANNELS = [int(ch.strip()) for ch in KVI_CHANNELS if ch.strip().isdigit()]
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')  # Thêm Gemini API key vào env

# Trạng thái theo dõi KVI cho từng kênh
kvi_sessions = {}

class KVIHelper:
    def __init__(self, bot):
        self.bot = bot
        if GEMINI_API_KEY:
            genai.configure(api_key=GEMINI_API_KEY)
            self.model = genai.GenerativeModel('gemini-1.5-flash')  # Model free tốt nhất
            print("✅ [GEMINI] Khởi tạo thành công!")
        else:
            self.model = None
            print("⚠️  Cảnh báo: Không có Gemini API key, sẽ sử dụng mock data")
        
    async def parse_karuta_embed(self, embed) -> Optional[Dict]:
        """Phân tích embed của Karuta để lấy thông tin KVI"""
        description = embed.description or ""
        
        print("\n" + "="*20 + " PHÂN TÍCH EMBED KARUTA " + "="*20)
        print("Nội dung embed nhận được:")
        print("----------------------------------------------------")
        print(description)
        print("----------------------------------------------------")
        
        # Tìm tên nhân vật
        char_match = re.search(r"Character · \*\*([^\*]+)\*\*", description)
        character_name = char_match.group(1).strip() if char_match else None
        
        # Tìm câu hỏi
        question_match = re.search(r'"([^"]*)"', description)
        question = question_match.group(1).strip() if question_match else None
        
        # Tìm các lựa chọn
        choices = []
        choice_lines = re.findall(r'^\d️⃣\s+(.+)$', description, re.MULTILINE)
        for i, choice in enumerate(choice_lines, 1):
            choices.append({"number": i, "text": choice.strip()})
        
        if not all([character_name, question, choices]):
            print("❌ Không đủ thông tin để phân tích")
            return None
            
        print(f"✅ Nhân vật: {character_name}")
        print(f"✅ Câu hỏi: {question}")
        print(f"✅ Số lựa chọn: {len(choices)}")
        print("="*64)
        
        return {
            "character": character_name,
            "question": question,
            "choices": choices,
            "num_choices": len(choices)
        }
    
    async def analyze_with_ai(self, character: str, question: str, choices: List[Dict]) -> Optional[Dict]:
        """Sử dụng Google Gemini để phân tích và đưa ra câu trả lời tốt nhất"""
        try:
            if not self.model:
                # Fallback với mock data nếu không có API key
                import random
                total = 100
                percentages = []
                for i, choice in enumerate(choices):
                    if i == len(choices) - 1:  # Choice cuối cùng
                        percent = total
                    else:
                        percent = random.randint(5, min(70, total - 5 * (len(choices) - i - 1)))
                        total -= percent
                    
                    percentages.append({
                        "choice": choice["number"], 
                        "percentage": percent, 
                        "reasoning": f"Mock analysis for choice {choice['number']}"
                    })
                
                return {
                    "analysis": f"Mock analysis cho nhân vật {character}",
                    "percentages": percentages
                }
            
            # Tạo prompt cho Gemini
            choices_text = "\n".join([f"{choice['number']}. {choice['text']}" for choice in choices])
            
            prompt = f"""
Bạn là chuyên gia phân tích nhân vật anime/manga với kiến thức sâu rộng về văn hóa Nhật Bản và các series phổ biến.

THÔNG TIN CẦN PHÂN TÍCH:
Nhân vật: {character}
Câu hỏi: "{question}"

CÁC LỰA CHỌN:
{choices_text}

NHIỆM VỤ:
1. Phân tích tính cách, tình huống và đặc điểm của nhân vật này dựa trên kiến thức anime/manga
2. Đánh giá độ chính xác của từng lựa chọn với tổng phần trăm = 100%
3. Đưa ra lý do cụ thể cho mỗi đánh giá

QUAN TRỌNG: Chỉ trả lời dưới dạng JSON hợp lệ, không thêm text nào khác:

{{
    "analysis": "Phân tích ngắn gọn về tính cách nhân vật (1-2 câu)",
    "percentages": [
        {{"choice": 1, "percentage": X, "reasoning": "Lý do cụ thể"}},
        {{"choice": 2, "percentage": Y, "reasoning": "Lý do cụ thể"}},
        {{"choice": 3, "percentage": Z, "reasoning": "Lý do cụ thể"}}
    ]
}}"""

            # Gọi Gemini API với async wrapper
            import asyncio
            
            def sync_generate():
                response = self.model.generate_content(prompt)
                return response.text
            
            # Chạy sync function trong thread pool
            loop = asyncio.get_event_loop()
            result_text = await loop.run_in_executor(None, sync_generate)
            
            # Parse JSON response
            result_text = result_text.strip()
            
            # Loại bỏ markdown code blocks nếu có
            if result_text.startswith('```json'):
                result_text = result_text[7:]
            if result_text.endswith('```'):
                result_text = result_text[:-3]
            result_text = result_text.strip()
            
            result = json.loads(result_text)
            
            # Validate và fix tổng phần trăm nếu cần
            total_percent = sum(item["percentage"] for item in result["percentages"])
            if abs(total_percent - 100) > 1:  # Cho phép sai số 1%
                # Điều chỉnh để tổng bằng 100
                diff = 100 - total_percent
                result["percentages"][0]["percentage"] += diff
            
            print(f"✅ [GEMINI] Phân tích thành công cho {character}")
            print(f"   └─ Kết quả: {[f'{p[\"choice\"]}({p[\"percentage\"]}%)' for p in result['percentages']]}")
            return result
            
        except json.JSONDecodeError as e:
            print(f"❌ [GEMINI] Lỗi parse JSON: {e}")
            print(f"Raw response: {result_text if 'result_text' in locals() else 'None'}")
            
            # Fallback với mock data
            return await self.analyze_with_ai("", "", choices)  # Recursive với model=None
            
        except Exception as e:
            print(f"❌ [GEMINI] Lỗi API: {e}")
            
            # Fallback với mock data
            import random
            total = 100
            percentages = []
            for i, choice in enumerate(choices):
                if i == len(choices) - 1:
                    percent = total
                else:
                    percent = random.randint(10, min(60, total - 10 * (len(choices) - i - 1)))
                    total -= percent
                
                percentages.append({
                    "choice": choice["number"], 
                    "percentage": percent, 
                    "reasoning": f"Fallback analysis cho choice {choice['number']}"
                })
            
            return {
                "analysis": f"Fallback analysis cho nhân vật {character}",
                "percentages": percentages
            }
    
    async def create_suggestion_embed(self, kvi_data: Dict, ai_result: Dict, channel_id: int) -> discord.Embed:
        """Tạo embed gợi ý giống như Hatsune"""
        
        embed = discord.Embed(
            title="🤖 Interlink KVI Helper",
            color=0x00ff88  # Màu xanh lá
        )
        
        # Tạo description với các gợi ý
        description_lines = []
        description_lines.append(f"**Character:** {kvi_data['character']}")
        description_lines.append(f"**Question:** \"{kvi_data['question']}\"")
        description_lines.append("")
        description_lines.append("**AI Analysis:**")
        description_lines.append(ai_result.get('analysis', 'Đang phân tích...'))
        description_lines.append("")
        description_lines.append("**Suggestions:**")
        
        # Sắp xếp theo phần trăm giảm dần
        percentages = sorted(ai_result.get('percentages', []), key=lambda x: x['percentage'], reverse=True)
        
        for item in percentages:
            choice_num = item['choice']
            percentage = item['percentage']
            reasoning = item.get('reasoning', '')
            
            # Tạo emoji số
            number_emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣']
            emoji = number_emojis[choice_num - 1] if choice_num <= len(number_emojis) else f"{choice_num}️⃣"
            
            # Tìm text của choice
            choice_text = next((c['text'] for c in kvi_data['choices'] if c['number'] == choice_num), f"Choice {choice_num}")
            
            description_lines.append(f"{emoji} **{percentage}%** - {choice_text}")
            if reasoning:
                description_lines.append(f"   ↳ *{reasoning}*")
        
        embed.description = "\n".join(description_lines)
        
        # Thêm footer với thông tin kênh
        embed.set_footer(text=f"Channel: {channel_id} | Powered by Interlink AI")
        
        return embed
    
    async def handle_kvi_message(self, message):
        """Xử lý tin nhắn KVI từ Karuta"""
        
        # Kiểm tra xem có phải tin nhắn KVI không
        if (message.author.id != KARUTA_ID or 
            message.channel.id not in KVI_CHANNELS or 
            not message.embeds):
            return
        
        embed = message.embeds[0]
        description = embed.description or ""
        
        # Bỏ qua tin nhắn kết quả
        if "Your Affection Rating has" in description:
            return
            
        # Chỉ xử lý tin nhắn có câu hỏi (có 1️⃣)
        if "1️⃣" not in description:
            return
        
        print(f"\n[INTERLINK KVI] Phát hiện câu hỏi KVI trong kênh {message.channel.id}")
        
        # Phân tích embed
        kvi_data = await self.parse_karuta_embed(embed)
        if not kvi_data:
            return
        
        # Kiểm tra xem có phải câu hỏi mới không
        session_key = f"{message.channel.id}_{message.id}"
        if session_key in kvi_sessions:
            return  # Đã xử lý rồi
        
        # Lưu session
        kvi_sessions[session_key] = {
            "message_id": message.id,
            "channel_id": message.channel.id,
            "kvi_data": kvi_data,
            "processed": True
        }
        
        # Phân tích với AI
        print("[INTERLINK KVI] Đang phân tích với AI...")
        ai_result = await self.analyze_with_ai(
            kvi_data["character"], 
            kvi_data["question"], 
            kvi_data["choices"]
        )
        
        if not ai_result:
            print("[INTERLINK KVI] ❌ Không thể phân tích với AI")
            return
        
        # Tạo và gửi embed gợi ý
        suggestion_embed = await self.create_suggestion_embed(kvi_data, ai_result, message.channel.id)
        
        try:
            sent_message = await message.channel.send(embed=suggestion_embed)
            print(f"[INTERLINK KVI] ✅ Đã gửi gợi ý cho câu hỏi: {kvi_data['question'][:50]}...")
            
            # Lưu message ID để có thể update sau
            kvi_sessions[session_key]["suggestion_message_id"] = sent_message.id
            
        except Exception as e:
            print(f"[INTERLINK KVI] ❌ Lỗi khi gửi embed: {e}")
    
    async def handle_kvi_update(self, before, after):
        """Xử lý khi tin nhắn KVI được update"""
        
        if (after.author.id != KARUTA_ID or 
            after.channel.id not in KVI_CHANNELS or 
            not after.embeds):
            return
        
        # Tìm session tương ứng
        session_key = None
        for key, session in kvi_sessions.items():
            if session["channel_id"] == after.channel.id:
                session_key = key
                break
        
        if not session_key:
            # Tin nhắn mới, xử lý như bình thường
            await self.handle_kvi_message(after)
            return
        
        embed = after.embeds[0]
        description = embed.description or ""
        
        # Nếu là câu hỏi mới
        if "1️⃣" in description and "Your Affection Rating has" not in description:
            print(f"[INTERLINK KVI] Phát hiện câu hỏi mới (update) trong kênh {after.channel.id}")
            
            # Phân tích embed mới
            kvi_data = await self.parse_karuta_embed(embed)
            if not kvi_data:
                return
            
            # Cập nhật session
            kvi_sessions[session_key]["kvi_data"] = kvi_data
            
            # Phân tích với AI
            print("[INTERLINK KVI] Đang phân tích câu hỏi mới với AI...")
            ai_result = await self.analyze_with_ai(
                kvi_data["character"], 
                kvi_data["question"], 
                kvi_data["choices"]
            )
            
            if not ai_result:
                return
            
            # Tạo embed mới
            new_embed = await self.create_suggestion_embed(kvi_data, ai_result, after.channel.id)
            
            # Update embed cũ nếu có
            if "suggestion_message_id" in kvi_sessions[session_key]:
                try:
                    old_message = await after.channel.fetch_message(kvi_sessions[session_key]["suggestion_message_id"])
                    await old_message.edit(embed=new_embed)
                    print(f"[INTERLINK KVI] ✅ Đã cập nhật gợi ý cho câu hỏi mới")
                except:
                    # Nếu không update được thì gửi mới
                    sent_message = await after.channel.send(embed=new_embed)
                    kvi_sessions[session_key]["suggestion_message_id"] = sent_message.id
            else:
                # Gửi embed mới
                sent_message = await after.channel.send(embed=new_embed)
                kvi_sessions[session_key]["suggestion_message_id"] = sent_message.id

    def cleanup_old_sessions(self):
        """Dọn dẹp các session cũ để tránh tràn RAM"""
        # Giữ lại tối đa 100 sessions gần nhất
        if len(kvi_sessions) > 100:
            # Xóa 50 session cũ nhất
            old_keys = list(kvi_sessions.keys())[:50]
            for key in old_keys:
                del kvi_sessions[key]
            print(f"[INTERLINK KVI] Đã dọn dẹp {len(old_keys)} session cũ")

# === CÁCH SỬ DỤNG TRONG BOT CHÍNH ===
"""
# Trong main bot file của bạn:

from kvi_support import KVIHelper

class YourBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=discord.Intents.all())
        self.kvi_helper = KVIHelper(self)
    
    @commands.Cog.listener()
    async def on_message(self, message):
        await self.kvi_helper.handle_kvi_message(message)
        # Các xử lý khác của bot...
    
    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        await self.kvi_helper.handle_kvi_update(before, after)
        # Các xử lý khác của bot...
    
    # Thêm task dọn dẹp session (optional)
    @tasks.loop(minutes=30)
    async def cleanup_kvi_sessions(self):
        self.kvi_helper.cleanup_old_sessions()
"""
