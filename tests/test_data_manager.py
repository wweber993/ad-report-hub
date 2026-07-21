import pytest
from app.modules.report_ad.utils.data_manager import _calculate_risk, calculate_iso_soc_compliance, _compliance_status

def test_calculate_risk_exception():
    """Testa se contas marcadas como exceção retornam risco zero."""
    user = {"isException": True, "exceptionReason": "Serviço legado"}
    result = _calculate_risk(user)
    assert result["score"] == 0
    assert "Exceção Aprovada" in result["factors"][0]


def test_calculate_risk_privileged():
    """Testa o incremento de risco por privilégio."""
    user = {"isPrivileged": True}
    result = _calculate_risk(user)
    assert result["score"] >= 40
    assert any("privilégios" in factor for factor in result["factors"])


def test_calculate_risk_locked_out():
    """Testa o incremento de risco por bloqueio."""
    user = {"LockedOut": True}
    result = _calculate_risk(user)
    assert result["score"] >= 30
    assert any("bloqueada" in factor for factor in result["factors"])


def test_calculate_risk_password_never_expires():
    """Testa incremento de risco por senha não expirável."""
    user = {"PasswordNeverExpires": True}
    result = _calculate_risk(user)
    assert result["score"] >= 25
    assert any("nunca expirar" in factor for factor in result["factors"])


def test_calculate_risk_bad_logon():
    """Testa incremento por falhas sucessivas de logon."""
    user = {"BadLogonCount": 6}
    result = _calculate_risk(user)
    assert result["score"] >= 20
    assert any("Alto índice" in factor for factor in result["factors"])


def test_calculate_risk_inactivity():
    """Testa inatividade."""
    user = {"DaysSinceLastLogon": 190}
    result = _calculate_risk(user)
    assert result["score"] >= 25
    assert any("Inatividade crítica" in factor for factor in result["factors"])


def test_compliance_status():
    """Testa a avaliação individual de compliance de um usuário."""
    # Exceção é sempre compliant
    assert _compliance_status({"isException": True}) is True

    # Tudo em ordem: habilitado, recente, senha OK
    assert _compliance_status({
        "Enabled": True,
        "DaysSinceLastLogon": 10,
        "PasswordExpired": False
    }) is True

    # Falha inatividade
    assert _compliance_status({
        "Enabled": True,
        "DaysSinceLastLogon": 100,
        "PasswordExpired": False
    }) is False


def test_calculate_iso_soc_compliance_empty():
    """Testa o relatório ISO/SOC sem usuários."""
    result = calculate_iso_soc_compliance([])
    summary = result["summary"]
    controls = result["controls"]
    assert summary["overallScore"] == 100
    assert summary["pass"] > 0
    assert len(controls) > 0


def test_calculate_iso_soc_compliance_violations():
    """Testa o relatório de compliance com usuários violando regras."""
    users = [
        {
            "Username": "admin_inativo",
            "Enabled": True,
            "isPrivileged": True,
            "DaysSinceLastLogon": 40,
            "isException": False
        },
        {
            "Username": "senha_nunca_expira",
            "Enabled": True,
            "PasswordNeverExpires": True,
            "isException": False
        }
    ]
    result = calculate_iso_soc_compliance(users)
    summary = result["summary"]
    controls = result["controls"]
    
    # Busca pelo controle de administradores inativos (A.9.2.5)
    ctrl_admin = next((c for c in controls if c["id"] == "A.9.2.5"), None)
    assert ctrl_admin is not None
    assert ctrl_admin["count"] == 1
    assert "admin_inativo" == ctrl_admin["violations"][0]["username"]

    # Busca pelo controle de senha nunca expira (A.9.3.1)
    ctrl_pwd = next((c for c in controls if c["id"] == "A.9.3.1"), None)
    assert ctrl_pwd is not None
    assert ctrl_pwd["count"] == 1
    assert "senha_nunca_expira" == ctrl_pwd["violations"][0]["username"]

    # O score geral não pode ser 100% com violações ativas
    assert summary["overallScore"] < 100
