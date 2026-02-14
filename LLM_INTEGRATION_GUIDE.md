# LLM Entegrasyon ve OpenRouter Kullanım Rehberi

Bu doküman, OpenRouter API kullanarak bir LLM (Large Language Model) ile nasıl etkileşime geçileceğini, request (istek) ve response (yanıt) süreçlerini detaylandırır.

## 1. Temel Gereksinimler

Projenizde LLM entegrasyonu için aşağıdaki temel bileşenlere ihtiyacınız vardır:

*   **OpenRouter API Key:** `https://openrouter.ai/keys` adresinden alınır.
*   **HTTP İstemcisi:** Python'da `httpx` (asenkron) veya `requests` (senkron) kütüphanesi.
*   **JSON Parser:** LLM yanıtlarını yapısal veriye çevirmek için.

## 2. API Bağlantı Yapısı

OpenRouter, OpenAI uyumlu bir API yapısı sunar. Bu sayede OpenAI kütüphaneleriyle veya standart HTTP istekleriyle kullanılabilir.

### Temel Ayarlar (Endpoint ve Headerlar)

Tüm istekler aşağıdaki adrese ve başlıklara sahip olmalıdır:

*   **Base URL:** `https://openrouter.ai/api/v1`
*   **Headers:**
    *   `Authorization`: `Bearer <YOUR_API_KEY>`
    *   `Content-Type`: `application/json`
    *   `HTTP-Referer`: (Opsiyonel) Sitenizin/Uygulamanızın URL'i (OpenRouter sıralamasında görünmek için).

## 3. Request (İstek) Oluşturma Süreci

LLM'e gönderilen istek genellikle bir "chat completion" formatındadır.

### Örnek Request Body (JSON)

```json
{
  "model": "qwen/qwen-3",
  "messages": [
    {
      "role": "system",
      "content": "Sen deneyimli bir finansal analistsin. Yanıtlarını sadece JSON formatında ver."
    },
    {
      "role": "user",
      "content": "xxxx"
    }
  ],
  "temperature": 0.1,
  "max_tokens": 4096
}
```

*   **model:** Kullanılacak model (örn: `qwen/qwen-3`, `anthropic/claude-3.5-sonnet`).
*   **messages:** Konuşma geçmişi veya prompt zinciri. `system` mesajı modelin davranışını belirler.
*   **temperature:** Yaratıcılık seviyesi (0.0 - 1.0 arası). Finansal analiz veya veri çıkarma gibi kesinlik gerektiren işlerde düşük (0.1) tutulmalıdır.

## 4. Response (Yanıt) Dinleme ve İşleme

Modelin yanıtı genellikle metin (string) olarak döner. Eğer modelden JSON istediysek, bu metni parse etmemiz gerekir.

### Akış Şeması

1.  **İstek Gönder:** `client.post("/chat/completions", json=payload)`
2.  **Yanıtı Al:** HTTP 200 OK beklenir.
3.  **İçeriği Çıkar:** `response.json()["choices"][0]["message"]["content"]`
4.  **JSON Temizleme (Önemli):** LLM'ler bazen JSON çıktısını Markdown blokları içine alabilir (örn: \`\`\`json ... \`\`\`). Bu fazlalıkları temizleyen bir fonksiyon yazılmalıdır.
5.  **Doğrulama:** Çıkan JSON verisinin beklenen şemaya (örn: `schema.py` içindeki Pydantic modelleri) uyup uymadığı kontrol edilir.

## 5. Örnek Python Uygulaması (Basitleştirilmiş)

Mevcut projedeki `QwenClient` yapısının basitleştirilmiş hali:

```python
import httpx
import json

class SimpleLLMClient:
    def __init__(self, api_key, model="qwen/qwen-3"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://openrouter.ai/api/v1"

    async def get_completion(self, system_prompt, user_prompt):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=60.0
            )
            
            if response.status_code != 200:
                raise Exception(f"API Hatası: {response.text}")
                
            # Yanıtı al
            content = response.json()["choices"][0]["message"]["content"]
            
            # JSON temizleme (Markdown bloklarını kaldır)
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].strip()
                
            return json.loads(content)
```

## 6. İpuçları ve Best Practices

1.  **Retry Mekanizması:** API çağrıları zaman zaman başarısız olabilir (timeout, rate limit). `tenacity` kütüphanesi ile "retry" (tekrar deneme) mantığı kurun (Referans: `qwen_client.py`).
2.  **Pydantic ile Doğrulama:** JSON çıktısını doğrudan dict olarak kullanmak yerine, `Response` gibi bir Pydantic modeli ile doğrulayın. Bu, eksik alanları veya hatalı veri tiplerini hemen yakalamanızı sağlar.
3.  **System Prompt:** Modelin çıktısının formatını (JSON) ve yapısını `system` prompt içinde çok net belirtin.

RUN:
.\venv\Scripts\Activate