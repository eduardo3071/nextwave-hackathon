# start_all.ps1 — sobe backend + tunel numa tacada só
#
# Uso:  .\start_all.ps1
#
# O que faz: abre duas janelas novas do PowerShell — uma com o uvicorn,
# outra com o ngrok. Cada uma imprime seus próprios logs pra você acompanhar.
# Depois disso, o painel do Lovable já bate no backend via ngrok.
#
# Pra derrubar: fecha as duas janelas (ou Ctrl+C em cada uma).
# Se preferir NGROK_DOMAIN diferente, seta a env var antes:
#   $env:NGROK_DOMAIN = "outro-dominio.ngrok-free.dev"; .\start_all.ps1

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$domain = if ($env:NGROK_DOMAIN) { $env:NGROK_DOMAIN } else { "clique-lukewarm-frail.ngrok-free.dev" }

Write-Host "── Amarra · sobe tudo ─────────────────────────" -ForegroundColor Cyan
Write-Host "backend .... uvicorn app.main:app  (porta 8000, --reload)"
Write-Host "tunel ...... ngrok --domain=$domain"
Write-Host ""

# Terminal 1 — uvicorn
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$here'; python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
) -WindowStyle Normal

Start-Sleep -Seconds 1

# Terminal 2 — ngrok
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "ngrok http --domain=$domain 8000"
) -WindowStyle Normal

Write-Host "duas janelas abertas. Pra testar:" -ForegroundColor Green
Write-Host "  curl.exe https://$domain/health"
Write-Host ""
Write-Host "pra derrubar: fecha as duas janelas ou Ctrl+C em cada."
