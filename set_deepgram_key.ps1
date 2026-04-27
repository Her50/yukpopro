# ─────────────────────────────────────────────────────────────
# Yukpo — Saisie sécurisée DEEPGRAM_API_KEY → Fly.io
# Lance ce script directement dans PowerShell.
# La clé n'est jamais affichée ni loguée.
# ─────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "  Yukpo — Configuration DEEPGRAM_API_KEY" -ForegroundColor Cyan
Write-Host "  ─────────────────────────────────────────" -ForegroundColor DarkGray
Write-Host ""

# Saisie masquée (caractères remplacés par *)
$secureKey = Read-Host "  Colle ta clé Deepgram (invisible)" -AsSecureString

# Conversion en texte brut en mémoire uniquement
$bstr   = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
$apiKey = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
[System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)

if ($apiKey.Length -lt 10) {
    Write-Host ""
    Write-Host "  ✗ Clé trop courte — abandonnée." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "  ✓ Clé reçue (longueur : $($apiKey.Length) chars)" -ForegroundColor Green
Write-Host "  → Envoi vers Fly.io (yukpopro-backend)..." -ForegroundColor DarkGray
Write-Host ""

# Injection dans Fly.io sans jamais afficher la valeur
$env:DEEPGRAM_API_KEY = $apiKey
fly secrets set "DEEPGRAM_API_KEY=$apiKey" --app yukpopro-backend

# Nettoyage mémoire immédiat
$apiKey  = $null
$env:DEEPGRAM_API_KEY = $null
[System.GC]::Collect()

Write-Host ""
Write-Host "  ✓ Secret configuré. Redéploiement..." -ForegroundColor Green
fly deploy --app yukpopro-backend

Write-Host ""
Write-Host "  ✓ Terminé. Vérification du statut STT :" -ForegroundColor Green
Start-Sleep -Seconds 5
try {
    $resp = Invoke-RestMethod "https://yukpopro-backend.fly.dev/api/v1/translate/live/status"
    if ($resp.stt_available -eq $true) {
        Write-Host "  ✓ STT opérationnel !" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ STT toujours inactif — vérifie la clé" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  ⚠ Backend non joignable encore (normal, attends 30s)" -ForegroundColor Yellow
}
