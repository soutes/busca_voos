"""Sincroniza os arquivos de src/busca_voos para vs_win e vs_linux e valida integridade SHA256."""
import hashlib
import os
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
src_base = RAIZ / "src" / "busca_voos"
destinations = [
    RAIZ / "vs_win" / "src" / "busca_voos",
    RAIZ / "vs_linux" / "src" / "busca_voos",
]

print("=== 1. SINCRONIZANDO ARQUIVOS ===")
for dest in destinations:
    print(f"Destino: {dest.relative_to(RAIZ)}")
    for src_file in src_base.rglob("*"):
        if src_file.is_file() and "__pycache__" not in str(src_file):
            rel = src_file.relative_to(src_base)
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, target)
            print(f"  Copiado: {rel}")

# Sincroniza scripts operacionais e documentacao
shutil.copy2(RAIZ / "atualizar.bat", RAIZ / "vs_win" / "atualizar.bat")
print("Copiado: atualizar.bat -> vs_win/atualizar.bat")

shutil.copy2(RAIZ / "atualizar.sh", RAIZ / "vs_linux" / "atualizar.sh")
print("Copiado: atualizar.sh -> vs_linux/atualizar.sh")

shutil.copy2(RAIZ / "README.md", RAIZ / "vs_win" / "README.md")
print("Copiado: README.md -> vs_win/README.md")

shutil.copy2(RAIZ / "README.md", RAIZ / "vs_linux" / "README.md")
print("Copiado: README.md -> vs_linux/README.md")

# Sincroniza .gitignore com protecao a chaves de segredo
for g_dest in [RAIZ / "vs_win" / ".gitignore", RAIZ / "vs_linux" / ".gitignore"]:
    conteudo_git = g_dest.read_text(encoding="utf-8")
    linhas = [l.strip() for l in conteudo_git.splitlines()]
    adicionados = []
    if ".segredo.key" not in linhas:
        adicionados.append(".segredo.key")
    if "*.key" not in linhas:
        adicionados.append("*.key")
    if adicionados:
        novo = conteudo_git.rstrip() + "\n" + "\n".join(adicionados) + "\n"
        g_dest.write_text(novo, encoding="utf-8")
        print(f"Atualizado {g_dest.relative_to(RAIZ)} com chaves de segredo")

print("\n=== 2. VERIFICANDO INTEGRIDADE SHA256 ===")
def get_hashes(base_dir):
    h = {}
    for r, d, files in os.walk(base_dir):
        if "__pycache__" in r:
            continue
        for f in files:
            p = os.path.join(r, f)
            rel = os.path.relpath(p, base_dir).replace("\\", "/")
            with open(p, "rb") as fp:
                h[rel] = hashlib.sha256(fp.read()).hexdigest()
    return h

src_h = get_hashes(src_base)
print(f"Total de arquivos em src: {len(src_h)}")

all_matched = True
for dest in destinations:
    dest_name = str(dest.relative_to(RAIZ))
    print(f"\nVerificando {dest_name}...")
    target_h = get_hashes(dest)
    
    missing = set(src_h.keys()) - set(target_h.keys())
    extra = set(target_h.keys()) - set(src_h.keys())
    if missing:
        print(f"  FALTANDO: {missing}")
        all_matched = False
    if extra:
        print(f"  EXTRAS: {extra}")
        all_matched = False

    for k in sorted(src_h.keys()):
        h_src = src_h[k]
        h_tgt = target_h.get(k)
        if h_src != h_tgt:
            print(f"  DIVERGENCIA {k}: src={h_src[:10]} {dest_name}={h_tgt[:10] if h_tgt else 'NULO'}")
            all_matched = False
        else:
            print(f"  OK {k}: {h_src[:12]}...")

if not all_matched:
    print("\nERRO: Inconsistência de SHA256 detectada!")
    sys.exit(1)
else:
    print("\nSUCESSO: 100% dos arquivos sincronizados e com hashes SHA256 idênticos!")
