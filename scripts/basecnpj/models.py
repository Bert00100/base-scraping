from __future__ import annotations

from pydantic import BaseModel, ConfigDict

# Modelos deliberadamente parciais: só os campos que o pipeline (Passo 5+) vai
# precisar de fato. `extra="allow"` porque a resposta real do BaseCNPJ tem mais
# campos do que os documentados no ARCTETURE.md, e não queremos quebrar o parsing
# por causa de um campo novo/desconhecido.


class EstabelecimentoMatriz(BaseModel):
    model_config = ConfigDict(extra="allow")

    nome_fantasia: str | None = None
    situacao_cadastral: str | None = None
    situacao_descricao: str | None = None
    data_inicio_atividade: str | None = None
    cnae_principal_codigo: str | None = None
    email: str | None = None
    uf: str | None = None
    municipio: str | None = None
    cep: str | None = None
    logradouro: str | None = None


class CnaeItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    tipo: str  # "Principal" | "Secundária"
    cnae: str
    desc: str | None = None


class Telefone(BaseModel):
    model_config = ConfigDict(extra="allow")

    tipo: str | None = None
    ddd: str | None = None
    numero: str | None = None


class Estabelecimento(BaseModel):
    model_config = ConfigDict(extra="allow")

    cnpj_completo_formatado: str | None = None
    matriz_filial_codigo: str | None = None  # "1"=Matriz, "2"=Filial
    matriz_filial: str | None = None
    situacao_cadastral: str | None = None
    uf: str | None = None
    municipio: str | None = None


class CNPJDetalhe(BaseModel):
    """Resposta de route=cnpj. Ver references/basecnpj.md para o formato real observado."""

    model_config = ConfigDict(extra="allow")

    cnpj_basico: str
    cnpj_completo_formatado: str
    razao_social: str
    capital_social: float | int | None = None
    porte_codigo: str | None = None
    porte_descricao: str | None = None
    natureza_juridica_descricao: str | None = None
    estabelecimento_matriz: EstabelecimentoMatriz | None = None
    estabelecimentos: list[Estabelecimento] = []
    cnaes: list[CnaeItem] = []
    telefones: list[Telefone] = []

    def telefone_principal(self) -> str | None:
        if not self.telefones:
            return None
        primeiro = self.telefones[0]
        return f"({primeiro.ddd}) {primeiro.numero}" if primeiro.ddd else primeiro.numero

    def cnae_principal(self) -> str | None:
        return next((c.cnae for c in self.cnaes if c.tipo == "Principal"), None)

    def cnaes_secundarios(self) -> list[str]:
        return [c.cnae for c in self.cnaes if c.tipo != "Principal"]

    def matriz_filial_codigo(self) -> str | None:
        for est in self.estabelecimentos:
            if est.cnpj_completo_formatado == self.cnpj_completo_formatado:
                return est.matriz_filial_codigo
        return None
