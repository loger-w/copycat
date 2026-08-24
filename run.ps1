# 一鍵啟動看盤工具:同一個 shell 內同時跑 backend(FastAPI)+ frontend(Vite)。
#
#   .\run.ps1                              一般交易日 / 非交易日(自動取最近交易日;configs/trading_holidays.json)
#   .\run.ps1 -BackfillDate 2026-07-28     手動指定回補日(TXO 面、或交易日盤前冷啟動想看前一日時)
#
# 前置:達錢 4(Touchance 4.0)桌面 app 已開啟並登入,否則 TC4 訂閱拿不到推播。
# Ctrl+C 一次同時收掉兩邊(finally 會補殺殘留的 node / python 子樹)。
# backend 輸出除了印在本 shell,另由 python -m copycat.server 自己 tee 到
# logs/server-YYYYMMDD-HHMM.log(手動起 server 也一樣落檔,不靠這支腳本重導向)。
#
# 本檔必須存成 UTF-8 with BOM —— Windows PowerShell 5.1 讀無 BOM 的 .ps1 會當 ANSI(CP950),
# 中文會變亂碼且可能生出假引號讓整份 parse error(已踩過)。編輯器另存時注意編碼。

[CmdletBinding()]
param(
    # 手動回補基準日(YYYY-MM-DD),對應 env TXO_BACKFILL_DATE;非交易日已由交易日曆自動處理,只在 TXO 面 / 盤前冷啟動需要
    [string]$BackfillDate
)

$ErrorActionPreference = 'Stop'

$root        = $PSScriptRoot
$python      = Join-Path $root '.venv\Scripts\python.exe'
$frontendDir = Join-Path $root 'frontend'

# canonical port(design §4 IR-3)。frontend/vite.config.ts 的 proxy target 寫死同一個 port,
# 要改必須兩邊一起改,否則 /api 與 /ws 會 proxy 到空的位址。
$port = 8721

function Fail {
    # 前置檢查失敗走這裡而不是 throw:啟動腳本的訊息要一眼可讀,不要被一坨 PowerShell 錯誤裝飾蓋掉
    param([string]$Message)
    Write-Host "[run] $Message" -ForegroundColor Red
    exit 1
}

function Test-PortListening {
    # 注意:Get-NetTCPConnection 查無符合連線時是「拋錯」不是回空,
    # 所以要用 SilentlyContinue 把「沒人聽」和「cmdlet 不存在」分開判,別混成同一個 catch。
    param([int]$Port)
    if (-not (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue)) { return $null }  # 無法判定
    return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Stop-Tree {
    param([System.Diagnostics.Process]$Proc, [string]$Label)
    if ($null -eq $Proc -or $Proc.HasExited) { return }
    Write-Host "[run] 收掉 $Label (pid $($Proc.Id)) ..." -ForegroundColor DarkGray
    # npm 會再長出 node 子行程,必須 /T 殺整棵樹才不會留 orphan 佔著 5173
    & taskkill.exe /PID $Proc.Id /T /F | Out-Null
}

function Wait-GracefulExit {
    # backend 專用:Ctrl+C 的 CTRL_C_EVENT 會同時送到子行程,uvicorn 隨即開始 graceful
    # shutdown —— 但這支腳本的 finally 幾十毫秒內就 taskkill /T /F,lifespan 根本跑不到
    # TC4 sources 的 close()(UNSUB + Disconnect)。沒 LOGOUT 就死的 session 要等 TC4 端
    # ~60s 的 ExecuteCheckPingTime 才被 reap,而 reap 會把它獨持的 refcount key 歸零、
    # 連帶把 symbol 的上游 feed 帶走 —— 下一台 server 開頭 ~60s 零推播(2026-08-18 實證,
    # 見 .claude/skills/tc4-market-facts/SKILL.md)。這裡先等它自己收乾淨,超時才硬殺。
    # 上限 15s 不是 10s:`_ensure_connected` 持 api 鎖跨 Connect()(最壞 _REQ_TIMEOUT_MS
    # = 10s),close() 開頭要拿同一把鎖 → 關機最壞先被那一發吃掉整整 10 秒,10s 的窗會
    # 剛好在 TC4 還沒退訂完時到期(review ST2)。
    param([System.Diagnostics.Process]$Proc, [int]$TimeoutSecs = 15)
    if ($null -eq $Proc -or $Proc.HasExited) { return }
    Write-Host "[run] 等 backend 自行收尾(TC4 退訂 + Disconnect,最多 ${TimeoutSecs}s) ..." -ForegroundColor DarkGray
    if ($Proc.WaitForExit($TimeoutSecs * 1000)) {
        Write-Host '[run] backend 已自行結束(TC4 session 已 LOGOUT)' -ForegroundColor DarkGray
    }
    else {
        Write-Host "[run] backend ${TimeoutSecs}s 內未結束,改為強制收掉(TC4 session 會留到 reap)" -ForegroundColor Yellow
    }
}

# --- 前置檢查(壞掉要有明確下一步,不要讓 uvicorn 或 vite 自己噴難懂的錯) ---

if (-not (Test-Path $python)) {
    Fail "找不到 venv:$python`n     先建立:py -3.13 -m venv .venv"
}

& $python -c "import fastapi, uvicorn, zmq" | Out-Null
if ($LASTEXITCODE -ne 0) {
    Fail "backend 缺 live extras`n     補裝:$python -m pip install -e `".[live]`""
}

$npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
if (-not $npm) { Fail '找不到 npm.cmd,請先裝 Node.js' }

if ((Test-PortListening -Port $port) -eq $true) {
    Fail "port $port 已被占用,可能已有一份 server 還在跑(先把它關掉)"
}

# 達錢 4 沒開的話 backend 會在 lifespan 噴一長串 ZMQ traceback 然後整組收掉,
# 看起來像「只跑了前端」。先擋在這裡講清楚。TC4 OpenAPI 登入 port 見 copycat/live/tc4.py 預設值。
$tc4Port = 50774
if ((Test-PortListening -Port $tc4Port) -eq $false) {
    Fail "達錢 4(Touchance 4.0)沒開或還沒登入(port $tc4Port 沒有 listener)`n     先把桌面 app 開起來登入,再跑這支腳本。"
}

if (-not (Test-Path (Join-Path $frontendDir 'node_modules'))) {
    Write-Host '[run] frontend/node_modules 不存在,先跑 npm install ...' -ForegroundColor Yellow
    Push-Location $frontendDir
    try { & $npm install } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { Fail 'npm install 失敗' }
}

# --- 啟動 ---

# 子行程繼承本 shell 的環境變數;server 端不載 dotenv,.env 由 runtime 自己逐 key fallback
$env:TXO_SERVER_PORT = "$port"
if ($BackfillDate) {
    $env:TXO_BACKFILL_DATE = $BackfillDate
    Write-Host "[run] TXO_BACKFILL_DATE=$BackfillDate" -ForegroundColor Cyan
}

$backend  = $null
$frontend = $null
# backend 有沒有收到 Ctrl+C(= 值不值得等它 graceful)。Ctrl+C 走的是「while 迴圈被
# 中斷、直接跳 finally」那條路,旗標維持 $true;而「frontend 自己先死」是我們主動
# break 出來的,那條路沒有人送 CTRL_C_EVENT 給 backend —— 等它只是白等一輪 timeout
# 再硬殺(review SP6)。PowerShell 5.1 沒有安全的「對別的 process 送 Ctrl+C」——
# AttachConsole + GenerateConsoleCtrlEvent 會連本 shell 自己的 handler 一起打到,
# 而 backend 沒有 HTTP 關機端點(不發明一個)→ 那條路維持直接硬殺,記留尾。
$backendGotCtrlC = $true

try {
    Write-Host "[run] backend  -> http://127.0.0.1:$port" -ForegroundColor Green
    $backend = Start-Process -FilePath $python -ArgumentList '-m', 'copycat.server' `
        -WorkingDirectory $root -NoNewWindow -PassThru

    Write-Host '[run] frontend -> vite dev(實際網址看下方 vite 輸出)' -ForegroundColor Green
    $frontend = Start-Process -FilePath $npm -ArgumentList 'run', 'dev' `
        -WorkingDirectory $frontendDir -NoNewWindow -PassThru

    # 先摸一次 .Handle 把 handle 快取住,否則行程結束後 .ExitCode 會是空的(PowerShell 已知行為)
    $null = $backend.Handle
    $null = $frontend.Handle

    Write-Host '[run] 兩邊的輸出會交錯印在這個 shell(backend 另存 logs\server-*.log);Ctrl+C 結束。' -ForegroundColor DarkGray

    # 任一邊死掉就整組收掉 —— 只剩半套在跑比全掛還難察覺
    while ($true) {
        if ($backend.HasExited) {
            Write-Host "[run] backend 結束(exit $($backend.ExitCode)),一併收掉 frontend" -ForegroundColor Red
            if ($backend.ExitCode -ne 0) {
                Write-Host '[run] 若錯誤是 TC4 quote connect failed:確認達錢 4 已開啟並登入' -ForegroundColor Yellow
            }
            break
        }
        if ($frontend.HasExited) {
            Write-Host "[run] frontend 結束(exit $($frontend.ExitCode)),一併收掉 backend" -ForegroundColor Red
            $backendGotCtrlC = $false
            break
        }
        Start-Sleep -Milliseconds 500
    }
} finally {
    Stop-Tree -Proc $frontend -Label 'frontend'
    # backend 先給 graceful 窗再硬殺(理由見 Wait-GracefulExit);沒收到 Ctrl+C 的那條
    # 路不等 —— 等了也不會有人叫它收尾(review SP6)
    if ($backendGotCtrlC) {
        Wait-GracefulExit -Proc $backend
    }
    else {
        Write-Host '[run] backend 未收到 Ctrl+C(frontend 先退),直接強制收掉;TC4 session 會留到 reap' -ForegroundColor Yellow
    }
    Stop-Tree -Proc $backend -Label 'backend'
}
