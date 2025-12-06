"""
=============================================================
INTERNATIONALIZATION (i18n) MODULE - Multi-Language Support
=============================================================
Modul ini menangani dukungan multi-bahasa untuk bot Telegram.

Fitur:
- Auto-detect bahasa user dari Telegram language_code
- Support untuk Indonesian (default), English, Hindi, Arabic, 
  Spanish, Portuguese, Russian, Chinese, Japanese, Korean, dll
- Fallback ke Indonesian jika bahasa tidak didukung
- Per-user language preference storage
- Easy-to-extend message catalog

Usage:
    from i18n import get_text, detect_language, SUPPORTED_LANGUAGES
    
    # Detect language from Telegram user
    lang = detect_language(update.effective_user.language_code)
    
    # Get translated text
    text = get_text("welcome_message", lang)
    
    # Get text with parameters
    text = get_text("balance_info", lang, balance=100.50, currency="USD")
=============================================================
"""

import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "id"

SUPPORTED_LANGUAGES = {
    "id": "Bahasa Indonesia",
    "en": "English",
    "hi": "हिन्दी (Hindi)",
    "ar": "العربية (Arabic)",
    "es": "Español (Spanish)",
    "pt": "Português (Portuguese)",
    "ru": "Русский (Russian)",
    "zh": "中文 (Chinese)",
    "ja": "日本語 (Japanese)",
    "ko": "한국어 (Korean)",
    "vi": "Tiếng Việt (Vietnamese)",
    "th": "ไทย (Thai)",
    "ms": "Bahasa Melayu (Malay)",
    "tr": "Türkçe (Turkish)",
    "de": "Deutsch (German)",
    "fr": "Français (French)",
    "it": "Italiano (Italian)",
    "nl": "Nederlands (Dutch)",
    "pl": "Polski (Polish)",
    "uk": "Українська (Ukrainian)",
    "bn": "বাংলা (Bengali)",
    "ta": "தமிழ் (Tamil)",
    "te": "తెలుగు (Telugu)",
    "ur": "اردو (Urdu)",
    "fa": "فارسی (Persian)",
    "fil": "Filipino",
}

LANGUAGE_CODE_MAPPING = {
    "id": "id",
    "en": "en",
    "en-US": "en",
    "en-GB": "en",
    "en-AU": "en",
    "hi": "hi",
    "hi-IN": "hi",
    "ar": "ar",
    "ar-SA": "ar",
    "ar-EG": "ar",
    "es": "es",
    "es-ES": "es",
    "es-MX": "es",
    "es-AR": "es",
    "pt": "pt",
    "pt-BR": "pt",
    "pt-PT": "pt",
    "ru": "ru",
    "zh": "zh",
    "zh-CN": "zh",
    "zh-TW": "zh",
    "zh-Hans": "zh",
    "zh-Hant": "zh",
    "ja": "ja",
    "ko": "ko",
    "vi": "vi",
    "th": "th",
    "ms": "ms",
    "tr": "tr",
    "de": "de",
    "de-DE": "de",
    "fr": "fr",
    "fr-FR": "fr",
    "it": "it",
    "nl": "nl",
    "pl": "pl",
    "uk": "uk",
    "bn": "bn",
    "ta": "ta",
    "te": "te",
    "ur": "ur",
    "fa": "fa",
    "fil": "fil",
    "tl": "fil",
}

MESSAGES: Dict[str, Dict[str, str]] = {
    "welcome_logged_in": {
        "id": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\nSelamat datang kembali! {account_emoji}\nAkun: **{account_type}**\n\n📊 **Indicators:** RSI, EMA, MACD, Stochastic, ATR\n\n📋 **Menu Utama:**\n• /akun - Kelola akun (saldo, switch demo/real)\n• /autotrade - Mulai auto trading\n• /stop - Hentikan trading\n• /status - Cek status bot\n• /help - Panduan lengkap\n\n⚠️ *Trading memiliki risiko. Gunakan dengan bijak.*",
        "en": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\nWelcome back! {account_emoji}\nAccount: **{account_type}**\n\n📊 **Indicators:** RSI, EMA, MACD, Stochastic, ATR\n\n📋 **Main Menu:**\n• /akun - Manage account (balance, switch demo/real)\n• /autotrade - Start auto trading\n• /stop - Stop trading\n• /status - Check bot status\n• /help - User guide\n\n⚠️ *Trading carries risks. Use wisely.*",
        "hi": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\nवापस स्वागत है! {account_emoji}\nखाता: **{account_type}**\n\n📊 **संकेतक:** RSI, EMA, MACD, Stochastic, ATR\n\n📋 **मुख्य मेनू:**\n• /akun - खाता प्रबंधित करें\n• /autotrade - ऑटो ट्रेडिंग शुरू करें\n• /stop - ट्रेडिंग बंद करें\n• /status - बॉट स्थिति जांचें\n• /help - उपयोगकर्ता गाइड\n\n⚠️ *ट्रेडिंग में जोखिम है। समझदारी से उपयोग करें।*",
        "ar": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\nمرحباً بعودتك! {account_emoji}\nالحساب: **{account_type}**\n\n📊 **المؤشرات:** RSI, EMA, MACD, Stochastic, ATR\n\n📋 **القائمة الرئيسية:**\n• /akun - إدارة الحساب\n• /autotrade - بدء التداول التلقائي\n• /stop - إيقاف التداول\n• /status - حالة البوت\n• /help - دليل المستخدم\n\n⚠️ *التداول ينطوي على مخاطر. استخدم بحكمة.*",
        "es": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\n¡Bienvenido de nuevo! {account_emoji}\nCuenta: **{account_type}**\n\n📊 **Indicadores:** RSI, EMA, MACD, Stochastic, ATR\n\n📋 **Menú Principal:**\n• /akun - Gestionar cuenta\n• /autotrade - Iniciar trading automático\n• /stop - Detener trading\n• /status - Estado del bot\n• /help - Guía de usuario\n\n⚠️ *El trading conlleva riesgos. Úsalo sabiamente.*",
        "pt": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\nBem-vindo de volta! {account_emoji}\nConta: **{account_type}**\n\n📊 **Indicadores:** RSI, EMA, MACD, Stochastic, ATR\n\n📋 **Menu Principal:**\n• /akun - Gerenciar conta\n• /autotrade - Iniciar trading automático\n• /stop - Parar trading\n• /status - Status do bot\n• /help - Guia do usuário\n\n⚠️ *Trading envolve riscos. Use com sabedoria.*",
        "ru": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\nС возвращением! {account_emoji}\nАккаунт: **{account_type}**\n\n📊 **Индикаторы:** RSI, EMA, MACD, Stochastic, ATR\n\n📋 **Главное меню:**\n• /akun - Управление аккаунтом\n• /autotrade - Начать автоторговлю\n• /stop - Остановить торговлю\n• /status - Статус бота\n• /help - Руководство\n\n⚠️ *Торговля связана с рисками. Используйте разумно.*",
        "zh": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\n欢迎回来! {account_emoji}\n账户: **{account_type}**\n\n📊 **指标:** RSI, EMA, MACD, Stochastic, ATR\n\n📋 **主菜单:**\n• /akun - 管理账户\n• /autotrade - 开始自动交易\n• /stop - 停止交易\n• /status - 检查机器人状态\n• /help - 用户指南\n\n⚠️ *交易存在风险，请谨慎使用。*",
        "ja": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\nおかえりなさい! {account_emoji}\nアカウント: **{account_type}**\n\n📊 **インジケーター:** RSI, EMA, MACD, Stochastic, ATR\n\n📋 **メインメニュー:**\n• /akun - アカウント管理\n• /autotrade - 自動取引開始\n• /stop - 取引停止\n• /status - ボット状態確認\n• /help - ユーザーガイド\n\n⚠️ *取引にはリスクがあります。賢明にご利用ください。*",
        "ko": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\n다시 오신 것을 환영합니다! {account_emoji}\n계정: **{account_type}**\n\n📊 **지표:** RSI, EMA, MACD, Stochastic, ATR\n\n📋 **메인 메뉴:**\n• /akun - 계정 관리\n• /autotrade - 자동 거래 시작\n• /stop - 거래 중지\n• /status - 봇 상태 확인\n• /help - 사용자 가이드\n\n⚠️ *거래에는 위험이 따릅니다. 현명하게 사용하세요.*",
        "vi": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\nChào mừng trở lại! {account_emoji}\nTài khoản: **{account_type}**\n\n📊 **Chỉ báo:** RSI, EMA, MACD, Stochastic, ATR\n\n📋 **Menu chính:**\n• /akun - Quản lý tài khoản\n• /autotrade - Bắt đầu giao dịch tự động\n• /stop - Dừng giao dịch\n• /status - Kiểm tra trạng thái bot\n• /help - Hướng dẫn sử dụng\n\n⚠️ *Giao dịch có rủi ro. Sử dụng cẩn thận.*",
        "th": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\nยินดีต้อนรับกลับ! {account_emoji}\nบัญชี: **{account_type}**\n\n📊 **ตัวชี้วัด:** RSI, EMA, MACD, Stochastic, ATR\n\n📋 **เมนูหลัก:**\n• /akun - จัดการบัญชี\n• /autotrade - เริ่มเทรดอัตโนมัติ\n• /stop - หยุดเทรด\n• /status - ตรวจสอบสถานะบอท\n• /help - คู่มือการใช้งาน\n\n⚠️ *การเทรดมีความเสี่ยง ใช้อย่างระมัดระวัง*",
        "ms": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\nSelamat kembali! {account_emoji}\nAkaun: **{account_type}**\n\n📊 **Penunjuk:** RSI, EMA, MACD, Stochastic, ATR\n\n📋 **Menu Utama:**\n• /akun - Urus akaun\n• /autotrade - Mula dagangan auto\n• /stop - Henti dagangan\n• /status - Semak status bot\n• /help - Panduan pengguna\n\n⚠️ *Dagangan melibatkan risiko. Gunakan dengan bijak.*",
        "tr": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\nTekrar hoş geldiniz! {account_emoji}\nHesap: **{account_type}**\n\n📊 **Göstergeler:** RSI, EMA, MACD, Stochastic, ATR\n\n📋 **Ana Menü:**\n• /akun - Hesap yönetimi\n• /autotrade - Otomatik işlem başlat\n• /stop - İşlemi durdur\n• /status - Bot durumu\n• /help - Kullanım kılavuzu\n\n⚠️ *İşlem risk içerir. Akıllıca kullanın.*",
        "de": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\nWillkommen zurück! {account_emoji}\nKonto: **{account_type}**\n\n📊 **Indikatoren:** RSI, EMA, MACD, Stochastic, ATR\n\n📋 **Hauptmenü:**\n• /akun - Konto verwalten\n• /autotrade - Autotrading starten\n• /stop - Trading stoppen\n• /status - Bot-Status prüfen\n• /help - Benutzerhandbuch\n\n⚠️ *Trading birgt Risiken. Nutze es weise.*",
        "fr": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\nBon retour! {account_emoji}\nCompte: **{account_type}**\n\n📊 **Indicateurs:** RSI, EMA, MACD, Stochastic, ATR\n\n📋 **Menu Principal:**\n• /akun - Gérer le compte\n• /autotrade - Démarrer le trading auto\n• /stop - Arrêter le trading\n• /status - Statut du bot\n• /help - Guide utilisateur\n\n⚠️ *Le trading comporte des risques. Utilisez-le judicieusement.*",
    },
    
    "welcome_not_logged_in": {
        "id": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\nSelamat datang! Bot ini adalah bot trading otomatis\nuntuk Binary Options (Volatility Index).\n\n🔐 **Anda belum login**\n\nUntuk menggunakan bot ini, Anda harus login terlebih dahulu\ndengan token API Deriv Anda.\n\n📍 **Cara Login:**\n1. Klik tombol LOGIN di bawah\n2. Pilih tipe akun (Demo/Real)\n3. Kirim token API Deriv Anda\n\n⚠️ *Token Anda akan dienkripsi dan disimpan dengan aman.*",
        "en": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\nWelcome! This is an automated trading bot\nfor Binary Options (Volatility Index).\n\n🔐 **You are not logged in**\n\nTo use this bot, you must first login\nwith your Deriv API token.\n\n📍 **How to Login:**\n1. Click the LOGIN button below\n2. Choose account type (Demo/Real)\n3. Send your Deriv API token\n\n⚠️ *Your token will be encrypted and stored securely.*",
        "hi": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\nस्वागत है! यह बाइनरी ऑप्शंस के लिए\nएक स्वचालित ट्रेडिंग बॉट है।\n\n🔐 **आप लॉग इन नहीं हैं**\n\nइस बॉट का उपयोग करने के लिए, पहले\nअपने Deriv API टोकन से लॉगिन करें।\n\n📍 **लॉगिन कैसे करें:**\n1. नीचे LOGIN बटन क्लिक करें\n2. खाता प्रकार चुनें (Demo/Real)\n3. अपना Deriv API टोकन भेजें\n\n⚠️ *आपका टोकन एन्क्रिप्ट और सुरक्षित रूप से संग्रहीत किया जाएगा।*",
        "ar": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\nمرحباً! هذا روبوت تداول آلي\nللخيارات الثنائية.\n\n🔐 **أنت غير مسجل الدخول**\n\nلاستخدام هذا الروبوت، يجب تسجيل الدخول أولاً\nباستخدام رمز API الخاص بك.\n\n📍 **كيفية تسجيل الدخول:**\n1. اضغط على زر تسجيل الدخول أدناه\n2. اختر نوع الحساب\n3. أرسل رمز API الخاص بك\n\n⚠️ *سيتم تشفير رمزك وتخزينه بأمان.*",
        "es": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\n¡Bienvenido! Este es un bot de trading automático\npara Opciones Binarias.\n\n🔐 **No has iniciado sesión**\n\nPara usar este bot, primero debes iniciar sesión\ncon tu token API de Deriv.\n\n📍 **Cómo iniciar sesión:**\n1. Haz clic en el botón LOGIN abajo\n2. Elige el tipo de cuenta\n3. Envía tu token API de Deriv\n\n⚠️ *Tu token será encriptado y almacenado de forma segura.*",
        "pt": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\nBem-vindo! Este é um bot de trading automático\npara Opções Binárias.\n\n🔐 **Você não está logado**\n\nPara usar este bot, primeiro faça login\ncom seu token API da Deriv.\n\n📍 **Como fazer login:**\n1. Clique no botão LOGIN abaixo\n2. Escolha o tipo de conta\n3. Envie seu token API da Deriv\n\n⚠️ *Seu token será criptografado e armazenado com segurança.*",
        "ru": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\nДобро пожаловать! Это автоматический торговый бот\nдля бинарных опционов.\n\n🔐 **Вы не вошли в систему**\n\nДля использования бота сначала войдите\nс вашим API токеном Deriv.\n\n📍 **Как войти:**\n1. Нажмите кнопку LOGIN ниже\n2. Выберите тип аккаунта\n3. Отправьте ваш API токен Deriv\n\n⚠️ *Ваш токен будет зашифрован и надёжно сохранён.*",
        "zh": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\n欢迎！这是一个用于二元期权的\n自动交易机器人。\n\n🔐 **您尚未登录**\n\n要使用此机器人，您必须首先\n使用您的Deriv API令牌登录。\n\n📍 **如何登录:**\n1. 点击下方的登录按钮\n2. 选择账户类型\n3. 发送您的Deriv API令牌\n\n⚠️ *您的令牌将被加密并安全存储。*",
        "ja": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\nようこそ！これはバイナリーオプション用の\n自動取引ボットです。\n\n🔐 **ログインしていません**\n\nこのボットを使用するには、まず\nDeriv APIトークンでログインしてください。\n\n📍 **ログイン方法:**\n1. 下のLOGINボタンをクリック\n2. アカウントタイプを選択\n3. Deriv APIトークンを送信\n\n⚠️ *トークンは暗号化され安全に保存されます。*",
        "ko": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\n환영합니다! 이것은 바이너리 옵션을 위한\n자동 거래 봇입니다.\n\n🔐 **로그인되지 않았습니다**\n\n이 봇을 사용하려면 먼저\nDeriv API 토큰으로 로그인해야 합니다.\n\n📍 **로그인 방법:**\n1. 아래 LOGIN 버튼 클릭\n2. 계정 유형 선택\n3. Deriv API 토큰 전송\n\n⚠️ *토큰은 암호화되어 안전하게 저장됩니다.*",
        "vi": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\nChào mừng! Đây là bot giao dịch tự động\ncho Quyền chọn nhị phân.\n\n🔐 **Bạn chưa đăng nhập**\n\nĐể sử dụng bot này, bạn phải đăng nhập trước\nvới token API Deriv của bạn.\n\n📍 **Cách đăng nhập:**\n1. Nhấp vào nút ĐĂNG NHẬP bên dưới\n2. Chọn loại tài khoản\n3. Gửi token API Deriv của bạn\n\n⚠️ *Token của bạn sẽ được mã hóa và lưu trữ an toàn.*",
        "th": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\nยินดีต้อนรับ! นี่คือบอทเทรดอัตโนมัติ\nสำหรับ Binary Options\n\n🔐 **คุณยังไม่ได้เข้าสู่ระบบ**\n\nในการใช้บอทนี้ คุณต้องเข้าสู่ระบบก่อน\nด้วย Deriv API token ของคุณ\n\n📍 **วิธีเข้าสู่ระบบ:**\n1. คลิกปุ่ม LOGIN ด้านล่าง\n2. เลือกประเภทบัญชี\n3. ส่ง Deriv API token ของคุณ\n\n⚠️ *Token ของคุณจะถูกเข้ารหัสและจัดเก็บอย่างปลอดภัย*",
        "ms": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\nSelamat datang! Ini adalah bot dagangan automatik\nuntuk Pilihan Binari.\n\n🔐 **Anda belum log masuk**\n\nUntuk menggunakan bot ini, anda mesti log masuk dahulu\ndengan token API Deriv anda.\n\n📍 **Cara Log Masuk:**\n1. Klik butang LOGIN di bawah\n2. Pilih jenis akaun\n3. Hantar token API Deriv anda\n\n⚠️ *Token anda akan disulitkan dan disimpan dengan selamat.*",
        "tr": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\nHoş geldiniz! Bu, İkili Opsiyonlar için\notomatik bir işlem botudur.\n\n🔐 **Giriş yapmadınız**\n\nBu botu kullanmak için önce\nDeriv API tokeninizle giriş yapmalısınız.\n\n📍 **Nasıl giriş yapılır:**\n1. Aşağıdaki GİRİŞ butonuna tıklayın\n2. Hesap türünü seçin\n3. Deriv API tokeninizi gönderin\n\n⚠️ *Tokeniniz şifrelenerek güvenle saklanacaktır.*",
        "de": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\nWillkommen! Dies ist ein automatischer Trading-Bot\nfür Binäre Optionen.\n\n🔐 **Sie sind nicht angemeldet**\n\nUm diesen Bot zu nutzen, müssen Sie sich zuerst\nmit Ihrem Deriv API-Token anmelden.\n\n📍 **Wie man sich anmeldet:**\n1. Klicken Sie auf den LOGIN-Button unten\n2. Wählen Sie den Kontotyp\n3. Senden Sie Ihren Deriv API-Token\n\n⚠️ *Ihr Token wird verschlüsselt und sicher gespeichert.*",
        "fr": "🤖 **DERIV AUTO TRADING BOT v2.0**\n\nBienvenue! Ceci est un bot de trading automatique\npour les Options Binaires.\n\n🔐 **Vous n'êtes pas connecté**\n\nPour utiliser ce bot, vous devez d'abord vous connecter\navec votre token API Deriv.\n\n📍 **Comment se connecter:**\n1. Cliquez sur le bouton CONNEXION ci-dessous\n2. Choisissez le type de compte\n3. Envoyez votre token API Deriv\n\n⚠️ *Votre token sera chiffré et stocké en sécurité.*",
    },
    
    "connecting_deriv": {
        "id": "🔄 Menghubungkan ke Deriv...\n\nMohon tunggu sebentar.",
        "en": "🔄 Connecting to Deriv...\n\nPlease wait a moment.",
        "hi": "🔄 Deriv से कनेक्ट हो रहा है...\n\nकृपया प्रतीक्षा करें।",
        "ar": "🔄 جاري الاتصال بـ Deriv...\n\nيرجى الانتظار.",
        "es": "🔄 Conectando a Deriv...\n\nPor favor espere un momento.",
        "pt": "🔄 Conectando ao Deriv...\n\nPor favor, aguarde um momento.",
        "ru": "🔄 Подключение к Deriv...\n\nПожалуйста, подождите.",
        "zh": "🔄 正在连接到Deriv...\n\n请稍候。",
        "ja": "🔄 Derivに接続中...\n\n少々お待ちください。",
        "ko": "🔄 Deriv에 연결 중...\n\n잠시만 기다려 주세요.",
        "vi": "🔄 Đang kết nối với Deriv...\n\nVui lòng đợi một chút.",
        "th": "🔄 กำลังเชื่อมต่อกับ Deriv...\n\nกรุณารอสักครู่",
        "ms": "🔄 Menyambung ke Deriv...\n\nSila tunggu sebentar.",
        "tr": "🔄 Deriv'e bağlanılıyor...\n\nLütfen bekleyin.",
        "de": "🔄 Verbindung zu Deriv wird hergestellt...\n\nBitte warten Sie einen Moment.",
        "fr": "🔄 Connexion à Deriv...\n\nVeuillez patienter un moment.",
    },
    
    "connection_failed": {
        "id": "❌ **Gagal koneksi ke Deriv**\n\n{error_msg}\n\nCoba /login untuk login ulang dengan token baru.",
        "en": "❌ **Failed to connect to Deriv**\n\n{error_msg}\n\nTry /login to log in again with a new token.",
        "hi": "❌ **Deriv से कनेक्ट नहीं हो सका**\n\n{error_msg}\n\nनए टोकन के साथ /login का प्रयास करें।",
        "ar": "❌ **فشل الاتصال بـ Deriv**\n\n{error_msg}\n\nجرب /login لتسجيل الدخول برمز جديد.",
        "es": "❌ **Error al conectar con Deriv**\n\n{error_msg}\n\nIntenta /login para iniciar sesión con un nuevo token.",
        "pt": "❌ **Falha ao conectar ao Deriv**\n\n{error_msg}\n\nTente /login para fazer login com um novo token.",
        "ru": "❌ **Не удалось подключиться к Deriv**\n\n{error_msg}\n\nПопробуйте /login для входа с новым токеном.",
        "zh": "❌ **连接Deriv失败**\n\n{error_msg}\n\n尝试使用 /login 用新令牌重新登录。",
        "ja": "❌ **Derivへの接続に失敗しました**\n\n{error_msg}\n\n新しいトークンで /login を試してください。",
        "ko": "❌ **Deriv 연결 실패**\n\n{error_msg}\n\n새 토큰으로 /login을 시도하세요.",
        "vi": "❌ **Không thể kết nối với Deriv**\n\n{error_msg}\n\nThử /login để đăng nhập lại với token mới.",
        "th": "❌ **เชื่อมต่อกับ Deriv ไม่สำเร็จ**\n\n{error_msg}\n\nลอง /login เพื่อเข้าสู่ระบบด้วย token ใหม่",
        "ms": "❌ **Gagal menyambung ke Deriv**\n\n{error_msg}\n\nCuba /login untuk log masuk semula dengan token baru.",
        "tr": "❌ **Deriv'e bağlanılamadı**\n\n{error_msg}\n\nYeni bir tokenla /login deneyin.",
        "de": "❌ **Verbindung zu Deriv fehlgeschlagen**\n\n{error_msg}\n\nVersuchen Sie /login mit einem neuen Token.",
        "fr": "❌ **Échec de connexion à Deriv**\n\n{error_msg}\n\nEssayez /login pour vous reconnecter avec un nouveau token.",
    },
    
    "access_denied": {
        "id": "🔒 **AKSES DITOLAK**\n\nAnda belum login. Gunakan /login terlebih dahulu.",
        "en": "🔒 **ACCESS DENIED**\n\nYou are not logged in. Please use /login first.",
        "hi": "🔒 **पहुंच अस्वीकृत**\n\nआप लॉग इन नहीं हैं। कृपया पहले /login का उपयोग करें।",
        "ar": "🔒 **تم رفض الوصول**\n\nأنت غير مسجل الدخول. يرجى استخدام /login أولاً.",
        "es": "🔒 **ACCESO DENEGADO**\n\nNo has iniciado sesión. Por favor usa /login primero.",
        "pt": "🔒 **ACESSO NEGADO**\n\nVocê não está logado. Por favor, use /login primeiro.",
        "ru": "🔒 **ДОСТУП ЗАПРЕЩЕН**\n\nВы не вошли в систему. Пожалуйста, используйте /login.",
        "zh": "🔒 **拒绝访问**\n\n您尚未登录。请先使用 /login。",
        "ja": "🔒 **アクセス拒否**\n\nログインしていません。まず /login を使用してください。",
        "ko": "🔒 **접근 거부**\n\n로그인되지 않았습니다. 먼저 /login을 사용하세요.",
        "vi": "🔒 **TỪ CHỐI TRUY CẬP**\n\nBạn chưa đăng nhập. Vui lòng sử dụng /login trước.",
        "th": "🔒 **ปฏิเสธการเข้าถึง**\n\nคุณยังไม่ได้เข้าสู่ระบบ กรุณาใช้ /login ก่อน",
        "ms": "🔒 **AKSES DITOLAK**\n\nAnda belum log masuk. Sila gunakan /login dahulu.",
        "tr": "🔒 **ERİŞİM REDDEDİLDİ**\n\nGiriş yapmadınız. Lütfen önce /login kullanın.",
        "de": "🔒 **ZUGANG VERWEIGERT**\n\nSie sind nicht angemeldet. Bitte verwenden Sie zuerst /login.",
        "fr": "🔒 **ACCÈS REFUSÉ**\n\nVous n'êtes pas connecté. Veuillez utiliser /login d'abord.",
    },
    
    "account_info": {
        "id": "💼 **INFORMASI AKUN**\n\n• Tipe: {account_type} {account_emoji}\n• ID: `{account_id}`\n• Saldo: **${balance:.2f}** {currency}\n• Saldo IDR: **Rp {balance_idr:,.0f}**",
        "en": "💼 **ACCOUNT INFO**\n\n• Type: {account_type} {account_emoji}\n• ID: `{account_id}`\n• Balance: **${balance:.2f}** {currency}\n• Balance IDR: **Rp {balance_idr:,.0f}**",
        "hi": "💼 **खाता जानकारी**\n\n• प्रकार: {account_type} {account_emoji}\n• ID: `{account_id}`\n• शेष: **${balance:.2f}** {currency}\n• IDR में शेष: **Rp {balance_idr:,.0f}**",
        "ar": "💼 **معلومات الحساب**\n\n• النوع: {account_type} {account_emoji}\n• المعرف: `{account_id}`\n• الرصيد: **${balance:.2f}** {currency}\n• الرصيد بالروبية: **Rp {balance_idr:,.0f}**",
        "es": "💼 **INFO DE CUENTA**\n\n• Tipo: {account_type} {account_emoji}\n• ID: `{account_id}`\n• Saldo: **${balance:.2f}** {currency}\n• Saldo IDR: **Rp {balance_idr:,.0f}**",
        "pt": "💼 **INFO DA CONTA**\n\n• Tipo: {account_type} {account_emoji}\n• ID: `{account_id}`\n• Saldo: **${balance:.2f}** {currency}\n• Saldo IDR: **Rp {balance_idr:,.0f}**",
        "ru": "💼 **ИНФОРМАЦИЯ ОБ АККАУНТЕ**\n\n• Тип: {account_type} {account_emoji}\n• ID: `{account_id}`\n• Баланс: **${balance:.2f}** {currency}\n• Баланс IDR: **Rp {balance_idr:,.0f}**",
        "zh": "💼 **账户信息**\n\n• 类型: {account_type} {account_emoji}\n• ID: `{account_id}`\n• 余额: **${balance:.2f}** {currency}\n• IDR余额: **Rp {balance_idr:,.0f}**",
        "ja": "💼 **アカウント情報**\n\n• タイプ: {account_type} {account_emoji}\n• ID: `{account_id}`\n• 残高: **${balance:.2f}** {currency}\n• IDR残高: **Rp {balance_idr:,.0f}**",
        "ko": "💼 **계정 정보**\n\n• 유형: {account_type} {account_emoji}\n• ID: `{account_id}`\n• 잔액: **${balance:.2f}** {currency}\n• IDR 잔액: **Rp {balance_idr:,.0f}**",
        "vi": "💼 **THÔNG TIN TÀI KHOẢN**\n\n• Loại: {account_type} {account_emoji}\n• ID: `{account_id}`\n• Số dư: **${balance:.2f}** {currency}\n• Số dư IDR: **Rp {balance_idr:,.0f}**",
        "th": "💼 **ข้อมูลบัญชี**\n\n• ประเภท: {account_type} {account_emoji}\n• ID: `{account_id}`\n• ยอดเงิน: **${balance:.2f}** {currency}\n• ยอดเงิน IDR: **Rp {balance_idr:,.0f}**",
        "ms": "💼 **INFO AKAUN**\n\n• Jenis: {account_type} {account_emoji}\n• ID: `{account_id}`\n• Baki: **${balance:.2f}** {currency}\n• Baki IDR: **Rp {balance_idr:,.0f}**",
        "tr": "💼 **HESAP BİLGİSİ**\n\n• Tür: {account_type} {account_emoji}\n• ID: `{account_id}`\n• Bakiye: **${balance:.2f}** {currency}\n• IDR Bakiye: **Rp {balance_idr:,.0f}**",
        "de": "💼 **KONTOINFORMATIONEN**\n\n• Typ: {account_type} {account_emoji}\n• ID: `{account_id}`\n• Saldo: **${balance:.2f}** {currency}\n• IDR Saldo: **Rp {balance_idr:,.0f}**",
        "fr": "💼 **INFO DU COMPTE**\n\n• Type: {account_type} {account_emoji}\n• ID: `{account_id}`\n• Solde: **${balance:.2f}** {currency}\n• Solde IDR: **Rp {balance_idr:,.0f}**",
    },
    
    "account_info_failed": {
        "id": "❌ Gagal mendapatkan info akun.",
        "en": "❌ Failed to get account info.",
        "hi": "❌ खाता जानकारी प्राप्त करने में विफल।",
        "ar": "❌ فشل في الحصول على معلومات الحساب.",
        "es": "❌ Error al obtener información de la cuenta.",
        "pt": "❌ Falha ao obter informações da conta.",
        "ru": "❌ Не удалось получить информацию об аккаунте.",
        "zh": "❌ 获取账户信息失败。",
        "ja": "❌ アカウント情報の取得に失敗しました。",
        "ko": "❌ 계정 정보를 가져오지 못했습니다.",
        "vi": "❌ Không thể lấy thông tin tài khoản.",
        "th": "❌ ไม่สามารถดึงข้อมูลบัญชีได้",
        "ms": "❌ Gagal mendapatkan info akaun.",
        "tr": "❌ Hesap bilgisi alınamadı.",
        "de": "❌ Kontoinformationen konnten nicht abgerufen werden.",
        "fr": "❌ Échec de récupération des informations du compte.",
    },
    
    "ws_not_connected": {
        "id": "❌ WebSocket belum terkoneksi. Tunggu beberapa detik...",
        "en": "❌ WebSocket not connected. Please wait a few seconds...",
        "hi": "❌ WebSocket कनेक्ट नहीं है। कृपया कुछ सेकंड प्रतीक्षा करें...",
        "ar": "❌ WebSocket غير متصل. يرجى الانتظار بضع ثوان...",
        "es": "❌ WebSocket no conectado. Por favor espere unos segundos...",
        "pt": "❌ WebSocket não conectado. Por favor, aguarde alguns segundos...",
        "ru": "❌ WebSocket не подключен. Подождите несколько секунд...",
        "zh": "❌ WebSocket未连接。请稍等几秒...",
        "ja": "❌ WebSocketが接続されていません。数秒お待ちください...",
        "ko": "❌ WebSocket이 연결되지 않았습니다. 몇 초만 기다려 주세요...",
        "vi": "❌ WebSocket chưa kết nối. Vui lòng đợi vài giây...",
        "th": "❌ WebSocket ยังไม่เชื่อมต่อ กรุณารอสักครู่...",
        "ms": "❌ WebSocket belum disambung. Sila tunggu beberapa saat...",
        "tr": "❌ WebSocket bağlı değil. Lütfen birkaç saniye bekleyin...",
        "de": "❌ WebSocket nicht verbunden. Bitte warten Sie einige Sekunden...",
        "fr": "❌ WebSocket non connecté. Veuillez patienter quelques secondes...",
    },
    
    "trading_manager_not_ready": {
        "id": "❌ Trading manager belum siap.",
        "en": "❌ Trading manager not ready.",
        "hi": "❌ ट्रेडिंग मैनेजर तैयार नहीं है।",
        "ar": "❌ مدير التداول غير جاهز.",
        "es": "❌ El gestor de trading no está listo.",
        "pt": "❌ Gerenciador de trading não está pronto.",
        "ru": "❌ Менеджер торговли не готов.",
        "zh": "❌ 交易管理器未就绪。",
        "ja": "❌ トレーディングマネージャーの準備ができていません。",
        "ko": "❌ 거래 관리자가 준비되지 않았습니다.",
        "vi": "❌ Trình quản lý giao dịch chưa sẵn sàng.",
        "th": "❌ ตัวจัดการเทรดยังไม่พร้อม",
        "ms": "❌ Pengurus dagangan belum sedia.",
        "tr": "❌ İşlem yöneticisi hazır değil.",
        "de": "❌ Trading-Manager nicht bereit.",
        "fr": "❌ Le gestionnaire de trading n'est pas prêt.",
    },
    
    "min_stake_warning": {
        "id": "⚠️ Stake minimum adalah ${min_stake}. Dikoreksi otomatis.",
        "en": "⚠️ Minimum stake is ${min_stake}. Auto-corrected.",
        "hi": "⚠️ न्यूनतम स्टेक ${min_stake} है। स्वचालित सुधार किया गया।",
        "ar": "⚠️ الحد الأدنى للرهان هو ${min_stake}. تم التصحيح تلقائياً.",
        "es": "⚠️ La apuesta mínima es ${min_stake}. Corregido automáticamente.",
        "pt": "⚠️ A aposta mínima é ${min_stake}. Corrigido automaticamente.",
        "ru": "⚠️ Минимальная ставка ${min_stake}. Автоматически исправлено.",
        "zh": "⚠️ 最低投注为 ${min_stake}。已自动更正。",
        "ja": "⚠️ 最小ステークは ${min_stake} です。自動修正されました。",
        "ko": "⚠️ 최소 스테이크는 ${min_stake}입니다. 자동 수정됨.",
        "vi": "⚠️ Mức cược tối thiểu là ${min_stake}. Đã tự động sửa.",
        "th": "⚠️ เงินเดิมพันขั้นต่ำคือ ${min_stake} ปรับแก้อัตโนมัติแล้ว",
        "ms": "⚠️ Pertaruhan minimum ialah ${min_stake}. Diperbetulkan secara automatik.",
        "tr": "⚠️ Minimum bahis ${min_stake}. Otomatik düzeltildi.",
        "de": "⚠️ Mindesteinsatz ist ${min_stake}. Automatisch korrigiert.",
        "fr": "⚠️ La mise minimum est ${min_stake}. Corrigé automatiquement.",
    },
    
    "invalid_stake_format": {
        "id": "❌ Format stake tidak valid. Gunakan angka.",
        "en": "❌ Invalid stake format. Use numbers.",
        "hi": "❌ अमान्य स्टेक प्रारूप। संख्याओं का उपयोग करें।",
        "ar": "❌ تنسيق الرهان غير صالح. استخدم الأرقام.",
        "es": "❌ Formato de apuesta inválido. Usa números.",
        "pt": "❌ Formato de aposta inválido. Use números.",
        "ru": "❌ Неверный формат ставки. Используйте цифры.",
        "zh": "❌ 无效的投注格式。请使用数字。",
        "ja": "❌ 無効なステーク形式。数字を使用してください。",
        "ko": "❌ 잘못된 스테이크 형식입니다. 숫자를 사용하세요.",
        "vi": "❌ Định dạng cược không hợp lệ. Sử dụng số.",
        "th": "❌ รูปแบบเงินเดิมพันไม่ถูกต้อง ใช้ตัวเลข",
        "ms": "❌ Format pertaruhan tidak sah. Gunakan nombor.",
        "tr": "❌ Geçersiz bahis formatı. Sayı kullanın.",
        "de": "❌ Ungültiges Einsatzformat. Verwenden Sie Zahlen.",
        "fr": "❌ Format de mise invalide. Utilisez des chiffres.",
    },
    
    "symbol_not_found": {
        "id": "⚠️ Symbol '{symbol}' tidak dikenal. Menggunakan default: {default_symbol}\n\nSymbol tersedia: {available}",
        "en": "⚠️ Symbol '{symbol}' not recognized. Using default: {default_symbol}\n\nAvailable symbols: {available}",
        "hi": "⚠️ सिंबल '{symbol}' पहचाना नहीं गया। डिफ़ॉल्ट का उपयोग: {default_symbol}\n\nउपलब्ध सिंबल: {available}",
        "ar": "⚠️ الرمز '{symbol}' غير معروف. باستخدام الافتراضي: {default_symbol}\n\nالرموز المتاحة: {available}",
        "es": "⚠️ Símbolo '{symbol}' no reconocido. Usando predeterminado: {default_symbol}\n\nSímbolos disponibles: {available}",
        "pt": "⚠️ Símbolo '{symbol}' não reconhecido. Usando padrão: {default_symbol}\n\nSímbolos disponíveis: {available}",
        "ru": "⚠️ Символ '{symbol}' не распознан. Используется по умолчанию: {default_symbol}\n\nДоступные символы: {available}",
        "zh": "⚠️ 未识别符号 '{symbol}'。使用默认值: {default_symbol}\n\n可用符号: {available}",
        "ja": "⚠️ シンボル '{symbol}' が認識されません。デフォルトを使用: {default_symbol}\n\n利用可能なシンボル: {available}",
        "ko": "⚠️ 심볼 '{symbol}'을(를) 인식할 수 없습니다. 기본값 사용: {default_symbol}\n\n사용 가능한 심볼: {available}",
        "vi": "⚠️ Symbol '{symbol}' không được nhận dạng. Sử dụng mặc định: {default_symbol}\n\nSymbol có sẵn: {available}",
        "th": "⚠️ ไม่รู้จักสัญลักษณ์ '{symbol}' ใช้ค่าเริ่มต้น: {default_symbol}\n\nสัญลักษณ์ที่มี: {available}",
        "ms": "⚠️ Simbol '{symbol}' tidak dikenali. Menggunakan lalai: {default_symbol}\n\nSimbol tersedia: {available}",
        "tr": "⚠️ '{symbol}' sembolü tanınmadı. Varsayılan kullanılıyor: {default_symbol}\n\nMevcut semboller: {available}",
        "de": "⚠️ Symbol '{symbol}' nicht erkannt. Verwende Standard: {default_symbol}\n\nVerfügbare Symbole: {available}",
        "fr": "⚠️ Symbole '{symbol}' non reconnu. Utilisation par défaut: {default_symbol}\n\nSymboles disponibles: {available}",
    },
    
    "trading_stopped": {
        "id": "⏹️ **Trading dihentikan**",
        "en": "⏹️ **Trading stopped**",
        "hi": "⏹️ **ट्रेडिंग रोक दी गई**",
        "ar": "⏹️ **تم إيقاف التداول**",
        "es": "⏹️ **Trading detenido**",
        "pt": "⏹️ **Trading parado**",
        "ru": "⏹️ **Торговля остановлена**",
        "zh": "⏹️ **交易已停止**",
        "ja": "⏹️ **取引が停止しました**",
        "ko": "⏹️ **거래 중지됨**",
        "vi": "⏹️ **Giao dịch đã dừng**",
        "th": "⏹️ **หยุดเทรดแล้ว**",
        "ms": "⏹️ **Dagangan dihentikan**",
        "tr": "⏹️ **İşlem durduruldu**",
        "de": "⏹️ **Trading gestoppt**",
        "fr": "⏹️ **Trading arrêté**",
    },
    
    "trading_not_active": {
        "id": "ℹ️ Trading tidak sedang aktif.",
        "en": "ℹ️ Trading is not currently active.",
        "hi": "ℹ️ ट्रेडिंग वर्तमान में सक्रिय नहीं है।",
        "ar": "ℹ️ التداول غير نشط حالياً.",
        "es": "ℹ️ El trading no está activo actualmente.",
        "pt": "ℹ️ O trading não está ativo no momento.",
        "ru": "ℹ️ Торговля в данный момент не активна.",
        "zh": "ℹ️ 交易当前未激活。",
        "ja": "ℹ️ 現在取引はアクティブではありません。",
        "ko": "ℹ️ 현재 거래가 활성화되어 있지 않습니다.",
        "vi": "ℹ️ Giao dịch hiện không hoạt động.",
        "th": "ℹ️ ขณะนี้ไม่ได้เทรดอยู่",
        "ms": "ℹ️ Dagangan tidak aktif pada masa ini.",
        "tr": "ℹ️ İşlem şu anda aktif değil.",
        "de": "ℹ️ Trading ist derzeit nicht aktiv.",
        "fr": "ℹ️ Le trading n'est pas actif actuellement.",
    },
    
    "login_select_account": {
        "id": "🔐 **LOGIN KE DERIV**\n\nPilih tipe akun yang akan digunakan:\n\n• **DEMO** 🎮 - Latihan trading tanpa risiko\n• **REAL** 💵 - Trading dengan uang sungguhan\n\n⚠️ Pastikan token API sudah dibuat di Deriv Dashboard.",
        "en": "🔐 **LOGIN TO DERIV**\n\nSelect the account type to use:\n\n• **DEMO** 🎮 - Practice trading without risk\n• **REAL** 💵 - Trade with real money\n\n⚠️ Make sure the API token is created in Deriv Dashboard.",
        "hi": "🔐 **DERIV में लॉगिन करें**\n\nउपयोग करने के लिए खाता प्रकार चुनें:\n\n• **DEMO** 🎮 - जोखिम के बिना अभ्यास\n• **REAL** 💵 - असली पैसे से ट्रेड करें\n\n⚠️ सुनिश्चित करें कि API टोकन Deriv Dashboard में बनाया गया है।",
        "ar": "🔐 **تسجيل الدخول إلى DERIV**\n\nاختر نوع الحساب المراد استخدامه:\n\n• **تجريبي** 🎮 - تداول تجريبي بدون مخاطر\n• **حقيقي** 💵 - تداول بأموال حقيقية\n\n⚠️ تأكد من إنشاء رمز API في لوحة تحكم Deriv.",
        "es": "🔐 **INICIAR SESIÓN EN DERIV**\n\nSelecciona el tipo de cuenta a usar:\n\n• **DEMO** 🎮 - Practica sin riesgo\n• **REAL** 💵 - Opera con dinero real\n\n⚠️ Asegúrate de crear el token API en Deriv Dashboard.",
        "pt": "🔐 **LOGIN NO DERIV**\n\nSelecione o tipo de conta a usar:\n\n• **DEMO** 🎮 - Pratique sem risco\n• **REAL** 💵 - Negocie com dinheiro real\n\n⚠️ Certifique-se de que o token API foi criado no Deriv Dashboard.",
        "ru": "🔐 **ВХОД В DERIV**\n\nВыберите тип аккаунта:\n\n• **DEMO** 🎮 - Практика без риска\n• **REAL** 💵 - Торговля на реальные деньги\n\n⚠️ Убедитесь, что API токен создан в панели Deriv.",
        "zh": "🔐 **登录DERIV**\n\n选择要使用的账户类型:\n\n• **DEMO** 🎮 - 无风险练习交易\n• **REAL** 💵 - 用真实资金交易\n\n⚠️ 确保已在Deriv控制面板创建API令牌。",
        "ja": "🔐 **DERIVにログイン**\n\n使用するアカウントタイプを選択:\n\n• **DEMO** 🎮 - リスクなしで練習\n• **REAL** 💵 - 実際のお金で取引\n\n⚠️ DerivダッシュボードでAPIトークンが作成されていることを確認してください。",
        "ko": "🔐 **DERIV 로그인**\n\n사용할 계정 유형을 선택하세요:\n\n• **DEMO** 🎮 - 위험 없이 연습\n• **REAL** 💵 - 실제 돈으로 거래\n\n⚠️ Deriv 대시보드에서 API 토큰이 생성되었는지 확인하세요.",
        "vi": "🔐 **ĐĂNG NHẬP DERIV**\n\nChọn loại tài khoản để sử dụng:\n\n• **DEMO** 🎮 - Thực hành không rủi ro\n• **REAL** 💵 - Giao dịch với tiền thật\n\n⚠️ Đảm bảo đã tạo token API trong Deriv Dashboard.",
        "th": "🔐 **เข้าสู่ระบบ DERIV**\n\nเลือกประเภทบัญชีที่จะใช้:\n\n• **DEMO** 🎮 - ฝึกซ้อมโดยไม่มีความเสี่ยง\n• **REAL** 💵 - เทรดด้วยเงินจริง\n\n⚠️ ตรวจสอบให้แน่ใจว่าสร้าง API token ใน Deriv Dashboard แล้ว",
        "ms": "🔐 **LOG MASUK KE DERIV**\n\nPilih jenis akaun untuk digunakan:\n\n• **DEMO** 🎮 - Latihan tanpa risiko\n• **REAL** 💵 - Berdagang dengan wang sebenar\n\n⚠️ Pastikan token API telah dibuat di Deriv Dashboard.",
        "tr": "🔐 **DERIV'E GİRİŞ**\n\nKullanılacak hesap türünü seçin:\n\n• **DEMO** 🎮 - Risksiz pratik yapın\n• **REAL** 💵 - Gerçek parayla işlem yapın\n\n⚠️ API tokeninin Deriv Dashboard'da oluşturulduğundan emin olun.",
        "de": "🔐 **BEI DERIV ANMELDEN**\n\nWählen Sie den Kontotyp:\n\n• **DEMO** 🎮 - Risikofrei üben\n• **REAL** 💵 - Mit echtem Geld handeln\n\n⚠️ Stellen Sie sicher, dass der API-Token im Deriv Dashboard erstellt wurde.",
        "fr": "🔐 **CONNEXION À DERIV**\n\nSélectionnez le type de compte à utiliser:\n\n• **DEMO** 🎮 - Pratiquez sans risque\n• **REAL** 💵 - Tradez avec de l'argent réel\n\n⚠️ Assurez-vous que le token API est créé dans le tableau de bord Deriv.",
    },
    
    "send_token": {
        "id": "🔑 **MASUKKAN TOKEN API**\n\nAkun: **{account_type}** {emoji}\n\nKirim token API Deriv Anda sekarang.\n\n⚠️ Token akan dihapus dari chat setelah terverifikasi.\n\n📍 Dapatkan token di: app.deriv.com → Settings → API Token",
        "en": "🔑 **ENTER API TOKEN**\n\nAccount: **{account_type}** {emoji}\n\nSend your Deriv API token now.\n\n⚠️ Token will be deleted from chat after verification.\n\n📍 Get token at: app.deriv.com → Settings → API Token",
        "hi": "🔑 **API टोकन दर्ज करें**\n\nखाता: **{account_type}** {emoji}\n\nअभी अपना Deriv API टोकन भेजें।\n\n⚠️ सत्यापन के बाद टोकन चैट से हटा दिया जाएगा।\n\n📍 टोकन प्राप्त करें: app.deriv.com → Settings → API Token",
        "ar": "🔑 **أدخل رمز API**\n\nالحساب: **{account_type}** {emoji}\n\nأرسل رمز API الخاص بك الآن.\n\n⚠️ سيتم حذف الرمز من المحادثة بعد التحقق.\n\n📍 احصل على الرمز من: app.deriv.com → Settings → API Token",
        "es": "🔑 **INGRESA EL TOKEN API**\n\nCuenta: **{account_type}** {emoji}\n\nEnvía tu token API de Deriv ahora.\n\n⚠️ El token se eliminará del chat después de la verificación.\n\n📍 Obtén el token en: app.deriv.com → Settings → API Token",
        "pt": "🔑 **DIGITE O TOKEN API**\n\nConta: **{account_type}** {emoji}\n\nEnvie seu token API da Deriv agora.\n\n⚠️ O token será excluído do chat após a verificação.\n\n📍 Obtenha o token em: app.deriv.com → Settings → API Token",
        "ru": "🔑 **ВВЕДИТЕ API ТОКЕН**\n\nАккаунт: **{account_type}** {emoji}\n\nОтправьте ваш API токен Deriv сейчас.\n\n⚠️ Токен будет удалён из чата после проверки.\n\n📍 Получите токен: app.deriv.com → Settings → API Token",
        "zh": "🔑 **输入API令牌**\n\n账户: **{account_type}** {emoji}\n\n现在发送您的Deriv API令牌。\n\n⚠️ 验证后令牌将从聊天中删除。\n\n📍 获取令牌: app.deriv.com → Settings → API Token",
        "ja": "🔑 **APIトークンを入力**\n\nアカウント: **{account_type}** {emoji}\n\nDeriv APIトークンを今すぐ送信してください。\n\n⚠️ 確認後、トークンはチャットから削除されます。\n\n📍 トークン取得: app.deriv.com → Settings → API Token",
        "ko": "🔑 **API 토큰 입력**\n\n계정: **{account_type}** {emoji}\n\nDeriv API 토큰을 지금 보내주세요.\n\n⚠️ 확인 후 토큰은 채팅에서 삭제됩니다.\n\n📍 토큰 받기: app.deriv.com → Settings → API Token",
        "vi": "🔑 **NHẬP TOKEN API**\n\nTài khoản: **{account_type}** {emoji}\n\nGửi token API Deriv của bạn ngay bây giờ.\n\n⚠️ Token sẽ được xóa khỏi chat sau khi xác minh.\n\n📍 Lấy token tại: app.deriv.com → Settings → API Token",
        "th": "🔑 **ใส่ API TOKEN**\n\nบัญชี: **{account_type}** {emoji}\n\nส่ง Deriv API token ของคุณตอนนี้\n\n⚠️ Token จะถูกลบจากแชทหลังการยืนยัน\n\n📍 รับ token ที่: app.deriv.com → Settings → API Token",
        "ms": "🔑 **MASUKKAN TOKEN API**\n\nAkaun: **{account_type}** {emoji}\n\nHantar token API Deriv anda sekarang.\n\n⚠️ Token akan dipadam dari chat selepas pengesahan.\n\n📍 Dapatkan token di: app.deriv.com → Settings → API Token",
        "tr": "🔑 **API TOKEN GİRİN**\n\nHesap: **{account_type}** {emoji}\n\nDeriv API tokeninizi şimdi gönderin.\n\n⚠️ Token doğrulamadan sonra sohbetten silinecektir.\n\n📍 Token alın: app.deriv.com → Settings → API Token",
        "de": "🔑 **API TOKEN EINGEBEN**\n\nKonto: **{account_type}** {emoji}\n\nSenden Sie jetzt Ihren Deriv API-Token.\n\n⚠️ Token wird nach Verifizierung aus dem Chat gelöscht.\n\n📍 Token erhalten: app.deriv.com → Settings → API Token",
        "fr": "🔑 **ENTREZ LE TOKEN API**\n\nCompte: **{account_type}** {emoji}\n\nEnvoyez votre token API Deriv maintenant.\n\n⚠️ Le token sera supprimé du chat après vérification.\n\n📍 Obtenez le token: app.deriv.com → Settings → API Token",
    },
    
    "login_success": {
        "id": "✅ **Login berhasil!**\n\n• Tipe: {account_type}\n• Token: ...{fingerprint}\n\nMenghubungkan ke Deriv...",
        "en": "✅ **Login successful!**\n\n• Type: {account_type}\n• Token: ...{fingerprint}\n\nConnecting to Deriv...",
        "hi": "✅ **लॉगिन सफल!**\n\n• प्रकार: {account_type}\n• टोकन: ...{fingerprint}\n\nDeriv से कनेक्ट हो रहा है...",
        "ar": "✅ **تم تسجيل الدخول بنجاح!**\n\n• النوع: {account_type}\n• الرمز: ...{fingerprint}\n\nجاري الاتصال بـ Deriv...",
        "es": "✅ **¡Inicio de sesión exitoso!**\n\n• Tipo: {account_type}\n• Token: ...{fingerprint}\n\nConectando a Deriv...",
        "pt": "✅ **Login bem-sucedido!**\n\n• Tipo: {account_type}\n• Token: ...{fingerprint}\n\nConectando ao Deriv...",
        "ru": "✅ **Вход выполнен успешно!**\n\n• Тип: {account_type}\n• Токен: ...{fingerprint}\n\nПодключение к Deriv...",
        "zh": "✅ **登录成功!**\n\n• 类型: {account_type}\n• 令牌: ...{fingerprint}\n\n正在连接到Deriv...",
        "ja": "✅ **ログイン成功!**\n\n• タイプ: {account_type}\n• トークン: ...{fingerprint}\n\nDerivに接続中...",
        "ko": "✅ **로그인 성공!**\n\n• 유형: {account_type}\n• 토큰: ...{fingerprint}\n\nDeriv에 연결 중...",
        "vi": "✅ **Đăng nhập thành công!**\n\n• Loại: {account_type}\n• Token: ...{fingerprint}\n\nĐang kết nối với Deriv...",
        "th": "✅ **เข้าสู่ระบบสำเร็จ!**\n\n• ประเภท: {account_type}\n• Token: ...{fingerprint}\n\nกำลังเชื่อมต่อกับ Deriv...",
        "ms": "✅ **Log masuk berjaya!**\n\n• Jenis: {account_type}\n• Token: ...{fingerprint}\n\nMenyambung ke Deriv...",
        "tr": "✅ **Giriş başarılı!**\n\n• Tür: {account_type}\n• Token: ...{fingerprint}\n\nDeriv'e bağlanılıyor...",
        "de": "✅ **Anmeldung erfolgreich!**\n\n• Typ: {account_type}\n• Token: ...{fingerprint}\n\nVerbinde mit Deriv...",
        "fr": "✅ **Connexion réussie!**\n\n• Type: {account_type}\n• Token: ...{fingerprint}\n\nConnexion à Deriv...",
    },
    
    "logout_confirm": {
        "id": "⚠️ **KONFIRMASI LOGOUT**\n\nApakah Anda yakin ingin logout?\nSemua data sesi akan dihapus.",
        "en": "⚠️ **CONFIRM LOGOUT**\n\nAre you sure you want to logout?\nAll session data will be deleted.",
        "hi": "⚠️ **लॉगआउट की पुष्टि करें**\n\nक्या आप वाकई लॉगआउट करना चाहते हैं?\nसभी सत्र डेटा हटा दिया जाएगा।",
        "ar": "⚠️ **تأكيد تسجيل الخروج**\n\nهل أنت متأكد من تسجيل الخروج?\nسيتم حذف جميع بيانات الجلسة.",
        "es": "⚠️ **CONFIRMAR CIERRE DE SESIÓN**\n\n¿Estás seguro de que quieres cerrar sesión?\nSe eliminarán todos los datos de la sesión.",
        "pt": "⚠️ **CONFIRMAR LOGOUT**\n\nTem certeza de que deseja sair?\nTodos os dados da sessão serão excluídos.",
        "ru": "⚠️ **ПОДТВЕРДИТЕ ВЫХОД**\n\nВы уверены, что хотите выйти?\nВсе данные сессии будут удалены.",
        "zh": "⚠️ **确认退出**\n\n您确定要退出吗?\n所有会话数据将被删除。",
        "ja": "⚠️ **ログアウト確認**\n\n本当にログアウトしますか？\nすべてのセッションデータが削除されます。",
        "ko": "⚠️ **로그아웃 확인**\n\n정말 로그아웃하시겠습니까?\n모든 세션 데이터가 삭제됩니다.",
        "vi": "⚠️ **XÁC NHẬN ĐĂNG XUẤT**\n\nBạn có chắc muốn đăng xuất không?\nTất cả dữ liệu phiên sẽ bị xóa.",
        "th": "⚠️ **ยืนยันออกจากระบบ**\n\nคุณแน่ใจหรือไม่ว่าต้องการออกจากระบบ?\nข้อมูลเซสชันทั้งหมดจะถูกลบ",
        "ms": "⚠️ **SAHKAN LOG KELUAR**\n\nAdakah anda pasti mahu log keluar?\nSemua data sesi akan dipadam.",
        "tr": "⚠️ **ÇIKIŞ ONAYI**\n\nÇıkış yapmak istediğinizden emin misiniz?\nTüm oturum verileri silinecektir.",
        "de": "⚠️ **LOGOUT BESTÄTIGEN**\n\nSind Sie sicher, dass Sie sich abmelden möchten?\nAlle Sitzungsdaten werden gelöscht.",
        "fr": "⚠️ **CONFIRMER LA DÉCONNEXION**\n\nÊtes-vous sûr de vouloir vous déconnecter?\nToutes les données de session seront supprimées.",
    },
    
    "logout_success": {
        "id": "👋 **Logout berhasil!**\n\nSampai jumpa lagi!\nGunakan /login untuk masuk kembali.",
        "en": "👋 **Logout successful!**\n\nSee you again!\nUse /login to sign in again.",
        "hi": "👋 **लॉगआउट सफल!**\n\nफिर मिलेंगे!\nदोबारा साइन इन करने के लिए /login का उपयोग करें।",
        "ar": "👋 **تم تسجيل الخروج بنجاح!**\n\nإلى اللقاء!\nاستخدم /login لتسجيل الدخول مرة أخرى.",
        "es": "👋 **¡Cierre de sesión exitoso!**\n\n¡Hasta luego!\nUsa /login para iniciar sesión de nuevo.",
        "pt": "👋 **Logout bem-sucedido!**\n\nAté logo!\nUse /login para entrar novamente.",
        "ru": "👋 **Выход выполнен успешно!**\n\nДо встречи!\nИспользуйте /login для повторного входа.",
        "zh": "👋 **退出成功!**\n\n再见!\n使用 /login 重新登录。",
        "ja": "👋 **ログアウト成功!**\n\nまたお会いしましょう!\n再度ログインするには /login を使用してください。",
        "ko": "👋 **로그아웃 성공!**\n\n다음에 또 만나요!\n다시 로그인하려면 /login을 사용하세요.",
        "vi": "👋 **Đăng xuất thành công!**\n\nHẹn gặp lại!\nSử dụng /login để đăng nhập lại.",
        "th": "👋 **ออกจากระบบสำเร็จ!**\n\nแล้วพบกันใหม่!\nใช้ /login เพื่อเข้าสู่ระบบอีกครั้ง",
        "ms": "👋 **Log keluar berjaya!**\n\nJumpa lagi!\nGunakan /login untuk log masuk semula.",
        "tr": "👋 **Çıkış başarılı!**\n\nTekrar görüşmek üzere!\nTekrar giriş yapmak için /login kullanın.",
        "de": "👋 **Logout erfolgreich!**\n\nAuf Wiedersehen!\nVerwenden Sie /login, um sich erneut anzumelden.",
        "fr": "👋 **Déconnexion réussie!**\n\nÀ bientôt!\nUtilisez /login pour vous reconnecter.",
    },
    
    "btn_check_account": {
        "id": "💰 Cek Akun",
        "en": "💰 Check Account",
        "hi": "💰 खाता जांचें",
        "ar": "💰 تحقق من الحساب",
        "es": "💰 Ver Cuenta",
        "pt": "💰 Ver Conta",
        "ru": "💰 Проверить счёт",
        "zh": "💰 查看账户",
        "ja": "💰 アカウント確認",
        "ko": "💰 계정 확인",
        "vi": "💰 Kiểm tra Tài khoản",
        "th": "💰 ตรวจสอบบัญชี",
        "ms": "💰 Semak Akaun",
        "tr": "💰 Hesabı Kontrol Et",
        "de": "💰 Konto prüfen",
        "fr": "💰 Vérifier le Compte",
    },
    
    "btn_auto_trade": {
        "id": "🚀 Auto Trade",
        "en": "🚀 Auto Trade",
        "hi": "🚀 ऑटो ट्रेड",
        "ar": "🚀 تداول تلقائي",
        "es": "🚀 Auto Trade",
        "pt": "🚀 Auto Trade",
        "ru": "🚀 Авто Торговля",
        "zh": "🚀 自动交易",
        "ja": "🚀 自動取引",
        "ko": "🚀 자동 거래",
        "vi": "🚀 Giao dịch tự động",
        "th": "🚀 เทรดอัตโนมัติ",
        "ms": "🚀 Dagangan Auto",
        "tr": "🚀 Otomatik İşlem",
        "de": "🚀 Auto Trade",
        "fr": "🚀 Auto Trade",
    },
    
    "btn_status": {
        "id": "📊 Status",
        "en": "📊 Status",
        "hi": "📊 स्थिति",
        "ar": "📊 الحالة",
        "es": "📊 Estado",
        "pt": "📊 Status",
        "ru": "📊 Статус",
        "zh": "📊 状态",
        "ja": "📊 ステータス",
        "ko": "📊 상태",
        "vi": "📊 Trạng thái",
        "th": "📊 สถานะ",
        "ms": "📊 Status",
        "tr": "📊 Durum",
        "de": "📊 Status",
        "fr": "📊 Statut",
    },
    
    "btn_help": {
        "id": "❓ Help",
        "en": "❓ Help",
        "hi": "❓ मदद",
        "ar": "❓ مساعدة",
        "es": "❓ Ayuda",
        "pt": "❓ Ajuda",
        "ru": "❓ Помощь",
        "zh": "❓ 帮助",
        "ja": "❓ ヘルプ",
        "ko": "❓ 도움말",
        "vi": "❓ Trợ giúp",
        "th": "❓ ช่วยเหลือ",
        "ms": "❓ Bantuan",
        "tr": "❓ Yardım",
        "de": "❓ Hilfe",
        "fr": "❓ Aide",
    },
    
    "btn_logout": {
        "id": "👋 Logout",
        "en": "👋 Logout",
        "hi": "👋 लॉगआउट",
        "ar": "👋 تسجيل الخروج",
        "es": "👋 Cerrar Sesión",
        "pt": "👋 Sair",
        "ru": "👋 Выйти",
        "zh": "👋 退出",
        "ja": "👋 ログアウト",
        "ko": "👋 로그아웃",
        "vi": "👋 Đăng xuất",
        "th": "👋 ออกจากระบบ",
        "ms": "👋 Log Keluar",
        "tr": "👋 Çıkış",
        "de": "👋 Abmelden",
        "fr": "👋 Déconnexion",
    },
    
    "btn_login": {
        "id": "🔐 LOGIN",
        "en": "🔐 LOGIN",
        "hi": "🔐 लॉगिन",
        "ar": "🔐 تسجيل الدخول",
        "es": "🔐 INICIAR SESIÓN",
        "pt": "🔐 ENTRAR",
        "ru": "🔐 ВХОД",
        "zh": "🔐 登录",
        "ja": "🔐 ログイン",
        "ko": "🔐 로그인",
        "vi": "🔐 ĐĂNG NHẬP",
        "th": "🔐 เข้าสู่ระบบ",
        "ms": "🔐 LOG MASUK",
        "tr": "🔐 GİRİŞ",
        "de": "🔐 ANMELDEN",
        "fr": "🔐 CONNEXION",
    },
    
    "btn_demo": {
        "id": "🎮 DEMO",
        "en": "🎮 DEMO",
        "hi": "🎮 डेमो",
        "ar": "🎮 تجريبي",
        "es": "🎮 DEMO",
        "pt": "🎮 DEMO",
        "ru": "🎮 ДЕМО",
        "zh": "🎮 模拟",
        "ja": "🎮 デモ",
        "ko": "🎮 데모",
        "vi": "🎮 DEMO",
        "th": "🎮 เดโม",
        "ms": "🎮 DEMO",
        "tr": "🎮 DEMO",
        "de": "🎮 DEMO",
        "fr": "🎮 DÉMO",
    },
    
    "btn_real": {
        "id": "💵 REAL",
        "en": "💵 REAL",
        "hi": "💵 असली",
        "ar": "💵 حقيقي",
        "es": "💵 REAL",
        "pt": "💵 REAL",
        "ru": "💵 РЕАЛЬНЫЙ",
        "zh": "💵 真实",
        "ja": "💵 リアル",
        "ko": "💵 실제",
        "vi": "💵 THẬT",
        "th": "💵 จริง",
        "ms": "💵 SEBENAR",
        "tr": "💵 GERÇEK",
        "de": "💵 ECHT",
        "fr": "💵 RÉEL",
    },
    
    "btn_cancel": {
        "id": "❌ Batal",
        "en": "❌ Cancel",
        "hi": "❌ रद्द करें",
        "ar": "❌ إلغاء",
        "es": "❌ Cancelar",
        "pt": "❌ Cancelar",
        "ru": "❌ Отмена",
        "zh": "❌ 取消",
        "ja": "❌ キャンセル",
        "ko": "❌ 취소",
        "vi": "❌ Hủy",
        "th": "❌ ยกเลิก",
        "ms": "❌ Batal",
        "tr": "❌ İptal",
        "de": "❌ Abbrechen",
        "fr": "❌ Annuler",
    },
    
    "btn_yes": {
        "id": "✅ Ya",
        "en": "✅ Yes",
        "hi": "✅ हाँ",
        "ar": "✅ نعم",
        "es": "✅ Sí",
        "pt": "✅ Sim",
        "ru": "✅ Да",
        "zh": "✅ 是",
        "ja": "✅ はい",
        "ko": "✅ 예",
        "vi": "✅ Có",
        "th": "✅ ใช่",
        "ms": "✅ Ya",
        "tr": "✅ Evet",
        "de": "✅ Ja",
        "fr": "✅ Oui",
    },
    
    "btn_no": {
        "id": "❌ Tidak",
        "en": "❌ No",
        "hi": "❌ नहीं",
        "ar": "❌ لا",
        "es": "❌ No",
        "pt": "❌ Não",
        "ru": "❌ Нет",
        "zh": "❌ 否",
        "ja": "❌ いいえ",
        "ko": "❌ 아니요",
        "vi": "❌ Không",
        "th": "❌ ไม่",
        "ms": "❌ Tidak",
        "tr": "❌ Hayır",
        "de": "❌ Nein",
        "fr": "❌ Non",
    },
    
    "btn_refresh_balance": {
        "id": "🔄 Refresh Saldo",
        "en": "🔄 Refresh Balance",
        "hi": "🔄 शेष ताज़ा करें",
        "ar": "🔄 تحديث الرصيد",
        "es": "🔄 Actualizar Saldo",
        "pt": "🔄 Atualizar Saldo",
        "ru": "🔄 Обновить баланс",
        "zh": "🔄 刷新余额",
        "ja": "🔄 残高更新",
        "ko": "🔄 잔액 새로고침",
        "vi": "🔄 Làm mới Số dư",
        "th": "🔄 รีเฟรชยอดเงิน",
        "ms": "🔄 Muat Semula Baki",
        "tr": "🔄 Bakiyeyi Yenile",
        "de": "🔄 Saldo aktualisieren",
        "fr": "🔄 Actualiser le Solde",
    },
    
    "btn_switch_demo": {
        "id": "🎮 Switch ke DEMO",
        "en": "🎮 Switch to DEMO",
        "hi": "🎮 डेमो पर स्विच करें",
        "ar": "🎮 التبديل إلى التجريبي",
        "es": "🎮 Cambiar a DEMO",
        "pt": "🎮 Mudar para DEMO",
        "ru": "🎮 Переключить на ДЕМО",
        "zh": "🎮 切换到模拟",
        "ja": "🎮 デモに切り替え",
        "ko": "🎮 데모로 전환",
        "vi": "🎮 Chuyển sang DEMO",
        "th": "🎮 สลับไปเดโม",
        "ms": "🎮 Tukar ke DEMO",
        "tr": "🎮 DEMO'ya Geç",
        "de": "🎮 Zu DEMO wechseln",
        "fr": "🎮 Passer à DÉMO",
    },
    
    "btn_switch_real": {
        "id": "💵 Switch ke REAL",
        "en": "💵 Switch to REAL",
        "hi": "💵 असली पर स्विच करें",
        "ar": "💵 التبديل إلى الحقيقي",
        "es": "💵 Cambiar a REAL",
        "pt": "💵 Mudar para REAL",
        "ru": "💵 Переключить на РЕАЛЬНЫЙ",
        "zh": "💵 切换到真实",
        "ja": "💵 リアルに切り替え",
        "ko": "💵 실제로 전환",
        "vi": "💵 Chuyển sang THẬT",
        "th": "💵 สลับไปจริง",
        "ms": "💵 Tukar ke SEBENAR",
        "tr": "💵 GERÇEK'e Geç",
        "de": "💵 Zu ECHT wechseln",
        "fr": "💵 Passer à RÉEL",
    },
    
    "btn_reset_connection": {
        "id": "🔌 Reset Koneksi",
        "en": "🔌 Reset Connection",
        "hi": "🔌 कनेक्शन रीसेट करें",
        "ar": "🔌 إعادة تعيين الاتصال",
        "es": "🔌 Restablecer Conexión",
        "pt": "🔌 Resetar Conexão",
        "ru": "🔌 Сброс подключения",
        "zh": "🔌 重置连接",
        "ja": "🔌 接続リセット",
        "ko": "🔌 연결 재설정",
        "vi": "🔌 Đặt lại Kết nối",
        "th": "🔌 รีเซ็ตการเชื่อมต่อ",
        "ms": "🔌 Set Semula Sambungan",
        "tr": "🔌 Bağlantıyı Sıfırla",
        "de": "🔌 Verbindung zurücksetzen",
        "fr": "🔌 Réinitialiser Connexion",
    },
    
    "trade_opened": {
        "id": "🔔 **POSISI DIBUKA**\n\n{symbol} - {contract_type}\n• Stake: ${stake:.2f}\n• Duration: {duration}\n• Entry: {entry_price}",
        "en": "🔔 **POSITION OPENED**\n\n{symbol} - {contract_type}\n• Stake: ${stake:.2f}\n• Duration: {duration}\n• Entry: {entry_price}",
        "hi": "🔔 **पोज़ीशन खोली गई**\n\n{symbol} - {contract_type}\n• स्टेक: ${stake:.2f}\n• अवधि: {duration}\n• प्रवेश: {entry_price}",
        "ar": "🔔 **تم فتح الصفقة**\n\n{symbol} - {contract_type}\n• الرهان: ${stake:.2f}\n• المدة: {duration}\n• الدخول: {entry_price}",
        "es": "🔔 **POSICIÓN ABIERTA**\n\n{symbol} - {contract_type}\n• Apuesta: ${stake:.2f}\n• Duración: {duration}\n• Entrada: {entry_price}",
        "pt": "🔔 **POSIÇÃO ABERTA**\n\n{symbol} - {contract_type}\n• Aposta: ${stake:.2f}\n• Duração: {duration}\n• Entrada: {entry_price}",
        "ru": "🔔 **ПОЗИЦИЯ ОТКРЫТА**\n\n{symbol} - {contract_type}\n• Ставка: ${stake:.2f}\n• Длительность: {duration}\n• Вход: {entry_price}",
        "zh": "🔔 **仓位已开**\n\n{symbol} - {contract_type}\n• 投注: ${stake:.2f}\n• 时长: {duration}\n• 入场: {entry_price}",
        "ja": "🔔 **ポジション開始**\n\n{symbol} - {contract_type}\n• ステーク: ${stake:.2f}\n• 期間: {duration}\n• エントリー: {entry_price}",
        "ko": "🔔 **포지션 개시**\n\n{symbol} - {contract_type}\n• 스테이크: ${stake:.2f}\n• 기간: {duration}\n• 진입: {entry_price}",
        "vi": "🔔 **VỊ THẾ ĐÃ MỞ**\n\n{symbol} - {contract_type}\n• Cược: ${stake:.2f}\n• Thời gian: {duration}\n• Vào lệnh: {entry_price}",
        "th": "🔔 **เปิดสถานะแล้ว**\n\n{symbol} - {contract_type}\n• เงินเดิมพัน: ${stake:.2f}\n• ระยะเวลา: {duration}\n• ราคาเข้า: {entry_price}",
        "ms": "🔔 **KEDUDUKAN DIBUKA**\n\n{symbol} - {contract_type}\n• Pertaruhan: ${stake:.2f}\n• Tempoh: {duration}\n• Masuk: {entry_price}",
        "tr": "🔔 **POZİSYON AÇILDI**\n\n{symbol} - {contract_type}\n• Bahis: ${stake:.2f}\n• Süre: {duration}\n• Giriş: {entry_price}",
        "de": "🔔 **POSITION ERÖFFNET**\n\n{symbol} - {contract_type}\n• Einsatz: ${stake:.2f}\n• Dauer: {duration}\n• Einstieg: {entry_price}",
        "fr": "🔔 **POSITION OUVERTE**\n\n{symbol} - {contract_type}\n• Mise: ${stake:.2f}\n• Durée: {duration}\n• Entrée: {entry_price}",
    },
    
    "trade_win": {
        "id": "✅ **WIN** +${profit:.2f}\n\nBalance: ${balance:.2f}",
        "en": "✅ **WIN** +${profit:.2f}\n\nBalance: ${balance:.2f}",
        "hi": "✅ **जीत** +${profit:.2f}\n\nशेष: ${balance:.2f}",
        "ar": "✅ **فوز** +${profit:.2f}\n\nالرصيد: ${balance:.2f}",
        "es": "✅ **GANANCIA** +${profit:.2f}\n\nSaldo: ${balance:.2f}",
        "pt": "✅ **VITÓRIA** +${profit:.2f}\n\nSaldo: ${balance:.2f}",
        "ru": "✅ **ПОБЕДА** +${profit:.2f}\n\nБаланс: ${balance:.2f}",
        "zh": "✅ **获胜** +${profit:.2f}\n\n余额: ${balance:.2f}",
        "ja": "✅ **勝利** +${profit:.2f}\n\n残高: ${balance:.2f}",
        "ko": "✅ **승리** +${profit:.2f}\n\n잔액: ${balance:.2f}",
        "vi": "✅ **THẮNG** +${profit:.2f}\n\nSố dư: ${balance:.2f}",
        "th": "✅ **ชนะ** +${profit:.2f}\n\nยอดเงิน: ${balance:.2f}",
        "ms": "✅ **MENANG** +${profit:.2f}\n\nBaki: ${balance:.2f}",
        "tr": "✅ **KAZANÇ** +${profit:.2f}\n\nBakiye: ${balance:.2f}",
        "de": "✅ **GEWINN** +${profit:.2f}\n\nSaldo: ${balance:.2f}",
        "fr": "✅ **GAIN** +${profit:.2f}\n\nSolde: ${balance:.2f}",
    },
    
    "trade_loss": {
        "id": "❌ **LOSS** -${loss:.2f}\n\nBalance: ${balance:.2f}",
        "en": "❌ **LOSS** -${loss:.2f}\n\nBalance: ${balance:.2f}",
        "hi": "❌ **हार** -${loss:.2f}\n\nशेष: ${balance:.2f}",
        "ar": "❌ **خسارة** -${loss:.2f}\n\nالرصيد: ${balance:.2f}",
        "es": "❌ **PÉRDIDA** -${loss:.2f}\n\nSaldo: ${balance:.2f}",
        "pt": "❌ **PERDA** -${loss:.2f}\n\nSaldo: ${balance:.2f}",
        "ru": "❌ **ПРОИГРЫШ** -${loss:.2f}\n\nБаланс: ${balance:.2f}",
        "zh": "❌ **亏损** -${loss:.2f}\n\n余额: ${balance:.2f}",
        "ja": "❌ **敗北** -${loss:.2f}\n\n残高: ${balance:.2f}",
        "ko": "❌ **손실** -${loss:.2f}\n\n잔액: ${balance:.2f}",
        "vi": "❌ **THUA** -${loss:.2f}\n\nSố dư: ${balance:.2f}",
        "th": "❌ **แพ้** -${loss:.2f}\n\nยอดเงิน: ${balance:.2f}",
        "ms": "❌ **RUGI** -${loss:.2f}\n\nBaki: ${balance:.2f}",
        "tr": "❌ **KAYIP** -${loss:.2f}\n\nBakiye: ${balance:.2f}",
        "de": "❌ **VERLUST** -${loss:.2f}\n\nSaldo: ${balance:.2f}",
        "fr": "❌ **PERTE** -${loss:.2f}\n\nSolde: ${balance:.2f}",
    },
    
    "session_complete": {
        "id": "🏁 **SESSION SELESAI**\n\n📊 **Statistik:**\n• Total Trade: {total}\n• Win: {wins} | Loss: {losses}\n• Win Rate: {winrate:.1f}%\n• Net Profit: ${profit:.2f}\n\n💰 Balance: ${balance:.2f}",
        "en": "🏁 **SESSION COMPLETE**\n\n📊 **Statistics:**\n• Total Trades: {total}\n• Win: {wins} | Loss: {losses}\n• Win Rate: {winrate:.1f}%\n• Net Profit: ${profit:.2f}\n\n💰 Balance: ${balance:.2f}",
        "hi": "🏁 **सत्र पूर्ण**\n\n📊 **आंकड़े:**\n• कुल ट्रेड: {total}\n• जीत: {wins} | हार: {losses}\n• जीत दर: {winrate:.1f}%\n• शुद्ध लाभ: ${profit:.2f}\n\n💰 शेष: ${balance:.2f}",
        "ar": "🏁 **انتهت الجلسة**\n\n📊 **الإحصائيات:**\n• إجمالي الصفقات: {total}\n• فوز: {wins} | خسارة: {losses}\n• نسبة الفوز: {winrate:.1f}%\n• صافي الربح: ${profit:.2f}\n\n💰 الرصيد: ${balance:.2f}",
        "es": "🏁 **SESIÓN COMPLETA**\n\n📊 **Estadísticas:**\n• Total Trades: {total}\n• Ganadas: {wins} | Perdidas: {losses}\n• Tasa de Ganancia: {winrate:.1f}%\n• Beneficio Neto: ${profit:.2f}\n\n💰 Saldo: ${balance:.2f}",
        "pt": "🏁 **SESSÃO CONCLUÍDA**\n\n📊 **Estatísticas:**\n• Total de Trades: {total}\n• Vitórias: {wins} | Perdas: {losses}\n• Taxa de Vitória: {winrate:.1f}%\n• Lucro Líquido: ${profit:.2f}\n\n💰 Saldo: ${balance:.2f}",
        "ru": "🏁 **СЕССИЯ ЗАВЕРШЕНА**\n\n📊 **Статистика:**\n• Всего сделок: {total}\n• Победы: {wins} | Проигрыши: {losses}\n• Процент побед: {winrate:.1f}%\n• Чистая прибыль: ${profit:.2f}\n\n💰 Баланс: ${balance:.2f}",
        "zh": "🏁 **交易结束**\n\n📊 **统计:**\n• 总交易: {total}\n• 胜: {wins} | 负: {losses}\n• 胜率: {winrate:.1f}%\n• 净利润: ${profit:.2f}\n\n💰 余额: ${balance:.2f}",
        "ja": "🏁 **セッション完了**\n\n📊 **統計:**\n• 総取引: {total}\n• 勝利: {wins} | 敗北: {losses}\n• 勝率: {winrate:.1f}%\n• 純利益: ${profit:.2f}\n\n💰 残高: ${balance:.2f}",
        "ko": "🏁 **세션 완료**\n\n📊 **통계:**\n• 총 거래: {total}\n• 승리: {wins} | 패배: {losses}\n• 승률: {winrate:.1f}%\n• 순이익: ${profit:.2f}\n\n💰 잔액: ${balance:.2f}",
        "vi": "🏁 **PHIÊN HOÀN THÀNH**\n\n📊 **Thống kê:**\n• Tổng giao dịch: {total}\n• Thắng: {wins} | Thua: {losses}\n• Tỷ lệ thắng: {winrate:.1f}%\n• Lợi nhuận ròng: ${profit:.2f}\n\n💰 Số dư: ${balance:.2f}",
        "th": "🏁 **เซสชันเสร็จสิ้น**\n\n📊 **สถิติ:**\n• ทั้งหมด: {total}\n• ชนะ: {wins} | แพ้: {losses}\n• อัตราชนะ: {winrate:.1f}%\n• กำไรสุทธิ: ${profit:.2f}\n\n💰 ยอดเงิน: ${balance:.2f}",
        "ms": "🏁 **SESI SELESAI**\n\n📊 **Statistik:**\n• Jumlah Dagangan: {total}\n• Menang: {wins} | Kalah: {losses}\n• Kadar Menang: {winrate:.1f}%\n• Untung Bersih: ${profit:.2f}\n\n💰 Baki: ${balance:.2f}",
        "tr": "🏁 **OTURUM TAMAMLANDI**\n\n📊 **İstatistikler:**\n• Toplam İşlem: {total}\n• Kazanç: {wins} | Kayıp: {losses}\n• Kazanma Oranı: {winrate:.1f}%\n• Net Kâr: ${profit:.2f}\n\n💰 Bakiye: ${balance:.2f}",
        "de": "🏁 **SITZUNG ABGESCHLOSSEN**\n\n📊 **Statistiken:**\n• Gesamte Trades: {total}\n• Gewonnen: {wins} | Verloren: {losses}\n• Gewinnrate: {winrate:.1f}%\n• Nettogewinn: ${profit:.2f}\n\n💰 Saldo: ${balance:.2f}",
        "fr": "🏁 **SESSION TERMINÉE**\n\n📊 **Statistiques:**\n• Total des Trades: {total}\n• Gains: {wins} | Pertes: {losses}\n• Taux de Victoire: {winrate:.1f}%\n• Profit Net: ${profit:.2f}\n\n💰 Solde: ${balance:.2f}",
    },
    
    "signal_detected": {
        "id": "📡 **SINYAL TERDETEKSI**\n\n{symbol}: {signal_type}\nRSI: {rsi:.1f} | Confidence: {confidence}%",
        "en": "📡 **SIGNAL DETECTED**\n\n{symbol}: {signal_type}\nRSI: {rsi:.1f} | Confidence: {confidence}%",
        "hi": "📡 **सिग्नल मिला**\n\n{symbol}: {signal_type}\nRSI: {rsi:.1f} | विश्वास: {confidence}%",
        "ar": "📡 **تم اكتشاف إشارة**\n\n{symbol}: {signal_type}\nRSI: {rsi:.1f} | الثقة: {confidence}%",
        "es": "📡 **SEÑAL DETECTADA**\n\n{symbol}: {signal_type}\nRSI: {rsi:.1f} | Confianza: {confidence}%",
        "pt": "📡 **SINAL DETECTADO**\n\n{symbol}: {signal_type}\nRSI: {rsi:.1f} | Confiança: {confidence}%",
        "ru": "📡 **СИГНАЛ ОБНАРУЖЕН**\n\n{symbol}: {signal_type}\nRSI: {rsi:.1f} | Уверенность: {confidence}%",
        "zh": "📡 **检测到信号**\n\n{symbol}: {signal_type}\nRSI: {rsi:.1f} | 置信度: {confidence}%",
        "ja": "📡 **シグナル検出**\n\n{symbol}: {signal_type}\nRSI: {rsi:.1f} | 信頼度: {confidence}%",
        "ko": "📡 **신호 감지됨**\n\n{symbol}: {signal_type}\nRSI: {rsi:.1f} | 신뢰도: {confidence}%",
        "vi": "📡 **TÍN HIỆU ĐƯỢC PHÁT HIỆN**\n\n{symbol}: {signal_type}\nRSI: {rsi:.1f} | Độ tin cậy: {confidence}%",
        "th": "📡 **ตรวจพบสัญญาณ**\n\n{symbol}: {signal_type}\nRSI: {rsi:.1f} | ความเชื่อมั่น: {confidence}%",
        "ms": "📡 **ISYARAT DIKESAN**\n\n{symbol}: {signal_type}\nRSI: {rsi:.1f} | Keyakinan: {confidence}%",
        "tr": "📡 **SİNYAL TESPİT EDİLDİ**\n\n{symbol}: {signal_type}\nRSI: {rsi:.1f} | Güven: {confidence}%",
        "de": "📡 **SIGNAL ERKANNT**\n\n{symbol}: {signal_type}\nRSI: {rsi:.1f} | Vertrauen: {confidence}%",
        "fr": "📡 **SIGNAL DÉTECTÉ**\n\n{symbol}: {signal_type}\nRSI: {rsi:.1f} | Confiance: {confidence}%",
    },
    
    "deriv_connected": {
        "id": "✅ **Terkoneksi ke Deriv**\n\n• Account: {account_id}\n• Balance: ${balance:.2f} {currency}\n• Type: {account_type}\n\n🔄 Scanner aktif untuk 8 pairs",
        "en": "✅ **Connected to Deriv**\n\n• Account: {account_id}\n• Balance: ${balance:.2f} {currency}\n• Type: {account_type}\n\n🔄 Scanner active for 8 pairs",
        "hi": "✅ **Deriv से जुड़ा**\n\n• खाता: {account_id}\n• शेष: ${balance:.2f} {currency}\n• प्रकार: {account_type}\n\n🔄 8 जोड़ों के लिए स्कैनर सक्रिय",
        "ar": "✅ **متصل بـ Deriv**\n\n• الحساب: {account_id}\n• الرصيد: ${balance:.2f} {currency}\n• النوع: {account_type}\n\n🔄 الماسح نشط لـ 8 أزواج",
        "es": "✅ **Conectado a Deriv**\n\n• Cuenta: {account_id}\n• Saldo: ${balance:.2f} {currency}\n• Tipo: {account_type}\n\n🔄 Escáner activo para 8 pares",
        "pt": "✅ **Conectado ao Deriv**\n\n• Conta: {account_id}\n• Saldo: ${balance:.2f} {currency}\n• Tipo: {account_type}\n\n🔄 Scanner ativo para 8 pares",
        "ru": "✅ **Подключено к Deriv**\n\n• Аккаунт: {account_id}\n• Баланс: ${balance:.2f} {currency}\n• Тип: {account_type}\n\n🔄 Сканер активен для 8 пар",
        "zh": "✅ **已连接到Deriv**\n\n• 账户: {account_id}\n• 余额: ${balance:.2f} {currency}\n• 类型: {account_type}\n\n🔄 8个交易对的扫描器已激活",
        "ja": "✅ **Derivに接続済み**\n\n• アカウント: {account_id}\n• 残高: ${balance:.2f} {currency}\n• タイプ: {account_type}\n\n🔄 8ペアのスキャナーがアクティブ",
        "ko": "✅ **Deriv에 연결됨**\n\n• 계정: {account_id}\n• 잔액: ${balance:.2f} {currency}\n• 유형: {account_type}\n\n🔄 8개 페어에 대한 스캐너 활성화",
        "vi": "✅ **Đã kết nối với Deriv**\n\n• Tài khoản: {account_id}\n• Số dư: ${balance:.2f} {currency}\n• Loại: {account_type}\n\n🔄 Trình quét đang hoạt động cho 8 cặp",
        "th": "✅ **เชื่อมต่อกับ Deriv แล้ว**\n\n• บัญชี: {account_id}\n• ยอดเงิน: ${balance:.2f} {currency}\n• ประเภท: {account_type}\n\n🔄 สแกนเนอร์ทำงานสำหรับ 8 คู่",
        "ms": "✅ **Disambung ke Deriv**\n\n• Akaun: {account_id}\n• Baki: ${balance:.2f} {currency}\n• Jenis: {account_type}\n\n🔄 Pengimbas aktif untuk 8 pasangan",
        "tr": "✅ **Deriv'e Bağlandı**\n\n• Hesap: {account_id}\n• Bakiye: ${balance:.2f} {currency}\n• Tür: {account_type}\n\n🔄 8 çift için tarayıcı aktif",
        "de": "✅ **Mit Deriv verbunden**\n\n• Konto: {account_id}\n• Saldo: ${balance:.2f} {currency}\n• Typ: {account_type}\n\n🔄 Scanner aktiv für 8 Paare",
        "fr": "✅ **Connecté à Deriv**\n\n• Compte: {account_id}\n• Solde: ${balance:.2f} {currency}\n• Type: {account_type}\n\n🔄 Scanner actif pour 8 paires",
    },
    
    "help_text": {
        "id": "📖 **PANDUAN PENGGUNAAN BOT**\n\n**Commands:**\n• /start - Mulai bot\n• /login - Login dengan token Deriv\n• /akun - Cek saldo dan info akun\n• /autotrade [stake] [durasi] [target] - Mulai trading\n• /stop - Hentikan trading\n• /status - Status bot\n• /help - Panduan ini\n\n**Contoh:**\n`/autotrade 0.50 5t 10` - Trading $0.50, 5 ticks, 10 trade\n\n**Fitur:**\n• Multi-indicator (RSI, EMA, MACD, Stochastic)\n• Recovery Martingale 2.1x\n• 8 Volatility Index pairs\n• Unlimited signals 24/7",
        "en": "📖 **BOT USER GUIDE**\n\n**Commands:**\n• /start - Start bot\n• /login - Login with Deriv token\n• /akun - Check balance and account info\n• /autotrade [stake] [duration] [target] - Start trading\n• /stop - Stop trading\n• /status - Bot status\n• /help - This guide\n\n**Example:**\n`/autotrade 0.50 5t 10` - Trade $0.50, 5 ticks, 10 trades\n\n**Features:**\n• Multi-indicator (RSI, EMA, MACD, Stochastic)\n• Recovery Martingale 2.1x\n• 8 Volatility Index pairs\n• Unlimited signals 24/7",
        "hi": "📖 **बॉट उपयोगकर्ता गाइड**\n\n**कमांड:**\n• /start - बॉट शुरू करें\n• /login - Deriv टोकन से लॉगिन\n• /akun - बैलेंस और खाता जानकारी देखें\n• /autotrade [stake] [duration] [target] - ट्रेडिंग शुरू करें\n• /stop - ट्रेडिंग बंद करें\n• /status - बॉट स्थिति\n• /help - यह गाइड\n\n**उदाहरण:**\n`/autotrade 0.50 5t 10` - $0.50, 5 टिक, 10 ट्रेड\n\n**विशेषताएं:**\n• मल्टी-इंडिकेटर (RSI, EMA, MACD, Stochastic)\n• Recovery Martingale 2.1x\n• 8 Volatility Index जोड़े\n• 24/7 असीमित सिग्नल",
        "ar": "📖 **دليل المستخدم**\n\n**الأوامر:**\n• /start - بدء البوت\n• /login - تسجيل الدخول برمز Deriv\n• /akun - التحقق من الرصيد\n• /autotrade [stake] [duration] [target] - بدء التداول\n• /stop - إيقاف التداول\n• /status - حالة البوت\n• /help - هذا الدليل\n\n**مثال:**\n`/autotrade 0.50 5t 10`\n\n**الميزات:**\n• مؤشرات متعددة\n• Recovery Martingale 2.1x\n• 8 أزواج\n• إشارات غير محدودة 24/7",
        "es": "📖 **GUÍA DE USUARIO**\n\n**Comandos:**\n• /start - Iniciar bot\n• /login - Iniciar sesión con token Deriv\n• /akun - Ver saldo e info de cuenta\n• /autotrade [stake] [duración] [objetivo] - Iniciar trading\n• /stop - Detener trading\n• /status - Estado del bot\n• /help - Esta guía\n\n**Ejemplo:**\n`/autotrade 0.50 5t 10`\n\n**Características:**\n• Multi-indicador (RSI, EMA, MACD, Stochastic)\n• Recovery Martingale 2.1x\n• 8 pares Volatility Index\n• Señales ilimitadas 24/7",
        "pt": "📖 **GUIA DO USUÁRIO**\n\n**Comandos:**\n• /start - Iniciar bot\n• /login - Entrar com token Deriv\n• /akun - Ver saldo e info da conta\n• /autotrade [stake] [duração] [alvo] - Iniciar trading\n• /stop - Parar trading\n• /status - Status do bot\n• /help - Este guia\n\n**Exemplo:**\n`/autotrade 0.50 5t 10`\n\n**Recursos:**\n• Multi-indicador (RSI, EMA, MACD, Stochastic)\n• Recovery Martingale 2.1x\n• 8 pares Volatility Index\n• Sinais ilimitados 24/7",
        "ru": "📖 **РУКОВОДСТВО ПОЛЬЗОВАТЕЛЯ**\n\n**Команды:**\n• /start - Запустить бота\n• /login - Войти с токеном Deriv\n• /akun - Проверить баланс\n• /autotrade [ставка] [длительность] [цель] - Начать торговлю\n• /stop - Остановить торговлю\n• /status - Статус бота\n• /help - Это руководство\n\n**Пример:**\n`/autotrade 0.50 5t 10`\n\n**Функции:**\n• Мульти-индикаторы\n• Recovery Martingale 2.1x\n• 8 пар\n• Безлимитные сигналы 24/7",
        "zh": "📖 **用户指南**\n\n**命令:**\n• /start - 启动机器人\n• /login - 用Deriv令牌登录\n• /akun - 查看余额和账户信息\n• /autotrade [投注] [时长] [目标] - 开始交易\n• /stop - 停止交易\n• /status - 机器人状态\n• /help - 本指南\n\n**示例:**\n`/autotrade 0.50 5t 10`\n\n**功能:**\n• 多指标 (RSI, EMA, MACD, Stochastic)\n• Recovery Martingale 2.1x\n• 8个波动率指数对\n• 24/7无限信号",
        "ja": "📖 **ユーザーガイド**\n\n**コマンド:**\n• /start - ボット開始\n• /login - Derivトークンでログイン\n• /akun - 残高とアカウント情報を確認\n• /autotrade [ステーク] [期間] [目標] - 取引開始\n• /stop - 取引停止\n• /status - ボット状態\n• /help - このガイド\n\n**例:**\n`/autotrade 0.50 5t 10`\n\n**機能:**\n• マルチインジケーター\n• Recovery Martingale 2.1x\n• 8ペア\n• 24/7無制限シグナル",
        "ko": "📖 **사용자 가이드**\n\n**명령어:**\n• /start - 봇 시작\n• /login - Deriv 토큰으로 로그인\n• /akun - 잔액 및 계정 정보 확인\n• /autotrade [스테이크] [기간] [목표] - 거래 시작\n• /stop - 거래 중지\n• /status - 봇 상태\n• /help - 이 가이드\n\n**예시:**\n`/autotrade 0.50 5t 10`\n\n**기능:**\n• 멀티 인디케이터\n• Recovery Martingale 2.1x\n• 8개 페어\n• 24/7 무제한 신호",
        "vi": "📖 **HƯỚNG DẪN SỬ DỤNG**\n\n**Lệnh:**\n• /start - Khởi động bot\n• /login - Đăng nhập với token Deriv\n• /akun - Kiểm tra số dư và thông tin tài khoản\n• /autotrade [cược] [thời gian] [mục tiêu] - Bắt đầu giao dịch\n• /stop - Dừng giao dịch\n• /status - Trạng thái bot\n• /help - Hướng dẫn này\n\n**Ví dụ:**\n`/autotrade 0.50 5t 10`\n\n**Tính năng:**\n• Đa chỉ báo\n• Recovery Martingale 2.1x\n• 8 cặp\n• Tín hiệu không giới hạn 24/7",
        "th": "📖 **คู่มือการใช้งาน**\n\n**คำสั่ง:**\n• /start - เริ่มบอท\n• /login - เข้าสู่ระบบด้วย Deriv token\n• /akun - ตรวจสอบยอดเงินและข้อมูลบัญชี\n• /autotrade [เงินเดิมพัน] [ระยะเวลา] [เป้าหมาย] - เริ่มเทรด\n• /stop - หยุดเทรด\n• /status - สถานะบอท\n• /help - คู่มือนี้\n\n**ตัวอย่าง:**\n`/autotrade 0.50 5t 10`\n\n**คุณสมบัติ:**\n• หลายตัวชี้วัด\n• Recovery Martingale 2.1x\n• 8 คู่\n• สัญญาณไม่จำกัด 24/7",
        "ms": "📖 **PANDUAN PENGGUNA**\n\n**Arahan:**\n• /start - Mulakan bot\n• /login - Log masuk dengan token Deriv\n• /akun - Semak baki dan info akaun\n• /autotrade [pertaruhan] [tempoh] [sasaran] - Mula dagangan\n• /stop - Henti dagangan\n• /status - Status bot\n• /help - Panduan ini\n\n**Contoh:**\n`/autotrade 0.50 5t 10`\n\n**Ciri-ciri:**\n• Pelbagai penunjuk\n• Recovery Martingale 2.1x\n• 8 pasangan\n• Isyarat tanpa had 24/7",
        "tr": "📖 **KULLANIM KILAVUZU**\n\n**Komutlar:**\n• /start - Botu başlat\n• /login - Deriv tokeniyle giriş yap\n• /akun - Bakiye ve hesap bilgilerini kontrol et\n• /autotrade [bahis] [süre] [hedef] - İşlemi başlat\n• /stop - İşlemi durdur\n• /status - Bot durumu\n• /help - Bu kılavuz\n\n**Örnek:**\n`/autotrade 0.50 5t 10`\n\n**Özellikler:**\n• Çoklu gösterge\n• Recovery Martingale 2.1x\n• 8 çift\n• 7/24 sınırsız sinyal",
        "de": "📖 **BENUTZERHANDBUCH**\n\n**Befehle:**\n• /start - Bot starten\n• /login - Mit Deriv-Token anmelden\n• /akun - Saldo und Kontoinformationen prüfen\n• /autotrade [Einsatz] [Dauer] [Ziel] - Trading starten\n• /stop - Trading stoppen\n• /status - Bot-Status\n• /help - Diese Anleitung\n\n**Beispiel:**\n`/autotrade 0.50 5t 10`\n\n**Funktionen:**\n• Multi-Indikator\n• Recovery Martingale 2.1x\n• 8 Paare\n• Unbegrenzte Signale 24/7",
        "fr": "📖 **GUIDE D'UTILISATION**\n\n**Commandes:**\n• /start - Démarrer le bot\n• /login - Connexion avec token Deriv\n• /akun - Vérifier le solde et infos du compte\n• /autotrade [mise] [durée] [objectif] - Démarrer le trading\n• /stop - Arrêter le trading\n• /status - Statut du bot\n• /help - Ce guide\n\n**Exemple:**\n`/autotrade 0.50 5t 10`\n\n**Fonctionnalités:**\n• Multi-indicateurs\n• Recovery Martingale 2.1x\n• 8 paires\n• Signaux illimités 24/7",
    },
}

_user_languages: Dict[int, str] = {}

_auth_manager = None

def _get_auth_manager():
    """Lazy import auth_manager to avoid circular imports"""
    global _auth_manager
    if _auth_manager is None:
        try:
            from user_auth import auth_manager
            _auth_manager = auth_manager
        except ImportError:
            pass
    return _auth_manager


def detect_language(telegram_language_code: Optional[str]) -> str:
    """
    Detect user language from Telegram language_code.
    
    Args:
        telegram_language_code: Language code from Telegram user object (e.g., "en", "id", "hi-IN")
        
    Returns:
        Supported language code (default: "id" for Indonesian)
    """
    if not telegram_language_code:
        return DEFAULT_LANGUAGE
    
    lang_code = telegram_language_code.lower()
    
    if lang_code in LANGUAGE_CODE_MAPPING:
        return LANGUAGE_CODE_MAPPING[lang_code]
    
    base_lang = lang_code.split("-")[0].split("_")[0]
    if base_lang in LANGUAGE_CODE_MAPPING:
        return LANGUAGE_CODE_MAPPING[base_lang]
    
    return DEFAULT_LANGUAGE


def set_user_language(user_id: int, language_code: str) -> bool:
    """
    Set language preference for a user. Persists to auth_manager if user is authenticated.
    
    Args:
        user_id: Telegram user ID
        language_code: Language code (must be in SUPPORTED_LANGUAGES)
        
    Returns:
        True if language was set, False if language not supported
    """
    if language_code not in SUPPORTED_LANGUAGES:
        logger.warning(f"Unsupported language: {language_code}")
        return False
    
    _user_languages[user_id] = language_code
    
    auth = _get_auth_manager()
    if auth and auth.is_authenticated(user_id):
        auth.set_user_language(user_id, language_code)
    
    logger.info(f"Set language for user {user_id}: {language_code}")
    return True


def get_user_language(user_id: int, telegram_language_code: Optional[str] = None) -> str:
    """
    Get language for a user. Priority:
    1. Stored user preference (from auth_manager if authenticated)
    2. In-memory cache
    3. Telegram language_code detection
    4. Default language (Indonesian)
    
    Args:
        user_id: Telegram user ID
        telegram_language_code: Optional language code from Telegram
        
    Returns:
        Language code
    """
    auth = _get_auth_manager()
    if auth and auth.is_authenticated(user_id):
        stored_lang = auth.get_user_language(user_id)
        if stored_lang and stored_lang != "id":
            _user_languages[user_id] = stored_lang
            return stored_lang
    
    if user_id in _user_languages:
        return _user_languages[user_id]
    
    if telegram_language_code:
        detected = detect_language(telegram_language_code)
        _user_languages[user_id] = detected
        if auth and auth.is_authenticated(user_id):
            auth.set_user_language(user_id, detected)
        return detected
    
    return DEFAULT_LANGUAGE


def get_text(key: str, lang: str = DEFAULT_LANGUAGE, **kwargs) -> str:
    """
    Get translated text for a given key and language.
    
    Args:
        key: Message key from MESSAGES dictionary
        lang: Language code
        **kwargs: Format parameters for the message
        
    Returns:
        Translated and formatted message
    """
    if key not in MESSAGES:
        logger.warning(f"Message key not found: {key}")
        return f"[{key}]"
    
    translations = MESSAGES[key]
    
    if lang in translations:
        text = translations[lang]
    elif DEFAULT_LANGUAGE in translations:
        text = translations[DEFAULT_LANGUAGE]
    else:
        text = list(translations.values())[0] if translations else f"[{key}]"
    
    if kwargs:
        try:
            text = text.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Missing format key {e} for message {key}")
        except Exception as e:
            logger.warning(f"Error formatting message {key}: {e}")
    
    return text


def t(key: str, lang: str = DEFAULT_LANGUAGE, **kwargs) -> str:
    """Shorthand for get_text"""
    return get_text(key, lang, **kwargs)


def get_language_name(lang_code: str) -> str:
    """Get human-readable language name"""
    return SUPPORTED_LANGUAGES.get(lang_code, lang_code)


def get_all_supported_languages() -> Dict[str, str]:
    """Get all supported languages as dict of code -> name"""
    return SUPPORTED_LANGUAGES.copy()
