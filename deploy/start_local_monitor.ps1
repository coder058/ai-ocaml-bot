param([switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$webRoot = Join-Path $repoRoot 'web'
$localState = Join-Path $repoRoot '.local'
$syncScript = Join-Path $PSScriptRoot 'sync_local_monitor.py'
$nextCli = Join-Path $webRoot 'node_modules\next\dist\bin\next'
$nodeExecutable = (Get-Command node -ErrorAction Stop).Source
$pythonExecutable = (& python -c 'import sys; print(sys.executable)').Trim()
# SOURCE: port 3000 is the documented Next.js default. Bind only loopback.
$monitorPort = 3000
if (Get-NetTCPConnection -State Listen -LocalPort $monitorPort -ErrorAction SilentlyContinue) {
    throw "Port $monitorPort is already in use. Existing processes have been left running."
}
New-Item -ItemType Directory -Path $localState -Force | Out-Null
if (-not $SkipBuild) {
    Push-Location $webRoot
    try {
        & npm run build
        if ($LASTEXITCODE -ne 0) { throw 'Monitor build failed.' }
    } finally { Pop-Location }
}
& $pythonExecutable $syncScript
if ($LASTEXITCODE -ne 0) { throw 'Initial SSH snapshot failed.' }
$previousFileSetting = $env:AI_OCAML_MONITOR_TELEMETRY_FILE
try {
    $env:AI_OCAML_MONITOR_TELEMETRY_FILE = Join-Path $localState 'telemetry.json'
    $webProcess = Start-Process -FilePath $nodeExecutable -ArgumentList @(
        ('"{0}"' -f $nextCli), 'start', '--hostname', '127.0.0.1', '--port', $monitorPort
    ) -WorkingDirectory $webRoot -WindowStyle Hidden -PassThru `
      -RedirectStandardOutput (Join-Path $localState 'web.stdout.log') `
      -RedirectStandardError (Join-Path $localState 'web.stderr.log')
    $webProcess.Id | Set-Content -LiteralPath (Join-Path $localState 'web.pid')
    $syncPidFile = Join-Path $localState 'sync.pid'
    $syncIsRunning = $false
    if (Test-Path -LiteralPath $syncPidFile) {
        $savedPid = [int](Get-Content -LiteralPath $syncPidFile)
        $savedProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$savedPid"
        $syncIsRunning = $savedProcess -and $savedProcess.CommandLine.Contains($syncScript)
    }
    if (-not $syncIsRunning) {
        $syncProcess = Start-Process -FilePath $pythonExecutable -ArgumentList @(
            '-u', ('"{0}"' -f $syncScript), '--loop', '--delay-first'
        ) -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru `
          -RedirectStandardOutput (Join-Path $localState 'sync.stdout.log') `
          -RedirectStandardError (Join-Path $localState 'sync.stderr.log')
        $syncProcess.Id | Set-Content -LiteralPath $syncPidFile
    }
} finally {
    $env:AI_OCAML_MONITOR_TELEMETRY_FILE = $previousFileSetting
}
Write-Output 'Monitor started at http://127.0.0.1:3000. Data refreshes every five minutes while this computer is on.'
