# === KVI SUPPORT MODULE FOR INTERLINK BOT ===
import discord
import re
import os
import asyncio
from typing import Optional, List, Tuple, Dict
from openai import AsyncOpenAI

# Cấu hình
KARUTA_ID = 646937666251915264
KVI_CHANNELS = os.getenv('KVI_CHANNELS', '').split(',')  # Nhập nhiều kênh cách nhau bởi dấu phẩy
KVI_CHANNELS = [int(ch.strip()) for ch in KVI_CHANNELS if ch.strip().isdigit()]
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')  # Thêm API key vào env

# Trạng thái theo dõi KVI cho từng kênh
kvi_sessions = {}

class KVIHelper:
    def __init__(self, bot):
        self.bot = bot
        if OPENAI_API_KEY:
            self.ai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        else:
            self.ai_client = None
            print("⚠️  Cảnh báo: Không có OpenAI API key, sẽ sử dụng mock data")
        
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
        """
        Sử dụng ChatGPT để phân tích.
        Nếu không có API key hoặc có lỗi, sẽ tự động chuyển sang chế độ chọn ngẫu nhiên.
        """
        # --- PHẦN GỌI AI THẬT ---
        if self.ai_client:
            try:
                choices_text = "\n".join([f"{c['number']}. {c['text']}" for c in choices])
                prompt = (
                    f"You are an expert anime character analyst. Analyze the personality of '{character}'. "
                    f"Based on their personality, determine the most likely correct answer to the question: '{question}'.\n"
                    f"Choices:\n{choices_text}\n"
                    f"Respond ONLY with a valid JSON object in the format: "
                    f'{{"analysis":"brief analysis","percentages":[{{"choice":1,"percentage":_}},{{"choice":2,"percentage":_}}]}}'
                )
                
                print("[INTERLINK KVI] Đang phân tích với OpenAI...")
                response = await self.ai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "You are an expert anime character analyst. Respond accurately in the requested JSON format."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=500,
                    temperature=0.6
                )
                result_text = response.choices[0].message.content
                # Trả về kết quả từ AI
                return json.loads(result_text)
            except Exception as e:
                print(f"❌ Lỗi khi gọi API OpenAI: {e}. Chuyển sang chế độ ngẫu nhiên.")
                # Nếu có lỗi, sẽ chạy xuống phần fallback bên dưới
    
        # --- PHẦN FALLBACK MIỄN PHÍ (CHỌN NGẪU NHIÊN) ---
        print("⚠️  Không có API Key hoặc API lỗi. Chuyển sang chế độ gợi ý ngẫu nhiên (MIỄN PHÍ).")
        import random
        
        # Tạo ra các phần trăm ngẫu nhiên
        percentages_list = []
        num_choices = len(choices)
        remaining_percent = 100
        
        for i in range(num_choices - 1):
            # Mỗi lựa chọn sẽ nhận một phần ngẫu nhiên, chừa lại ít nhất 5% cho các lựa chọn sau
            percent = random.randint(5, remaining_percent - (5 * (num_choices - 1 - i)))
            percentages_list.append(percent)
            remaining_percent -= percent
        percentages_list.append(remaining_percent) # Lựa chọn cuối cùng nhận phần còn lại
        
        random.shuffle(percentages_list) # Xáo trộn các phần trăm để không bị thiên vị
    
        # Tạo cấu trúc JSON giả để trả về
        mock_percentages = [
            {"choice": choice["number"], "percentage": percentages_list[i]} 
            for i, choice in enumerate(choices)
        ]
    
        return {
            "analysis": "Chế độ miễn phí: Gợi ý được tạo ngẫu nhiên do không có API key hoặc API bị lỗi.",
            "percentages": mock_percentages
        }
            
            # Tạo prompt cho ChatGPT
            choices_text = "\n".join([f"{choice['number']}. {choice['text']}" for choice in choices])
            
            prompt = f"""
Bạn là chuyên gia phân tích nhân vật anime/manga với kiến thức sâu rộng.

THÔNG TIN:
- Nhân vật: {character}
- Câu hỏi: "{question}"

CÁC LỰA CHỌN:
{choices_text}

YÊU CẦU:
1. Phân tích tính cách, background và đặc điểm của nhân vật này
2. Đánh giá độ chính xác của từng lựa chọn (tổng phần trăm = 100%)
3. Đưa ra lý do ngắn gọn cho mỗi lựa chọn

ĐỊNH DẠNG TRẢ LỜI (JSON):
{{
    "analysis": "Phân tích tính cách nhân vật (1-2 câu)",
    "percentages": [
        {{"choice": 1, "percentage": X, "reasoning": "Lý do ngắn gọn"}},
        {{"choice": 2, "percentage": Y, "reasoning": "Lý do ngắn gọn"}},
        {{"choice": 3, "percentage": Z, "reasoning": "Lý do ngắn gọn"}}
    ]
}}

LưU ý: Chỉ trả lời JSON, không thêm text nào khác."""

            # Gọi ChatGPT API
            response = await self.ai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Bạn là chuyên gia phân tích nhân vật anime/manga. Trả lời chính xác theo format JSON được yêu cầu."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=600,
                temperature=0.7
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Parse JSON response
            import json
            result = json.loads(result_text)
            
            # Validate và fix tổng phần trăm nếu cần
            total_percent = sum(item["percentage"] for item in result["percentages"])
            if total_percent != 100:
                # Điều chỉnh để tổng bằng 100
                diff = 100 - total_percent
                result["percentages"][0]["percentage"] += diff
            
            print(f"✅ [ChatGPT] Phân tích thành công cho {character}")
            return result
            
        except json.JSONDecodeError as e:
            print(f"❌ [ChatGPT] Lỗi parse JSON: {e}")
            print(f"Raw response: {result_text if 'result_text' in locals() else 'None'}")
            return None
        except Exception as e:
            print(f"❌ [ChatGPT] Lỗi API: {e}")
            return None
    
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
