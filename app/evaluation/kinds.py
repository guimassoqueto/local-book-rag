"""The kinds of experiment the benchmark runs.

The runner and the report share them. The report reads them from here because `benchmark-report`
must not load the runner's stack, which imports the whole application to render a Markdown table.
"""

from typing import Literal, get_args

ExperimentKind = Literal["retrieval", "generation", "summarization", "performance"]

EXPERIMENT_KINDS: tuple[str, ...] = get_args(ExperimentKind)
