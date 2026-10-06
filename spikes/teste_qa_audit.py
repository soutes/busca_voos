import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import tempfile
import shutil
import re

from busca_voos.config import (
    adicionar_rota_config,
    remover_rota_config,
    salvar_intervalo_cron,
    obter_intervalo_cron,
    carregar_config,
    ErroConfig,
)

def run_audit():
    print("=== 1. Auditing Route Validation ===")
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "config.yaml"
        shutil.copyfile("config.yaml", cfg)

        # same origin/dest
        try:
            adicionar_rota_config(cfg, {"origem": "GRU", "destino": "gru", "janela_ida": {"de": "2026-11-01", "ate": "2026-11-05"}, "preco_maximo": 500})
            sys.exit("FAIL: same origin/dest accepted")
        except ErroConfig as e:
            print(f"  OK: same origin/dest rejected ({e})")

        # invalid origin length
        for inv in ["A", "ABCDEF", "", "   "]:
            try:
                adicionar_rota_config(cfg, {"origem": inv, "destino": "GRU", "janela_ida": {"de": "2026-11-01", "ate": "2026-11-05"}, "preco_maximo": 500})
                sys.exit(f"FAIL: invalid origin {inv!r} accepted")
            except ErroConfig:
                pass
        print("  OK: invalid origin lengths rejected")

        # non-alphanumeric
        try:
            adicionar_rota_config(cfg, {"origem": "GR-U", "destino": "FLN", "janela_ida": {"de": "2026-11-01", "ate": "2026-11-05"}, "preco_maximo": 500})
            sys.exit("FAIL: non-alphanumeric origin accepted")
        except ErroConfig:
            print("  OK: non-alphanumeric origin rejected")

        # inverted ida
        try:
            adicionar_rota_config(cfg, {"origem": "GRU", "destino": "FLN", "janela_ida": {"de": "2026-11-10", "ate": "2026-11-05"}, "preco_maximo": 500})
            sys.exit("FAIL: inverted ida dates accepted")
        except ErroConfig:
            print("  OK: inverted ida dates rejected")

        # return before ida
        try:
            adicionar_rota_config(cfg, {"origem": "GRU", "destino": "FLN", "janela_ida": {"de": "2026-11-10", "ate": "2026-11-15"}, "janela_volta": {"de": "2026-11-05", "ate": "2026-11-08"}, "preco_maximo": 500})
            sys.exit("FAIL: return before ida accepted")
        except ErroConfig:
            print("  OK: return before ida rejected")

        # return inverted
        try:
            adicionar_rota_config(cfg, {"origem": "GRU", "destino": "FLN", "janela_ida": {"de": "2026-11-10", "ate": "2026-11-15"}, "janela_volta": {"de": "2026-11-20", "ate": "2026-11-18"}, "preco_maximo": 500})
            sys.exit("FAIL: return inverted rejected")
        except ErroConfig:
            print("  OK: return inverted rejected")

        # price zero or negative
        for p in [0, -10, "abc"]:
            try:
                adicionar_rota_config(cfg, {"origem": "GRU", "destino": "FLN", "janela_ida": {"de": "2026-11-10", "ate": "2026-11-15"}, "preco_maximo": p})
                sys.exit(f"FAIL: invalid price {p!r} accepted")
            except ErroConfig:
                pass
        print("  OK: invalid prices rejected")

    print("\n=== 2. Auditing YAML Comment Preservation ===")
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "config.yaml"
        shutil.copyfile("config.yaml", cfg)
        content_orig = cfg.read_text(encoding="utf-8")
        comments_to_check = [
            "# moeda pedida nas buscas",
            "# true = busca nesta fonte a cada ciclo",
            "# conta que envia",
            '# periodicidade do modo "run" (daemon)',
            "# false para ver o navegador (depurar)",
        ]
        for c in comments_to_check:
            assert c in content_orig, f"Original missing comment {c}"

        adicionar_rota_config(cfg, {
            "origem": "BSB", "destino": "SDU",
            "janela_ida": {"de": "2026-11-01", "ate": "2026-11-05"},
            "janela_volta": {"de": "2026-11-10", "ate": "2026-11-15"},
            "preco_maximo": 600, "nome": "Brasilia Rio"
        })
        content_after_add = cfg.read_text(encoding="utf-8")
        for c in comments_to_check:
            assert c in content_after_add, f"After add missing comment {c}"
        print("  OK: all comments preserved after add")

        remover_rota_config(cfg, 1)
        content_after_del = cfg.read_text(encoding="utf-8")
        for c in comments_to_check:
            assert c in content_after_del, f"After del missing comment {c}"
        print("  OK: all comments preserved after delete")

        # Audit cron interval edit
        salvar_intervalo_cron(cfg, 2.5)
        content_after_cron = cfg.read_text(encoding="utf-8")
        for c in comments_to_check:
            assert c in content_after_cron, f"After cron edit missing comment {c}"
        assert "intervalo_minutos: 150" in content_after_cron
        assert obter_intervalo_cron(cfg) == 2.5
        print("  OK: all comments preserved after cron interval edit (2.5h -> 150m)")

        salvar_intervalo_cron(cfg, 1.0)
        content_after_cron2 = cfg.read_text(encoding="utf-8")
        for c in comments_to_check:
            assert c in content_after_cron2, f"After 2nd cron edit missing comment {c}"
        assert "intervalo_minutos: 60" in content_after_cron2
        assert obter_intervalo_cron(cfg) == 1.0
        print("  OK: all comments preserved after second cron interval edit (1.0h -> 60m)")

    print("\n=== 3. Auditing HTML Security & CDN Constraints ===")
    html_paths = [
        Path("src/busca_voos/painel.html"),
        Path("vs_win/src/busca_voos/painel.html"),
        Path("vs_linux/src/busca_voos/painel.html")
    ]
    for p in html_paths:
        html = p.read_text(encoding="utf-8")
        assert "innerHTML" not in html, f"innerHTML found in {p}"
        assert "outerHTML" not in html, f"outerHTML found in {p}"
        assert "document.write" not in html, f"document.write found in {p}"
        # No external scripts: <script src=...
        assert not re.search(r"<script[^>]+src=", html, re.IGNORECASE), f"External script tag found in {p}"
        # No external stylesheets: <link rel=...
        assert not re.search(r"<link[^>]+", html, re.IGNORECASE), f"Link tag found in {p}"
        # No @import
        assert "@import" not in html, f"@import found in {p}"
        print(f"  OK: {p} passed zero-innerHTML and zero-CDN check")

    print("\n=== 4. Auditing Bundle Synchronization Integrity ===")
    src_dir = Path("src/busca_voos")
    win_dir = Path("vs_win/src/busca_voos")
    lin_dir = Path("vs_linux/src/busca_voos")

    for file in src_dir.rglob("*"):
        if file.is_file() and "__pycache__" not in str(file):
            rel = file.relative_to(src_dir)
            f_win = win_dir / rel
            f_lin = lin_dir / rel
            assert f_win.exists(), f"Missing file in vs_win: {rel}"
            assert f_lin.exists(), f"Missing file in vs_linux: {rel}"
            assert file.read_bytes() == f_win.read_bytes(), f"Mismatch in vs_win: {rel}"
            assert file.read_bytes() == f_lin.read_bytes(), f"Mismatch in vs_linux: {rel}"
    print("  OK: All source files in vs_win and vs_linux are 100% byte-identical to src/")

    print("\n=== 5. Auditing Live Search Updates & Cron Scheduling Contracts ===")
    from busca_voos.web import criar_app
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmp:
        db_p = Path(tmp) / "audit.sqlite3"
        cfg_p = Path(tmp) / "config.yaml"
        shutil.copyfile("config.yaml", cfg_p)

        app = criar_app(db_p, caminho_config=cfg_p)
        client = TestClient(app)

        # 5.1 GET /api/cron schema
        r_cron = client.get("/api/cron")
        assert r_cron.status_code == 200
        d_cron = r_cron.json()
        for field in ["ativo", "intervalo_horas", "intervalo_minutos", "proxima_execucao", "segundos_restantes"]:
            assert field in d_cron, f"Missing field in /api/cron: {field}"
        print("  OK: /api/cron schema valid")

        # 5.2 POST /api/cron validation
        assert client.post("/api/cron", json={"intervalo_horas": 0.01}).status_code == 400
        assert client.post("/api/cron", json={"intervalo_horas": 200}).status_code == 400
        assert client.post("/api/cron", json={"intervalo_horas": "abc"}).status_code == 400
        print("  OK: /api/cron input bounds and types strictly validated [0.1, 168]")

        # 5.3 POST /api/cron update
        r_up = client.post("/api/cron", json={"ativo": True, "intervalo_horas": 3.0})
        assert r_up.status_code == 200
        assert r_up.json()["ativo"] is True
        assert r_up.json()["intervalo_horas"] == 3.0
        assert r_up.json()["intervalo_minutos"] == 180
        assert r_up.json()["proxima_execucao"] is not None
        assert obter_intervalo_cron(cfg_p) == 3.0
        print("  OK: /api/cron active scheduling and sync to config.yaml verified")

        # 5.4 GET /api/ciclo/status live progressive search fields
        r_status = client.get("/api/ciclo/status")
        assert r_status.status_code == 200
        d_status = r_status.json()
        for field in ["rodando", "ultimo_ciclo", "erro", "mensagem", "iniciado_em", "consultas_feitas", "ofertas_encontradas", "fonte_atual", "diagnostico"]:
            assert field in d_status, f"Missing live progress field in /api/ciclo/status: {field}"
        print("  OK: /api/ciclo/status progressive search telemetry fields verified")

    print("\n============================================================")
    print("ALL QA SECURITY, COMPLIANCE, AND AUDIT CHECKS PASSED!")

if __name__ == "__main__":
    run_audit()
