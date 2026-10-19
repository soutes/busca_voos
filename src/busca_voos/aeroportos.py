"""Catálogo de aeroportos e códigos metropolitanos do busca_voos.

Fornece busca tolerante a acentos e maiúsculas/minúsculas, validação de códigos
IATA e resolução de códigos metropolitanos (ex.: RIO -> GIG) para fontes que não
oferecem suporte a áreas metropolitanas (como o Skiplagged).
"""
from __future__ import annotations

import logging
import unicodedata
from typing import Any

log = logging.getLogger(__name__)

# Códigos metropolitanos e seus aeroportos primários / alternativos
METROPOLITANOS_CONFIG: dict[str, dict[str, Any]] = {
    "RIO": {
        "cidade": "Rio de Janeiro",
        "nome": "Todos os aeroportos",
        "estado": "RJ",
        "pais": "Brasil",
        "primario": "GIG",
        "alternativos": ["GIG", "SDU"],
    },
    "SAO": {
        "cidade": "São Paulo",
        "nome": "Todos os aeroportos",
        "estado": "SP",
        "pais": "Brasil",
        "primario": "GRU",
        "alternativos": ["GRU", "CGH", "VCP"],
    },
    "BHZ": {
        "cidade": "Belo Horizonte",
        "nome": "Todos os aeroportos",
        "estado": "MG",
        "pais": "Brasil",
        "primario": "CNF",
        "alternativos": ["CNF"],
    },
    "BUE": {
        "cidade": "Buenos Aires",
        "nome": "Todos os aeroportos",
        "estado": "BA",
        "pais": "Argentina",
        "primario": "EZE",
        "alternativos": ["EZE", "AEP"],
    },
    "NYC": {
        "cidade": "Nova York",
        "nome": "Todos os aeroportos",
        "estado": "NY",
        "pais": "Estados Unidos",
        "primario": "JFK",
        "alternativos": ["JFK", "EWR", "LGA"],
    },
    "LON": {
        "cidade": "Londres",
        "nome": "Todos os aeroportos",
        "estado": "Inglaterra",
        "pais": "Reino Unido",
        "primario": "LHR",
        "alternativos": ["LHR", "LGW", "STN", "LTN", "LCY"],
    },
    "PAR": {
        "cidade": "Paris",
        "nome": "Todos os aeroportos",
        "estado": "Île-de-France",
        "pais": "França",
        "primario": "CDG",
        "alternativos": ["CDG", "ORY"],
    },
}

# Mapeamento rápido de metro -> primário
METROPOLITANOS_PRIMARIOS: dict[str, str] = {
    cod: info["primario"] for cod, info in METROPOLITANOS_CONFIG.items()
}

# Fontes que não aceitam códigos metropolitanos na busca direta
FONTES_SEM_METROPOLITANO = {"skiplagged", "latam", "gol", "azul"}

# Top 15 aeroportos comerciais mais movimentados/relevantes do Brasil
TOP_AEROPORTOS_BR = [
    "GRU",
    "CGH",
    "BSB",
    "GIG",
    "SDU",
    "CNF",
    "VCP",
    "SSA",
    "REC",
    "POA",
    "FOR",
    "CWB",
    "FLN",
    "VIX",
    "GYN",
]

# Dados base dos aeroportos (código IATA -> dados)
_DADOS_AEROPORTOS: list[dict[str, str]] = [
    # --- BRASIL: Principais e Comerciais ---
    {"codigo": "FLN", "cidade": "Florianópolis", "nome": "Hercílio Luz", "estado": "SC", "pais": "Brasil"},
    {"codigo": "GRU", "cidade": "São Paulo", "nome": "Guarulhos - Gov. André Franco Montoro", "estado": "SP", "pais": "Brasil"},
    {"codigo": "CGH", "cidade": "São Paulo", "nome": "Congonhas", "estado": "SP", "pais": "Brasil"},
    {"codigo": "VCP", "cidade": "Campinas", "nome": "Viracopos", "estado": "SP", "pais": "Brasil"},
    {"codigo": "GIG", "cidade": "Rio de Janeiro", "nome": "Galeão - Tom Jobim", "estado": "RJ", "pais": "Brasil"},
    {"codigo": "SDU", "cidade": "Rio de Janeiro", "nome": "Santos Dumont", "estado": "RJ", "pais": "Brasil"},
    {"codigo": "BSB", "cidade": "Brasília", "nome": "Presidente Juscelino Kubitschek", "estado": "DF", "pais": "Brasil"},
    {"codigo": "CNF", "cidade": "Belo Horizonte", "nome": "Confins - Tancredo Neves", "estado": "MG", "pais": "Brasil"},
    {"codigo": "SSA", "cidade": "Salvador", "nome": "Deputado Luís Eduardo Magalhães", "estado": "BA", "pais": "Brasil"},
    {"codigo": "REC", "cidade": "Recife", "nome": "Guararapes - Gilberto Freyre", "estado": "PE", "pais": "Brasil"},
    {"codigo": "FOR", "cidade": "Fortaleza", "nome": "Pinto Martins", "estado": "CE", "pais": "Brasil"},
    {"codigo": "POA", "cidade": "Porto Alegre", "nome": "Salgado Filho", "estado": "RS", "pais": "Brasil"},
    {"codigo": "CWB", "cidade": "Curitiba", "nome": "Afonso Pena", "estado": "PR", "pais": "Brasil"},
    {"codigo": "VIX", "cidade": "Vitória", "nome": "Eurico de Aguiar Salles", "estado": "ES", "pais": "Brasil"},
    {"codigo": "GYN", "cidade": "Goiânia", "nome": "Santa Genoveva", "estado": "GO", "pais": "Brasil"},
    {"codigo": "BEL", "cidade": "Belém", "nome": "Val-de-Cans - Júlio Cezar Ribeiro", "estado": "PA", "pais": "Brasil"},
    {"codigo": "MAO", "cidade": "Manaus", "nome": "Eduardo Gomes", "estado": "AM", "pais": "Brasil"},
    {"codigo": "MCZ", "cidade": "Maceió", "nome": "Zumbi dos Palmares", "estado": "AL", "pais": "Brasil"},
    {"codigo": "NAT", "cidade": "Natal", "nome": "Governador Aluízio Alves", "estado": "RN", "pais": "Brasil"},
    {"codigo": "IGU", "cidade": "Foz do Iguaçu", "nome": "Cataratas", "estado": "PR", "pais": "Brasil"},
    {"codigo": "NVT", "cidade": "Navegantes", "nome": "Ministro Victor Konder", "estado": "SC", "pais": "Brasil"},
    {"codigo": "XAP", "cidade": "Chapecó", "nome": "Serafin Enoss Bertaso", "estado": "SC", "pais": "Brasil"},
    {"codigo": "UDI", "cidade": "Uberlândia", "nome": "Ten.-Cel.-Av. César Bombonato", "estado": "MG", "pais": "Brasil"},
    {"codigo": "CGB", "cidade": "Cuiabá", "nome": "Marechal Rondon", "estado": "MT", "pais": "Brasil"},
    {"codigo": "CGR", "cidade": "Campo Grande", "nome": "Campo Grande", "estado": "MS", "pais": "Brasil"},
    {"codigo": "JPA", "cidade": "João Pessoa", "nome": "Presidente Castro Pinto", "estado": "PB", "pais": "Brasil"},
    {"codigo": "AJU", "cidade": "Aracaju", "nome": "Santa Maria", "estado": "SE", "pais": "Brasil"},
    {"codigo": "SLZ", "cidade": "São Luís", "nome": "Marechal Cunha Machado", "estado": "MA", "pais": "Brasil"},
    {"codigo": "PMW", "cidade": "Palmas", "nome": "Brigadeiro Lysias Rodrigues", "estado": "TO", "pais": "Brasil"},
    {"codigo": "PVH", "cidade": "Porto Velho", "nome": "Gov. Jorge Teixeira de Oliveira", "estado": "RO", "pais": "Brasil"},
    {"codigo": "BPS", "cidade": "Porto Seguro", "nome": "Porto Seguro", "estado": "BA", "pais": "Brasil"},
    {"codigo": "IOS", "cidade": "Ilhéus", "nome": "Jorge Amado", "estado": "BA", "pais": "Brasil"},
    {"codigo": "JDO", "cidade": "Juazeiro do Norte", "nome": "Orlando Bezerra de Menezes", "estado": "CE", "pais": "Brasil"},
    {"codigo": "IMP", "cidade": "Imperatriz", "nome": "Prefeito Renato Moreira", "estado": "MA", "pais": "Brasil"},
    {"codigo": "MGF", "cidade": "Maringá", "nome": "Sílvio Name Júnior", "estado": "PR", "pais": "Brasil"},
    {"codigo": "LDB", "cidade": "Londrina", "nome": "Governador José Richa", "estado": "PR", "pais": "Brasil"},
    {"codigo": "CXJ", "cidade": "Caxias do Sul", "nome": "Hugo Cantergiani", "estado": "RS", "pais": "Brasil"},
    {"codigo": "JOI", "cidade": "Joinville", "nome": "Lauro Carneiro de Loyola", "estado": "SC", "pais": "Brasil"},
    {"codigo": "MCP", "cidade": "Macapá", "nome": "Alberto Alcolumbre", "estado": "AP", "pais": "Brasil"},
    {"codigo": "RBR", "cidade": "Rio Branco", "nome": "Plácido de Castro", "estado": "AC", "pais": "Brasil"},
    {"codigo": "BVB", "cidade": "Boa Vista", "nome": "Atlas Brasil Cantanhede", "estado": "RR", "pais": "Brasil"},
    {"codigo": "STM", "cidade": "Santarém", "nome": "Maestro Wilson Fonseca", "estado": "PA", "pais": "Brasil"},
    {"codigo": "MAB", "cidade": "Marabá", "nome": "João Correa da Rocha", "estado": "PA", "pais": "Brasil"},
    {"codigo": "PFB", "cidade": "Passo Fundo", "nome": "Lauro Kortz", "estado": "RS", "pais": "Brasil"},
    {"codigo": "PET", "cidade": "Pelotas", "nome": "João Simões Lopes Neto", "estado": "RS", "pais": "Brasil"},
    {"codigo": "RIA", "cidade": "Santa Maria", "nome": "Santa Maria", "estado": "RS", "pais": "Brasil"},
    {"codigo": "CFB", "cidade": "Cabo Frio", "nome": "Cabo Frio", "estado": "RJ", "pais": "Brasil"},
    {"codigo": "RAO", "cidade": "Ribeirão Preto", "nome": "Doutor Leite Lopes", "estado": "SP", "pais": "Brasil"},
    {"codigo": "SJP", "cidade": "São José do Rio Preto", "nome": "Prof. Eribelto Manoel Reino", "estado": "SP", "pais": "Brasil"},
    {"codigo": "PPB", "cidade": "Presidente Prudente", "nome": "Adhemar de Barros", "estado": "SP", "pais": "Brasil"},
    {"codigo": "BYO", "cidade": "Bonito", "nome": "Bonito", "estado": "MS", "pais": "Brasil"},
    {"codigo": "CPV", "cidade": "Campina Grande", "nome": "Presidente João Suassuna", "estado": "PB", "pais": "Brasil"},
    {"codigo": "THE", "cidade": "Teresina", "nome": "Senador Petrônio Portella", "estado": "PI", "pais": "Brasil"},
    {"codigo": "PHB", "cidade": "Parnaíba", "nome": "Prefeito Dr. João Silva Filho", "estado": "PI", "pais": "Brasil"},
    {"codigo": "FEN", "cidade": "Fernando de Noronha", "nome": "Gov. Carlos Wilson", "estado": "PE", "pais": "Brasil"},
    {"codigo": "JJD", "cidade": "Jericoacoara", "nome": "Comandante Ariston Pessoa", "estado": "CE", "pais": "Brasil"},
    {"codigo": "CAC", "cidade": "Cascavel", "nome": "Adalberto Mendes da Silva", "estado": "PR", "pais": "Brasil"},
    {"codigo": "ATM", "cidade": "Altamira", "nome": "Altamira", "estado": "PA", "pais": "Brasil"},
    {"codigo": "SJK", "cidade": "São José dos Campos", "nome": "Prof. Urbano Ernesto Stumpf", "estado": "SP", "pais": "Brasil"},
    {"codigo": "ARU", "cidade": "Araçatuba", "nome": "Dario Guarita", "estado": "SP", "pais": "Brasil"},
    {"codigo": "BAU", "cidade": "Bauru", "nome": "Moussa Nakhl Tobias", "estado": "SP", "pais": "Brasil"},
    {"codigo": "MOC", "cidade": "Montes Claros", "nome": "Mário Ribeiro", "estado": "MG", "pais": "Brasil"},
    {"codigo": "IPN", "cidade": "Ipatinga", "nome": "Vale do Aço", "estado": "MG", "pais": "Brasil"},
    {"codigo": "VAG", "cidade": "Varginha", "nome": "Maj. Brig. Trompowsky", "estado": "MG", "pais": "Brasil"},
    {"codigo": "CAW", "cidade": "Campos dos Goytacazes", "nome": "Bartolomeu Lysandro", "estado": "RJ", "pais": "Brasil"},
    {"codigo": "MEA", "cidade": "Macaé", "nome": "Joaquim de Azevedo Mancebo", "estado": "RJ", "pais": "Brasil"},
    {"codigo": "URG", "cidade": "Uruguaiana", "nome": "Ruben Berta", "estado": "RS", "pais": "Brasil"},
    {"codigo": "GEL", "cidade": "Santo Ângelo", "nome": "Sepé Tiaraju", "estado": "RS", "pais": "Brasil"},
    {"codigo": "SMU", "cidade": "São Mateus", "nome": "Tancredo Neves", "estado": "ES", "pais": "Brasil"},
    {"codigo": "JPR", "cidade": "Ji-Paraná", "nome": "José Coleto", "estado": "RO", "pais": "Brasil"},
    {"codigo": "OAL", "cidade": "Cacoal", "nome": "Capital do Café", "estado": "RO", "pais": "Brasil"},
    {"codigo": "BRA", "cidade": "Barreiras", "nome": "Dom Ricardo Weberberger", "estado": "BA", "pais": "Brasil"},
    {"codigo": "TXF", "cidade": "Teixeira de Freitas", "nome": "9 de Maio", "estado": "BA", "pais": "Brasil"},
    {"codigo": "VDC", "cidade": "Vitória da Conquista", "nome": "Glauber Rocha", "estado": "BA", "pais": "Brasil"},
    {"codigo": "PAV", "cidade": "Paulo Afonso", "nome": "Paulo Afonso", "estado": "BA", "pais": "Brasil"},
    {"codigo": "LEC", "cidade": "Lençóis", "nome": "Horácio de Mattos", "estado": "BA", "pais": "Brasil"},
    {"codigo": "GNM", "cidade": "Guanambi", "nome": "Guanambi", "estado": "BA", "pais": "Brasil"},
    {"codigo": "ARX", "cidade": "Aracati", "nome": "Dragão do Mar", "estado": "CE", "pais": "Brasil"},
    {"codigo": "GVR", "cidade": "Governador Valadares", "nome": "Cel. Altino Machado", "estado": "MG", "pais": "Brasil"},
    {"codigo": "AAX", "cidade": "Araxá", "nome": "Romeu Zema", "estado": "MG", "pais": "Brasil"},
    {"codigo": "TJL", "cidade": "Três Lagoas", "nome": "Plínio Alarcom", "estado": "MS", "pais": "Brasil"},
    {"codigo": "DOU", "cidade": "Dourados", "nome": "Francisco de Matos Pereira", "estado": "MS", "pais": "Brasil"},
    {"codigo": "ROO", "cidade": "Rondonópolis", "nome": "Maestro Marinho Franco", "estado": "MT", "pais": "Brasil"},
    {"codigo": "SMX", "cidade": "Sorriso", "nome": "Adolino Bedin", "estado": "MT", "pais": "Brasil"},
    {"codigo": "OPS", "cidade": "Sinop", "nome": "Presidente João Figueiredo", "estado": "MT", "pais": "Brasil"},
    {"codigo": "AFL", "cidade": "Alta Floresta", "nome": "Piloto Osvaldo Marques Dias", "estado": "MT", "pais": "Brasil"},
    {"codigo": "PIN", "cidade": "Parintins", "nome": "Júlio Belém", "estado": "AM", "pais": "Brasil"},
    {"codigo": "TBT", "cidade": "Tabatinga", "nome": "Tabatinga", "estado": "AM", "pais": "Brasil"},
    {"codigo": "TFF", "cidade": "Tefé", "nome": "Tefé", "estado": "AM", "pais": "Brasil"},
    {"codigo": "JJG", "cidade": "Jaguaruna", "nome": "Humberto Ghizzo Bortoluzzi", "estado": "SC", "pais": "Brasil"},
    {"codigo": "LAJ", "cidade": "Lages", "nome": "Antônio Correia Pinto de Macedo", "estado": "SC", "pais": "Brasil"},

    # --- INTERNACIONAIS POPULARES ---
    {"codigo": "MIA", "cidade": "Miami", "nome": "Miami International", "estado": "FL", "pais": "Estados Unidos"},
    {"codigo": "MCO", "cidade": "Orlando", "nome": "Orlando International", "estado": "FL", "pais": "Estados Unidos"},
    {"codigo": "JFK", "cidade": "Nova York", "nome": "John F. Kennedy", "estado": "NY", "pais": "Estados Unidos"},
    {"codigo": "EWR", "cidade": "Newark", "nome": "Newark Liberty", "estado": "NJ", "pais": "Estados Unidos"},
    {"codigo": "LGA", "cidade": "Nova York", "nome": "LaGuardia", "estado": "NY", "pais": "Estados Unidos"},
    {"codigo": "LIS", "cidade": "Lisboa", "nome": "Humberto Delgado", "estado": "Lisboa", "pais": "Portugal"},
    {"codigo": "OPO", "cidade": "Porto", "nome": "Francisco Sá Carneiro", "estado": "Porto", "pais": "Portugal"},
    {"codigo": "MAD", "cidade": "Madri", "nome": "Adolfo Suárez Madrid-Barajas", "estado": "Madri", "pais": "Espanha"},
    {"codigo": "BCN", "cidade": "Barcelona", "nome": "Josep Tarradellas Barcelona-El Prat", "estado": "Catalunha", "pais": "Espanha"},
    {"codigo": "CDG", "cidade": "Paris", "nome": "Charles de Gaulle", "estado": "Île-de-France", "pais": "França"},
    {"codigo": "ORY", "cidade": "Paris", "nome": "Orly", "estado": "Île-de-France", "pais": "França"},
    {"codigo": "FCO", "cidade": "Roma", "nome": "Leonardo da Vinci-Fiumicino", "estado": "Lácio", "pais": "Itália"},
    {"codigo": "MXP", "cidade": "Milão", "nome": "Malpensa", "estado": "Lombardia", "pais": "Itália"},
    {"codigo": "LHR", "cidade": "Londres", "nome": "Heathrow", "estado": "Inglaterra", "pais": "Reino Unido"},
    {"codigo": "LGW", "cidade": "Londres", "nome": "Gatwick", "estado": "Inglaterra", "pais": "Reino Unido"},
    {"codigo": "EZE", "cidade": "Buenos Aires", "nome": "Ministro Pistarini (Ezeiza)", "estado": "BA", "pais": "Argentina"},
    {"codigo": "AEP", "cidade": "Buenos Aires", "nome": "Aeroparque Jorge Newbery", "estado": "BA", "pais": "Argentina"},
    {"codigo": "SCL", "cidade": "Santiago", "nome": "Arturo Merino Benítez", "estado": "RM", "pais": "Chile"},
    {"codigo": "BOG", "cidade": "Bogotá", "nome": "El Dorado", "estado": "Cundinamarca", "pais": "Colômbia"},
    {"codigo": "MVD", "cidade": "Montevidéu", "nome": "Carrasco", "estado": "Canelones", "pais": "Uruguai"},
    {"codigo": "LIM", "cidade": "Lima", "nome": "Jorge Chávez", "estado": "Callao", "pais": "Peru"},
    {"codigo": "PTY", "cidade": "Cidade do Panamá", "nome": "Tocumen", "estado": "Panamá", "pais": "Panamá"},
    {"codigo": "CUN", "cidade": "Cancún", "nome": "Cancún International", "estado": "Quintana Roo", "pais": "México"},
    {"codigo": "MEX", "cidade": "Cidade do México", "nome": "Benito Juárez", "estado": "CDMX", "pais": "México"},
    {"codigo": "DXB", "cidade": "Dubai", "nome": "Dubai International", "estado": "Dubai", "pais": "Emirados Árabes Unidos"},
    {"codigo": "DOH", "cidade": "Doha", "nome": "Hamad International", "estado": "Doha", "pais": "Catar"},
    {"codigo": "AMS", "cidade": "Amsterdã", "nome": "Schiphol", "estado": "Holanda do Norte", "pais": "Holanda"},
    {"codigo": "FRA", "cidade": "Frankfurt", "nome": "Frankfurt am Main", "estado": "Hesse", "pais": "Alemanha"},
    {"codigo": "MUC", "cidade": "Munique", "nome": "Franz Josef Strauss", "estado": "Baviera", "pais": "Alemanha"},
    {"codigo": "ZRH", "cidade": "Zurique", "nome": "Kloten", "estado": "Zurique", "pais": "Suíça"},
    {"codigo": "ORD", "cidade": "Chicago", "nome": "O'Hare", "estado": "IL", "pais": "Estados Unidos"},
    {"codigo": "LAX", "cidade": "Los Angeles", "nome": "Los Angeles International", "estado": "CA", "pais": "Estados Unidos"},
    {"codigo": "SFO", "cidade": "São Francisco", "nome": "San Francisco International", "estado": "CA", "pais": "Estados Unidos"},
    {"codigo": "BOS", "cidade": "Boston", "nome": "Logan International", "estado": "MA", "pais": "Estados Unidos"},
    {"codigo": "YYZ", "cidade": "Toronto", "nome": "Toronto Pearson", "estado": "Ontário", "pais": "Canadá"},
]


def _montar_descricao(
    codigo: str, cidade: str, nome: str, estado: str, pais: str, tipo: str
) -> str:
    """Gera string descritiva legível para dropdowns e resultados de busca."""
    if tipo == "metropolitano":
        if pais == "Brasil" and estado:
            return f"{codigo} - {cidade}, {estado} ({nome})"
        return f"{codigo} - {cidade}, {pais} ({nome})"
    if pais == "Brasil":
        return f"{codigo} - {cidade}, {estado} ({nome})"
    if estado and pais != estado:
        return f"{codigo} - {cidade}, {estado} - {pais} ({nome})"
    return f"{codigo} - {cidade}, {pais} ({nome})"


def _construir_catalogo() -> dict[str, dict[str, Any]]:
    """Monta o catálogo consolidado indexado pelo código IATA em maiúsculas."""
    cat: dict[str, dict[str, Any]] = {}

    # Adiciona metropolitanos
    for cod, m in METROPOLITANOS_CONFIG.items():
        desc = _montar_descricao(
            cod, m["cidade"], m["nome"], m.get("estado", ""), m["pais"], "metropolitano"
        )
        cat[cod] = {
            "codigo": cod,
            "cidade": m["cidade"],
            "nome": m["nome"],
            "estado": m.get("estado", ""),
            "pais": m["pais"],
            "tipo": "metropolitano",
            "primario": m["primario"],
            "alternativos": list(m["alternativos"]),
            "descricao": desc,
        }

    # Adiciona aeroportos convencionais
    for a in _DADOS_AEROPORTOS:
        cod = a["codigo"].upper()
        desc = _montar_descricao(
            cod, a["cidade"], a["nome"], a.get("estado", ""), a["pais"], "aeroporto"
        )
        cat[cod] = {
            "codigo": cod,
            "cidade": a["cidade"],
            "nome": a["nome"],
            "estado": a.get("estado", ""),
            "pais": a["pais"],
            "tipo": "aeroporto",
            "descricao": desc,
        }

    return cat


AEROPORTOS: dict[str, dict[str, Any]] = _construir_catalogo()


def _remover_acentos(texto: str) -> str:
    """Normaliza texto para minúsculas sem acentos."""
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    ).lower()


def buscar_aeroportos(termo: str, limite: int = 15) -> list[dict[str, Any]]:
    """Busca aeroportos por código IATA, cidade ou nome (tolerante a acentos).

    Se `termo` for vazio, retorna os principais aeroportos comerciais do Brasil.
    """
    limite = max(1, min(limite, 50))
    if not termo or not termo.strip():
        destaques = [AEROPORTOS[c] for c in TOP_AEROPORTOS_BR if c in AEROPORTOS]
        if limite <= 15:
            return [dict(a) for a in destaques[:limite]]
        metros = [AEROPORTOS[c] for c in METROPOLITANOS_CONFIG if c in AEROPORTOS]
        vistos = set()
        combinados = []
        for a in metros + destaques:
            if a["codigo"] not in vistos:
                vistos.add(a["codigo"])
                combinados.append(a)
        return [dict(a) for a in combinados[:limite]]

    q = _remover_acentos(termo.strip())
    resultados: list[tuple[int, int, str, dict[str, Any]]] = []

    for aeroporto in AEROPORTOS.values():
        cod_norm = _remover_acentos(aeroporto["codigo"])
        cid_norm = _remover_acentos(aeroporto["cidade"])
        nom_norm = _remover_acentos(aeroporto["nome"])
        desc_norm = _remover_acentos(aeroporto["descricao"])
        est_norm = _remover_acentos(aeroporto["estado"])

        score: int | None = None
        if cod_norm == q:
            score = 0
        elif cod_norm.startswith(q):
            score = 1
        elif cid_norm == q:
            score = 2
        elif cid_norm.startswith(q):
            score = 3
        elif q in cid_norm:
            score = 4
        elif nom_norm.startswith(q):
            score = 5
        elif q in nom_norm:
            score = 6
        elif q in desc_norm or q in est_norm:
            score = 7

        if score is not None:
            # Desempate: metropolitanos e aeroportos destaque do Brasil recebem prioridade
            prioridade = (
                0 if (aeroporto["tipo"] == "metropolitano" or aeroporto["codigo"] in TOP_AEROPORTOS_BR)
                else 1
            )
            resultados.append((score, prioridade, aeroporto["cidade"], aeroporto))

    resultados.sort(key=lambda x: (x[0], x[1], x[2]))
    return [dict(item[3]) for item in resultados[:limite]]


def validar_iata(codigo: str) -> dict[str, Any] | None:
    """Verifica se o código IATA existe no catálogo.

    Retorna o dicionário de informações do aeroporto ou None se inválido.
    """
    if not codigo or not isinstance(codigo, str):
        return None
    chave = codigo.strip().upper()
    item = AEROPORTOS.get(chave)
    if item is not None:
        return dict(item)
    return None


def resolver_para_fonte(codigo: str, nome_fonte: str) -> str:
    """Mapeia código metropolitano para código de aeroporto primário se necessário.

    Fontes que não suportam códigos de área metropolitana (como o Skiplagged)
    recebem o aeroporto primário (ex.: RIO -> GIG, SAO -> GRU). Caso contrário,
    retorna o próprio código.
    """
    if not codigo or not isinstance(codigo, str):
        return ""
    cod = codigo.strip().upper()
    fonte = (nome_fonte or "").strip().lower()
    if fonte in FONTES_SEM_METROPOLITANO:
        item = AEROPORTOS.get(cod)
        if item and item.get("tipo") == "metropolitano" and item.get("primario"):
            return str(item["primario"])
        if cod in METROPOLITANOS_PRIMARIOS:
            return METROPOLITANOS_PRIMARIOS[cod]
    return cod
