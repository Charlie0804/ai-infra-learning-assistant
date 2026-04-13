param(
    [string]$LogPath = (Join-Path $PSScriptRoot "..\..\logs\cc-connect\cc-connect.log"),
    [string]$ErrorLogPath = (Join-Path $PSScriptRoot "..\..\logs\cc-connect\cc-connect.err.log"),
    [string]$ProxyHost = "127.0.0.1",
    [int]$ProxyPort = 7890,
    [switch]$AsJson,
    [switch]$RepairIfUnhealthy
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-LatestCcConnectProcess {
    return Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -like "cc-connect*" } |
        Sort-Object StartTime -Descending |
        Select-Object -First 1
}

function Get-LastMatch {
    param(
        [string[]]$Lines,
        [string]$Pattern
    )

    for ($i = $Lines.Count - 1; $i -ge 0; $i--) {
        if ($Lines[$i] -match $Pattern) {
            return $Lines[$i]
        }
    }
    return $null
}

function Get-StatusLevel {
    param(
        [bool]$IsHealthy,
        [bool]$CanRepair
    )

    if ($IsHealthy) { return "healthy" }
    if ($CanRepair) { return "repairable" }
    return "unhealthy"
}

$proc = Get-LatestCcConnectProcess
$logLines = @()
$errLines = @()

if (Test-Path -LiteralPath $LogPath) {
    $logLines = @(Get-Content -LiteralPath $LogPath -Tail 300)
}

if (Test-Path -LiteralPath $ErrorLogPath) {
    $errLines = @(Get-Content -LiteralPath $ErrorLogPath -Tail 80)
}

$latestConnected = Get-LastMatch -Lines $logLines -Pattern "connected to wss://msg-frontier\.feishu\.cn"
$latestDisconnected = Get-LastMatch -Lines $logLines -Pattern "disconnected to wss://msg-frontier\.feishu\.cn"
$latestConnectFailed = Get-LastMatch -Lines $logLines -Pattern "connect failed"
$latestReconnect = Get-LastMatch -Lines $logLines -Pattern "trying to reconnect"
$latestTurnComplete = Get-LastMatch -Lines $logLines -Pattern "turn complete"

$connections = @()
if ($proc) {
    $connections = @(Get-NetTCPConnection -OwningProcess $proc.Id -ErrorAction SilentlyContinue)
}

$proxyConnection = $connections |
    Where-Object {
        $_.State -eq "Established" -and
        $_.RemoteAddress -eq $ProxyHost -and
        $_.RemotePort -eq $ProxyPort
    } |
    Select-Object -First 1

$directTlsConnection = $connections |
    Where-Object {
        $_.State -eq "Established" -and
        $_.RemotePort -eq 443 -and
        $_.RemoteAddress -ne $ProxyHost
    } |
    Select-Object -First 1

$hasEstablishedPath = ($null -ne $proxyConnection) -or ($null -ne $directTlsConnection)

$logSuggestsConnected = $false
if ($latestConnected) {
    $cIdx = [array]::LastIndexOf($logLines, $latestConnected)
    $dIdx = if ($latestDisconnected) { [array]::LastIndexOf($logLines, $latestDisconnected) } else { -1 }
    $fIdx = if ($latestConnectFailed) { [array]::LastIndexOf($logLines, $latestConnectFailed) } else { -1 }
    $logSuggestsConnected = ($cIdx -gt $dIdx) -and ($cIdx -gt $fIdx)
}

$reasons = New-Object System.Collections.Generic.List[string]
if (-not $proc) {
    $reasons.Add("cc-connect process not found")
}
if (-not $latestConnected) {
    $reasons.Add("No successful Feishu websocket connection was found in the recent log")
}
if ($latestConnected -and -not $logSuggestsConnected) {
    $reasons.Add("The recent log shows a Feishu disconnect without a newer successful reconnect")
}
if ($proc -and -not $hasEstablishedPath) {
    $reasons.Add("The cc-connect process has no visible established proxy or HTTPS connection")
}

$isHealthy = ($reasons.Count -eq 0)
$repairScript = Join-Path $PSScriptRoot "restart-with-proxy.ps1"
$canRepair = Test-Path -LiteralPath $repairScript
$status = Get-StatusLevel -IsHealthy:$isHealthy -CanRepair:$canRepair

$result = [ordered]@{
    status = $status
    is_healthy = $isHealthy
    checked_at = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    process = if ($proc) {
        [ordered]@{
            id = $proc.Id
            start_time = $proc.StartTime.ToString("yyyy-MM-dd HH:mm:ss")
        }
    } else { $null }
    proxy_path_established = ($null -ne $proxyConnection)
    direct_tls_path_established = ($null -ne $directTlsConnection)
    latest_connected = $latestConnected
    latest_disconnected = $latestDisconnected
    latest_connect_failed = $latestConnectFailed
    latest_reconnect = $latestReconnect
    latest_turn_complete = $latestTurnComplete
    reasons = @($reasons)
}

if ($RepairIfUnhealthy -and -not $isHealthy) {
    & $repairScript
    $result["repair_attempted"] = $true
} elseif ($RepairIfUnhealthy) {
    $result["repair_attempted"] = $false
}

if ($AsJson) {
    $result | ConvertTo-Json -Depth 10
    return
}

Write-Output ("status: " + $result.status)
Write-Output ("checked_at: " + $result.checked_at)
if ($result.process) {
    Write-Output ("pid: " + $result.process.id)
    Write-Output ("started: " + $result.process.start_time)
}
Write-Output ("proxy_path_established: " + $result.proxy_path_established)
Write-Output ("direct_tls_path_established: " + $result.direct_tls_path_established)

if ($result.latest_connected) { Write-Output ("latest_connected: " + $result.latest_connected) }
if ($result.latest_disconnected) { Write-Output ("latest_disconnected: " + $result.latest_disconnected) }
if ($result.latest_connect_failed) { Write-Output ("latest_connect_failed: " + $result.latest_connect_failed) }
if ($result.latest_turn_complete) { Write-Output ("latest_turn_complete: " + $result.latest_turn_complete) }

if ($result.reasons.Count -gt 0) {
    Write-Output ""
    Write-Output "reasons:"
    foreach ($reason in $result.reasons) {
        Write-Output ("- " + $reason)
    }
}

if ($RepairIfUnhealthy) {
    Write-Output ""
    Write-Output ("repair_attempted: " + $result.repair_attempted)
}
