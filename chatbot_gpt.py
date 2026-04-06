import streamlit as st
import json
import time
import re
import traceback
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh

# ══════════════════════════════════════════════════════
#  設定區 — 依需求調整
# ══════════════════════════════════════════════════════
RESET_SECONDS  = 300
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
OPENAI_MODEL   = "gpt-4o-mini"
AUTOREFRESH_MS = 1000

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
【第三優先：題庫問答】
==========================================================
根據以下題庫找語意最接近的問題並回傳答案。

--- 天氣類 ---
今天天氣怎麼樣/今天溫度如何/今天會下雨嗎/今天太陽會不會很大/會不會有颱風/今天適合出門嗎/今天需要帶雨傘嗎/天氣會不會突然變化/今天的天氣適合洗衣服嗎/今天風會不會很大/今天會不會很潮濕/今天會不會起霧
→ {"text":"你可以點下方連結查看最新天氣預報！","links":["https://www.cwa.gov.tw/V8/C/W/County/index.html"]}
為什麼天空是藍色的 → {"text":"因為太陽進入大氣層時，波長較短的藍光比波長較長的紅光更容易被空氣中的微小分子散射，散射的藍光充滿了整個天空，所以我們看到天空是藍色的 🌈","links":[]}

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
台北推薦甚麼景點/台北有什麼好玩的 → {"text":"以下有台北景點推薦，點進去看看吧！🏙️","links":["https://www.klook.com/zh-TW/blog/taipei-destination-taiwan/?aid=api%7C67008%7C691fd6d0a233360001887676%7Cpid%7C886667&aff_pid=886667&aff_sid=&aff_adid=948770&utm_medium=affiliate-alwayson&utm_source=non-network&utm_campaign=67008&utm_term=886667&utm_content=&aff_klick_id=114951889007-api%7C67008%7C691fd6d0a233360001887676%7Cpid%7C886667-948770-86eb656&gad_source=1","https://bobbyfun.tw/2024-03-06-3082/"]}
台北車站附近有什麼好玩的景點 → {"text":"台北車站周邊有很多景點！🚉","links":["https://www.google.com/maps/search/臺北車站景點"]}
台北小巨蛋附近有什麼好玩的 → {"text":"台北小巨蛋附近有不少好玩的地方！點下方連結看看 🎪","links":["https://www.travel.taipei/zh-tw/attraction/nearby-attractions/271?page=1"]}
新店碧潭/碧潭捷運 → {"text":"點下方連結可以看碧潭風景區的捷運出口資訊！🚇","links":["https://foundi.tw/%E7%A2%A7%E6%BD%AD%E9%A2%A8%E6%99%AF%E5%8D%80-%E5%B9%BE%E8%99%9F%E5%87%BA%E5%8F%A3%EF%BC%9F/"]}
東區逛街/東區捷運 → {"text":"想去東區逛街，點下方連結有更多資訊！👗","links":["https://www.housefeel.com.tw/article"]}
有什麼電影推薦 → {"text":"以下有電影推薦文章，點進去看看吧！🎬","links":["https://vocus.cc/article/668677b2fd897800018b7dea","https://awds5438qq.pixnet.net/blog/posts/14122488247"]}
有什麼動漫推薦 → {"text":"點下方連結看看動漫推薦！🎌","links":["https://shonm32.com/anime-osusume000/"]}
有什麼推薦的劇/電視劇推薦 → {"text":"以下有最新劇集推薦！📺","links":["https://www.elle.com/tw/entertainment/drama/g63502713/best-chinese-drama-list-2025/","https://www.elle.com/tw/entertainment/drama/g63055787/2025-chinese-drama/"]}
休息房間/開休息的地方 → {"text":"以下有台北休息房資訊！","links":["https://tiya.tw/%E5%8F%B0%E5%8C%97%E4%BC%91%E6%81%AF3%E5%B0%8F%E6%99%82/","https://www.google.com/maps?authuser=0"]}
可以看電影的地方/電影院在哪 → {"text":"以下有台北電影院資訊！🍿","links":["https://www.tripadvisor.com.tw/Attractions-g293913-Activities-c56-t97-Taipei.html","https://www.google.com/maps?authuser=0"]}

--- 醫療類 ---
我不想吃藥 → {"text":"有時候藥可以讓你身體或心情好起來，不吃藥可能會讓病情變慢康復喔。如果真的不想吃，可以告訴醫生、Karen、Doris、Amy，一起討論解決方法！","links":[]}
為什麼要吃藥 → {"text":"吃藥可以幫助控制病情、減輕不舒服的症狀，讓身體或心情恢復得比較快 💊","links":[]}
如果忘記吃藥會怎麼樣 → {"text":"可能會病情不好或症狀加重，所以要盡量記得按時吃喔！","links":[]}
什麼時候要看醫生 → {"text":"如果身體或心情不舒服、症狀加重或不確定怎麼辦，就要去看醫生！不用等到很嚴重才去 🏥","links":[]}
醫生說的話我不懂要怎麼問 → {"text":"可以直接說「我不懂，可以再解釋一次嗎？」醫生會願意再解釋的，不用不好意思！","links":[]}
如果生病了要休息多久 → {"text":"看病的嚴重程度而定，一般多休息、不要太累，聽醫生的建議最安全。","links":[]}
我一直想睡覺怎麼辦 → {"text":"可以多休息沒關係，但如果一直沒有好轉，應該要去看醫生，或是問問 Karen、Doris、Amy 怎麼辦喔！","links":[]}
夢是真的嗎 → {"text":"關於夢的知識，點下方連結看看！😴","links":["https://goodholiday.com.tw/article/EA7119007E1558C8340B"]}
為什麼睡覺會打呼 → {"text":"關於打呼的原因，點下方連結看看！","links":["https://ck.ccgh.com.tw/doctor_listDetail169.htm"]}
為什麼不能吃糖 → {"text":"關於糖對身體的影響，點下方連結看看！🍬","links":["https://www.skmh.com.tw/education_detail.php?Key=31"]}

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
各個星座月份/星座日期 → {"text":"星座日期如下：\n♈ 牡羊座 3/21-4/19\n♉ 金牛座 4/20-5/20\n♊ 雙子座 5/21-6/20\n♋ 巨蟹座 6/21-7/22\n♌ 獅子座 7/23-8/22\n♍ 處女座 8/23-9/22\n♎ 天秤座 9/23-10/22\n♏ 天蠍座 10/23-11/21\n♐ 射手座 11/22-12/21\n♑ 魔羯座 12/22-1/19\n♒ 水瓶座 1/20-2/18\n♓ 雙魚座 2/19-3/20","links":[]}
血型有什麼有趣的地方/血型個性 → {"text":"點下方連結看看血型的有趣知識！🩸","links":["https://vocus.cc/article/668677b2fd897800018b7dea"]}

--- 理財類 ---
悠遊卡要怎麼儲值 → {"text":"可以到超商（7-11、全家）、捷運站的儲值機儲值，把錢加到卡裡就可以用了！🎫","links":[]}
我的錢包怎麼管理才不會亂花 → {"text":"可以分門別類放錢，例如零用錢、交通錢、購物錢，每次只拿需要的錢出來花。","links":[]}
如果我想存零用錢要怎麼開始 → {"text":"可以先每天或每週存一小部分，放在存錢罐，慢慢累積。從小金額開始，習慣了就會越存越多！💰","links":[]}
我怎麼知道自己還有多少錢 → {"text":"可以記下每次花錢或儲值的金額、悠遊卡餘額或錢包裡的錢。用小本子記帳是個好方法！","links":[]}
買東西要怎麼比價才划算 → {"text":"可以先看看不同店家的價格或網路比價，再選價格合理、品質好的商品，不一定要買最貴的！","links":[]}
如果不小心花太多錢要怎麼處理 → {"text":"可以減少下一次的花費，暫時存錢，或者重新規劃零用錢，避免再超支。","links":[]}
我可以給別人借錢嗎要注意什麼 → {"text":"可以借，但要先想清楚對方會還嗎，借多少、什麼時候還都要講清楚，最好有記錄，這樣比較安全！","links":[]}

==========================================================
【第四優先：自由回答（題庫以外的日常問題）】
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
        end = start
        for i, ch in enumerate(raw[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        parsed = json.loads(raw[start:end])
        text = str(parsed.get("text", ""))
        links = parsed.get("links", [])
        return {"text": text, "links": links if isinstance(links, list) else []}
    except (ValueError, json.JSONDecodeError):
        pass
    m = re.search(r'"text"\s*:\s*"(.*?)"(?:\s*,|\s*})', raw, re.DOTALL)
    if m:
        return {"text": m.group(1), "links": []}
    return {"text": raw, "links": []}


def call_gpt(history: list, user_text: str) -> dict:
    clean_key = "".join(c for c in OPENAI_API_KEY if ord(c) < 128).strip()
    client = OpenAI(api_key=clean_key)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in history:
        role = "user" if msg["role"] == "user" else "assistant"
        messages.append({"role": role, "content": msg["content"]})
    messages.append({"role": "user", "content": user_text})
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        temperature=0.2,
        max_tokens=1000,
    )
    raw = response.choices[0].message.content.strip()
    result = parse_response(raw)
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
        page_title="生活小幫手",
        page_icon="🌿",
        layout="centered",
    )

    init_state()

    # ── Query Param 重置 ──
    if st.query_params.get("reset") == "1":
        st.query_params.clear()
        reset_chat()
        st.rerun()

    check_auto_reset()

    # 每 30 秒 rerun 一次
    st_autorefresh(interval=30000, limit=None, key="reset_check")

    # 計算剩餘時間
    elapsed   = int(time.time() - st.session_state.last_activity)
    remaining = max(0, RESET_SECONDS - elapsed)
    mins, secs = divmod(remaining, 60)

    # ══════════════════════════════════════════════════
    # ★ 重置按鈕：使用原生 st.button（Python 層處理，100% 可靠）
    #   必須在 header markdown 之前 render，才能是頁面第一個 stButton。
    #   Timer JS 會用 window.parent 把它的容器移到 header 右側。
    # ══════════════════════════════════════════════════
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

    /* ── 固定 Header ── */
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

    /* ── 重置按鈕容器（由 JS 加上此 ID 後生效）── */
    #hdr-reset-container {{
        position: fixed;
        top: calc(2.875rem + 11px);   /* JS 會覆蓋為精確值 */
        right: 140px;                  /* JS 會覆蓋為精確值 */
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

    /* 連結按鈕 */
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
          <h1>🌿 生活小幫手</h1>
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

    # ── Timer JS ＋ 把原生 st.button 搬到 header 右側 ──
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

    // 把第一個 stButton（原生 st.button 重置按鈕）移到 header 右側
    // 動態讀取 timer-box 的實際 DOM 位置，讓按鈕與計時器對齊
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
                    // 垂直：與 timer-box 頂端對齊
                    container.style.top  = rect.top + 'px';
                    // 水平：緊靠 timer-box 左側，間距 10px
                    var btnW = container.offsetWidth || 90;
                    container.style.right = (window.parent.innerWidth - rect.left + 10) + 'px';
                    container.style.left  = 'auto';
                }}
            }} else {{
                setTimeout(moveResetBtn, 100);
            }}
        }} catch(e) {{}}
    }}
    // 頁面載入後執行，同時每 500ms 修正一次（應對 Streamlit rerun）
    moveResetBtn();
    setInterval(moveResetBtn, 500);
    </script>
    """, height=1)

    # Reset notice
    if st.session_state.reset_notice:
        st.success("✨ 對話已自動重置，歡迎再次提問！")
        st.session_state.reset_notice = False

    st.divider()

    # 歡迎訊息
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
            "有什麼電影推薦？",  "悠遊卡要怎麼儲值？",
        ]
        cols = st.columns(2)
        for i, q in enumerate(quick_qs):
            if cols[i % 2].button(q, use_container_width=True, key=f"qq_{i}"):
                st.session_state.messages.append({"role": "user", "content": q, "links": []})
                st.session_state.last_activity = time.time()
                st.session_state["_pending"] = q
                st.rerun()

    # 顯示歷史訊息
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

    # 呼叫 GPT
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
            "role": "assistant",
            "content": result["text"],
            "links": result.get("links", []),
        })
        st.rerun()

    # ── 輸入列：文字輸入框 ──
    user_input = st.chat_input("輸入問題，或點擊上方 🎤 錄音後說話")

    # ── 語音輸入 ──
    audio_file = st.audio_input(
        "錄音",
        key=f"mic_{st.session_state.mic_key}",
        label_visibility="collapsed",
    )

    # 處理文字輸入
    if user_input:
        st.session_state.last_activity = time.time()
        st.session_state.messages.append({"role": "user", "content": user_input.strip(), "links": []})
        st.session_state["_pending"] = user_input.strip()
        st.rerun()

    # 處理語音輸入
    if audio_file is not None:
        audio_bytes = audio_file.read()
        with st.spinner("🎤 語音辨識中…"):
            try:
                clean_key = "".join(c for c in OPENAI_API_KEY if ord(c) < 128).strip()
                client_stt = OpenAI(api_key=clean_key)

                mime = getattr(audio_file, "type", "") or ""
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
                    st.session_state["_pending"] = voice_text
            except Exception as e:
                st.warning(f"語音辨識失敗：{e}")
            finally:
                st.session_state.mic_key += 1
                st.rerun()


if __name__ == "__main__":
    main()