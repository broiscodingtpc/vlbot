# Deployment Guide - Railway + GitHub

Ghid pas cu pas pentru a urca botul pe Railway folosind GitHub.

## 📋 Pași de Deployment

### 1. Pregătirea Repository-ului GitHub

#### 1.1. Inițializează Git (dacă nu e deja)

```bash
cd volumebot
git init
```

#### 1.2. Adaugă toate fișierele (exceptând cele din .gitignore)

```bash
git add .
```

#### 1.3. Commit primul commit

```bash
git commit -m "Initial commit - KodeS Volume Bot"
```

#### 1.4. Creează repository pe GitHub

1. Mergi pe [GitHub](https://github.com)
2. Click pe **"New repository"**
3. Numește repository-ul (ex: `volumebot`)
4. **NU** bifea "Initialize with README" (avem deja README.md)
5. Click **"Create repository"**

#### 1.5. Conectează repository-ul local cu GitHub

```bash
git branch -M main
git remote add origin https://github.com/TU_USERNAME/volumebot.git
git push -u origin main
```

**Notă**: Înlocuiește `TU_USERNAME` cu username-ul tău GitHub.

### 2. Deployment pe Railway

#### 2.1. Creează cont Railway

1. Mergi pe [Railway](https://railway.app)
2. Sign in cu GitHub (recomandat) sau email
3. Acceptă termenii și condițiile

#### 2.2. Creează proiect nou

1. Click pe **"New Project"**
2. Selectează **"Deploy from GitHub repo"**
3. Autorizează Railway să acceseze GitHub (dacă e necesar)
4. Selectează repository-ul `volumebot`
5. Click **"Deploy Now"**

#### 2.3. Configurează Environment Variables

Railway va detecta automat `Procfile` și va începe build-ul. Înainte să ruleze, trebuie să adaugi variabilele de mediu:

1. În dashboard-ul Railway, click pe proiectul tău
2. Click pe tab-ul **"Variables"**
3. Adaugă următoarele variabile:

| Variable Name | Value | Description |
|--------------|-------|-------------|
| `TELEGRAM_BOT_TOKEN` | `your_bot_token` | Token-ul botului Telegram (de la @BotFather) |
| `RPC_URL` | `https://mainnet.helius-rpc.com/?api-key=YOUR_KEY` | URL-ul RPC Solana (recomandat Helius) |
| `DEV_WALLET_ADDRESS` | `YourWalletAddress` | Adresa wallet-ului pentru colectarea taxelor |
| `DATABASE_PATH` | `/data/volumebot.db` | Path-ul către baza de date (folosește `/data` pentru persistent storage) |

**Important**: 
- Pentru `DATABASE_PATH`, folosește `/data/volumebot.db` pentru persistent storage pe Railway
- Railway oferă `/data` directory pentru persistent storage
- Dacă nu folosești `/data`, datele se vor pierde la redeploy

#### 2.4. Adaugă Persistent Volume (Recomandat)

1. În dashboard-ul Railway, click pe proiectul tău
2. Click pe **"Settings"**
3. Scroll la **"Volumes"**
4. Click **"Add Volume"**
5. Mount path: `/data`
6. Click **"Add"**

Aceasta va asigura că baza de date persistă între redeploy-uri.

#### 2.5. Verifică Deployment

1. După ce build-ul se termină, click pe **"Deployments"**
2. Click pe ultimul deployment
3. Verifică logs-urile pentru erori
4. Dacă totul e OK, vei vedea: `🚀 Bot is running...`

### 3. Verificare și Testare

#### 3.1. Testează botul

1. Deschide Telegram
2. Caută botul tău
3. Trimite `/start`
4. Verifică dacă botul răspunde

#### 3.2. Verifică logs-urile

1. În Railway dashboard, click pe **"Deployments"**
2. Click pe deployment-ul activ
3. Click pe **"View Logs"**
4. Verifică dacă există erori

### 4. Monitorizare

#### 4.1. Railway Dashboard

- **Metrics**: Vezi CPU, Memory, Network usage
- **Logs**: Vezi logs-urile în timp real
- **Deployments**: Istoricul deployment-urilor

#### 4.2. Telegram Bot

- Botul trimite rapoarte la fiecare 5 minute
- Poți folosi `/admin_stats` pentru statistici

## 🔧 Troubleshooting

### Problema: Botul nu pornește

**Soluție**:
1. Verifică logs-urile în Railway
2. Verifică dacă toate environment variables sunt setate
3. Verifică dacă `TELEGRAM_BOT_TOKEN` este valid

### Problema: Baza de date se resetează

**Soluție**:
1. Asigură-te că ai adăugat Volume la `/data`
2. Verifică că `DATABASE_PATH=/data/volumebot.db`
3. Verifică că directory-ul `/data` există

### Problema: Build-ul eșuează

**Soluție**:
1. Verifică `requirements.txt` - toate dependențele sunt corecte?
2. Verifică `runtime.txt` - versiunea Python este suportată?
3. Verifică logs-urile de build pentru erori specifice

### Problema: Botul se oprește după câteva minute

**Soluție**:
1. Railway poate opri procesele inactive
2. Botul Telegram ar trebui să rămână activ dacă primește mesaje
3. Consideră să adaugi un health check endpoint (opțional)

## 📝 Notițe Importante

1. **Security**: Nu comite niciodată `.env` sau `*.db` în Git
2. **Backup**: Fă backup regulat al bazei de date
3. **Updates**: Pentru a actualiza botul, fă commit și push pe GitHub, Railway va redeploy automat
4. **Costs**: Railway oferă free tier generos, dar verifică limitele

## 🚀 Updates și Redeploy

Pentru a actualiza botul:

```bash
# Fă modificările în cod
git add .
git commit -m "Update: description of changes"
git push origin main
```

Railway va detecta automat push-ul și va redeploy botul.

## 📞 Support

Dacă întâmpini probleme:
1. Verifică logs-urile în Railway
2. Verifică environment variables
3. Verifică că toate dependențele sunt instalate corect

---

**Succes cu deployment-ul! 🎉**

