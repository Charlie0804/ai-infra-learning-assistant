param(
    [string]$ConfigPath = "$env:USERPROFILE\.cc-connect\config.toml",
    [string]$CcConnectPath = "$env:APPDATA\npm\cc-connect.cmd",
    [string]$LogDir = (Join-Path $PSScriptRoot "..\..\logs\cc-connect"),
    [string]$ProxyUrl,
    [string]$NoProxy = "127.0.0.1,localhost",
    [switch]$Restart
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-ProxyUrl {
    param([string]$ExplicitProxyUrl)

    if ($ExplicitProxyUrl) { return $ExplicitProxyUrl }
    if ($env:HTTPS_PROXY) { return $env:HTTPS_PROXY }
    if ($env:HTTP_PROXY) { return $env:HTTP_PROXY }

    $internetSettings = Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings" -ErrorAction SilentlyContinue
    if ($internetSettings -and $internetSettings.ProxyEnable -eq 1 -and $internetSettings.ProxyServer) {
        $proxyServer = [string]$internetSettings.ProxyServer
        if ($proxyServer -match "=") {
            $httpsMatch = [regex]::Match($proxyServer, "(?i)(?:^|;)https=([^;]+)")
            if ($httpsMatch.Success) {
                $proxyServer = $httpsMatch.Groups[1].Value
            } else {
                $httpMatch = [regex]::Match($proxyServer, "(?i)(?:^|;)http=([^;]+)")
                if ($httpMatch.Success) {
                    $proxyServer = $httpMatch.Groups[1].Value
                }
            }
        }
        if ($proxyServer -and $proxyServer -notmatch "^[a-z]+://") {
            $proxyServer = "http://$proxyServer"
        }
        if ($proxyServer) { return $proxyServer }
    }

    return $null
}

if (-not (Test-Path -LiteralPath $ConfigPath)) {
    throw "Config file not found: $ConfigPath"
}

if (-not (Test-Path -LiteralPath $CcConnectPath)) {
    throw "cc-connect launcher not found: $CcConnectPath"
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -like "cc-connect*" })
if ($running.Count -gt 0 -and -not $Restart) {
    $ids = ($running | Select-Object -ExpandProperty Id) -join ", "
    throw "cc-connect is already running. Existing PID(s): $ids. Re-run with -Restart to restart it."
}

if ($running.Count -gt 0 -and $Restart) {
    foreach ($proc in $running) {
        Stop-Process -Id $proc.Id -Force
    }
    Start-Sleep -Seconds 2
}

$resolvedProxy = Resolve-ProxyUrl -ExplicitProxyUrl $ProxyUrl
if ($resolvedProxy) {
    $env:HTTP_PROXY = $resolvedProxy
    $env:HTTPS_PROXY = $resolvedProxy
    $env:ALL_PROXY = $resolvedProxy
    $env:NO_PROXY = $NoProxy
}

$stdout = Join-Path $LogDir "cc-connect.log"
$stderr = Join-Path $LogDir "cc-connect.err.log"

$proc = Start-Process `
    -FilePath $CcConnectPath `
    -ArgumentList "--config", $ConfigPath `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -PassThru `
    -WindowStyle Hidden

Start-Sleep -Seconds 6

Write-Output ("PID=" + $proc.Id)
Write-Output ("PROXY=" + $(if ($resolvedProxy) { $resolvedProxy } else { "direct" }))
Write-Output ("LOG=" + $stdout)
Write-Output ""
Get-Content -LiteralPath $stdout -Tail 40
