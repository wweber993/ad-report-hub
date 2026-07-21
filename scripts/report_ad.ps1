<#
.SYNOPSIS
    AD Report Hub — Active Directory Security & Compliance Collector

.DESCRIPTION
    Collects user account metrics, inactivity data, password policies, privileged group memberships,
    and security risk indicators from Active Directory domains. The data can be exported to a local
    JSON report file or posted directly to the AD Report Hub API endpoint.

    To configure the script, simply edit the $CONFIG variables below.

.EXAMPLE
    # Run the collector manually
    .\report_ad.ps1

.EXAMPLE
    # Install as a scheduled task to run automatically every day at 02:00 AM
    .\report_ad.ps1 -InstallTask
#>

[CmdletBinding()]
param (
    [switch]$InstallTask,
    [string]$TaskTime = "02:00"
)

# ==============================================================================
# CONFIGURATION
# Edit these values to match your environment before running or scheduling.
# ==============================================================================

$CONFIG = @{
    # EN: Target domain/environment label (e.g., "Production", "Headquarters")
    # PT: Rótulo do domínio/ambiente alvo (ex: "Produção", "Matriz")
    Environment = "Production"

    # EN: Single Distinguished Name (DN) OU base to search users from.
    # EN: Leave empty to search the entire domain.
    # PT: Unidade Organizacional (OU/DN) única base para buscar usuários.
    # PT: Deixe vazio para buscar em todo o domínio.
    SearchBase = ""

    # EN: Array of OU Distinguished Names to query multiple OUs.
    # PT: Lista (Array) de Unidades Organizacionais (DN) para consultar múltiplas OUs.
    SearchBases = @()

    # EN: Optional Distinguished Name (DN) to query privileged accounts domain-wide.
    # PT: Distinguished Name (DN) opcional para consultar contas privilegiadas em todo o domínio.
    SearchPrivilege = ""

    # EN: Array of OU Distinguished Names to exclude from user collection.
    # PT: Lista (Array) de OUs (DN) para excluir da coleta de usuários.
    ExcludedOUs = @()

    # EN: Threshold in days to flag accounts as inactive based on last logon.
    # PT: Limite de dias sem logon para marcar uma conta como inativa.
    InactiveDays = 60

    # EN: Fallback password max age in days if domain password policy is unreachable.
    # PT: Idade máxima da senha (em dias) caso a política de senha do domínio seja inacessível.
    PasswordMaxAgeDays = 60

    # EN: Auto-discover Domain Controllers dynamically. If $false, fill DomainControllers array.
    # PT: Descobrir Controladores de Domínio automaticamente. Se $false, preencha o array DomainControllers.
    UseAutoDC = $true
    DomainControllers = @()

    # EN: AD Report Hub API settings
    # PT: Configurações de API do AD Report Hub
    ApiUrl = "http://localhost:8090/ad/api/ingest"
    ApiToken = "your_secret_ingest_token_here"

    # EN: Optional file path to save the generated report JSON locally (e.g., "C:\Reports\ad_report.json").
    # EN: Leave empty to not save locally.
    # PT: Caminho opcional do arquivo para salvar o relatório JSON localmente (ex: "C:\Reports\ad_report.json").
    # PT: Deixe vazio para não salvar localmente.
    OutputFile = ""
}

# ==============================================================================
# SCHEDULED TASK INSTALLATION
# ==============================================================================

if ($InstallTask) {
    $TaskName = "ADReportHub_Collector"
    $ScriptPath = $PSCommandPath

    Write-Host "[+] Creating Scheduled Task '$TaskName' to run daily at $TaskTime..." -ForegroundColor Cyan

    try {
        $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -NoProfile -File `"$ScriptPath`""
        $trigger = New-ScheduledTaskTrigger -Daily -At $TaskTime
        $principal = New-ScheduledTaskPrincipal -UserId "NT AUTHORITY\SYSTEM" -LogonType ServiceAccount -RunLevel Highest

        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null
        
        Write-Host "[✔] Scheduled Task '$TaskName' successfully registered to run daily at $TaskTime!" -ForegroundColor Green
    }
    catch {
        Write-Error "Failed to create scheduled task: $_"
    }
    exit
}

# ==============================================================================
# PREREQUISITES & MODULE VERIFICATION
# ==============================================================================

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "         AD Report Hub — Active Directory Data Collector        " -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

if (-not (Get-Module -ListAvailable -Name ActiveDirectory)) {
    Write-Error "The ActiveDirectory PowerShell module (RSAT) is not installed on this system."
    Write-Host "Please install Remote Server Administration Tools (RSAT) or run on a Domain Joined server." -ForegroundColor Yellow
    exit 1
}

Import-Module ActiveDirectory -ErrorAction Stop

# ==============================================================================
# EXCLUDED OUs HELPERS
# ==============================================================================

$excludedOUList = @()
foreach ($ou in $CONFIG.ExcludedOUs) {
    if (-not [string]::IsNullOrWhiteSpace($ou)) {
        $excludedOUList += $ou.Trim()
    }
}

function Is-UserInExcludedOU {
    param ([string]$userDN)

    foreach ($excludedOU in $excludedOUList) {
        if ($userDN -like "*$excludedOU") {
            return $true
        }
    }
    return $false
}

$timestamp = (Get-Date).ToUniversalTime().ToString("o")

# ==============================================================================
# DOMAIN CONTROLLERS DISCOVERY
# ==============================================================================

$discoveredDCs = @()

if ($CONFIG.UseAutoDC) {
    try {
        Write-Host "[+] Auto-discovering Domain Controllers..." -ForegroundColor Green
        $discoveredDCs = (Get-ADDomainController -Filter *).HostName
    }
    catch {
        Write-Warning "Could not auto-discover Domain Controllers: $_"
    }
}
else {
    $discoveredDCs = $CONFIG.DomainControllers
}

# ==============================================================================
# DOMAIN PASSWORD POLICY
# ==============================================================================

try {
    $policy = Get-ADDefaultDomainPasswordPolicy -ErrorAction Stop
    $maxPasswordAge = $policy.MaxPasswordAge.Days
    Write-Host "[+] Domain Default Password Policy Max Age: $maxPasswordAge days" -ForegroundColor Green
}
catch {
    $maxPasswordAge = [int]$CONFIG.PasswordMaxAgeDays
    Write-Host "[!] Could not fetch default password policy. Using fallback: $maxPasswordAge days" -ForegroundColor Yellow
}

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

function Get-UserOUPath {
    param ([string]$dn)

    $ous = ($dn -split ',') |
        Where-Object { $_ -like 'OU=*' } |
        ForEach-Object { $_ -replace '^OU=' }

    [array]::Reverse($ous)
    return ($ous -join '/')
}

function Get-TrueLastLogon {
    param ([string]$sam)

    $last = 0
    if ($discoveredDCs.Count -gt 0) {
        foreach ($dc in $discoveredDCs) {
            try {
                $u = Get-ADUser $sam -Server $dc -Properties lastLogon -ErrorAction SilentlyContinue
                if ($u -and $u.lastLogon -gt $last) {
                    $last = $u.lastLogon
                }
            }
            catch {}
        }
    }

    if ($last -gt 0) {
        return [DateTime]::FromFileTime($last)
    }
    return $null
}

# Group Membership Cache
$groupCache = @{}

function Get-UserGroups {
    param ($user)

    if ($groupCache.ContainsKey($user.SamAccountName)) {
        return $groupCache[$user.SamAccountName]
    }

    try {
        # Recursive group membership using LDAP Matching Rule In Chain
        $filter = "(member:1.2.840.113556.1.4.1941:=$($user.DistinguishedName))"
        $groups = Get-ADGroup -LDAPFilter $filter -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name
        
        $directGroups = Get-ADPrincipalGroupMembership $user -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name
        $allGroups = ($groups + $directGroups) | Sort-Object -Unique
    }
    catch {
        $allGroups = @()
    }

    $groupCache[$user.SamAccountName] = $allGroups
    return $allGroups
}

# ==============================================================================
# USER COLLECTION
# ==============================================================================

$users = @()

if ($CONFIG.SearchBases -and $CONFIG.SearchBases.Count -gt 0) {
    foreach ($base in $CONFIG.SearchBases) {
        if ([string]::IsNullOrWhiteSpace($base)) { continue }
        Write-Host "[+] Querying users in SearchBase: $base" -ForegroundColor Cyan
        try {
            $users += Get-ADUser -Filter * -SearchBase $base.Trim() -Properties *
        }
        catch {
            Write-Warning "Failed to query SearchBase '$base': $_"
        }
    }
}
elseif (-not [string]::IsNullOrWhiteSpace($CONFIG.SearchBase)) {
    Write-Host "[+] Querying users in SearchBase: $($CONFIG.SearchBase)" -ForegroundColor Cyan
    try {
        $users = Get-ADUser -Filter * -SearchBase $CONFIG.SearchBase -Properties *
    }
    catch {
        Write-Warning "Failed to query SearchBase '$($CONFIG.SearchBase)': $_"
    }
}
else {
    Write-Host "[+] Querying domain-wide users (Domain Root)..." -ForegroundColor Cyan
    try {
        $users = Get-ADUser -Filter * -Properties *
    }
    catch {
        Write-Error "Failed to query domain users: $_"
        exit 1
    }
}

# Additional Privileged Accounts Domain-Wide
if (-not [string]::IsNullOrWhiteSpace($CONFIG.SearchPrivilege)) {
    Write-Host "[+] Querying additional privileged users in: $($CONFIG.SearchPrivilege)" -ForegroundColor Cyan
    $privNames = @(
        "Domain Admins", "Enterprise Admins", "Schema Admins",
        "Administrators", "Account Operators", "Server Operators",
        "Backup Operators", "Print Operators", "DNSAdmins"
    )

    foreach ($groupName in $privNames) {
        try {
            $group = Get-ADGroup -Filter "Name -eq '$groupName'" -ErrorAction SilentlyContinue
            if ($group) {
                $users += Get-ADUser -SearchBase $CONFIG.SearchPrivilege -LDAPFilter "(memberOf:1.2.840.113556.1.4.1941:=$($group.DistinguishedName))" -Properties *
            }
        }
        catch {}
    }
}

# Remove Duplicate Accounts
$users = $users | Sort-Object SamAccountName -Unique
Write-Host "[+] Total unique accounts found: $($users.Count)" -ForegroundColor Green

# ==============================================================================
# PROCESS USERS & RISK SCORING
# ==============================================================================

$result = @()
$counter = 0
$totalUsers = $users.Count

foreach ($user in $users) {
    $counter++
    if ($totalUsers -gt 0) {
        Write-Progress -Activity "Processing AD Accounts" -Status "Account $counter of $totalUsers ($($user.SamAccountName))" -PercentComplete (($counter / $totalUsers) * 100)
    }

    if (Is-UserInExcludedOU $user.DistinguishedName) {
        continue
    }

    $ou = Get-UserOUPath $user.DistinguishedName

    # Logon & Inactivity
    $lastLogon = Get-TrueLastLogon $user.SamAccountName
    if (-not $lastLogon) { $lastLogon = $user.LastLogonDate }

    $daysSinceLastLogon = if ($lastLogon) {
        (New-TimeSpan -Start $lastLogon -End (Get-Date)).Days
    }
    else { $null }

    # Password Policy
    $passwordLastSet = $user.PasswordLastSet
    $passwordAgeDays = if ($passwordLastSet) {
        (New-TimeSpan -Start $passwordLastSet -End (Get-Date)).Days
    }
    else { $null }

    $passwordExpired = ($passwordAgeDays -ne $null -and $passwordAgeDays -ge $maxPasswordAge)

    # Inactivity Threshold
    $isInactive = ($daysSinceLastLogon -ne $null -and $daysSinceLastLogon -ge $CONFIG.InactiveDays)

    # Group Membership & Privilege Analysis
    $groups = Get-UserGroups $user

    $privGroups = @(
        "Domain Admins", "Enterprise Admins", "Schema Admins",
        "Administrators", "Account Operators", "Server Operators",
        "Backup Operators", "Print Operators", "DNSAdmins"
    )

    $privilegedGroups = $groups | Where-Object { $privGroups -contains $_ }
    $isPrivileged = ($privilegedGroups.Count -gt 0)

    # Account Heuristics
    $isServiceAccount = ($user.Name -match "svc|service|app" -or $user.SamAccountName -match "^svc_|^app_")
    $isExternal = ($user.Description -match "terceiro|externo|vendor|contractor")
    $hasSPN = ($null -ne $user.ServicePrincipalName -and $user.ServicePrincipalName.Count -gt 0)

    # Risk Scoring Logic
    $riskScore = 0
    if ($isInactive) { $riskScore += 30 }
    if ($passwordExpired) { $riskScore += 20 }
    if ($isPrivileged) { $riskScore += 40 }
    if ($hasSPN) { $riskScore += 30 }
    if ($user.PasswordNeverExpires) { $riskScore += 15 }

    # Compliance Status
    $compliant = ($user.Enabled -and -not $isInactive -and -not $passwordExpired)

    $obj = [PSCustomObject]@{
        Environment          = $CONFIG.Environment
        Timestamp            = $timestamp

        Username             = $user.SamAccountName
        Name                 = $user.Name
        Email                = $user.Mail

        EmployeeID           = $user.EmployeeID
        Department           = $user.Department
        Title                = $user.Title
        Company              = $user.Company

        OU                   = $ou
        CanonicalName        = $user.CanonicalName

        Enabled              = $user.Enabled
        LockedOut            = $user.LockedOut

        Groups               = $groups
        GroupCount           = $groups.Count
        PrivilegedGroups     = $privilegedGroups

        isPrivileged         = $isPrivileged
        IsServiceAccount     = $isServiceAccount
        IsExternal           = $isExternal
        HasSPN               = $hasSPN

        PasswordLastSet      = $passwordLastSet
        PasswordAgeDays      = $passwordAgeDays
        PasswordExpired      = $passwordExpired
        PasswordNeverExpires = $user.PasswordNeverExpires

        LastLogon            = $lastLogon
        DaysSinceLastLogon   = $daysSinceLastLogon
        LogonCount           = $user.LogonCount
        BadLogonCount        = $user.BadLogonCount

        IsInactive           = $isInactive
        ComplianceStatus     = $compliant
        RiskScore            = $riskScore

        Created              = $user.WhenCreated
        Modified             = $user.WhenChanged
    }

    $result += $obj
}

Write-Progress -Activity "Processing AD Accounts" -Completed

# ==============================================================================
# SUMMARY & OUTPUT BUILD
# ==============================================================================

$summary = [PSCustomObject]@{
    TotalUsers      = $result.Count
    ActiveUsers     = ($result | Where-Object { $_.Enabled }).Count
    InactiveUsers   = ($result | Where-Object { $_.IsInactive }).Count
    PrivilegedUsers = ($result | Where-Object { $_.IsPrivileged }).Count
    NonCompliant    = ($result | Where-Object { -not $_.ComplianceStatus }).Count
}

$outputData = @{
    environment = $CONFIG.Environment
    timestamp   = $timestamp
    summary     = $summary
    users       = $result
}

Write-Host "----------------------------------------------------------------" -ForegroundColor Gray
Write-Host "Collection Summary:" -ForegroundColor Green
Write-Host "  Total Processed Users : $($summary.TotalUsers)"
Write-Host "  Active Users          : $($summary.ActiveUsers)"
Write-Host "  Inactive Users        : $($summary.InactiveUsers)"
Write-Host "  Privileged Users      : $($summary.PrivilegedUsers)"
Write-Host "  Non-Compliant Accounts: $($summary.NonCompliant)"
Write-Host "----------------------------------------------------------------" -ForegroundColor Gray

# Convert to JSON
$jsonPayload = $outputData | ConvertTo-Json -Depth 6

# Save Local File (if requested)
if (-not [string]::IsNullOrWhiteSpace($CONFIG.OutputFile)) {
    try {
        $jsonPayload | Out-File -FilePath $CONFIG.OutputFile -Encoding utf8 -Force
        Write-Host "[+] Local JSON report saved to: $($CONFIG.OutputFile)" -ForegroundColor Green
    }
    catch {
        Write-Error "Failed to save local JSON file to '$($CONFIG.OutputFile)': $_"
    }
}

# ==============================================================================
# POST TO AD REPORT HUB API
# ==============================================================================

if (-not [string]::IsNullOrWhiteSpace($CONFIG.ApiUrl)) {
    Write-Host "[+] Sending data payload to API: $($CONFIG.ApiUrl)" -ForegroundColor Cyan
    try {
        $headers = @{
            "Content-Type" = "application/json; charset=utf-8"
        }
        if (-not [string]::IsNullOrWhiteSpace($CONFIG.ApiToken)) {
            $headers["X-API-Key"] = $CONFIG.ApiToken
        }

        $response = Invoke-RestMethod -Uri $CONFIG.ApiUrl -Method Post -Body $jsonPayload -Headers $headers -ContentType "application/json; charset=utf-8"
        Write-Host "[✔] API Response: $($response.message)" -ForegroundColor Green
    }
    catch {
        Write-Warning "Failed to post data to API '$($CONFIG.ApiUrl)': $_"
    }
}

Write-Host "[✔] Collection complete." -ForegroundColor Green