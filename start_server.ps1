$ErrorActionPreference = "Stop"

$repoRoot = $PSScriptRoot
$backendRoot = Join-Path $repoRoot "zhishi-master\backend"
$venvPython = Join-Path $repoRoot "zhishi-master\.venv\Scripts\python.exe"
$pythonExe = if (Test-Path -LiteralPath $venvPython) {
    $venvPython
} else {
    (Get-Command python -ErrorAction Stop).Source
}
$stdoutPath = Join-Path $repoRoot "server.log"
$stderrPath = Join-Path $repoRoot "server_error.log"
$backendPort = if ($env:ZHISHI_BACKEND_PORT) {
    [int]$env:ZHISHI_BACKEND_PORT
} else {
    8765
}
if ($backendPort -le 0 -or $backendPort -gt 65535) {
    throw "ZHISHI_BACKEND_PORT must be between 1 and 65535."
}
$startupTimeoutSeconds = if ($env:ZHISHI_STARTUP_TIMEOUT_SECONDS) {
    [int]$env:ZHISHI_STARTUP_TIMEOUT_SECONDS
} else {
    60
}
if ($startupTimeoutSeconds -le 0) {
    throw "ZHISHI_STARTUP_TIMEOUT_SECONDS must be a positive integer."
}

$existingListener = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() |
    Where-Object { $_.Port -eq $backendPort }
if ($existingListener) {
    throw "Port $backendPort is already in use. Stop the old backend before deploying this version."
}

$serverProcess = Start-Process `
    -FilePath $pythonExe `
    -ArgumentList @("-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "$backendPort") `
    -WorkingDirectory $backendRoot `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath `
    -WindowStyle Hidden `
    -PassThru

try {
    & (Join-Path $repoRoot "verify_api_contract.ps1") `
        -HealthUrl "http://127.0.0.1:$backendPort/health" `
        -TimeoutSeconds $startupTimeoutSeconds `
        -ProcessId $serverProcess.Id
} catch {
    $startupError = $_.Exception.Message
    $serverProcess.Refresh()
    if ($serverProcess.HasExited) {
        $startupError = "$startupError Exit code: $($serverProcess.ExitCode). See $stderrPath."
    }
    if (-not $serverProcess.HasExited) {
        Stop-Process -Id $serverProcess.Id -Force
    }
    throw "Backend startup verification failed: $startupError"
}

Write-Host "Backend started and API contract verified. PID: $($serverProcess.Id)"
