"""Test data for historical spelling (specs/001-historical-spelling).

Shared by tests/unit/test_bm25.py and devtools/measure_historical_spelling.py.
"""

# The spec's 28 pairs (specs/001-historical-spelling): a word as readers type it today, and as the
# benchmark's edition of Quincas Borba prints it.
PAIRS = [
    ("sofia", "sophia"),
    ("ele", "elle"),
    ("ela", "ella"),
    ("eles", "elles"),
    ("benedita", "benedicta"),
    ("teófilo", "theophilo"),
    ("comissão", "commissão"),
    ("frase", "phrase"),
    ("marquês", "marquez"),
    ("diretor", "director"),
    ("apesar", "apezar"),
    ("teresa", "thereza"),
    ("filósofo", "philosopho"),
    ("cupê", "coupé"),
    ("ano", "anno"),
    ("fato", "facto"),
    ("ofício", "officio"),
    ("aparecer", "apparecer"),
    ("cena", "scena"),
    ("compreendê", "comprehende"),
    ("alegoria", "allegoria"),
    ("assinasse", "assignasse"),
    ("tipográfico", "typographico"),
    ("constelação", "constellação"),
    ("alegando", "allegando"),
    ("tipo", "typo"),
    ("catástrofes", "catastrophes"),
    ("súdito", "subdito"),
]

# Different modern words that must stay apart: the known ones, then one per pattern that needed
# words left as they are. Three known ones (sessão, seção and cessão; selo and zelo) touch no pattern
# today: they would catch a new one that did, such as ss -> s or z -> s at the start of a word.
COLLISIONS = [
    ("facção", "facão"),
    ("pacto", "pato"),
    ("sessão", "seção"),
    ("seção", "cessão"),
    ("signo", "sino"),
    ("coser", "cozer"),
    ("selo", "zelo"),
    ("gnomo", "nome"),
    ("garoupa", "garupa"),
    ("Mathias", "mate"),
    ("Levy", "leva"),
    ("Bello", "bel"),
    ("espectador", "espetar"),
    ("compacta", "compatível"),
    ("cacto", "catar"),
    ("magna", "man"),
    ("abdicai", "adição"),
    ("reze", "rês"),
    ("Bahamas", "Baamas"),
]
