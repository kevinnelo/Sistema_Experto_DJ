"""Consola original, ahora con el motor del documento. No guarda nada en la base.

Uso:
  python3 main.py                       contexto interactivo, sin catálogo
  python3 main.py --catalogo cat.json --actual ID   recomendaciones de canciones
"""
import argparse
import json
from datos import RepositorioConocimiento
from negocio import MotorDJ, CAMPOS_CONTEXTO


def mostrar(resultado):
    if resultado["sin_reglas"]:
        print(resultado["aviso"])
        return
    print("\nReglas disparadas:")
    for r in resultado["reglas_disparadas"]:
        print(f"  {r['codigo']} · {r['conclusion']}")
    for c in resultado["conflictos"]:
        print(f"  CONFLICTO {c['reglas'][0]} vs {c['reglas'][1]}: {c['descripcion']}")
    for rec in resultado["recomendaciones"]:
        print(f"\n[{rec['accion']}] {rec['mensaje']}")
        if rec["filtro"]:
            print(f"  filtro: {rec['filtro']}")
        for n in rec["notas"]:
            print(f"  nota: {n}")
        for c in rec["canciones"]:
            tecnicas = ", ".join(t["nombre"] for t in c["transiciones"])
            print(f"  {c['id']} · {c['titulo']} ({c['artista']}) {c['bpm']} BPM {c['tonalidad_camelot']} "
                  f"energía {c['energia']} → {tecnicas}")


def pedir_contexto(repo):
    contexto = {}
    for variable in CAMPOS_CONTEXTO:
        valores = repo.valores(variable)
        print(f"\n{variable}: {', '.join(valores)}")
        respuesta = input("Respuesta (Enter omite): ").strip()
        while respuesta and respuesta not in valores:
            respuesta = input("Valor inválido. Intente de nuevo: ").strip()
        if respuesta:
            contexto[variable] = respuesta
    return contexto


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalogo", help="JSON con la lista de canciones del DJ")
    parser.add_argument("--actual", help="id de la canción que suena")
    args = parser.parse_args()
    repo = RepositorioConocimiento()
    try:
        motor = MotorDJ(repo)
        catalogo = []
        if args.catalogo:
            with open(args.catalogo, encoding="utf-8") as archivo:
                catalogo = json.load(archivo)
        print("Motor de reglas R01-R27 del documento (sin probabilidades).")
        contexto = pedir_contexto(repo)
        mostrar(motor.recomendar(contexto, catalogo, args.actual))
    except ValueError as error:
        print("Error:", error)
    finally:
        repo.cerrar()
