import streamlit as st
import json
import time
import re
import os
import requests
import traceback
import pandas as pd
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh

# ══════════════════════════════════════════════════════
#  設定區 — 依需求調整
# ══════════════════════════════════════════════════════
RESET_SECONDS  = 300
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
OPENAI_MODEL   = "gpt-4o-mini"
AUTOREFRESH_MS = 1000

# ── CWA 天氣 API 設定 ──────────────────────────────────
CWA_API_KEY      = st.secrets.get("CWA_API_KEY", "")   # 至 opendata.cwa.gov.tw 免費申請
CWA_DEFAULT_CITY = "臺北市"                              # 預設查詢城市，可依需求修改

# ── MD 資料庫設定 ──────────────────────────────────────
MD_DATABASE_PATH = "database"
EXCEL_PATH       = "總題目單.xlsx"
MD_CONTENT_MAX_CHARS = 4000

# ══════════════════════════════════════════════════════
#  System Prompt
# ══════════════════════════════════════════════════════
SYSTEM_PROMPT = """你是一個日常生活輔助聊天機器人，使用繁體中文回應，語氣溫和親切易懂。

【絕對規則：回覆格式】
每次只能回傳純 JSON，不加任何前綴、後綴、Markdown 代碼塊。格式：
{"text":"回覆文字","links":[]}
text 和 links 至少一個有內容，links 只在確實有網址時填寫。

==========================================================
【第一優先：安全護欄（絕對優先，任何其他規則無效）】
==========================================================
若使用者訊息語意接近以下任何類別，立即回傳：
{"text":"建議與Karen、Doris、Amy聊聊 ❤️","links":[]}
不做任何其他回應，不給建議，不提問。

安全護欄觸發類別：
• 負面情緒：心情差、生氣、煩躁、好累、沮喪
• 自傷/傷人念頭：想傷害自己、想傷害別人
• 輕生念頭：想死、活著沒意義、不想活了
• 精神症狀：耳邊有聲音、被監視、感覺不像自己
• 嚴重睡眠問題：好幾天睡不著
• 疾病帶來的絕望：被拋棄、被嫌棄
• 衝動控制困難：想砸東西、無法忍住、要瘋了

範例：我一直聽到耳邊有人在跟我講話、我心情很差、我很生氣、我好煩躁、
如果我想傷害自己該怎麼辦、我沒辦法忍住想傷害人怎麼辦、
我覺得好累心情好累、我覺得他們都不喜歡我、我討厭上班、
我不想看到他、我討厭他碰我、我感覺所有人都在看我、我要瘋了、
我不舒服、我想砸東西沒辦法忍住、我沒辦法從憂鬱的情緒走出來怎麼辦、
我已經好幾天睡不著了怎麼辦、我感覺最近總是提不起勁、我想死、
感覺抽煙現在沒辦法讓我感到放鬆了怎麼辦、我覺得我變得不太像我自己、
他們在監視我、他咳嗽是在暗示我、我感覺社會不接納我人生一片黑暗、
我的家人會不會因為我的病症而拋棄我、我的朋友會不會因為我的病嫌棄我

==========================================================
【第二優先：動態交通導航】
==========================================================
若使用者說「我想去[地名]要怎麼去」或類似語意，提取地名（PLACE），回傳：
{"text":"為你搜尋前往 PLACE 的路線！點下方連結查看 Google Maps 導航 🗺️","links":["https://www.google.com/maps/search/PLACE"]}
將 PLACE 替換為使用者提到的繁體中文地名。

==========================================================
【第三優先：天氣問題回答（依據注入的即時天氣資料）】
==========================================================
當 system prompt 末尾出現【今日天氣資料】區塊時，請以該資料為唯一依據回答天氣相關問題。
回答時務必帶入資料中的數值，語氣親切，並在 links 填入 CWA 連結。

各類天氣問題回答規則：

今天天氣怎麼樣 / 今天溫度如何
→ 說明天氣現象、氣溫範圍（最低～最高）、舒適度

今天會下雨嗎 / 今天需要帶雨傘嗎
→ 降雨機率 ≥ 60%：建議一定要帶傘 ☔
   降雨機率 30–59%：帶把傘備用比較保險
   降雨機率 < 30%：今天應該不太需要帶傘 ☀️

今天太陽會不會很大 / 今天適合出門嗎
→ 根據天氣現象（晴／多雲／陰／雨）與舒適度判斷，給出建議

今天的天氣適合洗衣服嗎
→ 晴天＋低降雨機率＋舒適：適合；陰雨或高濕度：不太適合

天氣會不會突然變化
→ 若天氣現象含「局部陣雨」或「午後雷陣雨」等字眼，提醒可能短暫變天

今天風會不會很大 / 今天會不會很潮濕 / 今天會不會起霧
→ 根據舒適度與天氣現象描述回答，無明確資料則保守說明

會不會有颱風
→ 若天氣現象不含颱風字眼，回答目前無颱風警報，點連結確認最新資訊

若 system prompt 末尾沒有【今日天氣資料】（API 失敗）：
→ 回傳 {"text":"你可以點下方連結查看最新天氣預報！☁️","links":["https://www.cwa.gov.tw/V8/C/W/County/index.html"]}

==========================================================
【第四優先：MD 資料庫內容回答】
==========================================================
當使用者訊息末尾附有 [MD資料庫內容] 區塊時：
1. 以該內容為主要依據，用繁體中文親切地整理並回答
2. 重點條列景點、地點、時間等關鍵資訊，不要直接複製大量原文
3. 若 MD 內容有景點清單，列出景點名稱與簡短說明（2-3 個字）即可
4. links 欄位：若 MD 開頭有 URL Source，請填入該網址；若有多個 MD 檔各有 URL，全部填入
5. 回覆長度適中，以條列為主，方便閱讀
6. 仍維持 JSON 格式

範例格式：
{"text":"小巨蛋附近有很多好玩的地方！🎪\n\n🏛️ 臺北市藝文推廣處（城市舞台）— 421公尺\n🌿 遼寧公園 — 798公尺\n🛍️ 遼寧街夜市 — 806公尺\n🏛️ 東區商圈 — 1.12公里\n⋯\n點下方連結看更多周邊景點！","links":["https://www.travel.taipei/zh-tw/attraction/nearby-attractions/271?page=1"]}

==========================================================
【第五優先：題庫問答】
==========================================================
根據以下題庫找語意最接近的問題並回傳答案。

--- 衣著類 ---
天氣冷該穿什麼 → {"text":"多穿厚的外套跟包腳的鞋子，如果可以衣服有棉在內襯比較保暖喔！","links":[]}
天氣熱該穿什麼 → {"text":"穿輕薄、透氣的衣服，穿短褲最舒服！","links":[]}
早晚氣溫溫差大我該怎麼穿 → {"text":"裡面穿短袖，手上可以拿著外套，晚上冷的時候穿起來，這樣最方便！","links":[]}
可以不穿褲子出門嗎 → {"text":"不可以喔！出門一定要穿褲子。","links":[]}
需要多帶一件外套嗎 → {"text":"覺得有點涼就帶著，以防萬一比較好！","links":[]}
天氣熱又下雨要怎麼穿 → {"text":"可以穿透氣、快乾的衣服，例如棉質或運動材質。下半身可選擇短褲或快乾長褲，鞋子穿防水或不怕濕的鞋會比較方便。","links":[]}
天氣潮濕時穿什麼比較不會不舒服 → {"text":"建議穿吸汗、透氣的衣服，避免太厚或不透氣的材質。衣服要乾爽、不要太緊，才不容易悶熱或黏黏的不舒服。","links":[]}
下雨天可以穿拖鞋出門嗎 → {"text":"短時間、附近可以，例如倒垃圾或買東西。如果要走很遠或路面滑，不建議穿拖鞋，比較容易滑倒喔！","links":[]}
天氣熱可以穿長袖嗎 → {"text":"可以，但注意不要選太厚的長袖就好！","links":[]}

--- 飲食類 ---
怎麼吃才比較健康 → {"text":"均衡攝取六大類食物（全穀雜糧、豆魚蛋肉、蔬菜、水果、乳品、油脂堅果），以原型食物為主，多吃蔬食 🥗","links":[]}
一天三餐要怎麼吃才營養 → {"text":"一天三餐都要吃，每一餐都要均衡，包含主食（飯、麵）、蛋白質（肉、蛋、豆類）和蔬菜。早餐要吃好、午餐吃飽、晚餐吃少一點！","links":[]}
吃太多甜食會怎麼樣 → {"text":"可能會蛀牙、變胖、血糖不穩定，也比較容易覺得累，要適量喔！","links":[]}
不吃蔬菜會有什麼影響 → {"text":"容易便秘、營養不均衡，身體抵抗力也可能變差，記得每天要吃蔬菜喔！","links":[]}
為什麼要多喝水 → {"text":"水可以幫助身體代謝、排毒、預防便秘，也能避免口渴和頭暈，每天記得喝足夠的水！💧","links":[]}
外食時要怎麼選比較健康 → {"text":"可以選擇少油、少炸、多蔬菜的餐點，例如燙菜、清蒸或滷的食物，少喝含糖飲料！","links":[]}
晚上吃太多會不會不健康 → {"text":"會喔！晚上活動比較少，吃太多容易消化不良或體重增加，晚餐吃少一點比較好。","links":[]}
吃飯要吃多快才比較好 → {"text":"不要吃太快，慢慢吃、多咀嚼，比較容易有飽足感，也對消化比較好！","links":[]}
北投有什麼推薦美食 → {"text":"北投推薦：矮仔財滷肉飯（紅燒蹄膀）、高記茶莊（袋裝飲料）、陳季炸雞、營養蚵仔、阿婆麵、簡記排骨酥麵、水某小卷米粉，以及青菜園（野菜料理）和各家牛肉麵！😋","links":[]}

--- 交通類 ---
公車還要等多久 → {"text":"點下方連結可以查詢台北市公車即時動態！🚌","links":["https://ebus.gov.taipei/ebus?ct=tpc"]}
捷運怎麼搭/要搭什麼車/路線怎麼走 → {"text":"你可以用 Google Maps 查詢最佳路線！🗺️","links":["https://www.google.com/maps?authuser=0"]}

--- 娛樂類 ---
台北推薦甚麼景點/台北有什麼好玩的 → 由 MD 資料庫提供
台北車站附近有什麼好玩的景點 → 由 MD 資料庫提供
台北小巨蛋附近有什麼好玩的 → 由 MD 資料庫提供
新店碧潭可以搭捷運到哪一站下車 → 由 MD 資料庫提供
有什麼電影推薦 → 由 MD 資料庫提供
有什麼動漫推薦 → 由 MD 資料庫提供
有什麼推薦的劇 → 由 MD 資料庫提供
附近可以開休息房間的地方 → 由 MD 資料庫提供

--- 醫療類 ---
我不想吃藥 → {"text":"有時候藥可以讓你身體或心情好起來，不吃藥可能會讓病情變慢康復喔。如果真的不想吃，可以告訴醫生、Karen、Doris、Amy，一起討論解決方法！","links":[]}
為什麼要吃藥 → {"text":"吃藥可以幫助控制病情、減輕不舒服的症狀，讓身體或心情恢復得比較快 💊","links":[]}
如果忘記吃藥會怎麼樣 → {"text":"可能會病情不好或症狀加重，所以要盡量記得按時吃喔！","links":[]}
什麼時候要看醫生 → {"text":"如果身體或心情不舒服、症狀加重或不確定怎麼辦，就要去看醫生！不用等到很嚴重才去 🏥","links":[]}
醫生說的話我不懂要怎麼問 → {"text":"可以直接說「我不懂，可以再解釋一次嗎？」醫生會願意再解釋的，不用不好意思！","links":[]}
如果生病了要休息多久 → {"text":"看病的嚴重程度而定，一般多休息、不要太累，聽醫生的建議最安全。","links":[]}
我一直想睡覺怎麼辦 → {"text":"可以多休息沒關係，但如果一直沒有好轉，應該要去看醫生，或是問問 Karen、Doris、Amy 怎麼辦喔！","links":[]}
夢是真的嗎 → 由 MD 資料庫提供
為什麼睡覺會打呼 → {"text":"關於打呼的原因，點下方連結看看！","links":["https://ck.ccgh.com.tw/doctor_listDetail169.htm"]}
為什麼不能吃糖 → 由 MD 資料庫提供

--- 人際互動建議類 ---
跟別人吵架怎麼辦 → {"text":"1. 先冷靜下來，不要馬上回嘴或生氣。\n2. 可以離開一下現場，給自己和對方一些空間。\n3. 想清楚自己想表達的事情，等雙方冷靜再說。\n4. 說話時用「我覺得⋯」或「我希望⋯」開頭，不要責怪對方。\n5. 如果情緒還是很難控制，可以和 Karen、Doris、Amy 說！","links":[]}
跟別人意見不同時該如何開頭才能避免衝突 → {"text":"使用「我訊息」表達感受，例如：「對於這個方案，我有一點點擔心⋯⋯」而不是說「你這個做法有問題」。","links":[]}
如果想拒絕別人但又不想傷害別人該怎麼做 → {"text":"採取「肯定＋拒絕＋提議」的模式。先感謝對方的邀請，誠實說明目前不方便的原因，最後主動提議另一個建議！","links":[]}
碰到陌生人時該怎麼互動 → {"text":"觀察當下的環境並提出「開放式問題」，例如：「你是怎麼知道這個活動的？」引導對方分享更多細節 😊","links":[]}
他不理我怎麼辦 → {"text":"可以先冷靜，不要生氣，過一會再嘗試說話。如果一直這樣，可以找 Karen、Doris、Amy 聊聊！","links":[]}
如果想跟別人聊天要怎麼開始 → {"text":"可以先打招呼，例如「你好！」，或問簡單問題，例如「你今天吃飯了嗎？」👋","links":[]}
別人跟我說笑話我聽不懂要怎麼回應 → {"text":"可以笑一笑或點頭，也可以說「我沒聽懂，可以再說一次嗎？」直接說不懂沒關係的！","links":[]}
想幫助別人但不知道怎麼開口 → {"text":"可以先問對方需不需要幫忙，例如「我可以幫你嗎？」簡單問一句就好！","links":[]}
如果想和不太熟的人交朋友要怎麼開始互動 → {"text":"可以先打招呼或問簡單問題，慢慢聊共同興趣，建立互動感覺。不用急，慢慢來就好！","links":[]}
別人表現出生氣我該怎麼反應 → {"text":"先冷靜，不生氣，不要反駁，聽對方說。給對方一些空間表達！","links":[]}
別人對我態度冷淡我該怎麼辦 → {"text":"不要生氣，可以先保持禮貌，給對方一些空間，或找其他朋友互動。也可以找 Karen、Doris、Amy 聊聊！","links":[]}
如果跟朋友意見不同要怎麼表達自己的想法 → {"text":"可以用「我覺得⋯」或「我想⋯」開頭，不要責怪對方，保持尊重和禮貌！","links":[]}
若使用者詢問某個日期是什麼星座（例如「8/18是什麼星座」「我的生日是1月5日是什麼星座」「3/21是哪個星座」），
請根據日期判斷對應星座，只回傳該星座名稱與符號，格式：
{"text":"8/18 是獅子座 ♌","links":[]}
血型有什麼有趣的地方/血型個性 → 由 MD 資料庫提供

--- 理財類 ---
悠遊卡要怎麼儲值 → {"text":"可以到超商（7-11、全家）、捷運站的儲值機儲值，把錢加到卡裡就可以用了！🎫","links":[]}
我的錢包怎麼管理才不會亂花 → {"text":"可以分門別類放錢，例如零用錢、交通錢、購物錢，每次只拿需要的錢出來花。","links":[]}
如果我想存零用錢要怎麼開始 → {"text":"可以先每天或每週存一小部分，放在存錢罐，慢慢累積。從小金額開始，習慣了就會越存越多！💰","links":[]}
我怎麼知道自己還有多少錢 → {"text":"可以記下每次花錢或儲值的金額、悠遊卡餘額或錢包裡的錢。用小本子記帳是個好方法！","links":[]}
買東西要怎麼比價才划算 → {"text":"可以先看看不同店家的價格或網路比價，再選價格合理、品質好的商品，不一定要買最貴的！","links":[]}
如果不小心花太多錢要怎麼處理 → {"text":"可以減少下一次的花費，暫時存錢，或者重新規劃零用錢，避免再超支。","links":[]}
我可以給別人借錢嗎要注意什麼 → {"text":"可以借，但要先想清楚對方會還嗎，借多少、什麼時候還都要講清楚，最好有記錄，這樣比較安全！","links":[]}

==========================================================
【第六優先：自由回答（題庫以外的日常問題）】
==========================================================
若問題不在題庫範圍內，也未觸發安全護欄，則用你自己的知識用繁體中文親切地回答。
規則：
1. 只回答日常生活、常識、知識性問題
2. 語氣保持溫和、簡單、易懂
3. 不得回答政治爭議、成人內容、危險操作等不適當問題
4. 回答仍需維持 JSON 格式：{"text":"你的回答內容","links":[]}

【重要】只回傳 JSON，不加任何其他文字。安全護欄永遠最優先。"""

# ══════════════════════════════════════════════════════
#  連結標籤對照表
# ══════════════════════════════════════════════════════
LINK_LABELS = {
    "cwa.gov.tw":         "🌤️ 中央氣象署 — 即時天氣查詢",
    "ebus.gov.taipei":    "🚌 台北市公車動態查詢",
    "maps/search":        "📍 Google Maps 路線導航",
    "google.com/maps":    "📍 Google Maps 搜尋",
    "klook.com":          "🎫 Klook 台北景點推薦",
    "bobbyfun.tw":        "🗺️ 台北旅遊完整指南",
    "travel.taipei":      "🏙️ 台北旅遊網 — 周邊景點",
    "foundi.tw":          "🚇 碧潭捷運出口資訊",
    "housefeel.com.tw":   "🛍️ 台北東區逛街資訊",
    "pixnet.net":         "🎬 電影推薦清單",
    "shonm32.com":        "🎌 動漫推薦清單",
    "drama/g63502713":    "📺 2025 熱門劇集推薦（上）",
    "drama/g63055787":    "📺 2025 熱門劇集推薦（下）",
    "elle.com.tw":        "📺 劇集推薦",
    "tiya.tw":            "🏨 台北休息房資訊",
    "tripadvisor.com.tw": "🎭 台北電影院推薦",
    "goodholiday.com.tw": "💤 夢境知識文章",
    "ck.ccgh.com.tw":     "🏥 打呼原因醫療說明",
    "skmh.com.tw":        "🏥 糖與健康醫療資訊",
    "vocus.cc":           "📖 推薦閱讀文章",
}

def get_link_label(url: str) -> str:
    for key, label in LINK_LABELS.items():
        if key in url:
            return label
    return "🔗 點此查看"


# ══════════════════════════════════════════════════════
#  文字→連結 fallback 對照表
# ══════════════════════════════════════════════════════
TEXT_TO_LINKS: list[tuple[str, list]] = [
    ("天氣預報",          ["https://www.cwa.gov.tw/V8/C/W/County/index.html"]),
    ("即時天氣",          ["https://www.cwa.gov.tw/V8/C/W/County/index.html"]),
    ("公車動態",          ["https://ebus.gov.taipei/ebus?ct=tpc"]),
    ("Google Maps",      ["https://www.google.com/maps?authuser=0"]),
    ("台北景點推薦",      ["https://www.klook.com/zh-TW/blog/taipei-destination-taiwan/",
                           "https://bobbyfun.tw/2024-03-06-3082/"]),
    ("台北車站周邊",      ["https://www.google.com/maps/search/臺北車站景點"]),
    ("小巨蛋",            ["https://www.travel.taipei/zh-tw/attraction/nearby-attractions/271?page=1"]),
    ("碧潭",              ["https://foundi.tw/%E7%A2%A7%E6%BD%AD%E9%A2%A8%E6%99%AF%E5%8D%80-%E5%B9%BE%E8%99%9F%E5%87%BA%E5%8F%A3%EF%BC%9F/"]),
    ("東區逛街",          ["https://www.housefeel.com.tw/article"]),
    ("電影推薦",          ["https://vocus.cc/article/668677b2fd897800018b7dea",
                           "https://awds5438qq.pixnet.net/blog/posts/14122488247"]),
    ("動漫推薦",          ["https://shonm32.com/anime-osusume000/"]),
    ("劇集推薦",          ["https://www.elle.com/tw/entertainment/drama/g63502713/best-chinese-drama-list-2025/",
                           "https://www.elle.com/tw/entertainment/drama/g63055787/2025-chinese-drama/"]),
    ("休息房",            ["https://tiya.tw/%E5%8F%B0%E5%8C%97%E4%BC%91%E6%81%AF3%E5%B0%8F%E6%99%82/",
                           "https://www.google.com/maps?authuser=0"]),
    ("電影院",            ["https://www.tripadvisor.com.tw/Attractions-g293913-Activities-c56-t97-Taipei.html",
                           "https://www.google.com/maps?authuser=0"]),
    ("夢境知識",          ["https://goodholiday.com.tw/article/EA7119007E1558C8340B"]),
    ("打呼",              ["https://ck.ccgh.com.tw/doctor_listDetail169.htm"]),
    ("糖與健康",          ["https://www.skmh.com.tw/education_detail.php?Key=31"]),
    ("血型",              ["https://vocus.cc/article/668677b2fd897800018b7dea"]),
]


def enrich_links(text: str, links: list) -> list:
    if links:
        return links
    import re as _re
    nav = _re.search(r'前往\s*(.+?)\s*的路線', text)
    if nav:
        place = nav.group(1).strip()
        import urllib.parse as _up
        return [f"https://www.google.com/maps/search/{_up.quote(place)}"]
    for keyword, fallback in TEXT_TO_LINKS:
        if keyword in text:
            return fallback
    return []


# ══════════════════════════════════════════════════════
#  ★ CWA 天氣 API 相關函式
# ══════════════════════════════════════════════════════

# 天氣問題關鍵字清單
WEATHER_KEYWORDS = [
    "天氣", "溫度", "下雨", "太陽", "颱風", "出門", "雨傘",
    "天氣變化", "洗衣服", "風大", "風會不會", "潮濕", "起霧",
    "帶傘", "會不會雨", "要帶傘",
]

# 城市名稱對照（使用者輸入 → CWA API locationName）
CITY_MAP = {
    "台北": "臺北市", "臺北": "臺北市",
    "新北": "新北市",
    "桃園": "桃園市",
    "台中": "臺中市", "臺中": "臺中市",
    "台南": "臺南市", "臺南": "臺南市",
    "高雄": "高雄市",
    "基隆": "基隆市",
    "新竹": "新竹縣",
    "苗栗": "苗栗縣",
    "彰化": "彰化縣",
    "南投": "南投縣",
    "雲林": "雲林縣",
    "嘉義": "嘉義縣",
    "屏東": "屏東縣",
    "宜蘭": "宜蘭縣",
    "花蓮": "花蓮縣",
    "台東": "臺東縣", "臺東": "臺東縣",
    "澎湖": "澎湖縣",
    "金門": "金門縣",
    "馬祖": "連江縣",
}


def is_weather_query(text: str) -> bool:
    """判斷是否為天氣相關問題。"""
    return any(kw in text for kw in WEATHER_KEYWORDS)


def extract_city_from_query(text: str) -> str:
    """從問題中擷取城市名；找不到則回傳預設城市。"""
    for keyword, full_name in CITY_MAP.items():
        if keyword in text:
            return full_name
    return CWA_DEFAULT_CITY


@st.cache_data(ttl=1800)   # 快取 30 分鐘，避免重複打 API
def fetch_cwa_weather(city: str) -> dict | None:
    """
    呼叫 CWA F-C0032-001（縣市 36 小時天氣預報）。
    回傳整理後的天氣摘要字典；失敗則回傳 None。

    使用 API：臺灣各縣市天氣預報資料（F-C0032-001）
    申請網址：https://opendata.cwa.gov.tw
    """
    if not CWA_API_KEY:
        return None
    try:
        url = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001"
        params = {
            "Authorization": CWA_API_KEY,
            "locationName":  city,
            "elementName":   "Wx,PoP,MinT,MaxT,CI",
        }
        res = requests.get(url, params=params, timeout=8)
        res.raise_for_status()
        data = res.json()

        locations = data.get("records", {}).get("location", [])
        if not locations:
            return None

        loc      = locations[0]
        elements = {
            e["elementName"]: e["time"][0]
            for e in loc["weatherElement"]
            if e.get("time")
        }

        return {
            "city":      loc["locationName"],
            "start":     elements.get("Wx", {}).get("startTime", ""),
            "end":       elements.get("Wx", {}).get("endTime", ""),
            "weather":   elements.get("Wx", {}).get("parameter", {}).get("parameterName", ""),
            "rain_pct":  elements.get("PoP", {}).get("parameter", {}).get("parameterValue", ""),
            "min_temp":  elements.get("MinT", {}).get("parameter", {}).get("parameterValue", ""),
            "max_temp":  elements.get("MaxT", {}).get("parameter", {}).get("parameterValue", ""),
            "comfort":   elements.get("CI", {}).get("parameter", {}).get("parameterName", ""),
        }
    except Exception:
        return None


def build_weather_system_block(weather: dict) -> str:
    """將天氣字典轉為注入 system prompt 的文字區塊。"""
    return (
        f"\n\n【今日天氣資料 — {weather['city']}】\n"
        f"預報時段：{weather['start']} ～ {weather['end']}\n"
        f"天氣現象：{weather['weather']}\n"
        f"降雨機率：{weather['rain_pct']}%\n"
        f"氣溫範圍：{weather['min_temp']}°C ～ {weather['max_temp']}°C\n"
        f"舒適度：{weather['comfort']}"
    )


# ══════════════════════════════════════════════════════
#  MD 資料庫相關函式
# ══════════════════════════════════════════════════════

@st.cache_data
def load_md_qa_database() -> list[dict]:
    if not os.path.exists(EXCEL_PATH):
        return []
    try:
        df = pd.read_excel(EXCEL_PATH)
    except Exception:
        return []

    entries = []
    for _, row in df.iterrows():
        answers = []
        for col in ["答案-1", "答案-2", "答案-3"]:
            val = row.get(col, "")
            if pd.notna(val) and str(val).strip():
                answers.append(str(val).strip())

        md_files  = [a for a in answers if a.endswith(".md")]
        other_ans = [a for a in answers if not a.endswith(".md")]

        if md_files:
            entries.append({
                "question": str(row["題目"]).strip(),
                "category": str(row["類別"]).strip(),
                "md_files": md_files,
                "other":    other_ans,
            })
    return entries


def extract_md_body(raw: str) -> str:
    marker = "Markdown Content:"
    idx    = raw.find(marker)
    body   = raw[idx + len(marker):].strip() if idx != -1 else raw.strip()
    if len(body) > MD_CONTENT_MAX_CHARS:
        body = body[:MD_CONTENT_MAX_CHARS] + "\n…（內容過長，已截斷）"
    return body


def extract_url_source(raw: str) -> str:
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("URL Source:"):
            return stripped.replace("URL Source:", "").strip()
    return ""


def load_md_file(filename: str) -> tuple[str, str]:
    path = os.path.join(MD_DATABASE_PATH, filename)
    if not os.path.exists(path):
        return "", ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        return extract_md_body(raw), extract_url_source(raw)
    except Exception:
        return "", ""


# ══════════════════════════════════════════════════════
#  星座判斷
# ══════════════════════════════════════════════════════
_ZODIAC_TABLE = [
    (1,  19, "魔羯座", "♑"),
    (2,  18, "水瓶座", "♒"),
    (3,  20, "雙魚座", "♓"),
    (4,  19, "牡羊座", "♈"),
    (5,  20, "金牛座", "♉"),
    (6,  20, "雙子座", "♊"),
    (7,  22, "巨蟹座", "♋"),
    (8,  22, "獅子座", "♌"),
    (9,  22, "處女座", "♍"),
    (10, 22, "天秤座", "♎"),
    (11, 21, "天蠍座", "♏"),
    (12, 21, "射手座", "♐"),
    (12, 31, "魔羯座", "♑"),
]

def get_zodiac(month: int, day: int) -> tuple[str, str] | None:
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    for end_m, end_d, name, symbol in _ZODIAC_TABLE:
        if month < end_m or (month == end_m and day <= end_d):
            return name, symbol
    return None


def detect_zodiac_query(user_text: str) -> dict | None:
    patterns = [
        r'(\d{1,2})[/月](\d{1,2})[日號]?',
        r'(\d{1,2})-(\d{1,2})',
    ]
    keywords = ["星座", "什麼座", "哪個座", "是幾座"]
    if not any(kw in user_text for kw in keywords):
        return None
    for pat in patterns:
        m = re.search(pat, user_text)
        if m:
            month, day = int(m.group(1)), int(m.group(2))
            result = get_zodiac(month, day)
            if result:
                name, symbol = result
                return {"text": f"{month}/{day} 是{name} {symbol}", "links": []}
    return None


# ══════════════════════════════════════════════════════
#  MD 題目比對
# ══════════════════════════════════════════════════════
def find_md_match(user_text: str, md_entries: list[dict]) -> dict | None:
    def normalize(s: str) -> str:
        return re.sub(r"[？?。，、！!　 ]", "", s)

    user_norm = normalize(user_text)
    best_entry, best_score = None, 0.0

    for entry in md_entries:
        q_norm = normalize(entry["question"])
        if not q_norm:
            continue
        common = sum(1 for c in q_norm if c in user_norm)
        score  = common / len(q_norm)
        if score > best_score and score >= 0.6:
            best_score = score
            best_entry = entry

    return best_entry


def build_md_context(entry: dict) -> tuple[str, list[str]]:
    parts, urls = [], []
    for md_file in entry["md_files"]:
        body, url = load_md_file(md_file)
        if body:
            label = md_file.replace(".md", "")
            parts.append(f"【{label}】\n{body}")
        if url:
            urls.append(url)
    for ans in entry.get("other", []):
        if ans.startswith("http") and ans not in urls:
            urls.append(ans)
    return "\n\n".join(parts), urls


# ══════════════════════════════════════════════════════
#  GPT 呼叫
# ══════════════════════════════════════════════════════
def parse_response(raw: str) -> dict:
    raw = raw.replace("\ufeff", "").replace("\u200b", "").replace("\u200c", "")
    raw = re.sub(r"```json|```", "", raw).strip()
    raw = raw.replace("\r\n", " ").replace("\r", " ")
    raw = raw.replace("\n", " ").replace("\t", " ")
    try:
        start = raw.index("{")
        depth = 0
        end   = start
        for i, ch in enumerate(raw[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        parsed = json.loads(raw[start:end])
        text   = str(parsed.get("text", ""))
        links  = parsed.get("links", [])
        return {"text": text, "links": links if isinstance(links, list) else []}
    except (ValueError, json.JSONDecodeError):
        pass
    m = re.search(r'"text"\s*:\s*"(.*?)"(?:\s*,|\s*})', raw, re.DOTALL)
    if m:
        return {"text": m.group(1), "links": []}
    return {"text": raw, "links": []}


def call_gpt(history: list, user_text: str) -> dict:
    print(f"[call_gpt] 收到問題：{user_text[:30]}")
    clean_key = "".join(c for c in OPENAI_API_KEY if ord(c) < 128).strip()
    client    = OpenAI(api_key=clean_key)

    # ── 1. 星座日期快速判斷（不需呼叫 GPT）────────────────
    zodiac_result = detect_zodiac_query(user_text)
    if zodiac_result:
        return zodiac_result

    # ── 2. ★ 天氣問題：呼叫 CWA API，注入即時資料 ──────────
    extra_system = ""
    weather_fallback_links = ["https://www.cwa.gov.tw/V8/C/W/County/index.html"]

    if is_weather_query(user_text):
        city    = extract_city_from_query(user_text)
        weather = fetch_cwa_weather(city)
        if weather:
            # 有資料 → 注入 system prompt，讓 GPT 直接回答
            extra_system = build_weather_system_block(weather)
        # 無資料（API 未設定或失敗）→ extra_system 為空，GPT 會依 prompt 給連結

    # ── 3. MD 資料庫比對 ───────────────────────────────────
    md_entries = load_md_qa_database()
    matched    = find_md_match(user_text, md_entries)
    hint_urls  = []

    if matched:
        context_text, hint_urls = build_md_context(matched)
        augmented = (
            f"{user_text}\n\n"
            "[MD資料庫內容 — 請根據以下內容整理並回答上方問題]\n"
            f"{context_text}"
        ) if context_text else user_text
    else:
        augmented = user_text

    # ── 4. 組合 messages（天氣資料附在 system prompt 末尾）──
    system_content = SYSTEM_PROMPT + extra_system
    messages = [{"role": "system", "content": system_content}]
    for msg in history:
        role = "user" if msg["role"] == "user" else "assistant"
        messages.append({"role": role, "content": msg["content"]})
    messages.append({"role": "user", "content": augmented})

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        temperature=0.2,
        max_tokens=1000,
    )
    raw    = response.choices[0].message.content.strip()
    result = parse_response(raw)

    # ── 5. 天氣問題一定附上 CWA 連結 ──────────────────────
    if is_weather_query(user_text) and not result["links"]:
        result["links"] = weather_fallback_links

    # MD hint_urls 補充
    if not result["links"] and hint_urls:
        result["links"] = hint_urls

    result["links"] = enrich_links(result["text"], result["links"])
    return result


# ══════════════════════════════════════════════════════
#  Session State
# ══════════════════════════════════════════════════════
def init_state():
    defaults = {
        "messages":      [],
        "last_activity": time.time(),
        "reset_notice":  False,
        "mic_key":       0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def reset_chat():
    st.session_state.messages      = []
    st.session_state.last_activity = time.time()
    st.session_state.reset_notice  = True


def check_auto_reset():
    elapsed = time.time() - st.session_state.last_activity
    if elapsed >= RESET_SECONDS and st.session_state.messages:
        reset_chat()


# ══════════════════════════════════════════════════════
#  主程式
# ══════════════════════════════════════════════════════
def main():
    st.set_page_config(
        page_title="演慈聊天機器人",
        page_icon="🤖",
        layout="centered",
    )

    init_state()

    if st.query_params.get("reset") == "1":
        st.query_params.clear()
        reset_chat()
        st.rerun()

    check_auto_reset()

    st_autorefresh(interval=30000, limit=None, key="reset_check")

    elapsed   = int(time.time() - st.session_state.last_activity)
    remaining = max(0, RESET_SECONDS - elapsed)
    mins, secs = divmod(remaining, 60)

    if st.button("🔄 重置", key="hdr_reset"):
        reset_chat()
        st.rerun()

    st.markdown(f"""
    <style>
    * {{ box-sizing: border-box; }}

    .main .block-container {{
        padding-top: 130px !important;
        padding-bottom: 90px !important;
        max-width: 760px;
    }}

    #fixed-header {{
        position: fixed;
        top: 2.875rem;
        left: 0; right: 0;
        z-index: 9999;
        background: linear-gradient(135deg, #1b4332, #2d6a4f);
        color: white;
        padding: 10px 20px;
        box-shadow: 0 2px 10px rgba(0,0,0,.35);
    }}
    #fixed-header .inner {{
        max-width: 760px;
        margin: 0 auto;
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 12px;
    }}
    #fixed-header h1 {{
        font-size: clamp(15px, 4vw, 19px);
        font-weight: 700;
        margin: 0;
        color: white;
    }}
    #fixed-header .sub {{
        font-size: clamp(10px, 2.5vw, 12px);
        opacity: .72;
        margin: 2px 0 0;
    }}
    #fixed-header .right {{
        display: flex;
        align-items: center;
        gap: 10px;
        flex-shrink: 0;
    }}
    #fixed-header .timer-box {{
        text-align: center;
        background: rgba(0,0,0,.22);
        border-radius: 10px;
        padding: 4px 12px;
        min-width: 72px;
    }}
    #fixed-header .timer-box small {{
        display: block;
        font-size: 9px;
        opacity: .65;
    }}
    #fixed-header .timer-box #hdr-countdown {{
        font-size: clamp(17px, 5vw, 21px);
        font-weight: 800;
        font-variant-numeric: tabular-nums;
        letter-spacing: 1px;
        color: #a7f3d0;
    }}

    #hdr-reset-container {{
        position: fixed;
        top: calc(2.875rem + 11px);
        right: 140px;
        z-index: 10001;
        margin: 0 !important;
    }}
    #hdr-reset-container button {{
        background: rgba(255,255,255,.15) !important;
        border: 1.5px solid rgba(255,255,255,.45) !important;
        color: white !important;
        font-size: 13px !important;
        font-weight: 600 !important;
        padding: 6px 16px !important;
        line-height: 1.4 !important;
        white-space: nowrap !important;
        min-height: unset !important;
        height: 36px !important;
        border-radius: 8px !important;
    }}
    #hdr-reset-container button:hover {{
        background: rgba(255,255,255,.28) !important;
        border-color: rgba(255,255,255,.75) !important;
    }}

    .stLinkButton a {{
        background: #f0fdf4 !important; color: #166534 !important;
        border: 1.5px solid #86efac !important;
        border-radius: 10px !important; font-weight: 500;
        word-break: break-word;
    }}
    .stLinkButton a:hover {{ background: #dcfce7 !important; border-color: #4ade80 !important; }}

    footer {{ visibility: hidden; }}
    </style>

    <div id="fixed-header">
      <div class="inner">
        <div>
          <h1>🤖 演慈聊天機器人</h1>
          <p class="sub">日常生活問答 · GPT-4o-mini</p>
        </div>
        <div class="right">
          <div class="timer-box">
            <small>對話重置倒數</small>
            <div id="hdr-countdown">{mins}:{secs:02d}</div>
          </div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.components.v1.html(f"""
    <script>
    var s = {remaining};
    function fmt(n) {{ var m=Math.floor(n/60),sec=n%60; return m+':'+(sec<10?'0':'')+sec; }}
    function color(n) {{ return n<=60?'#fca5a5':n<=120?'#fde68a':'#a7f3d0'; }}
    function tick() {{
        if(s>0) s--;
        var el=window.parent.document.getElementById('hdr-countdown');
        if(el){{ el.textContent=fmt(s); el.style.color=color(s); }}
    }}
    (function(){{
        var el=window.parent.document.getElementById('hdr-countdown');
        if(el) el.style.color=color(s);
    }})();
    setInterval(tick,1000);

    function moveResetBtn() {{
        try {{
            var doc = window.parent.document;
            var btn = doc.querySelector('[data-testid="stButton"]');
            var timerBox = doc.querySelector('.timer-box');
            if (btn && timerBox) {{
                var rect = timerBox.getBoundingClientRect();
                var container = btn.closest('[data-testid="element-container"]')
                                || btn.parentElement;
                if (container && container.id !== 'hdr-reset-container') {{
                    container.id = 'hdr-reset-container';
                }}
                if (container) {{
                    container.style.top  = rect.top + 'px';
                    var btnW = container.offsetWidth || 90;
                    container.style.right = (window.parent.innerWidth - rect.left + 10) + 'px';
                    container.style.left  = 'auto';
                }}
            }} else {{
                setTimeout(moveResetBtn, 100);
            }}
        }} catch(e) {{}}
    }}
    moveResetBtn();
    setInterval(moveResetBtn, 500);
    </script>
    """, height=1)

    if st.session_state.reset_notice:
        st.success("✨ 對話已自動重置，歡迎再次提問！")
        st.session_state.reset_notice = False

    st.divider()

    if not st.session_state.messages:
        with st.chat_message("assistant", avatar="🌿"):
            st.write(
                "你好！我是生活小幫手 👋\n\n"
                "我可以回答天氣、衣著、飲食、交通、娛樂、醫療、理財等"
                "日常生活問題，直接問我就可以喔！"
            )
        st.markdown("**💬 快速提問：**")
        quick_qs = [
            "今天天氣怎麼樣？", "台北推薦什麼景點？",
            "今天需要帶雨傘嗎？",  "悠遊卡要怎麼儲值？",
        ]
        cols = st.columns(2)
        for i, q in enumerate(quick_qs):
            if cols[i % 2].button(q, use_container_width=True, key=f"qq_{i}"):
                st.session_state.messages.append({"role": "user", "content": q, "links": []})
                st.session_state.last_activity = time.time()
                st.session_state["_pending"] = q
                st.rerun()

    for msg in st.session_state.messages:
        avatar = "🌿" if msg["role"] == "assistant" else "🙂"
        with st.chat_message(msg["role"], avatar=avatar):
            if msg.get("content"):
                st.write(msg["content"])
            for url in msg.get("links", []):
                label = get_link_label(url)
                st.markdown(
                    f'<a href="{url}" target="_blank" rel="noopener" style="'
                    'display:block;padding:10px 16px;margin:4px 0;'
                    'background:#f0fdf4;color:#166534;'
                    'border:1.5px solid #86efac;border-radius:10px;'
                    'text-align:center;text-decoration:none;font-weight:500;'
                    'word-break:break-word;">'
                    f'{label}</a>',
                    unsafe_allow_html=True,
                )

    if st.session_state.get("_pending"):
        user_text = st.session_state.pop("_pending")
        history_before = st.session_state.messages[:-1]
        with st.chat_message("assistant", avatar="🌿"):
            with st.spinner("思考中…"):
                try:
                    result = call_gpt(history_before, user_text)
                except Exception:
                    result = {"text": "⚠️ 發生錯誤：" + traceback.format_exc(), "links": []}
            if result["text"]:
                st.write(result["text"])
            for url in result.get("links", []):
                label = get_link_label(url)
                st.markdown(
                    f'<a href="{url}" target="_blank" rel="noopener" style="'
                    'display:block;padding:10px 16px;margin:4px 0;'
                    'background:#f0fdf4;color:#166534;'
                    'border:1.5px solid #86efac;border-radius:10px;'
                    'text-align:center;text-decoration:none;font-weight:500;'
                    'word-break:break-word;">'
                    f'{label}</a>',
                    unsafe_allow_html=True,
                )
        st.session_state.messages.append({
            "role":    "assistant",
            "content": result["text"],
            "links":   result.get("links", []),
        })
        st.rerun()

    user_input = st.chat_input("輸入問題，或點擊上方 🎤 錄音後說話")

    audio_file = st.audio_input(
        "錄音",
        key=f"mic_{st.session_state.mic_key}",
        label_visibility="collapsed",
    )

    if user_input:
        st.session_state.last_activity = time.time()
        st.session_state.messages.append({"role": "user", "content": user_input.strip(), "links": []})
        st.session_state["_pending"] = user_input.strip()
        st.rerun()

    if audio_file is not None:
        audio_bytes = audio_file.read()
        with st.spinner("🎤 語音辨識中…"):
            try:
                clean_key   = "".join(c for c in OPENAI_API_KEY if ord(c) < 128).strip()
                client_stt  = OpenAI(api_key=clean_key)
                mime        = getattr(audio_file, "type", "") or ""
                if "webm" in mime:
                    fname, fmime = "audio.webm", "audio/webm"
                elif "ogg" in mime:
                    fname, fmime = "audio.ogg",  "audio/ogg"
                else:
                    fname, fmime = "audio.wav",  "audio/wav"

                transcript = client_stt.audio.transcriptions.create(
                    model="whisper-1",
                    file=(fname, audio_bytes, fmime),
                    language="zh",
                    prompt="以下是繁體中文對話，請準確辨識每個字詞。",
                )
                voice_text = transcript.text.strip()
                if voice_text:
                    st.session_state.messages.append({"role": "user", "content": voice_text, "links": []})
                    st.session_state.last_activity = time.time()
                    st.session_state["_pending"]   = voice_text
            except Exception as e:
                st.warning(f"語音辨識失敗：{e}")
            finally:
                st.session_state.mic_key += 1
                st.rerun()


if __name__ == "__main__":
    main()