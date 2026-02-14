# Proje Çalıştırma Rehberi (Windows/PowerShell)

Bu rehber, projeyi Windows ortamında PowerShell kullanarak nasıl başlatacağınızı ve backtest botunu nasıl çalıştıracağınızı özetler.

## 1. Ön Hazırlıklar

Terminale başlamadan önce `.env` dosyanızın oluşturulduğundan ve gerekli API anahtarlarının (LLM vb.) tanımlandığından emin olun. Ayrıca `Indicators.md` dosyasında kullanmak istediğiniz indikatör listesinin doğru olduğundan emin olun (Örn: `Binance_Pure_Indicators.md` içeriğini buraya kopyalayabilirsiniz).

## 2. Sanal Ortamı (Virtual Environment) Aktifleştirme

Python projelerinde bağımlılıkların çakışmaması için sanal ortam kullanılır. PowerShell terminalinde şu komutu çalıştırın:

```powershell
# Eğer 'venv' klasörü oluşturulmamışsa (ilk kurulum):
python -m venv venv

# Sanal ortamı aktifleştirmek için:
.\venv\Scripts\Activate.ps1
```

*Not: Eğer yetki hatası alırsanız, `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser` komutunu çalıştırıp tekrar deneyebilirsiniz.*

Aktifleştirildiğinde terminalinizin başında `(venv)` ibaresini görmelisiniz.

## 3. Bağımlılıkları Yükleme (İlk Kurulum)

Sanal ortam aktifken, gerekli kütüphaneleri yükleyin:

```powershell
pip install -r requirements.txt
playwright install
```

## 4. Backtest Botunu Başlatma

Botu çalıştırmak için ana dosya olan `main.py`'yi çalıştırın:

```powershell
python main.py
```

### Bot Ne Yapar?
1.  Otomatik olarak bir Chromium tarayıcısı açar.
2.  Hyblock Capital sitesine giriş yapar (ilk girişte manuel login gerekebilir, sonra cookie kaydeder).
3.  `Indicators.md` listesinden stratejiler üretir (2 ile 4 indikatör arası kombinasyonlar).
4.  Sırasıyla backtest'leri çalıştırır ve sonuçları `backtest_results.csv` dosyasına kaydeder.

## 5. Sonuçların Analizi ve Raporlanması

Backtest sonuçları ham haliyle `.csv` dosyasında birikir. Bu sonuçları filtrelemek, temizlemek ve Excel formatına dönüştürmek için analiz scriptini kullanın.

Scripti çalıştırmak için:
```powershell
python clean_and_analyze.py
```

### Bu Script Ne Yapar?
1.  `backtest_results.csv` dosyasını okur.
2.  Veri tiplerini düzeltir (% işaretlerini kaldırır, sayıya çevirir).
3.  Sadece **BAŞARILI (PASS)** olan ve belirli kriterleri (Örn: >50 işlem, >%0 kar) sağlayan stratejileri filtreler.
4.  Çıktıları **`best_strategies.xlsx`** (Excel) ve `.csv` formatında kaydeder.
5.  Bu dosyayı stratejilerinizi incelemek için kullanabilirsiniz.

## 6. İşleyişi Durdurma

Bot sonsuz döngüde çalışacak şekilde ayarlanmıştır. Durdurmak için terminalde `CTRL + C` tuşlarına basabilirsiniz.
