"""Utilidades compartidas de los clips de Albertesonrrei."""


def frase_lenta(ws, k, max_antes=2.0, max_despues=2.4, pausa=1.0):
    """Tramo (inicio, fin) en segundos de la transcripción para ralentizar la FRASE que contiene la palabra k.

    La frase se corta en los puntos (. ? !) y en las pausas largas; si es muy larga, se queda con
    ~1,4 s antes y ~2,2 s después de la palabra malsonante, siempre en límites de palabra.
    """
    fin_frase = (".", "?", "!", "»")
    i = k
    while i > 0:
        prev = ws[i - 1]
        if prev["text"].strip().endswith(fin_frase) or ws[i]["start"] - prev["end"] > pausa:
            break
        if ws[k]["start"] - prev["start"] > max_antes:
            break
        i -= 1
    j = k
    while j < len(ws) - 1:
        if ws[j]["text"].strip().endswith(fin_frase) or ws[j + 1]["start"] - ws[j]["end"] > pausa:
            break
        if ws[j + 1]["end"] - ws[k]["end"] > max_despues:
            break
        j += 1
    return ws[i]["start"], ws[j]["end"], i, j
