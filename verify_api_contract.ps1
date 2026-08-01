param(
    [Parameter(Mandatory = $true)]
    [string]$HealthUrl,
    [int]$TimeoutSeconds = 60,
    [int]$ProcessId = 0
)

$ErrorActionPreference = "Stop"

if ($TimeoutSeconds -le 0) {
    throw "TimeoutSeconds must be a positive integer."
}

$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
$lastError = "The health endpoint did not become ready."

while ([DateTime]::UtcNow -lt $deadline) {
    if ($ProcessId -gt 0) {
        $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
        if ($null -eq $process) {
            throw "Backend process $ProcessId exited before startup verification completed."
        }
    }

    try {
        $health = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 2
    } catch {
        $lastError = $_.Exception.Message
        if ([DateTime]::UtcNow -lt $deadline) {
            Start-Sleep -Seconds 1
        }
        continue
    }

    if ($null -eq $health.api_contract) {
        throw "The running backend does not expose the deployment API contract."
    }
    if ($health.api_contract.status -ne "ok") {
        $missing = $health.api_contract.missing_paths -join ", "
        throw "Backend is missing required API paths: $missing"
    }

    Write-Output "API contract verified."
    return
}

throw "Backend startup verification timed out after $TimeoutSeconds seconds: $lastError"
