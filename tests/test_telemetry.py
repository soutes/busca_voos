from busca_voos.telemetry import (
    medir_tempo,
    registrar_busca,
    registrar_erro,
    registrar_ofertas,
)


def test_telemetria_registra_sem_excecao():
    # Testa se as funcoes de registro funcionam de forma segura mesmo sem collector rodando
    registrar_busca("GRU", "FLN", sucesso=True)
    registrar_ofertas("google_flights", 5)
    registrar_erro("google_flights", "layout_mudou")

    with medir_tempo("google_flights"):
        pass
