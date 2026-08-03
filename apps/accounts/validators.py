import re

from django.core.exceptions import ValidationError


def cpf_somente_digitos(value):
    if value is None:
        return ''
    return re.sub(r'\D', '', str(value))


def cpf_valido(cpf):
    """Valida CPF usando os dígitos verificadores (algoritmo módulo 11)."""
    cpf = cpf_somente_digitos(cpf)
    if len(cpf) != 11:
        return False
    if cpf == cpf[0] * 11:
        return False
    for i in range(9, 11):
        soma = sum(int(cpf[j]) * ((i + 1) - j) for j in range(i))
        resto = (soma * 10) % 11
        resto = 0 if resto == 10 else resto
        if int(cpf[i]) != resto:
            return False
    return True


def validar_cpf(value):
    """Validador Django — aceita vazio, valida os dígitos quando preenchido."""
    if not value:
        return
    if not cpf_valido(value):
        raise ValidationError('CPF inválido.')
