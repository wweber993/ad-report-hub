# ==============================================================================
# CONFIGURATION
# Edit these values to match your environment before running or scheduling.
# ==============================================================================

$CONFIG = @{
    # Defini um nome claro para o ambiente de testes
    Environment = "Lab_Corp"

    # Aponta a busca principal APENAS para a OU de laboratório que criamos
    SearchBase = "OU=Corp_Lab,DC=williamweber,DC=com,DC=br"

    # Deixamos vazio, pois já estamos usando o SearchBase acima
    SearchBases = @()

    # Apontamos para a raiz do domínio para que ele consiga ler o grupo "Domain Admins"
    # e encontrar aquele "admin.oculto" que colocamos lá no script anterior.
    SearchPrivilege = "DC=williamweber,DC=com,DC=br"

    # Sem exclusões necessárias para este laboratório
    ExcludedOUs = @()

    InactiveDays = 60
    PasswordMaxAgeDays = 60

    UseAutoDC = $true
    DomainControllers = @()

    # O IP e porta do seu AD Report Hub (ajuste se o IP da máquina for outro)
    ApiUrl = "http://192.168.10.122:8090/ad/api/ingest"
    ApiToken = "U5I=Osq5TAW(L5D+"

    # Adicionei um caminho local para você poder ver o arquivo gerado e validar 
    # os dados antes mesmo de olhar no dashboard da API.
    OutputFile = "C:\ADReportHub_Resultado_Lab.json"
}


# ==============================================================================
# PREREQUISITES & MODULE VERIFICATION
# ==============================================================================

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "         AD Report Hub — Active Directory Data Collector        " -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

if (-not (Get-Module -ListAvailable -Name ActiveDirectory)) {
    Write-Error "O módulo PowerShell ActiveDirectory (RSAT) não está instalado neste sistema."
    Write-Host "Por favor instale o Remote Server Administration Tools (RSAT) ou execute em um servidor ingressado no Domínio." -ForegroundColor Yellow
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
        Write-Host "[+] Descobrindo Controladores de Domínio automaticamente..." -ForegroundColor Green
        $discoveredDCs = (Get-ADDomainController -Filter *).HostName
    }
    catch {
        Write-Warning "Não foi possível descobrir Controladores de Domínio: $_"
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
    Write-Host "[+] Idade Máxima da Política de Senha Padrão do Domínio: $maxPasswordAge dias" -ForegroundColor Green
}
catch {
    $maxPasswordAge = [int]$CONFIG.PasswordMaxAgeDays
    Write-Host "[!] Não foi possível obter a política de senha. Usando fallback: $maxPasswordAge dias" -ForegroundColor Yellow
}

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

function Get-UserOUPath {
    param ([string]$dn)

    # O @() força o resultado a ser um Array, mesmo que seja vazio
    $ous = @(
        ($dn -split ',') |
        Where-Object { $_ -like 'OU=*' } |
        ForEach-Object { $_ -replace '^OU=' }
    )

    if ($ous.Count -gt 0) {
        [array]::Reverse($ous)
        return ($ous -join '/')
    }
    
    # Se não houver OU (ex: CN=Users), retorna um valor padrão
    return "Builtin/Containers"
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
        Write-Host "[+] Consultando usuários na SearchBase: $base" -ForegroundColor Cyan
        try {
            $users += Get-ADUser -Filter * -SearchBase $base.Trim() -Properties *
        }
        catch {
            Write-Warning "Falha ao consultar SearchBase '$base': $_"
        }
    }
}
elseif (-not [string]::IsNullOrWhiteSpace($CONFIG.SearchBase)) {
    Write-Host "[+] Consultando usuários na SearchBase: $($CONFIG.SearchBase)" -ForegroundColor Cyan
    try {
        $users = Get-ADUser -Filter * -SearchBase $CONFIG.SearchBase -Properties *
    }
    catch {
        Write-Warning "Falha ao consultar SearchBase '$($CONFIG.SearchBase)': $_"
    }
}
else {
    Write-Host "[+] Consultando usuários em todo o domínio (Raiz do Domínio)..." -ForegroundColor Cyan
    try {
        $users = Get-ADUser -Filter * -Properties *
    }
    catch {
        Write-Error "Falha ao consultar usuários do domínio: $_"
        exit 1
    }
}

# Additional Privileged Accounts Domain-Wide
if (-not [string]::IsNullOrWhiteSpace($CONFIG.SearchPrivilege)) {
    Write-Host "[+] Consultando usuários privilegiados adicionais em: $($CONFIG.SearchPrivilege)" -ForegroundColor Cyan
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
Write-Host "[+] Total de contas únicas encontradas: $($users.Count)" -ForegroundColor Green

# ==============================================================================
# PROCESS USERS & RISK SCORING
# ==============================================================================

$result = @()
$counter = 0
$totalUsers = $users.Count

foreach ($user in $users) {
    $counter++
    if ($totalUsers -gt 0) {
        Write-Progress -Activity "Processando Contas do AD" -Status "Conta $counter de $totalUsers ($($user.SamAccountName))" -PercentComplete (($counter / $totalUsers) * 100)
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

Write-Progress -Activity "Processando Contas do AD" -Completed

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
Write-Host "Resumo da Coleta:" -ForegroundColor Green
Write-Host "  Total de Usuários Processados : $($summary.TotalUsers)"
Write-Host "  Usuários Ativos               : $($summary.ActiveUsers)"
Write-Host "  Usuários Inativos             : $($summary.InactiveUsers)"
Write-Host "  Usuários Privilegiados        : $($summary.PrivilegedUsers)"
Write-Host "  Contas Não-Conformes          : $($summary.NonCompliant)"
Write-Host "----------------------------------------------------------------" -ForegroundColor Gray

# Convert to JSON
$jsonPayload = $outputData | ConvertTo-Json -Depth 6

# Save Local File (if requested)
if (-not [string]::IsNullOrWhiteSpace($CONFIG.OutputFile)) {
    try {
        $jsonPayload | Out-File -FilePath $CONFIG.OutputFile -Encoding utf8 -Force
        Write-Host "[+] Relatório JSON local salvo em: $($CONFIG.OutputFile)" -ForegroundColor Green
    }
    catch {
        Write-Error "Falha ao salvar relatório JSON local em '$($CONFIG.OutputFile)': $_"
    }
}

# ==============================================================================
# POST TO AD REPORT HUB API
# ==============================================================================

if (-not [string]::IsNullOrWhiteSpace($CONFIG.ApiUrl)) {
    Write-Host "[+] Enviando carga de dados para a API: $($CONFIG.ApiUrl)" -ForegroundColor Cyan
    try {
        $headers = @{
            "Content-Type" = "application/json; charset=utf-8"
        }
        if (-not [string]::IsNullOrWhiteSpace($CONFIG.ApiToken)) {
            $headers["X-API-Key"] = $CONFIG.ApiToken
        }

        $response = Invoke-RestMethod -Uri $CONFIG.ApiUrl -Method Post -Body $jsonPayload -Headers $headers -ContentType "application/json; charset=utf-8"
        Write-Host "[✔] Resposta da API: $($response.message)" -ForegroundColor Green
    }
    catch {
        Write-Error "Falha ao enviar dados para a API do AD Report Hub em '$($CONFIG.ApiUrl)': $_"
    }
}

Write-Host "[✔] Coleta concluída." -ForegroundColor Green