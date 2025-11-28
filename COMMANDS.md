# 📋 KodeS Volume Bot - Lista Comenzi

## 👤 COMENZI PENTRU USERI

### Comenzi Text (Commands)

| Comandă | Descriere | Utilizare |
|--------|-----------|-----------|
| `/start` | Pornește botul și afișează meniul principal | `/start` |
| `/withdraw <address>` | Retrage toate fondurile (tokeni + SOL) la adresa specificată | `/withdraw 7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU` |

### Butoane Interactive (Menu Navigation)

#### Meniul Principal (Main Menu)
- **🚀 Start Volume Session** - Începe o nouă sesiune de generare volum
- **💰 Withdraw Funds** - Meniu pentru retragere fonduri
- **📢 Join Channel** - Link către canalul oficial

#### Meniul Sesiunii Active (Active Session Menu)
- **📊 Live Statistics** - Afișează statistici în timp real
- **⚙️ Strategy Settings** - Setări strategie trading
- **🛑 Stop & Withdraw** - Oprește trading-ul și retrage fondurile
- **🔄 Start New Session** - Începe o nouă sesiune

#### Meniul Setări (Settings Menu)
- **🔄 Change Strategy** - Schimbă strategia de trading
- **🔙 Back** - Înapoi la meniul anterior

#### Strategii Disponibile
- **🐢 Slow (Organic)** - Strategie lentă, organică
- **🐇 Medium (Balanced)** - Strategie medie, echilibrată
- **🚀 Fast (Aggressive)** - Strategie rapidă, agresivă

#### Alte Butoane
- **🔄 Check Deposit** - Verifică dacă depozitul a fost primit
- **✅ Yes, Continue** - Confirmă tokenul și continuă
- **❌ No, Re-enter CA** - Anulează și reintrodu CA-ul
- **🔙 Cancel / Back** - Anulează sau revine înapoi

---

## 🔐 COMENZI PENTRU ADMIN

> **Notă:** Toate comenzile admin necesită ca utilizatorul să fie setat ca `ADMIN_TELEGRAM_ID` în config.

| Comandă | Descriere | Utilizare |
|--------|-----------|-----------|
| `/admin_stats` | Afișează statistici globale (utilizatori, sesiuni) | `/admin_stats` |
| `/admin_sessions` | Listează ultimele 20 de sesiuni | `/admin_sessions` |
| `/admin_sweep_all` | Transferă toate fondurile din toate sesiunile către dev wallet | `/admin_sweep_all` |
| `/set_channel <channel_id>` | Setează ID-ul canalului Telegram pentru anunțuri | `/set_channel -1001234567890` |

### Detalii Comenzi Admin

#### `/admin_stats`
Afișează:
- 👥 Total utilizatori
- 📝 Total sesiuni
- 🟢 Sesiuni active
- 🔴 Sesiuni inactive

#### `/admin_sessions`
Afișează ultimele 20 de sesiuni cu:
- Status (🟢 activ / 🔴 inactiv)
- ID sesiune
- Username utilizator
- Token CA (trunchiat)
- Strategie folosită

#### `/admin_sweep_all`
- Oprește toate sesiunile active
- Transferă toate fondurile (SOL + tokeni) din toate wallet-urile către `DEV_WALLET_ADDRESS`
- Generează un raport detaliat pentru fiecare sesiune

#### `/set_channel`
- Setează ID-ul canalului Telegram unde se trimit anunțurile
- Actualizează variabila de mediu `TELEGRAM_CHANNEL_ID`
- Format: `/set_channel -1001234567890` (ID-ul canalului)

---

## 🔄 FLUXUL UTILIZATORULUI

### 1. Pornirea Botului
```
/start → Meniu Principal
```

### 2. Crearea unei Sesiuni Noi
```
Start Volume Session → 
Introduceți CA token → 
Confirmați tokenul → 
Selectați strategia → 
Depuneți tokeni + 0.1 SOL → 
Verificați depozitul → 
Trading începe automat
```

### 3. Gestionarea Sesiunii
```
Meniu Sesiune → 
📊 Live Statistics (vezi status) / 
⚙️ Strategy Settings (schimbă strategia) / 
🛑 Stop & Withdraw (oprește și retrage)
```

### 4. Retragerea Fondurilor
```
Opțiunea 1: Buton "🛑 Stop & Withdraw" → Introduceți adresa
Opțiunea 2: Comandă directă: /withdraw <address>
```

---

## 📝 NOTIȚE IMPORTANTE

### Pentru Useri:
- **Depozit minim:** 0.1 SOL (pentru gaz) + tokeni
- **Lichiditate recomandată:** Minimum $1k pe Raydium/Jupiter
- **Actualizări:** Primești notificări la fiecare 5 minute când trading-ul este activ
- **Retragere:** Oprește automat trading-ul și returnează toate fondurile

### Pentru Admin:
- Toate comenzile admin verifică automat dacă utilizatorul este admin
- Dacă nu ești admin, vei primi mesaj: "❌ Unauthorized. Admin only."
- `admin_sweep_all` este o comandă puternică - folosește-o cu precauție!

---

## 🎯 EXEMPLE DE UTILIZARE

### User - Start Session
```
1. /start
2. Click "🚀 Start Volume Session"
3. Trimite CA-ul tokenului: 7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU
4. Click "✅ Yes, Continue"
5. Selectează strategia: "🐇 Medium (Balanced)"
6. Trimite tokeni + 0.1 SOL la adresa generată
7. Click "🔄 Check Deposit"
8. Trading începe automat!
```

### User - Withdraw
```
Opțiunea 1: /withdraw 7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU
Opțiunea 2: Meniu → "🛑 Stop & Withdraw" → Introduce adresa
```

### Admin - Check Stats
```
/admin_stats
→ Vezi: Total Users: 50, Total Sessions: 120, Active: 15
```

### Admin - Set Channel
```
/set_channel -1001234567890
→ Canalul este setat! Anunțurile vor fi trimise aici.
```

---

## 🛠️ DEPANARE

### Probleme comune:
1. **"❌ Invalid CA"** - CA-ul trebuie să aibă minim 30 de caractere
2. **"⏳ Waiting for SOL/Tokens"** - Verifică dacă ai trimis fondurile la adresa corectă
3. **"❌ Unauthorized"** - Comenzile admin sunt doar pentru admin
4. **"❌ Session not found"** - Rulează `/start` pentru a inițializa sesiunea

---

**Ultima actualizare:** 2024
**Bot:** KodeS Volume Bot
**Canal oficial:** [@Kodeprint](https://t.me/Kodeprint)

