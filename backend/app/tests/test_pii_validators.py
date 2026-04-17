"""Testes de regressão do detector de PII.

Cobre `IngestionService._valid_cpf/_valid_cnpj/_valid_luhn/_detect_pii`.
Gate para impedir regressão do bug de 2026-04-17 em que o regex de CNPJ
dava falso-positivo em runs de 14 dígitos contíguos em bytes de PDF
(xref tables, object IDs etc.), causando quarentena espúria do
questionário técnico preenchido.
"""
import pytest

from app.services.ingestion_service import IngestionService

pytestmark = pytest.mark.unit


# ─── CPF (mod-11) ────────────────────────────────────────────────────

# CPFs reais de cadastros públicos de teste
VALID_CPFS = ["11144477735", "12345678909", "52998224725"]
INVALID_CPFS = [
    "11144477736",   # último dígito trocado
    "12345678900",   # check digits errados
    "00000000000",   # todos iguais (rejeitado por convenção)
    "11111111111",
    "1234567890",    # 10 dígitos
    "111444777351",  # 12 dígitos
]


@pytest.mark.parametrize("cpf", VALID_CPFS)
def test_valid_cpf_accepts_real_numbers(cpf):
    assert IngestionService._valid_cpf(cpf) is True


@pytest.mark.parametrize("cpf", INVALID_CPFS)
def test_valid_cpf_rejects_bad_numbers(cpf):
    assert IngestionService._valid_cpf(cpf) is False


# ─── CNPJ (mod-11) ───────────────────────────────────────────────────

VALID_CNPJS = ["11222333000181", "04252011000110"]
INVALID_CNPJS = [
    "11222333000182",   # DV errado
    "00000000000000",   # todos zeros
    "99999999999999",   # todos 9s
    "1122233300018",    # 13 dígitos
    "112223330001811",  # 15 dígitos
]


@pytest.mark.parametrize("cnpj", VALID_CNPJS)
def test_valid_cnpj_accepts_real_numbers(cnpj):
    assert IngestionService._valid_cnpj(cnpj) is True


@pytest.mark.parametrize("cnpj", INVALID_CNPJS)
def test_valid_cnpj_rejects_bad_numbers(cnpj):
    assert IngestionService._valid_cnpj(cnpj) is False


# ─── Luhn (cartão de crédito) ────────────────────────────────────────

VALID_CARDS = [
    "4532015112830366",    # Visa test
    "5555555555554444",    # Mastercard test
    "378282246310005",     # Amex test (15 dígitos)
]
INVALID_CARDS = [
    "1234567812345678",
    "0000000000000000",
    "4532015112830367",    # Luhn errado
    "123",                 # muito curto
    "12345678901234567890",  # 20 dígitos (fora do range 13-19)
]


@pytest.mark.parametrize("card", VALID_CARDS)
def test_valid_luhn_accepts_test_cards(card):
    assert IngestionService._valid_luhn(card) is True


@pytest.mark.parametrize("card", INVALID_CARDS)
def test_valid_luhn_rejects_bad_numbers(card):
    assert IngestionService._valid_luhn(card) is False


# ─── _detect_pii: texto puro ─────────────────────────────────────────

def test_detect_pii_finds_valid_cpf_in_text():
    text = "Meu CPF é 111.444.777-35 ok?"
    detected, fields = IngestionService._detect_pii(text.encode("utf-8"), "markdown")
    assert detected is True
    assert "cpf" in fields


def test_detect_pii_finds_valid_cnpj_in_text():
    text = "CNPJ: 11.222.333/0001-81"
    detected, fields = IngestionService._detect_pii(text.encode("utf-8"), "markdown")
    assert detected is True
    assert "cnpj" in fields


def test_detect_pii_finds_gmail_email():
    text = "Entre em contato: foo@gmail.com"
    detected, fields = IngestionService._detect_pii(text.encode("utf-8"), "markdown")
    assert detected is True
    assert "email_pessoal" in fields


# ─── _detect_pii: regressão de falso-positivos ───────────────────────

def test_detect_pii_does_not_flag_random_14_digit_run():
    """Regressão: runs de 14 dígitos aleatórios (xref de PDF, IDs etc.)
    não podem ser flagados como CNPJ."""
    # 14 dígitos que NÃO passam pelo DV
    text = "00012345678901234 e 99988877766655 fim"
    detected, fields = IngestionService._detect_pii(text.encode("utf-8"), "markdown")
    assert "cnpj" not in fields


def test_detect_pii_does_not_flag_random_11_digit_run():
    """Regressão: runs de 11 dígitos aleatórios não podem virar CPF."""
    text = "Identificador interno: 12345678900 (não é CPF)"
    detected, fields = IngestionService._detect_pii(text.encode("utf-8"), "markdown")
    assert "cpf" not in fields


def test_detect_pii_does_not_flag_random_16_digit_run():
    """Regressão: 16 dígitos sem Luhn válido não podem virar cartão."""
    text = "Ref: 1234567812345678"
    detected, fields = IngestionService._detect_pii(text.encode("utf-8"), "markdown")
    assert "cartao_credito" not in fields


def test_detect_pii_skips_image_and_spreadsheet_types():
    """Tipos binários declarados não devem ser escaneados."""
    text = "CPF 111.444.777-35"
    assert IngestionService._detect_pii(text.encode(), "image") == (False, [])
    assert IngestionService._detect_pii(text.encode(), "spreadsheet") == (False, [])


def test_detect_pii_handles_non_utf8_bytes():
    """Bytes inválidos de UTF-8 não podem causar exception."""
    bad_bytes = b"\xff\xfe\x00\x01" * 100
    detected, fields = IngestionService._detect_pii(bad_bytes, "pdf")
    # Não deve estourar — retorna algo coerente
    assert isinstance(detected, bool)
    assert isinstance(fields, list)


# ─── _detect_pii: fixture de PDF real ────────────────────────────────

def test_detect_pii_does_not_flag_empty_questionnaire_pdf():
    """Regressão crítica: o PDF gerado por `generate_pdf` sem
    preenchimento NÃO pode ser flagado como PII.

    Bug de 2026-04-17: o detector flagava `cnpj` nos bytes binários
    do PDF (xref/object IDs/stream lengths têm corridas de 14 dígitos),
    quarentenando o doc e bloqueando o Arguidor.
    """
    from app.services.questionnaire_pdf_service import generate_pdf

    pdf_bytes = generate_pdf(
        project_name="Teste Regressão",
        deliverable_type="new_system",
        project_slug="teste-regressao",
    )
    detected, fields = IngestionService._detect_pii(pdf_bytes, "pdf")
    assert detected is False, f"PDF limpo foi flagado como PII: {fields}"
