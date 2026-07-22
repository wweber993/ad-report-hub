"""
CyberHub — Report AD — Data Manager
Handles loading JSON data files, risk scoring, compliance and stats calculation.
"""

import glob
import json
import logging
import os
import re
from datetime import datetime, timedelta

from dateutil import parser as dateutil_parser

logger = logging.getLogger(__name__)

# ── Privileged groups ──────────────────────────────────────────────
PRIVILEGED_GROUPS = [
    "Domain Admins",
    "Enterprise Admins",
    "Schema Admins",
    "Administrators",
    "Account Operators",
    "Server Operators",
    "Backup Operators",
    "Print Operators",
    "DNSAdmins",
]

_PRIVILEGED_LOWER = {g.lower() for g in PRIVILEGED_GROUPS}


# ── File helpers ───────────────────────────────────────────────────

def _read_json(path, default=None):
    if default is None:
        default = []
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            content = f.read().strip()
            return json.loads(content) if content else default
    except Exception as exc:
        logger.error("Failed to read %s: %s", path, exc)
        return default


def write_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        logger.error("Failed to write %s: %s", path, exc)


# ── Date parsing ───────────────────────────────────────────────────

def _parse_date(value):
    if not value:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000.0)
        if isinstance(value, str):
            if "/Date(" in value:
                ms = int(re.search(r"(\d+)", value).group(1))
                return datetime.fromtimestamp(ms / 1000.0)
            return dateutil_parser.parse(value)
    except Exception:
        pass
    return None


# ── OU extraction ──────────────────────────────────────────────────

def _extract_ou(dn):
    if not dn:
        return "Não Definido"
    if "/" in dn and "," not in dn:
        return dn
    try:
        parts = dn.split(",")
        ou_parts = [p.replace("OU=", "").strip() for p in parts if p.strip().startswith("OU=")]
        return " / ".join(ou_parts) if ou_parts else "Raiz"
    except Exception:
        return str(dn)


# ── OU → display department ───────────────────────────────────────

def _ou_to_department(ou_path: str) -> str:
    """Return the leaf (most specific) OU segment, formatted for display."""
    if not ou_path or ou_path in ("Raiz", "Não Definido"):
        return ou_path or "Não Definido"
    segments = [s.strip() for s in ou_path.replace(" / ", "/").split("/") if s.strip()]
    if not segments:
        return ou_path
    leaf = segments[-1].replace("_", " ")
    return leaf.title()


# ── Risk scoring ───────────────────────────────────────────────────

def _calculate_risk(user: dict) -> dict:
    if user.get("isException"):
        return {"score": 0, "factors": [f"Exceção Aprovada: {user.get('exceptionReason')}"]}

    score = 0
    factors = []

    if user.get("isPrivileged"):
        score += 40
        factors.append("Conta com privilégios administrativos")

    if user.get("LockedOut"):
        score += 30
        factors.append("Conta bloqueada por excesso de erros")

    if not user.get("Enabled"):
        score += 5

    if user.get("PasswordNeverExpires"):
        score += 25
        factors.append("Senha configurada para nunca expirar (Risco de Brute Force)")

    if user.get("PasswordExpired"):
        score += 20
        factors.append("Senha expirada no AD")

    bad_logon = user.get("BadLogonCount", 0) or 0
    if bad_logon > 5:
        score += 20
        factors.append(f"Alto índice de falhas de logon ({bad_logon} tentativas)")
    elif bad_logon > 0:
        score += 5
        factors.append(f"Existem falhas de logon registradas ({bad_logon})")

    logon_days = user.get("DaysSinceLastLogon")
    if logon_days is not None:
        if logon_days > 180:
            score += 25
            factors.append("Inatividade crítica (+180 dias)")
        elif logon_days > 90:
            score += 15
            factors.append(f"Conta inativa há {logon_days} dias")

    json_score = user.get("RiskScore", 0) or 0
    if json_score > score:
        score = json_score
        factors.append("Risco identificado por análise heurística externa")

    final = min(max(score, 0), 100)
    if not factors:
        factors.append("Nenhum fator de risco imediato detectado")

    return {"score": final, "factors": factors}


def _compliance_status(user: dict) -> bool:
    if user.get("isException"):
        return True
    if user.get("ComplianceStatus") is not None:
        return bool(user.get("ComplianceStatus"))
    enabled = user.get("Enabled", False)
    recent_logon = (
        user.get("DaysSinceLastLogon") is not None
        and user["DaysSinceLastLogon"] < 90
    )
    pwd_ok = not user.get("PasswordExpired", False)
    return bool(enabled and recent_logon and pwd_ok)


# ── Load users ─────────────────────────────────────────────────────

def load_all_users(data_dir: str, overrides_path: str) -> list:
    overrides = _read_json(overrides_path, default={})
    all_users = []

    files = glob.glob(os.path.join(data_dir, "ad_users_report_*.json"))
    for file_path in files:
        data = _read_json(file_path, default={})
        users_list = data.get("users", [])
        env_name = data.get("environment", "Desconhecido")

        for u in users_list:
            u["Environment"] = u.get("Environment", env_name)
            u["DisplayName"] = u.get("DisplayName") or u.get("Name") or u.get("Username")
            u["Username"] = u.get("Username", "N/A")
            u["Department"] = u.get("Department") or "Não Definido"

            uname_lower = u["Username"].lower()
            if uname_lower in overrides:
                u["isException"] = True
                u["exceptionReason"] = overrides[uname_lower].get("reason", "Motivo não informado")
                u["exceptionDate"] = overrides[uname_lower].get("date")
                u["exceptionApprovedBy"] = overrides[uname_lower].get("approvedBy", "Sistema")
                u["exceptionApprovalDate"] = overrides[uname_lower].get("approvalDate", "-")
            else:
                u["isException"] = False

            created_dt = _parse_date(u.get("Created") or u.get("AccountCreated"))
            logon_dt   = _parse_date(u.get("LastLogon") or u.get("LastLogonDate"))
            modified_dt = _parse_date(u.get("Modified"))

            u["AccountCreated"] = created_dt.isoformat() if created_dt else None
            u["LastLogonDate"]  = logon_dt.isoformat()   if logon_dt  else "Nunca"
            u["Modified"]       = modified_dt.isoformat() if modified_dt else None

            raw_groups = u.get("Groups") or []
            if isinstance(raw_groups, str):
                groups_list = [g.strip() for g in raw_groups.split() if g.strip()]
            elif isinstance(raw_groups, list):
                groups_list = [str(g).strip() for g in raw_groups if g]
            else:
                groups_list = []

            u["Groups"] = groups_list
            user_groups_lower = [g.lower() for g in groups_list]
            u["isPrivileged"] = (
                u.get("isPrivileged", False)
                or any(g in _PRIVILEGED_LOWER for g in user_groups_lower)
            )

            risk = _calculate_risk(u)
            u["riskScore"]   = risk["score"]
            u["riskFactors"] = risk["factors"]
            u["isCompliant"] = _compliance_status(u)
            u["OU"]          = _extract_ou(u.get("OU") or u.get("DistinguishedName", ""))

            all_users.append({
                "Username":            u.get("Username"),
                "DisplayName":         u.get("DisplayName"),
                "Email":               u.get("Email"),
                "Department":          u.get("Department"),
                "DisplayDepartment":   _ou_to_department(u.get("OU", "")),
                "Title":               u.get("Title"),
                "Environment":         u.get("Environment"),
                "AccountCreated":      u.get("AccountCreated"),
                "LastLogonDate":       u.get("LastLogonDate"),
                "Modified":            u.get("Modified"),
                "riskScore":           u.get("riskScore"),
                "riskFactors":         u.get("riskFactors"),
                "isCompliant":         u.get("isCompliant"),
                "isException":         u.get("isException"),
                "exceptionReason":     u.get("exceptionReason"),
                "exceptionApprovedBy": u.get("exceptionApprovedBy"),
                "exceptionApprovalDate": u.get("exceptionApprovalDate"),
                "isPrivileged":        u["isPrivileged"],
                "OU":                  u.get("OU"),
                "Enabled":             u.get("Enabled"),
                "LockedOut":           u.get("LockedOut"),
                "PasswordNeverExpires": u.get("PasswordNeverExpires"),
                "PasswordAgeDays":     u.get("PasswordAgeDays"),
                "BadLogonCount":       u.get("BadLogonCount"),
                "DaysSinceLastLogon":  u.get("DaysSinceLastLogon"),
                "Groups":              u.get("Groups", []),
            })

    return all_users


# ── Stats calculation ──────────────────────────────────────────────

def calculate_stats(users: list) -> dict:
    if not users:
        return {
            "total": 0, "active": 0, "inactive": 0, "lockedOut": 0,
            "compliant": 0, "nonCompliant": 0, "healthScore": 0,
            "privileged": 0, "highRiskUsers": 0,
            "healthInsights": ["Sem dados."],
            "topDepartments": [], "environments": [],
            "privilegedGroups": PRIVILEGED_GROUPS,
            "creationStats": {"7d": 0, "30d": 0, "60d": 0},
        }

    now = datetime.now()
    active    = [u for u in users if u.get("Enabled")]
    compliant = [u for u in users if u.get("isCompliant")]
    privileged = [u for u in users if u.get("isPrivileged")]
    locked    = sum(1 for u in users if u.get("LockedOut"))

    insights = []
    if locked:
        insights.append(f"{locked} contas bloqueadas.")
    never_expires = sum(1 for u in active if u.get("PasswordNeverExpires"))
    if never_expires:
        insights.append(f"{never_expires} usuários com senha perpétua.")
    exceptions_count = sum(1 for u in users if u.get("isException"))
    if exceptions_count:
        insights.append(f"{exceptions_count} exceções aprovadas.")

    c7 = c30 = c60 = 0
    for u in users:
        c_str = u.get("AccountCreated")
        if c_str:
            try:
                dt = dateutil_parser.parse(c_str).replace(tzinfo=None)
                diff = (now - dt).days
                if diff <= 7:  c7  += 1
                if diff <= 30: c30 += 1
                if diff <= 60: c60 += 1
            except Exception:
                pass

    depts: dict = {}
    for u in [x for x in users if not x.get("isCompliant") or (x.get("riskScore") or 0) > 0]:
        disp = u.get("DisplayDepartment")
        dept = u.get("Department")
        if not disp or disp in ("Não Definido", "Raiz"):
            d = dept if dept and dept not in ("Não Definido", "Raiz") else "Não Definido"
        else:
            d = disp
        depts[d] = depts.get(d, 0) + 1

    top_depts = sorted(depts.items(), key=lambda x: x[1], reverse=True)[:5]

    envs = sorted({u.get("Environment") for u in users if u.get("Environment")})

    avg_risk = (sum(u.get("riskScore", 0) for u in users) / len(users)) if users else 0
    calculated_health = max(0, min(100, round(100 - avg_risk)))

    return {
        "total":          len(users),
        "active":         len(active),
        "inactive":       len(users) - len(active),
        "lockedOut":      locked,
        "compliant":      len(compliant),
        "nonCompliant":   len(users) - len(compliant),
        "privileged":     len(privileged),
        "privilegedGroups": PRIVILEGED_GROUPS,
        "healthScore":    calculated_health,
        "highRiskUsers":  sum(1 for u in users if (u.get("riskScore") or 0) >= 40),
        "healthInsights": insights or ["Nenhum incidente crítico detectado."],
        "environments":   envs,
        "topDepartments": [{"name": k, "count": v} for k, v in top_depts],
        "creationStats":  {"7d": c7, "30d": c30, "60d": c60},
    }


# ── ISO/SOC Compliance ─────────────────────────────────────────────

def calculate_iso_soc_compliance(users: list) -> dict:
    """Map AD user attributes to ISO 27001 and SOC 2 Type II controls."""
    total = len(users)
    
    if not total:
        return {
            "summary": {
                "iso27001": {"score": 0, "status": "N/A"},
                "soc2": {"score": 0, "status": "N/A"}
            },
            "controls": []
        }

    def _compliance_pct(violations: list, universe: list) -> int:
        n = len(universe)
        if not n:
            return 100
        return round((n - len(violations)) / n * 100)

    def _status(violations: list, warn_threshold: int = 3) -> str:
        if not violations:
            return "PASS"
        return "WARN" if len(violations) <= warn_threshold else "FAIL"

    def _user_list(lst: list) -> list:
        return [
            {
                "name":     u.get("DisplayName") or u.get("Username"),
                "username": u.get("Username"),
                "dept":     u.get("Department", "-"),
                "env":      u.get("Environment", "-"),
            }
            for u in lst[:15]
        ]

    enabled_users   = [u for u in users if u.get("Enabled")]
    disabled_users  = [u for u in users if not u.get("Enabled")]
    privileged      = [u for u in users if u.get("isPrivileged") and not u.get("isException")]

    inactive_enabled = [
        u for u in enabled_users
        if u.get("DaysSinceLastLogon") is not None
        and u["DaysSinceLastLogon"] > 90
        and not u.get("isException")
    ]

    cis_inactive_enabled = [
        u for u in enabled_users
        if u.get("DaysSinceLastLogon") is not None
        and u["DaysSinceLastLogon"] > 45
        and not u.get("isException")
    ]

    privileged_inactive = [
        u for u in privileged
        if u.get("DaysSinceLastLogon") is not None
        and u["DaysSinceLastLogon"] > 30
    ]

    disabled_privileged = [
        u for u in disabled_users if u.get("isPrivileged")
    ]

    pwd_never_expires = [
        u for u in enabled_users
        if u.get("PasswordNeverExpires") and not u.get("isException")
    ]

    pwd_expired = [
        u for u in enabled_users
        if u.get("PasswordExpired") and not u.get("isException")
    ]

    high_bad_logon = [
        u for u in enabled_users
        if (u.get("BadLogonCount") or 0) > 5 and not u.get("isException")
    ]

    locked_out = [u for u in users if u.get("LockedOut") and not u.get("isException")]

    built_in = [
        u for u in enabled_users
        if u.get("Username", "").lower() in ("administrator", "guest", "krbtgt") and not u.get("isException")
    ]

    spn_accounts = [
        u for u in enabled_users
        if u.get("HasSPN") and not u.get("isException")
    ]

    controls = [
        # ── ISO 27001 ──────────────────────────────────────────────
        {
            "id": "A.9.2.1",
            "framework": "ISO 27001",
            "domain": "Controle de Acesso",
            "title": "Registro e Cancelamento de Usuários",
            "description": "Contas ativas sem logon há mais de 90 dias devem ser revisadas e desativadas para evitar acessos não autorizados.",
            "rule": "Contas habilitadas com inatividade > 90 dias",
            "status": _status(inactive_enabled, warn_threshold=5),
            "score": _compliance_pct(inactive_enabled, enabled_users),
            "violations": _user_list(inactive_enabled),
            "count": len(inactive_enabled),
            "recommendation": "Desative ou remova contas que não foram utilizadas nos últimos 90 dias. Implemente um processo de revisão periódica de acessos (User Access Review) com frequência semestral.",
        },
        {
            "id": "A.9.2.3",
            "framework": "ISO 27001",
            "domain": "Controle de Acesso",
            "title": "Gerenciamento de Acessos Privilegiados",
            "description": "O número de contas com privilégios administrativos deve ser mínimo, documentado e justificado pelo negócio.",
            "rule": "Contas com grupos de privilégios administrativos",
            "status": _status(privileged, warn_threshold=3),
            "score": 100 if not privileged else max(0, 100 - len(privileged) * 8),
            "violations": _user_list(privileged),
            "count": len(privileged),
            "recommendation": "Aplique o princípio do menor privilégio. Crie uma matrix de papéis (RBAC) e documente toda concessão de acesso privilegiado com aprovação formal.",
        },
        {
            "id": "A.9.2.5",
            "framework": "ISO 27001",
            "domain": "Revisão de Acesso",
            "title": "Revisão de Direitos de Acesso",
            "description": "Contas com privilégios administrativos sem utilização recente indicam falha no ciclo de revisão de acessos.",
            "rule": "Administradores sem logon há mais de 30 dias",
            "status": _status(privileged_inactive, warn_threshold=1),
            "score": _compliance_pct(privileged_inactive, privileged) if privileged else 100,
            "violations": _user_list(privileged_inactive),
            "count": len(privileged_inactive),
            "recommendation": "Realize revisão mensal de contas administrativas. Suspenda o acesso privilegiado de contas sem atividade há 30+ dias até nova justificativa formal.",
        },
        {
            "id": "A.9.2.6",
            "framework": "ISO 27001",
            "domain": "Controle de Acesso",
            "title": "Remoção ou Ajuste de Direitos de Acesso",
            "description": "Contas desativadas não devem manter associação a grupos privilegiados (risco de reativação indevida).",
            "rule": "Contas desativadas ainda associadas a grupos privilegiados",
            "status": _status(disabled_privileged, warn_threshold=0),
            "score": _compliance_pct(disabled_privileged, disabled_users) if disabled_users else 100,
            "violations": _user_list(disabled_privileged),
            "count": len(disabled_privileged),
            "recommendation": "Ao desativar uma conta, remova imediatamente todos os grupos privilegiados. Automatize este controle no processo de offboarding via script PowerShell ou GPO.",
        },
        {
            "id": "A.9.3.1",
            "framework": "ISO 27001",
            "domain": "Autenticação",
            "title": "Uso de Informações de Autenticação Secreta",
            "description": "Senhas devem ter expiração configurada. Senhas permanentes aumentam o risco de comprometimento por brute force.",
            "rule": "Contas ativas com senha configurada para nunca expirar",
            "status": _status(pwd_never_expires, warn_threshold=3),
            "score": _compliance_pct(pwd_never_expires, enabled_users),
            "violations": _user_list(pwd_never_expires),
            "count": len(pwd_never_expires),
            "recommendation": "Configure políticas de expiração de senha via GPO (máx. 90 dias). Contas de serviço com senha permanente devem ser documentadas e aprovadas formalmente.",
        },
        {
            "id": "A.9.4.3",
            "framework": "ISO 27001",
            "domain": "Autenticação",
            "title": "Sistema de Gerenciamento de Senhas",
            "description": "Senhas expiradas em contas ativas indicam falha no ciclo de gestão de credenciais e bloqueio operacional.",
            "rule": "Contas ativas com senha expirada",
            "status": _status(pwd_expired, warn_threshold=5),
            "score": _compliance_pct(pwd_expired, enabled_users),
            "violations": _user_list(pwd_expired),
            "count": len(pwd_expired),
            "recommendation": "Force a troca de senha em contas expiradas. Implemente notificações proativas de expiração (15, 7 e 1 dia antes). Configure Fine-Grained Password Policies.",
        },
        # ── SOC 2 Type II ──────────────────────────────────────────
        {
            "id": "CC6.1",
            "framework": "SOC 2",
            "domain": "Controle de Acesso Lógico",
            "title": "Controles de Acesso Lógico",
            "description": "A entidade implementa controles lógicos para proteger contra ameaças externas e internas. Alto índice de falhas de logon pode indicar ataque de força bruta.",
            "rule": "Contas com mais de 5 falhas de logon consecutivas",
            "status": _status(high_bad_logon, warn_threshold=3),
            "score": _compliance_pct(high_bad_logon, users),
            "violations": _user_list(high_bad_logon),
            "count": len(high_bad_logon),
            "recommendation": "Configure Account Lockout Policy (ex: bloqueio após 5 tentativas). Investigue imediatamente contas com alto BadLogonCount. Integre alertas com SIEM.",
        },
        {
            "id": "CC6.2",
            "framework": "SOC 2",
            "domain": "Autenticação",
            "title": "Autenticação — Política de Senhas",
            "description": "Credenciais de acesso devem atender requisitos mínimos de segurança, incluindo expiração e complexidade.",
            "rule": "Usuários ativos com senha permanente (PasswordNeverExpires)",
            "status": _status(pwd_never_expires, warn_threshold=3),
            "score": _compliance_pct(pwd_never_expires, enabled_users),
            "violations": _user_list(pwd_never_expires),
            "count": len(pwd_never_expires),
            "recommendation": "Implemente política de rotação de senhas via GPO. Para sistemas críticos, exija MFA (Microsoft Authenticator, FIDO2). Documente exceções com aprovação formal.",
        },
        {
            "id": "CC6.3",
            "framework": "SOC 2",
            "domain": "Controle de Acesso Lógico",
            "title": "Revogação de Acesso",
            "description": "Acessos de usuários inativos ou desligados devem ser revogados prontamente para evitar uso indevido.",
            "rule": "Contas habilitadas sem logon há 90+ dias",
            "status": _status(inactive_enabled, warn_threshold=5),
            "score": _compliance_pct(inactive_enabled, enabled_users),
            "violations": _user_list(inactive_enabled),
            "count": len(inactive_enabled),
            "recommendation": "Implemente revisão trimestral de acessos (User Access Review). Configure scripts automáticos para desativar contas sem logon após 60 dias.",
        },
        {
            "id": "CC6.6",
            "framework": "SOC 2",
            "domain": "Acesso Privilegiado",
            "title": "Restrição de Acesso Privilegiado",
            "description": "O acesso privilegiado deve ser limitado ao mínimo necessário para execução das funções (Least Privilege Principle).",
            "rule": "Total de contas com grupos administrativos",
            "status": _status(privileged, warn_threshold=3),
            "score": 100 if not privileged else max(0, 100 - len(privileged) * 8),
            "violations": _user_list(privileged),
            "count": len(privileged),
            "recommendation": "Implemente RBAC (Role-Based Access Control). Exija contas separadas para tarefas administrativas (admin account x user account). Revise trimestralmente.",
        },
        {
            "id": "CC7.2",
            "framework": "SOC 2",
            "domain": "Monitoramento",
            "title": "Monitoramento de Ameaças ao Sistema",
            "description": "Contas bloqueadas e anomalias de autenticação devem ser monitoradas e investigadas ativamente.",
            "rule": "Contas atualmente bloqueadas no Active Directory",
            "status": _status(locked_out, warn_threshold=2),
            "score": _compliance_pct(locked_out, users),
            "violations": _user_list(locked_out),
            "count": len(locked_out),
            "recommendation": "Configure alertas em tempo real para bloqueios de contas. Investigue a causa antes de desbloquear. Integre logs do AD com SIEM para correlação de eventos.",
        },
        # ── CIS Controls v8.1 ──────────────────────────────────────
        {
            "id": "CIS 5.3",
            "framework": "CIS Controls",
            "domain": "Account Management",
            "title": "Desativar Contas Dormentes",
            "description": "Desative ou remova quaisquer contas inativas por um período superior a 45 dias, a fim de minimizar o vetor de ataque em credenciais abandonadas.",
            "rule": "Contas habilitadas sem logon há mais de 45 dias",
            "status": _status(cis_inactive_enabled, warn_threshold=2),
            "score": _compliance_pct(cis_inactive_enabled, enabled_users),
            "violations": _user_list(cis_inactive_enabled),
            "count": len(cis_inactive_enabled),
            "recommendation": "Programe um script para desativar automaticamente contas sem login há 45 dias. Documente exceções para serviços de long-running batch jobs.",
        },
        {
            "id": "CIS 5.2",
            "framework": "CIS Controls",
            "domain": "Account Management",
            "title": "Uso de Senhas Únicas e Seguras",
            "description": "Exigir a rotação e uso de credenciais seguras, desencorajando contas que possuem flag de 'PasswordNeverExpires' configurada.",
            "rule": "Usuários com senha permanente (PasswordNeverExpires)",
            "status": _status(pwd_never_expires, warn_threshold=0),
            "score": _compliance_pct(pwd_never_expires, enabled_users),
            "violations": _user_list(pwd_never_expires),
            "count": len(pwd_never_expires),
            "recommendation": "Remova a flag 'Senha nunca expira' de contas ativas. Implemente políticas baseadas em Fine-Grained Passwords para credenciais de serviço, rotacionando anualmente.",
        },
        {
            "id": "CIS 6.2",
            "framework": "CIS Controls",
            "domain": "Access Control Management",
            "title": "Revogar Acessos Pós-Desligamento",
            "description": "Revogar rapidamente privilégios assim que o funcionário for desligado. Contas desativadas não podem manter acessos de administradores.",
            "rule": "Contas desativadas com grupos de privilégio",
            "status": _status(disabled_privileged, warn_threshold=0),
            "score": _compliance_pct(disabled_privileged, disabled_users) if disabled_users else 100,
            "violations": _user_list(disabled_privileged),
            "count": len(disabled_privileged),
            "recommendation": "Certifique-se de que o processo de offboarding remove todos os grupos dos usuários desativados (ou os mova para uma OU restrita sem permissões).",
        },
        # ── SOC 2 Type II Adicional ──────────────────────────────────────────────
        {
            "id": "CC6.1",
            "framework": "SOC 2",
            "domain": "Logical Access",
            "title": "Contas Padrão Desativadas",
            "description": "Contas built-in como Administrator e Guest devem ser desativadas ou ter nomes alterados (renamed) para evitar ataques baseados em padrões conhecidos.",
            "rule": "Contas Built-in (Administrator/Guest) ativas",
            "status": _status(built_in, warn_threshold=0),
            "score": _compliance_pct(built_in, enabled_users),
            "violations": _user_list(built_in),
            "count": len(built_in),
            "recommendation": "Desative as contas Guest e Administrator. Utilize contas administrativas nomeadas para garantir auditoria adequada (Accountability).",
        },
        {
            "id": "CC6.6",
            "framework": "SOC 2",
            "domain": "Security Measures",
            "title": "Mitigação de Ataques de Força Bruta",
            "description": "Monitorar e agir sobre contas que excedem os limites de falha de login (Brute force / Password spraying).",
            "rule": "Contas ativas com mais de 5 Bad Logons recentes",
            "status": _status(high_bad_logon, warn_threshold=3),
            "score": _compliance_pct(high_bad_logon, enabled_users),
            "violations": _user_list(high_bad_logon),
            "count": len(high_bad_logon),
            "recommendation": "Investigue os logs do Domain Controller para identificar a origem das falhas de login. Verifique se há senhas salvas em cache ou tentativas de força bruta.",
        },
        {
            "id": "CIS 5.1",
            "framework": "CIS Controls",
            "domain": "Account Management",
            "title": "Inventário de Contas de Serviço (SPN)",
            "description": "Contas com Service Principal Names (SPN) configurados são alvos de Kerberoasting. Devem possuir senhas complexas de 25+ caracteres.",
            "rule": "Contas com SPN atrelado",
            "status": "WARN" if spn_accounts else "PASS",
            "score": 80 if spn_accounts else 100,
            "violations": _user_list(spn_accounts),
            "count": len(spn_accounts),
            "recommendation": "Revise todas as contas de serviço. Certifique-se de que possuem senhas complexas. Idealmente utilize Group Managed Service Accounts (gMSA).",
        }
    ]

    pass_count    = sum(1 for c in controls if c["status"] == "PASS")
    fail_count    = sum(1 for c in controls if c["status"] == "FAIL")
    warn_count    = sum(1 for c in controls if c["status"] == "WARN")
    overall_score = round(sum(c["score"] for c in controls) / len(controls)) if controls else 0

    return {
        "controls":   controls,
        "totalUsers": total,
        "summary": {
            "total":        len(controls),
            "pass":         pass_count,
            "fail":         fail_count,
            "warn":         warn_count,
            "overallScore": overall_score,
        },
    }


# ── Snapshot / History ──────────────────────────────────────────────────────

def _snapshot_dir(data_dir: str) -> str:
    return os.path.join(data_dir, "snapshots")


def write_snapshot(data_dir: str, environment: str, stats: dict, compliance_summary: dict) -> str:
    """
    Persist a compact metrics snapshot for the given ingest event.
    Stores in data_dir/snapshots/<env>/<YYYYMMDD_HHMMSS>.json
    Returns the path written.
    """
    env_slug = environment.replace(" ", "_").lower()
    snap_dir = os.path.join(_snapshot_dir(data_dir), env_slug)
    os.makedirs(snap_dir, exist_ok=True)

    ts = datetime.now()
    filename = ts.strftime("%Y%m%d_%H%M%S") + ".json"
    path = os.path.join(snap_dir, filename)

    payload = {
        "timestamp": ts.isoformat(),
        "environment": environment,
        "stats": {
            "total":        stats.get("total", 0),
            "active":       stats.get("active", 0),
            "inactive":     stats.get("inactive", 0),
            "lockedOut":    stats.get("lockedOut", 0),
            "nonCompliant": stats.get("nonCompliant", 0),
            "privileged":   stats.get("privileged", 0),
            "highRiskUsers": stats.get("highRiskUsers", 0),
            "healthScore":  stats.get("healthScore", 0),
        },
        "compliance": compliance_summary,
    }
    write_json(path, payload)
    logger.info("Snapshot written: %s", path)
    return path


def purge_old_snapshots(data_dir: str, retention_days: int = 90) -> int:
    """
    Delete snapshots older than retention_days. Returns count deleted.
    """
    cutoff = datetime.now() - timedelta(days=retention_days)
    snap_base = _snapshot_dir(data_dir)
    deleted = 0
    for path in glob.glob(os.path.join(snap_base, "**", "*.json"), recursive=True):
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(path))
            if mtime < cutoff:
                os.remove(path)
                deleted += 1
        except Exception as exc:
            logger.warning("Could not purge snapshot %s: %s", path, exc)
    if deleted:
        logger.info("Purged %d old snapshots (retention=%d days)", deleted, retention_days)
    return deleted


def load_history_snapshots(data_dir: str, environment: str = None, days: int = 30) -> list:
    """
    Load compact snapshots for the given environment (or all envs) within the last N days.
    Returns list of snapshot dicts sorted by timestamp ascending.
    """
    snap_base = _snapshot_dir(data_dir)
    cutoff = datetime.now() - timedelta(days=days)

    if environment:
        env_slug = environment.replace(" ", "_").lower()
        pattern = os.path.join(snap_base, env_slug, "*.json")
    else:
        pattern = os.path.join(snap_base, "**", "*.json")

    results = []
    for path in glob.glob(pattern, recursive=True):
        try:
            data = _read_json(path, default={})
            if not data:
                continue
            ts_str = data.get("timestamp", "")
            ts = datetime.fromisoformat(ts_str) if ts_str else None
            if ts and ts >= cutoff:
                results.append(data)
        except Exception as exc:
            logger.warning("Could not load snapshot %s: %s", path, exc)

    results.sort(key=lambda x: x.get("timestamp", ""))
    return results
