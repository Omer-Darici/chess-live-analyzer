# Chess Live Analyzer

Ekranınızı okuyup tahtayı tanıyan, hamleyi **Stockfish** ile hesaplayan ve
sonucu ekranınızda renkli bir ok + karelerle gösteren canlı satranç analiz
 aracı. Oynarken **neden bu hamle, neden diğerleri elendi** sorusunun Türkçe
cevabını üretir ve oyun sonunda kaydeder.

> **Kapsam:** Yerel rakipler (LucasChessR, masaüstü programları) ve kendi
> oyun analiziniz içindir. Chess.com / Lichess gibi platformlarda canlı oynama
> desteği **bilinçli olarak yoktur**.

---

## Ne yapar

| | |
|---|---|
| **Ekran okuma** | Bölgeyi bir kez seçersiniz; araç tahtayı kendi kendine hizalar ve kare kare okur |
| **Hızlı hesap** | Varsayılan 300 ms / derinlik 18, 3 aday hamle (MultiPV) |
| **Görsel geri bildirim** | Taşın üzerine **sarı** dolgu, hedef kareye **yeşil** çerçeve, aralarında **ok**; elenen adaylar **turuncu** çerçeve |
| **Türkçe açıklama** | En iyi hamle neden iyi, rakip adaylar neden geride (puan farkı ve derinlikle birlikte) |
| **Kayıt** | `logs/` altına hamle bazlı **JSONL**, oyun sonunda **Markdown + PGN** |
| **Hotkey** | Klavye kombinasyonu **ve** fare tuşu — ikisi de yeniden atanabilir |
| **2 monitör** | Sanal masaüstü genişliğinde çalışır; bölge herhangi bir ekranda olabilir |

---

## Gereksinimler

* Windows 10/11
* Python 3.11+ (yalnızca kaynaktan çalıştırıyorsanız)
* Stockfish binary — varsayılan:
  `C:\Users\Storm\Downloads\LucasChessR\bin\OS\win32\Engines\stockfish\stockfish-windows-x86-64-universal.exe`
  (istediğinizden farklıysa arayüzden **Stockfish Yolu…** ile seçin)

Pip bağımlılıkları:

```
python -m pip install python-chess mss numpy opencv-python pynput
```

---

## Kullanım

### 1. Kaynaktan

```
python -m src.main
```

### 2. `.exe` olarak

```
powershell -ExecutionPolicy Bypass -File build.ps1
```

Çıktı: `dist\ChessLiveAnalyzer.exe` (tek dosya, kurulum gerektirmez).

Daha hızlı açılış istiyorsanız klasörlü sürüm:

```
powershell -ExecutionPolicy Bypass -File build.ps1 -OneDir
```

### Akış

1. **Bölge Seç…** — tahtanın çevresine fareyle sürükleyin.
2. **Otomatik Hizala** — ızgara tahtaya oturur; gerekirse `X / Y / Kenar`
   alanlarıyla elle düzeltin, **Izgarayı Göster** ile kontrol edin.
3. Oyunu **başlangıç pozisyonuna** getirin → **Kalibre Et**.
   (Araç bu karelerden taş şablonlarını öğrenir.)
4. **Canlı Başlat** — araç ekranı izler, pozisyon değişince yeniden analiz eder.
5. **Kaydı Bitir ve Kaydet** → `logs/game-*.md` + `logs/game-*.pgn`.

### Hotkey

Varsayılan **`Ctrl+Shift+S`** (aynı anda **orta fare tuşu**).
**Hotkey Değiştir…**’e basın, yeni kombinasyonu tuşlayın — `config.json`'a yazılır.

> Not: fare bağlaması yakalama sırasında bir kez tetiklenebilir; bir sonraki
> kombinasyon tamamlandığında normale döner.

---

## Ayarlar

Hepsi `config.json` içinde saklanır ve arayüzden değiştirilebilir:

| Anahtar | Varsayılan | Açıklama |
|---|---|---|
| `stockfish_path` | LucasChessR yolu | Motor binary |
| `movetime_ms` | `300` | Hamle başına süre |
| `depth` | `18` | Üst derinlik sınırı |
| `multipv` | `3` | Gösterilen aday hamle sayısı |
| `threads` / `hash_mb` | `2` / `128` | Motor kaynakları |
| `poll_interval_s` | `0.20` | Ekran tarama aralığı |
| `min_confidence` | `0.55` | Tespit güven eşiği |
| `my_color` | `white` | Puanın hangi taraf açısından gösterileceği |
| `hotkey_combo` / `mouse_hotkey` | `ctrl_l,shift,s` / `button.middle` | Yeniden atanabilir bağlamalar |
| `board_x/y/size` | `0` | Son hizalanan ızgara |

---

## Çıktılar

**`logs/game.jsonl`** — her analiz için bir satır:

```json
{
  "ts": "2026-10-22T21:04:11",
  "fen_before": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
  "move": "g1f3",
  "label": "at g1-f3",
  "reason": "En iyi hamle **at g1-f3** — puan +0.31 ...",
  "eval_cp": 31.0,
  "depth": 18,
  "candidates": [
    {"move": "g1f3", "eval_cp": 31.0, "depth": 18},
    {"move": "d2d4", "eval_cp": 12.0, "depth": 18}
  ]
}
```

**`logs/game-*.md`** — hamle numaralı, açıklama ve elenen adaylarla Türkçe rapor.

**`logs/game-*.pgn`** — standart PGN; her hamleye Türkçe yorum eklenir.

---

## Proje yapısı

```
chess-live-analyzer/
├─ src/
│  ├─ main.py           giriş + --test duman testi
│  ├─ ui.py             kontrol paneli
│  ├─ config.py         ayarlar (config.json)
│  ├─ screen_capture.py mss ile çok monitörlü yakalama
│  ├─ region_select.py  fareyle bölge seçimi
│  ├─ board_detect.py   ızgara hizalama + şablon eşleştirme
│  ├─ engine.py         Stockfish (python-chess UCI)
│  ├─ analyzer.py       arka plan çalışma döngüsü
│  ├─ overlay.py        tıklanabilir, yarı saydam vurgu katmanı
│  ├─ hotkeys.py        yeniden atanabilir klavye + fare
│  └─ logger.py         JSONL / PGN / Markdown + Türkçe açıklama
├─ tests/
│  ├─ synth_board.py    gerçekçi sentetik tahta (yüzey/taş kontrastı)
│  ├─ test_detect.py    tahta okuma birim testleri
│  └─ test_flow.py      ekran→okuma→analiz→PGN uçtan uca testi
├─ logs/
├─ build.ps1            PyInstaller paketleme
└─ README.md
```

### Test

```
python main.py --test          # motor + açıklama + kayıt duman testi
python tests\test_detect.py    # tahta okuma (12 kontrol)
python tests\test_flow.py      # uçtan uca akış (19 kontrol)
```

`tests/` içindeki iki paket, ekran okumayı sentetik bir tahta üzerinden
gerçek API ile sınırdan sınıra işletir: güven eşiği, rok haklarının geri
üretilmesi, yan tarafın değişmesi, geçen alma (en passant), kaydın oynanan
hamleleri değil motorun önerilerini değil kaydettiği ve PGN'in aynı oyunu
oynatması.

---

## Sınırlar

* Kalibrasyon **başlangıç pozisyonu** ile yapılır; farklı bir FEN'den
  başlarken tahtayı o pozisyona getirip yeniden **Kalibre Et** deyin.
* **Yan taraf (sıra kimde) ekranda görünmez.** İlk okumada beyaz varsayılır;
  bundan sonraki her hamle sırayı kendiliğinden çevirir. Sırası siyahla
  başlayan bir oyunu, ilk konumu okuttuktan sonra bir hamle oynatın.
* Tahta animasyonu sırasında alınan kareler tutarsızdır — bu kareler
  `min_confidence` eşiğiyle elemek için tasarlanmıştır. Izgara tahtanın
  dışına taştığında (bölge çok darsa) 64 karenin hepsi okunamaz ve program
  sessizce yanlış okumak yerine "tutarsız" der.
* Ses, görüntü kaydı, bulut senkronizasyonu yoktur. Her şey yerel çalışır.
