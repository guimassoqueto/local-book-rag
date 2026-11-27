"""The benchmarks, their metrics and their judges.

RAGAS posts usage analytics to its authors (t.explodinggradients.com) when a judge is built and on
each embedding request, unless RAGAS_DO_NOT_TRACK is "true". Nothing may contact a third party
nobody chose (constitution, Principle I). Every module that imports RAGAS is in this package, so
this runs first, before RAGAS reads the switch, which it reads once and caches. It is set
outright, so that a value left in the environment can't turn the analytics back on.
docs/decisions.md (Evaluation) records why it is set here and not in the Dockerfile.
"""

import os

os.environ["RAGAS_DO_NOT_TRACK"] = "true"
