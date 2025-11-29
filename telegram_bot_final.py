import requests
from bs4 import BeautifulSoup
import time
import json
from datetime import datetime
import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackContext

# Telegram Bot Token - Buraya kendi bot tokenını yaz
TELEGRAM_BOT_TOKEN = "8505318715:AAF2rzPR-UJ-PoANC2MKj-kE6yFX52WgDJs"

# Logging ayarı
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class NDUStudentBot:
    def __init__(self):
        # Her instance için YENİ session oluştur
        self.create_new_session()
        self.base_url = "https://tmis.ndu.edu.az"
        self.login_url = f"{self.base_url}/login"
        self.dashboard_url = f"{self.base_url}/student"

    def create_new_session(self):
        """Yeni bir session oluştur - HER KULLANICI İÇİN YENİ"""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://tmis.ndu.edu.az',
            'Referer': 'https://tmis.ndu.edu.az/login',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Upgrade-Insecure-Requests': '1',
        })

    def clear_session(self):
        """Session'ı tamamen temizle"""
        self.session.close()
        self.create_new_session()

    def get_csrf_token(self):
        """CSRF token'ını al"""
        try:
            # Önce session'ı temizle
            self.clear_session()
            
            response = self.session.get(self.login_url, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            csrf_input = soup.find('input', {'name': '_token'})
            if csrf_input:
                token = csrf_input.get('value')
                logger.info(f"CSRF token alındı: {token[:20]}...")
                return token
            else:
                logger.error("CSRF token bulunamadı!")
                return None
        except Exception as e:
            logger.error(f"CSRF token alma hatası: {e}")
            return None

    def login(self, username, password):
        """Siteye giriş yap - HER KULLANICI İÇİN YENİ SESSION"""
        try:
            csrf_token = self.get_csrf_token()
            if not csrf_token:
                return False

            login_data = {
                '_token': csrf_token,
                'user_type': 'student',
                'username': username,
                'password': password
            }

            logger.info(f"Giriş denemesi: {username}")

            # Doğrudan /student/login endpoint'ine POST
            student_login_url = f"{self.base_url}/student/login"
            response = self.session.post(
                student_login_url,
                data=login_data,
                allow_redirects=True,
                timeout=30
            )
            
            if response.status_code == 200:
                if "student" in response.url or "Mem Doğuhan" in response.text:
                    logger.info(f"✅ Giriş başarılı: {username}")
                    return True
                else:
                    # Hata mesajını kontrol et
                    soup = BeautifulSoup(response.content, 'html.parser')
                    error_msg = soup.find('div', class_='session-message-error')
                    if error_msg:
                        error_text = error_msg.get_text(strip=True)
                        logger.error(f"Giriş hatası ({username}): {error_text}")
                    else:
                        logger.error(f"Giriş başarısız ({username}): Yönlendirme yapılmadı")
                    return False
            else:
                logger.error(f"HTTP Hatası ({username}): {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Login hatası ({username}): {e}")
            return False

    def get_student_data(self, username):
        """Öğrenci verilerini çek ve formatlı string olarak döndür"""
        try:
            logger.info(f"Veri çekiliyor: {username}")
            response = self.session.get(self.dashboard_url, timeout=30)
            
            if response.status_code != 200:
                logger.error(f"Veri çekme hatası ({username}): {response.status_code}")
                return "❌ Veri çekme hatası! Lütfen daha sonra tekrar deneyin."

            # Başarılı giriş kontrolü
            if "student" not in response.url:
                logger.error(f"Giriş yapılmamış ({username}): {response.url}")
                return "❌ Giriş yapılamadı! Lütfen kodunuzu kontrol edin."

            soup = BeautifulSoup(response.content, 'html.parser')
            
            student_data = {
                'name': '',
                'department': '',
                'last_lessons': [],
                'attendance_limits': [],
            }

            # Öğrenci adı
            name_element = soup.find('h3', {'id': 'studentFullName'})
            if name_element:
                student_data['name'] = name_element.get_text(strip=True)
                logger.info(f"Öğrenci bulundu: {student_data['name']}")

            # Bölüm bilgisi
            department_element = soup.find('p', class_='student_fenn')
            if department_element:
                student_data['department'] = department_element.get_text(strip=True)

            # SON DERSLERİ ÇEK
            last_subjects_section = soup.find('div', class_='last-subjects')
            if last_subjects_section:
                table = last_subjects_section.find('table')
                if table:
                    rows = table.find_all('tr')[1:]  # İlk satır başlık
                    
                    for row in rows:
                        cols = row.find_all('td')
                        if len(cols) >= 4:
                            ders_adi = cols[0].get_text(strip=True)
                            konu = cols[1].get_text(strip=True)
                            devamsizlik = cols[2].get_text(strip=True)
                            tarih = cols[3].get_text(strip=True)
                            
                            # ⚠️ DEĞİŞİKLİK: Kollekvium notlarını tespit et
                            # Eğer devamsızlık kısmında sayısal bir değer varsa (örneğin "7", "8"), bu bir nottur.
                            if devamsizlik.isdigit():
                                devam_durumu = f"📝 NOT: {devamsizlik}"
                            elif "Q/b" in devamsizlik or "q/b" in devamsizlik:
                                devam_durumu = "❌ YOK"
                            else:
                                devam_durumu = "✅ VAR"
                            
                            lesson_data = {
                                'ders': ders_adi,
                                'konu': konu,
                                'devamsizlik': devamsizlik,
                                'devam_durumu': devam_durumu,
                                'tarih': tarih
                            }
                            student_data['last_lessons'].append(lesson_data)

            # DEVLAMSIZLIK LİMİTLERİ
            absence_section = soup.find('div', class_='absence-limit')
            if absence_section:
                table = absence_section.find('table')
                if table:
                    rows = table.find_all('tr')[1:]
                    
                    for row in rows:
                        cols = row.find_all('td')
                        if len(cols) >= 3:
                            ders_adi = cols[0].get_text(strip=True)
                            
                            devamsizlik_div = cols[1].find('div', class_='progress-text')
                            devamsizlik_text = devamsizlik_div.get_text(strip=True) if devamsizlik_div else cols[1].get_text(strip=True)
                            devamsizlik_puani = cols[2].get_text(strip=True)
                            
                            absence_data = {
                                'ders': ders_adi,
                                'devamsizlik': devamsizlik_text,
                                'devamsizlik_puani': devamsizlik_puani
                            }
                            student_data['attendance_limits'].append(absence_data)

            # Session'ı temizle (bir sonraki kullanıcı için)
            self.clear_session()
            
            return self.format_message(student_data)

        except Exception as e:
            logger.error(f"Veri çekme hatası ({username}): {e}")
            # Hata durumunda da session'ı temizle
            self.clear_session()
            return f"❌ Veri çekilirken hata oluştu: {str(e)}"

    def format_message(self, data):
        """Verileri güzel formatlanmış mesaja dönüştür"""
        if not data['name']:
            return "❌ Öğrenci bilgileri bulunamadı! Lütfen kodunuzu kontrol edin."

        message = f"👤 *Öğrenci:* {data['name']}\n"
        message += f"🎓 *Bölüm:* {data['department']}\n"
        message += f"📅 *Son Güncelleme:* {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
        
        if data['last_lessons']:
            message += "*📚 SON DERSLER:*\n"
            for lesson in data['last_lessons'][:8]:  # Son 8 ders göster
                message += f"{lesson['devam_durumu']} *{lesson['ders']}*\n"
                message += f"   📖 {lesson['konu'][:30]}...\n" if len(lesson['konu']) > 30 else f"   📖 {lesson['konu']}\n"
                message += f"   🕒 {lesson['tarih']}\n\n"

            # İstatistikler - DEĞİŞİKLİK: Notları da say
            yok_sayisi = sum(1 for lesson in data['last_lessons'] if "YOK" in lesson['devam_durumu'])
            var_sayisi = sum(1 for lesson in data['last_lessons'] if "VAR" in lesson['devam_durumu'])
            not_sayisi = sum(1 for lesson in data['last_lessons'] if "NOT" in lesson['devam_durumu'])
            
            message += f"*📊 İSTATİSTİKLER:*\n"
            message += f"   • Toplam {len(data['last_lessons'])} ders\n"
            message += f"   • {var_sayisi} derse VAR\n"
            message += f"   • {yok_sayisi} derse YOK\n"
            message += f"   • {not_sayisi} kollekvium notu\n\n"
        else:
            message += "📚 *Son ders bilgisi bulunamadı*\n\n"

        # Devamsızlık limitleri
        if data['attendance_limits']:
            message += "*⚠️ DEVLAMSIZLIK LİMİTLERİ:*\n"
            for limit in data['attendance_limits'][:5]:  # İlk 5 ders
                ders_adi = limit['ders'][:25] + "..." if len(limit['ders']) > 25 else limit['ders']
                message += f"   📖 {ders_adi}\n"
                message += f"      📊 {limit['devamsizlik']} | Puan: {limit['devamsizlik_puani']}\n\n"
        else:
            message += "*⚠️ Devamsızlık limiti bilgisi bulunamadı*\n"

        return message

# Telegram komutları
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kullanıcıyı karşılar ve kullanımı açıklar."""
    user = update.message.from_user
    welcome_text = """
🤖 *NDU Öğrenci Botuna Hoş Geldiniz!*

Bu bot ile son ders bilgilerinizi ve yoklama durumunuzu anında öğrenebilirsiniz.

*Kullanım:*
Sadece 6 haneli öğrenci kodunuzu yazın ve gönderin.


Bot sizin için:
• Son dersleri
• Yoklama durumunuzu (VAR/YOK)
• Devamsızlık limitlerinizi
gösterecektir.

⚠️ *Not:* Bir problem olursa Doğuhan Çakır'a ulaşın +90 538 446 65 65
    """
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kullanıcının girdiği kodu işler - HER KULLANICI İÇİN YENİ BOT INSTANCE'ı"""
    user = update.message.from_user
    code = update.message.text.strip().upper()

    logger.info(f"Kullanıcı {user.first_name} ({user.id}) kod girdi: {code}")

    # Kodu kontrol et
    if len(code) != 6 or not code.isalnum():
        await update.message.reply_text(
            "❌ *Geçersiz kod!*\n\n"
            "Lütfen 6 haneli öğrenci kodunuzu girin.\n"
            "*Örnek:* `43XXXX`",
            parse_mode='Markdown'
        )
        return

    # Kullanıcıya işlemin başladığını bildir
    processing_msg = await update.message.reply_text("🔄 *Bilgileriniz alınıyor...*", parse_mode='Markdown')

    try:
        # ⚠️ HER KULLANICI İÇİN YENİ BOT INSTANCE'ı oluştur
        ndu_bot = NDUStudentBot()
        username = code
        password = code  # Kullanıcı adı ve şifre aynı

        if ndu_bot.login(username, password):
            # Verileri çek
            student_info = ndu_bot.get_student_data(username)
            await context.bot.edit_message_text(
                chat_id=processing_msg.chat_id,
                message_id=processing_msg.message_id,
                text=student_info,
                parse_mode='Markdown'
            )
            
            # Başarılı işlem logu
            logger.info(f"✅ Başarılı: {user.first_name} ({user.id}) - {code}")
            
        else:
            await context.bot.edit_message_text(
                chat_id=processing_msg.chat_id,
                message_id=processing_msg.message_id,
                text="❌ *Giriş başarısız!*\n\n"
                     "Kullanıcı adı veya şifre hatalı olabilir. "
                     "Lütfen kodunuzu kontrol edip tekrar deneyin.",
                parse_mode='Markdown'
            )
            logger.warning(f"❌ Giriş başarısız: {user.first_name} ({user.id}) - {code}")

    except Exception as e:
        logger.error(f"Kullanıcı {user.first_name} ({user.id}) için hata: {e}")
        await context.bot.edit_message_text(
            chat_id=processing_msg.chat_id,
            message_id=processing_msg.message_id,
            text="❌ *Bir hata oluştu!*\n\n"
                 "Lütfen daha sonra tekrar deneyin. "
                 "Bu geçici bir sorun olabilir.",
            parse_mode='Markdown'
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Yardım mesajı gönderir."""
    help_text = """
*🤖 NDU Öğrenci Botu - Yardım*

*Komutlar:*
/start - Botu başlatır
/help - Bu yardım mesajını gösterir

*Kullanım:*
1. 6 haneli öğrenci kodunuzu yazın
2. Bot sizin için bilgileri çekecek
3. Sonuçları anında alacaksınız

*Örnek:*
`43XXXX`

*Not:* Kodunuzu güvende tutun ve başkalarıyla paylaşmayın.

Sorun yaşarsanız, lütfen bot yöneticisiyle iletişime geçin.
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Hataları loglar."""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

def main() -> None:
    """Botu başlat."""
    # Telegram uygulamasını oluştur
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Komut handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    
    # Mesaj handler - kullanıcı kodu yazdığında
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_code))

    # Hata handler
    application.add_error_handler(error_handler)

    # Botu başlat
    print("🤖 Telegram bot başlatılıyor...")
    print("📍 Bot aktif! Şimdi Telegram'da botu bulup /start yazabilirsiniz.")
    print("⚠️  HER KULLANICI İÇİN YENİ SESSION KULLANILACAK")
    application.run_polling()

if __name__ == '__main__':
    main()