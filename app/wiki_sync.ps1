param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('resolve','sync-file','sync-latest','sync-all')]
    [string]$Command,
    [string]$WikiUrl = $env:FEISHU_WIKI_URL,
    [string]$File,
    [string]$Title,
    [switch]$Force,
    [switch]$IncludeState = $true
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$NotesDir = if ($env:SGLANG_NOTES_DIR) { $env:SGLANG_NOTES_DIR } else { Join-Path $ProjectRoot 'notes' }
$StateFile = if ($env:SGLANG_LEARNING_STATE_FILE) { $env:SGLANG_LEARNING_STATE_FILE } else { Join-Path $NotesDir 'sglang-learning-state.md' }
$RootNotePatterns = @()
$RegistryPath = Join-Path $ProjectRoot 'data\wiki_sync_registry.json'
$CcConfigPath = Join-Path $env:USERPROFILE '.cc-connect\config.toml'
$FeishuBaseUrl = 'https://open.feishu.cn'
$script:WikiContext = $null
$script:GroupNodeCache = @{}

function ConvertTo-HashtableRecursive {
    param([Parameter(ValueFromPipeline = $true)]$InputObject)
    if ($null -eq $InputObject) { return $null }
    if ($InputObject -is [System.Collections.IDictionary]) {
        $table = @{}
        foreach ($key in $InputObject.Keys) {
            $table[$key] = ConvertTo-HashtableRecursive $InputObject[$key]
        }
        return $table
    }
    if ($InputObject -is [System.Collections.IEnumerable] -and -not ($InputObject -is [string])) {
        $arr = @()
        foreach ($item in $InputObject) {
            $arr += ,(ConvertTo-HashtableRecursive $item)
        }
        return $arr
    }
    $props = @($InputObject.PSObject.Properties)
    if (-not ($InputObject -is [string]) -and $props.Count -gt 0) {
        $table = @{}
        foreach ($prop in $props) {
            $table[$prop.Name] = ConvertTo-HashtableRecursive $prop.Value
        }
        return $table
    }
    return $InputObject
}

function Load-Registry {
    if (-not (Test-Path -LiteralPath $RegistryPath)) { return @{} }
    $raw = Get-Content -Raw -LiteralPath $RegistryPath
    if (-not $raw.Trim()) { return @{} }
    return ConvertTo-HashtableRecursive (ConvertFrom-Json $raw)
}

function Save-Registry([hashtable]$Registry) {
    $dir = Split-Path -Parent $RegistryPath
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $Registry | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $RegistryPath -Encoding utf8
}

function Get-MarkdownSha([string]$Path) {
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        return ([System.BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').ToLower()
    }
    finally {
        $sha.Dispose()
    }
}

function Get-DerivedTitle([string]$Path) {
    $fileName = [System.IO.Path]::GetFileNameWithoutExtension($Path)
    $titleMap = @{
        'sglang-learning-state' = 'SGLang 学习状态'
        'sglang-reading-guide-zh' = 'SGLang 阅读导读'
        'sglang-notes-tokenizer-manager-generate-request' = 'TokenizerManager.generate_request 精读'
        'sglang-notes-scheduler-handle-generate-request' = 'Scheduler.handle_generate_request 精读'
        'sglang-notes-scheduler-add-request-to-queue' = 'Scheduler._add_request_to_queue 精读'
        'sglang-notes-llm-vs-diffusion-scheduler-entry' = 'LLM 与 diffusion 调度入口对比'
        'sglang-notes-scheduler-main-loop-new-batch' = 'Scheduler 主循环与新 Batch 形成'
        'sglang-notes-scheduler-prefill-result-running-batch' = 'Prefill 结果回流与 running batch'
        'scheduler-stream-output-prepare-for-decode' = 'stream_output、KV 释放与 prepare_for_decode'
        'scheduler-waiting-queue-to-new-batch' = 'waiting queue 到新 Batch 的形成'
        'scheduler-budget-chunk-preempt-clarified' = '预算、chunk 与 preempt 直白解释'
        'scheduler-preempt-list-to-schedule-batch' = 'preempt_list 到 ScheduleBatch 的形成'
        'sglang-learning-style' = 'SGLang 学习回复风格约束'
    }
    if ($titleMap.ContainsKey($fileName)) { return $titleMap[$fileName] }
    return $fileName.Replace('-', ' ').Replace('_', ' ').Trim()
}

function Get-GroupTitle([string]$Path) {
    $fileName = [System.IO.Path]::GetFileNameWithoutExtension($Path)
    switch ($fileName) {
        'sglang-reading-guide-zh' { return '00 导读与状态' }
        'sglang-learning-state' { return '00 导读与状态' }
        'sglang-notes-tokenizer-manager-generate-request' { return '10 请求进入与准入' }
        'sglang-notes-scheduler-handle-generate-request' { return '10 请求进入与准入' }
        'sglang-notes-scheduler-add-request-to-queue' { return '10 请求进入与准入' }
        'sglang-notes-scheduler-main-loop-new-batch' { return '20 主循环与执行闭环' }
        'sglang-notes-scheduler-prefill-result-running-batch' { return '20 主循环与执行闭环' }
        'scheduler-stream-output-prepare-for-decode' { return '20 主循环与执行闭环' }
        'scheduler-waiting-queue-to-new-batch' { return '20 主循环与执行闭环' }
        'scheduler-budget-chunk-preempt-clarified' { return '20 主循环与执行闭环' }
        'scheduler-preempt-list-to-schedule-batch' { return '20 主循环与执行闭环' }
        'sglang-notes-llm-vs-diffusion-scheduler-entry' { return '30 对比与扩展' }
        default { return '90 其他笔记' }
    }
}

function Get-GroupIntro([string]$GroupTitle) {
    switch ($GroupTitle) {
        '00 导读与状态' { return '本目录保存阅读导读、学习状态，以及后续复习时优先查看的总览信息。' }
        '10 请求进入与准入' { return '本目录聚焦请求从接入层进入调度系统的过程，包括生命周期协调、准入控制与 waiting queue 成员资格。' }
        '20 主循环与执行闭环' { return '本目录聚焦 Scheduler 主循环、waiting queue 形成 batch、prefill 结果回流、decode 继续推进，以及执行后半段闭环。' }
        '30 对比与扩展' { return '本目录保存当前阶段的横向比较与后续扩展观察，用于为下一阶段阅读预埋对比框架。' }
        default { return '本目录保存未归入主线层级的补充笔记。' }
    }
}

function Test-IsExcludedNote([string]$Path) {
    $fileName = [System.IO.Path]::GetFileNameWithoutExtension($Path).ToLowerInvariant()
    if ($fileName -match '(^|-)qa\d*$') { return $true }
    if ($fileName -match '(^|-)draft($|-)') { return $true }
    return $false
}

function Get-AllNoteFiles {
    $items = @()
    if (Test-Path -LiteralPath $NotesDir) {
        $items += Get-ChildItem -LiteralPath $NotesDir -Filter *.md -File
    }
    foreach ($pattern in $RootNotePatterns) {
        $items += Get-ChildItem -Path $pattern -File -ErrorAction SilentlyContinue
    }
    return @(
        $items |
        Where-Object { -not (Test-IsExcludedNote -Path $_.FullName) } |
        Sort-Object FullName -Unique
    )
}

function Get-AppCredentials {
    $appId = $env:FEISHU_APP_ID
    $appSecret = $env:FEISHU_APP_SECRET
    if (-not $appId -or -not $appSecret) {
        if (Test-Path -LiteralPath $CcConfigPath) {
            $text = Get-Content -Raw -LiteralPath $CcConfigPath
            $appIdMatch = [regex]::Match($text, '(?m)^\s*app_id\s*=\s*"([^"]+)"')
            $secretMatch = [regex]::Match($text, '(?m)^\s*app_secret\s*=\s*"([^"]+)"')
            if ($appIdMatch.Success) { $appId = $appIdMatch.Groups[1].Value.Trim() }
            if ($secretMatch.Success) { $appSecret = $secretMatch.Groups[1].Value.Trim() }
        }
    }
    if (-not $appId -or -not $appSecret) {
        throw 'Missing FEISHU_APP_ID / FEISHU_APP_SECRET and no fallback found in ~/.cc-connect/config.toml.'
    }
    return @{ app_id = $appId; app_secret = $appSecret }
}

$script:TenantAccessToken = $null
$script:TenantExpireAt = Get-Date '1970-01-01'

function Get-TenantAccessToken {
    if ($script:TenantAccessToken -and (Get-Date) -lt $script:TenantExpireAt) {
        return $script:TenantAccessToken
    }
    $creds = Get-AppCredentials
    $payload = @{ app_id = $creds.app_id; app_secret = $creds.app_secret } | ConvertTo-Json
    $resp = Invoke-RestMethod -Method Post -Uri ($FeishuBaseUrl + '/open-apis/auth/v3/tenant_access_token/internal') -ContentType 'application/json' -Body $payload
    if ($resp.code -ne 0) {
        throw "Failed to get tenant access token: $($resp | ConvertTo-Json -Depth 10)"
    }
    $script:TenantAccessToken = [string]$resp.tenant_access_token
    $script:TenantExpireAt = (Get-Date).AddSeconds([Math]::Max([int]$resp.expire - 120, 60))
    return $script:TenantAccessToken
}

function Invoke-FeishuApi {
    param(
        [string]$Method,
        [string]$Path,
        $Body = $null,
        [hashtable]$Query = $null
    )
    $uriBuilder = New-Object System.UriBuilder($FeishuBaseUrl + $Path)
    if ($Query) {
        $pairs = @()
        foreach ($k in $Query.Keys) {
            $pairs += ('{0}={1}' -f [System.Uri]::EscapeDataString([string]$k), [System.Uri]::EscapeDataString([string]$Query[$k]))
        }
        $uriBuilder.Query = [string]::Join('&', $pairs)
    }
    $headers = @{ Authorization = 'Bearer ' + (Get-TenantAccessToken) }
    if ($null -ne $Body) {
        $json = $Body | ConvertTo-Json -Depth 20
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
        $resp = Invoke-RestMethod -Method $Method -Uri $uriBuilder.Uri -Headers $headers -ContentType 'application/json; charset=utf-8' -Body $bytes
    }
    else {
        $resp = Invoke-RestMethod -Method $Method -Uri $uriBuilder.Uri -Headers $headers
    }
    if ($resp.code -ne 0) {
        throw "Feishu API failed: $Method $Path => $($resp | ConvertTo-Json -Depth 10)"
    }
    return $resp
}

function Get-WikiToken([string]$WikiUrlOrToken) {
    $m = [regex]::Match($WikiUrlOrToken, '/wiki/([A-Za-z0-9]+)')
    if ($m.Success) { return $m.Groups[1].Value }
    if ($WikiUrlOrToken) { return $WikiUrlOrToken.Trim() }
    throw 'Wiki URL or node token is empty.'
}

function Get-WikiNode([string]$NodeToken) {
    $resp = Invoke-FeishuApi -Method 'GET' -Path '/open-apis/wiki/v2/spaces/get_node' -Query @{ token = $NodeToken }
    return (ConvertTo-HashtableRecursive $resp.data.node)
}

function Initialize-WikiContext([string]$TargetWikiUrl) {
    if ($script:WikiContext -and $script:WikiContext.root_token -eq (Get-WikiToken -WikiUrlOrToken $TargetWikiUrl)) {
        return $script:WikiContext
    }
    $rootToken = Get-WikiToken -WikiUrlOrToken $TargetWikiUrl
    $rootNode = Get-WikiNode -NodeToken $rootToken
    $script:WikiContext = @{
        root_token = $rootToken
        root_node = $rootNode
        space_id = [string]$rootNode.space_id
    }
    $script:GroupNodeCache = @{}
    return $script:WikiContext
}

function Get-WikiChildren([string]$SpaceId, [string]$ParentNodeToken) {
    $items = @()
    $pageToken = $null
    do {
        $query = @{ parent_node_token = $ParentNodeToken; page_size = '50' }
        if ($pageToken) { $query.page_token = $pageToken }
        $resp = Invoke-FeishuApi -Method 'GET' -Path ("/open-apis/wiki/v2/spaces/{0}/nodes" -f $SpaceId) -Query $query
        $data = ConvertTo-HashtableRecursive $resp.data
        if ($null -ne $data -and $data.ContainsKey('items') -and $data.items) {
            $items += @($data.items)
        }
        $pageToken = if ($null -ne $data -and $data.ContainsKey('has_more') -and $data.has_more) { [string]$data.page_token } else { $null }
    } while ($pageToken)
    return @($items)
}

function New-WikiChildPage([string]$SpaceId, [string]$ParentNodeToken, [string]$PageTitle) {
    $resp = Invoke-FeishuApi -Method 'POST' -Path ("/open-apis/wiki/v2/spaces/{0}/nodes" -f $SpaceId) -Body @{
        parent_node_token = $ParentNodeToken
        obj_type = 'docx'
        node_type = 'origin'
        title = $PageTitle
    }
    $data = ConvertTo-HashtableRecursive $resp.data
    if ($data.ContainsKey('node')) { return $data.node }
    return $data
}

function Ensure-WikiChildPage([string]$SpaceId, [string]$ParentNodeToken, [string]$PageTitle, [string]$InitialText = $null) {
    $children = Get-WikiChildren -SpaceId $SpaceId -ParentNodeToken $ParentNodeToken
    foreach ($child in $children) {
        if ($child.title -eq $PageTitle) { return $child }
    }
    $created = New-WikiChildPage -SpaceId $SpaceId -ParentNodeToken $ParentNodeToken -PageTitle $PageTitle
    if ($InitialText -and $created.obj_token) {
        Add-DocumentChildren -DocumentId ([string]$created.obj_token) -Children @((New-TextBlock -BlockType 2 -Key 'text' -Text $InitialText))
    }
    return $created
}

function Get-OrCreate-GroupNode([string]$TargetWikiUrl, [string]$GroupTitle) {
    $ctx = Initialize-WikiContext -TargetWikiUrl $TargetWikiUrl
    if ($script:GroupNodeCache.ContainsKey($GroupTitle)) {
        return $script:GroupNodeCache[$GroupTitle]
    }
    $groupNode = Ensure-WikiChildPage -SpaceId $ctx.space_id -ParentNodeToken $ctx.root_token -PageTitle $GroupTitle -InitialText (Get-GroupIntro -GroupTitle $GroupTitle)
    $groupDocumentId = [string]$groupNode.obj_token
    if ($groupDocumentId) {
        Clear-Document -DocumentId $groupDocumentId
        Add-DocumentChildren -DocumentId $groupDocumentId -Children @((New-TextBlock -BlockType 2 -Key 'text' -Text (Get-GroupIntro -GroupTitle $GroupTitle)))
    }
    $script:GroupNodeCache[$GroupTitle] = $groupNode
    return $groupNode
}

function Get-DocumentChildren([string]$DocumentId, [string]$BlockId) {
    $children = @()
    $pageToken = $null
    do {
        $query = @{ page_size = '500' }
        if ($pageToken) { $query.page_token = $pageToken }
        $resp = Invoke-FeishuApi -Method 'GET' -Path ("/open-apis/docx/v1/documents/{0}/blocks/{1}/children" -f $DocumentId, $BlockId) -Query $query
        $data = ConvertTo-HashtableRecursive $resp.data
        foreach ($item in @($data.items)) {
            if ($item.block_id) { $children += [string]$item.block_id }
        }
        $pageToken = if ($data.has_more) { [string]$data.page_token } else { $null }
    } while ($pageToken)
    return $children
}

function Clear-Document([string]$DocumentId) {
    while ($true) {
        $children = @(Get-DocumentChildren -DocumentId $DocumentId -BlockId $DocumentId)
        if (-not $children -or $children.Count -eq 0) { return }
        Invoke-FeishuApi -Method 'DELETE' -Path ("/open-apis/docx/v1/documents/{0}/blocks/{1}/children/batch_delete" -f $DocumentId, $DocumentId) -Query @{ client_token = [guid]::NewGuid().ToString() } -Body @{
            start_index = 0
            end_index = $children.Count
        } | Out-Null
    }
}

function New-TextBlock([int]$BlockType, [string]$Key, [string]$Text) {
    return @{
        block_type = $BlockType
        $Key = @{
            elements = @(@{ text_run = @{ content = $Text; text_element_style = @{} } })
            style = @{}
        }
    }
}

function Split-TextChunks([string]$Text, [int]$MaxLength = 220) {
    $normalized = ($Text -replace '\s+', ' ').Trim()
    if (-not $normalized) { return @() }
    $chunks = New-Object System.Collections.ArrayList
    $remaining = $normalized
    while ($remaining.Length -gt $MaxLength) {
        $window = $remaining.Substring(0, $MaxLength)
        $cut = $window.LastIndexOfAny([char[]]'。！？；，、,;: )]')
        if ($cut -lt [Math]::Floor($MaxLength / 2)) {
            $cut = $window.LastIndexOf(' ')
        }
        if ($cut -lt [Math]::Floor($MaxLength / 2)) {
            $cut = $MaxLength - 1
        }
        [void]$chunks.Add($remaining.Substring(0, $cut + 1).Trim())
        $remaining = $remaining.Substring($cut + 1).Trim()
    }
    if ($remaining) {
        [void]$chunks.Add($remaining)
    }
    return @($chunks)
}

function Add-ChunkedBlocks($Blocks, [int]$BlockType, [string]$Key, [string]$Text) {
    foreach ($chunk in (Split-TextChunks -Text $Text)) {
        [void]$Blocks.Add((New-TextBlock -BlockType $BlockType -Key $Key -Text $chunk))
    }
}

function Convert-MarkdownToBlocks([string]$MarkdownText) {
    $blocks = New-Object System.Collections.ArrayList
    $paragraph = New-Object System.Collections.ArrayList

    function Flush-Paragraph {
        param($Paragraph, $Blocks)
        if ($Paragraph.Count -eq 0) { return }
        $content = (($Paragraph | ForEach-Object { $_.Trim() } | Where-Object { $_ }) -join ' ').Trim()
        if ($content) {
            Add-ChunkedBlocks -Blocks $Blocks -BlockType 2 -Key 'text' -Text $content
        }
        $Paragraph.Clear() | Out-Null
    }

    foreach ($rawLine in ($MarkdownText -split "`r?`n")) {
        $line = $rawLine.TrimEnd()
        if (-not $line.Trim()) {
            Flush-Paragraph -Paragraph $paragraph -Blocks $blocks
            continue
        }
        if ($line.StartsWith('```')) {
            Flush-Paragraph -Paragraph $paragraph -Blocks $blocks
            Add-ChunkedBlocks -Blocks $blocks -BlockType 2 -Key 'text' -Text $line
            continue
        }
        $heading = [regex]::Match($line, '^(#{1,6})\s+(.*)$')
        if ($heading.Success) {
            Flush-Paragraph -Paragraph $paragraph -Blocks $blocks
            $level = [Math]::Min($heading.Groups[1].Value.Length, 6)
            Add-ChunkedBlocks -Blocks $blocks -BlockType (2 + $level) -Key ("heading{0}" -f $level) -Text $heading.Groups[2].Value.Trim()
            continue
        }
        $bullet = [regex]::Match($line, '^\s*[-*]\s+(.*)$')
        if ($bullet.Success) {
            Flush-Paragraph -Paragraph $paragraph -Blocks $blocks
            Add-ChunkedBlocks -Blocks $blocks -BlockType 2 -Key 'text' -Text ('- ' + $bullet.Groups[1].Value.Trim())
            continue
        }
        $ordered = [regex]::Match($line, '^\s*\d+\.\s+(.*)$')
        if ($ordered.Success) {
            Flush-Paragraph -Paragraph $paragraph -Blocks $blocks
            Add-ChunkedBlocks -Blocks $blocks -BlockType 2 -Key 'text' -Text ($line.Trim())
            continue
        }
        [void]$paragraph.Add($line)
    }

    Flush-Paragraph -Paragraph $paragraph -Blocks $blocks
    return @($blocks)
}

function Add-DocumentChildren([string]$DocumentId, [array]$Children) {
    if (-not $Children -or $Children.Count -eq 0) { return }
    $index = 0
    for ($i = 0; $i -lt $Children.Count; $i += 50) {
        $end = [Math]::Min($i + 49, $Children.Count - 1)
        $batch = @($Children[$i..$end])
        Invoke-FeishuApi -Method 'POST' -Path ("/open-apis/docx/v1/documents/{0}/blocks/{1}/children" -f $DocumentId, $DocumentId) -Query @{ client_token = [guid]::NewGuid().ToString() } -Body @{
            index = $index
            children = $batch
        } | Out-Null
        $index += $batch.Count
    }
}

function Sort-NoteFiles([array]$Files) {
    return @($Files | Sort-Object @{Expression={ Get-GroupTitle $_.FullName }}, @{Expression={ Get-DerivedTitle $_.FullName }})
}

function Sync-OneFile([hashtable]$Registry, [string]$TargetWikiUrl, [string]$SourcePath, [string]$PageTitle, [bool]$ForceSync) {
    if (-not (Test-Path -LiteralPath $SourcePath)) {
        throw "Source file does not exist: $SourcePath"
    }
    $resolved = (Resolve-Path -LiteralPath $SourcePath).Path
    $sourceHash = Get-MarkdownSha -Path $resolved
    if (-not $ForceSync -and $Registry.ContainsKey($resolved) -and $Registry[$resolved].source_hash -eq $sourceHash) {
        return $Registry[$resolved]
    }

    $ctx = Initialize-WikiContext -TargetWikiUrl $TargetWikiUrl
    $titleToUse = if ($PageTitle) { $PageTitle } else { Get-DerivedTitle -Path $resolved }
    $groupTitle = Get-GroupTitle -Path $resolved
    $groupNode = Get-OrCreate-GroupNode -TargetWikiUrl $TargetWikiUrl -GroupTitle $groupTitle
    $parentToken = [string]$groupNode.node_token

    $entry = if ($Registry.ContainsKey($resolved)) { $Registry[$resolved] } else { $null }
    $documentId = $null
    $nodeToken = $null

    if ($entry -and $entry.document_id) {
        $documentId = [string]$entry.document_id
        $nodeToken = [string]$entry.node_token
        try {
            Clear-Document -DocumentId $documentId
        }
        catch {
            $documentId = $null
            $nodeToken = $null
        }
    }

    if (-not $documentId) {
        $existing = Ensure-WikiChildPage -SpaceId $ctx.space_id -ParentNodeToken $parentToken -PageTitle $titleToUse
        $documentId = [string]$existing.obj_token
        $nodeToken = [string]$existing.node_token
        Clear-Document -DocumentId $documentId
    }

    $markdown = Get-Content -Raw -LiteralPath $resolved -Encoding utf8
    $markdown = $markdown -replace '[“”]', '"' -replace '[‘’]', "'"
    $blocks = Convert-MarkdownToBlocks -MarkdownText $markdown
    if (-not $blocks -or $blocks.Count -eq 0) {
        $blocks = @((New-TextBlock -BlockType 2 -Key 'text' -Text '(empty note)'))
    }
    Add-DocumentChildren -DocumentId $documentId -Children $blocks

    $record = @{
        title = $titleToUse
        group_title = $groupTitle
        source_hash = $sourceHash
        node_token = $nodeToken
        document_id = $documentId
        wiki_parent_token = $parentToken
        updated_at = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    }
    $Registry[$resolved] = $record
    return $record
}

$registry = Load-Registry

switch ($Command) {
    'resolve' {
        if (-not $WikiUrl) { throw 'Missing wiki url. Set FEISHU_WIKI_URL or pass -WikiUrl.' }
        $node = Get-WikiNode -NodeToken (Get-WikiToken -WikiUrlOrToken $WikiUrl)
        $node | ConvertTo-Json -Depth 10
    }
    'sync-file' {
        if (-not $WikiUrl) { throw 'Missing wiki url. Set FEISHU_WIKI_URL or pass -WikiUrl.' }
        if (-not $File) { throw '--File is required for sync-file.' }
        $entry = Sync-OneFile -Registry $registry -TargetWikiUrl $WikiUrl -SourcePath $File -PageTitle $Title -ForceSync $Force.IsPresent
        Save-Registry -Registry $registry
        $entry | ConvertTo-Json -Depth 10
    }
    'sync-latest' {
        if (-not $WikiUrl) { throw 'Missing wiki url. Set FEISHU_WIKI_URL or pass -WikiUrl.' }
        $latest = Get-AllNoteFiles | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if (-not $latest) { throw 'No note files found in configured note locations.' }
        $result = @{}
        $result[$latest.FullName] = Sync-OneFile -Registry $registry -TargetWikiUrl $WikiUrl -SourcePath $latest.FullName -PageTitle $null -ForceSync $Force.IsPresent
        if ($IncludeState -and (Test-Path -LiteralPath $StateFile)) {
            $result[$StateFile] = Sync-OneFile -Registry $registry -TargetWikiUrl $WikiUrl -SourcePath $StateFile -PageTitle 'SGLang 学习状态' -ForceSync $Force.IsPresent
        }
        Save-Registry -Registry $registry
        $result | ConvertTo-Json -Depth 20
    }
    'sync-all' {
        if (-not $WikiUrl) { throw 'Missing wiki url. Set FEISHU_WIKI_URL or pass -WikiUrl.' }
        $result = @{}
        foreach ($note in (Sort-NoteFiles -Files (Get-AllNoteFiles))) {
            $result[$note.FullName] = Sync-OneFile -Registry $registry -TargetWikiUrl $WikiUrl -SourcePath $note.FullName -PageTitle $null -ForceSync $Force.IsPresent
        }
        if ($IncludeState -and (Test-Path -LiteralPath $StateFile)) {
            $result[$StateFile] = Sync-OneFile -Registry $registry -TargetWikiUrl $WikiUrl -SourcePath $StateFile -PageTitle 'SGLang 学习状态' -ForceSync $Force.IsPresent
        }
        Save-Registry -Registry $registry
        $result | ConvertTo-Json -Depth 20
    }
}
