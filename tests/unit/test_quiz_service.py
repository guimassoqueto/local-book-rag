import json
import random
import re
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.errors import (
    BookNotFoundError,
    ChapterNotFoundError,
    ConfigurationError,
    GenerationError,
    NothingToAskError,
    NothingToSearchError,
    QuizAlreadyGradedError,
    ServiceUnavailableError,
)
from app.generation.quiz import QuizWriter
from app.services.quiz_service import (
    Question,
    QuestionReady,
    Quiz,
    QuizReady,
    QuizService,
    QuizStarted,
    QuizState,
    Scope,
)
from app.storage.catalog import Book, BookCatalog, BookStatus
from tests.fakes import FakeChunks, FakeLLM, make_chunk

SKIP = '{"skip": "Só lista referências bibliográficas."}'
UNREADABLE = "Não consigo."
MARKER = re.compile(r"\bm(\d{3})\b")


def draft_for(marker):
    return json.dumps(
        {
            "question": f"Segundo o autor, o que explica o caso {marker} discutido no livro?",
            "correct": f"A explicação certa do caso {marker}, que o autor defende com dados.",
            "wrong": [
                f"Uma explicação errada de número {n} para o caso {marker}, que o autor rejeita." for n in range(4)
            ],
            "explanation": f"O autor explica o caso {marker} com dados sobre salários e preços.",
        },
        ensure_ascii=False,
    )


class Script:
    """The writer's replies, by passage marker: the listed ones in order, then drafts.

    Args:
        replies: marker → replies for its first attempts.
        skipping: markers whose passage is always skipped.
        failure: raised on every call.
    """

    def __init__(self, replies=None, skipping=(), failure=None):
        self.replies = {marker: list(queue) for marker, queue in (replies or {}).items()}
        self.skipping = set(skipping)
        self.failure = failure
        self.asked = []

    def __call__(self, messages, parameters):
        if self.failure:
            raise self.failure
        marker = MARKER.search(messages[-1].content).group()
        self.asked.append(marker)
        if marker in self.skipping:
            return SKIP
        queue = self.replies.get(marker)
        if queue:
            return queue.pop(0)
        return draft_for(marker)


def book(status=BookStatus.INDEXED, language="pt", book_id="book_001"):
    return Book(
        book_id=book_id,
        title="História econômica global",
        author="Robert C. Allen",
        original_filename="b.pdf",
        original_path="x",
        checksum="c",
        format="pdf",
        language=language,
        chapter_count=3,
        chunk_count=1,
        embedding_model="m",
        index_version=1,
        status=status,
        status_detail=None,
        revision=1,
        created_at="now",
        indexed_at="now",
    )


def chapter(number, count, words=100, start=0, title=None):
    """A chapter of `count` passages of `words` words each, marked m<global index>."""
    chunks = []
    for index in range(start, start + count):
        chunk = make_chunk(
            f"m{index:03d} " + " ".join(["palavra"] * (words - 1)),
            index=index,
            chapter=number,
            page_start=10 + index,
            language="pt",
        )
        title_of_chapter = title or f"Capítulo {number}"
        chunks.append(replace(chunk, chapter_title=title_of_chapter, book_title="História econômica global"))
    return chunks


def chapter_of_words(number, count, total_words):
    """A chapter whose passages hold `total_words` words in all."""
    sizes = [total_words // count + (1 if index < total_words % count else 0) for index in range(count)]
    chunks = []
    for index, size in enumerate(sizes):
        chunks.extend(chapter(number, 1, words=size, start=index))
    return chunks


@pytest.fixture
def catalog(tmp_path):
    catalog = BookCatalog(tmp_path / "catalog.db")
    catalog.add(book())
    return catalog


class Lab:
    def __init__(self, settings, catalog, chunks, tmp_path, script=None, checker=None, **config):
        self.config = settings.generation.quiz.model_copy(update=config)
        self.script = script or Script()
        self.llm = FakeLLM(respond=self.script)
        self.checker = checker
        self.chunks = FakeChunks(chunks)
        self.writer = QuizWriter(self.config, 0.1, self.llm, checker)
        self.downloads = tmp_path / "downloads"
        self.service = QuizService(
            self.config, settings.generation.response_languages, catalog, self.chunks, self.writer, self.downloads
        )

    def events(self, chapter=1, count=None, seed=0, language=None):
        count = count if count is not None else self.service.default_count("book_001", chapter)
        return list(self.service.prepare("book_001", chapter, count, language=language, seed=seed))

    def quiz(self, chapter=1, count=None, seed=0):
        events = self.events(chapter, count, seed)
        assert isinstance(events[-1], QuizReady)
        return events[-1].quiz


@pytest.fixture
def lab(settings, catalog, tmp_path):
    def build(chunks, script=None, checker=None, **config):
        return Lab(settings, catalog, chunks, tmp_path, script, checker, **config)

    return build


def index_in_chapter(question, chunks):
    ordered = sorted(
        (chunk for chunk in chunks if chunk.chapter_number == question.passage.chapter_number),
        key=lambda chunk: chunk.chunk_index,
    )
    return [chunk.chunk_id for chunk in ordered].index(question.passage.chunk_id)


def strata(total, count):
    """Which stratum each of `total` passages falls in, for `count` contiguous strata."""
    bounds = [-(-stratum * total // count) for stratum in range(count + 1)]
    return [next(s for s in range(count) if bounds[s] <= index < bounds[s + 1]) for index in range(total)]


# Scope and counts (T013)


def test_the_limit_is_the_chapters_passages(lab):
    assert lab(chapter(1, 13)).service.limit("book_001", 1) == 13


def test_the_limit_is_capped_by_max_questions(lab):
    assert lab(chapter(1, 60)).service.limit("book_001", 1) == 50


def test_the_whole_books_limit_counts_every_passage(lab):
    chunks = chapter(1, 13) + chapter(2, 20, start=13)

    assert lab(chunks).service.limit("book_001", None) == 33


@pytest.mark.parametrize(("words", "expected"), [(3115, 10), (5010, 17), (9757, 20), (3150, 11), (100, 1), (10, 1)])
def test_the_default_count_follows_the_chapters_words(lab, words, expected):
    service = lab(chapter_of_words(1, 40, words)).service

    assert service.default_count("book_001", 1) == expected


def test_the_default_count_never_exceeds_the_limit(lab):
    assert lab(chapter_of_words(1, 4, 3115)).service.default_count("book_001", 1) == 4


@pytest.mark.parametrize("status", [BookStatus.PROCESSING, BookStatus.FAILED, BookStatus.PENDING, BookStatus.REMOVING])
def test_a_book_that_isnt_indexed_is_refused(settings, tmp_path, status):
    catalog = BookCatalog(tmp_path / "catalog.db")
    catalog.add(book(status=status))
    service = Lab(settings, catalog, chapter(1, 13), tmp_path).service

    with pytest.raises(NothingToSearchError, match=status.value):
        service.limit("book_001", 1)


def test_a_book_being_reindexed_can_be_quizzed(settings, tmp_path):
    catalog = BookCatalog(tmp_path / "catalog.db")
    catalog.add(book(status=BookStatus.REINDEXING))

    assert Lab(settings, catalog, chapter(1, 13), tmp_path).service.limit("book_001", 1) == 13


def test_an_unknown_book_is_refused(lab):
    with pytest.raises(BookNotFoundError):
        lab(chapter(1, 13)).service.limit("book_999", 1)


def test_an_unknown_chapter_is_refused(lab):
    with pytest.raises(ChapterNotFoundError):
        lab(chapter(1, 13)).service.default_count("book_001", 7)


@pytest.mark.parametrize("count", [0, 14])
def test_a_count_outside_the_limit_is_refused(lab, count):
    with pytest.raises(ConfigurationError, match="1 and 13"):
        lab(chapter(1, 13)).events(count=count)


def test_a_book_without_a_language_needs_one_chosen(settings, tmp_path):
    catalog = BookCatalog(tmp_path / "catalog.db")
    catalog.add(book(language=None))
    quiz_lab = Lab(settings, catalog, chapter(1, 13), tmp_path)

    with pytest.raises(ConfigurationError, match="language"):
        quiz_lab.events(count=3)
    assert isinstance(quiz_lab.events(count=3, language="Portuguese")[-1], QuizReady)


def test_a_language_outside_the_offered_ones_is_refused(lab):
    with pytest.raises(ConfigurationError, match="Klingon"):
        lab(chapter(1, 13)).events(count=3, language="Klingon")


def test_the_language_is_the_books_by_default(lab):
    assert lab(chapter(1, 13)).quiz(count=3).language == "Portuguese"


# Passages, letters and order (T014)


@pytest.mark.parametrize("count", range(1, 14))
def test_each_question_comes_from_its_own_stratum(lab, count):
    chunks = chapter(1, 13)
    for seed in range(15):
        quiz = lab(chunks).quiz(count=count, seed=seed)
        layout = strata(13, count)

        assert len(quiz.questions) == count
        assert sorted(layout[index_in_chapter(q, chunks)] for q in quiz.questions) == list(range(count))


@pytest.mark.parametrize("count", range(3, 14))
def test_every_third_of_the_chapter_has_a_question(lab, count):
    chunks = chapter(1, 13)
    for seed in range(30):
        quiz = lab(chunks).quiz(count=count, seed=seed)

        assert {3 * index_in_chapter(q, chunks) // 13 for q in quiz.questions} == {0, 1, 2}


@pytest.mark.parametrize("count", range(1, 14))
def test_the_letters_are_balanced(lab, count):
    for seed in range(15):
        quiz = lab(chapter(1, 13)).quiz(count=count, seed=seed)
        keys = Counter(question.key for question in quiz.questions)

        assert all(count // 5 <= keys[letter] <= -(-count // 5) for letter in "ABCDE")


def test_every_letter_is_the_key_somewhere_over_many_quizzes(lab):
    quizzes = [lab(chapter(1, 13)).quiz(count=3, seed=seed) for seed in range(20)]
    keys = Counter(question.key for quiz in quizzes for question in quiz.questions)

    assert set(keys) == set("ABCDE")


@pytest.mark.parametrize("count", range(2, 14))
def test_the_order_is_never_the_texts(lab, count):
    chunks = chapter(1, 13)
    for seed in range(30):
        quiz = lab(chunks).quiz(count=count, seed=seed)
        indexes = [index_in_chapter(question, chunks) for question in quiz.questions]

        assert indexes != sorted(indexes)


def test_the_right_answer_sits_at_its_key_and_the_wrong_ones_elsewhere(lab):
    quiz = lab(chapter(1, 13)).quiz(count=10)

    for question in quiz.questions:
        marker = MARKER.search(question.passage.text).group()
        letter_index = "ABCDE".index(question.key)
        assert question.options[letter_index].startswith(f"A explicação certa do caso {marker}")
        assert sum(option.startswith("Uma explicação errada") for option in question.options) == 4


def test_positions_count_from_one_in_order(lab):
    quiz = lab(chapter(1, 13)).quiz(count=10)

    assert [question.position for question in quiz.questions] == list(range(1, 11))


def test_the_same_seed_gives_the_same_quiz(lab):
    chunks = chapter(1, 13)

    first = lab(chunks).quiz(count=7, seed=42)
    second = lab(chunks).quiz(count=7, seed=42)

    def layout(quiz):
        return [(q.passage.chunk_id, q.key, q.options) for q in quiz.questions]

    assert layout(first) == layout(second)


def test_without_a_seed_quizzes_differ(lab):
    chunks = chapter(1, 13)

    layouts = {tuple(q.passage.chunk_id for q in lab(chunks).quiz(count=5, seed=None).questions) for _ in range(10)}

    assert len(layouts) > 1


def test_the_seed_reaches_the_model(lab):
    quiz_lab = lab(chapter(1, 13))

    quiz_lab.quiz(count=3, seed=100)

    assert [call[1].seed for call in quiz_lab.llm.calls] == [100, 101, 102]


# Preparing (T015)


def test_events_come_in_order(lab):
    events = lab(chapter(1, 13)).events(count=4)

    assert isinstance(events[0], QuizStarted)
    assert (events[0].asked, events[0].limit, events[0].book_title, events[0].chapter_title) == (
        4,
        13,
        "História econômica global",
        "Capítulo 1",
    )
    ready = events[1:-1]
    assert all(isinstance(event, QuestionReady) for event in ready)
    assert [event.question.position for event in ready] == [1, 2, 3, 4]
    assert [event.ready for event in ready] == [1, 2, 3, 4]
    assert isinstance(events[-1], QuizReady)
    assert events[-1].quiz.questions == tuple(event.question for event in ready)
    assert events[-1].quiz.state == QuizState.READY
    assert events[-1].shortfall == 0


def test_the_quiz_records_what_made_it(lab):
    quiz = lab(chapter(1, 13)).quiz(count=3)

    assert quiz.scope.book_id == "book_001"
    assert quiz.scope.chapter_number == 1
    assert (quiz.book_title, quiz.chapter_title, quiz.writer, quiz.checker, quiz.asked) == (
        "História econômica global",
        "Capítulo 1",
        "fake-llm",
        None,
        3,
    )
    assert quiz.prepared_at.tzinfo is not None


def test_a_refused_draft_is_written_again_then_its_stratum_is_used(lab):
    chunks = chapter(1, 13)
    clean = lab(chunks)
    clean_quiz = clean.quiz(count=2, seed=5)
    first = clean.script.asked[0]
    script = Script(replies={first: [UNREADABLE, '{"question": "", "correct": "x"}', "```nada```"]})

    events = lab(chunks, script).events(count=2, seed=5)

    assert script.asked[:3] == [first] * 3
    replacement = script.asked[3]
    assert replacement != first
    layout = strata(13, 2)
    first_index = int(first[1:])
    replacement_index = int(replacement[1:])
    assert layout[replacement_index] == layout[first_index]
    question = events[1].question
    assert question.position == 1
    assert question.key == clean_quiz.questions[0].key
    assert events[1].attempts == 4
    assert events[1].refusals == {"unreadable": 2, "blank_field": 1}


def test_a_passage_whose_stratum_is_used_up_gives_way_to_the_nearest(lab):
    chunks = chapter(1, 3)
    clean = lab(chunks)
    clean.quiz(count=2, seed=1)
    first = clean.script.asked[0]
    script = Script(replies={first: [UNREADABLE] * 3})

    events = lab(chunks, script).events(count=2, seed=1)

    replacement = script.asked[3]
    assert replacement not in (first, clean.script.asked[1])
    assert events[-1].shortfall == 0


def test_every_refusal_and_skip_is_counted(lab):
    chunks = chapter(1, 13)
    clean = lab(chunks)
    clean.quiz(count=3, seed=2)
    second = clean.script.asked[1]
    third = clean.script.asked[2]
    script = Script(replies={second: [UNREADABLE], third: [SKIP]})

    events = lab(chunks, script).events(count=3, seed=2)

    ready = [event for event in events if isinstance(event, QuestionReady)]
    assert [event.attempts for event in ready] == [1, 2, 2]
    assert [event.refusals for event in ready] == [{}, {"unreadable": 1}, {}]
    assert events[-1].skipped_passages == 1
    assert events[-1].passed_over_passages == 0
    assert events[-1].ruled_out_chapters == ()


def test_a_passage_too_long_is_passed_over_and_counted_apart(lab):
    chunks = chapter(1, 13)
    long_passage = chunks[4]
    chunks[4] = replace(long_passage, text=long_passage.text + " palavra" * 8000)

    events = lab(chunks).events(count=13, seed=0)

    assert events[-1].passed_over_passages == 1
    assert events[-1].shortfall == 1
    assert all(sum(event.refusals.values()) == 0 for event in events if isinstance(event, QuestionReady))


def test_a_chapter_whose_first_two_passages_are_skipped_has_nothing_to_ask(lab):
    chunks = chapter(1, 13)
    script = Script(skipping={f"m{index:03d}" for index in range(13)})

    with pytest.raises(NothingToAskError):
        lab(chunks, script).events(count=5)
    assert len(script.asked) == 2


def test_skips_after_a_question_is_ready_are_replaced(lab):
    chunks = chapter(1, 13)
    clean = lab(chunks)
    clean.quiz(count=3, seed=3)
    asked = clean.script.asked
    script = Script(skipping={asked[1], asked[2]})

    events = lab(chunks, script).events(count=3, seed=3)

    assert isinstance(events[-1], QuizReady)
    assert len(events[-1].quiz.questions) == 3
    assert events[-1].skipped_passages >= 2


def test_one_skip_then_a_question_keeps_the_chapter(lab):
    chunks = chapter(1, 13)
    clean = lab(chunks)
    clean.quiz(count=3, seed=4)
    script = Script(skipping={clean.script.asked[0]})

    events = lab(chunks, script).events(count=3, seed=4)

    assert len(events[-1].quiz.questions) == 3
    assert events[-1].skipped_passages == 1


def test_running_out_of_passages_leaves_a_counted_shortfall(lab):
    chunks = chapter(1, 3)
    clean = lab(chunks)
    clean.quiz(count=3, seed=0)
    script = Script(replies={clean.script.asked[2]: [UNREADABLE] * 3})

    events = lab(chunks, script).events(count=3, seed=0)

    assert events[-1].shortfall == 1
    assert len(events[-1].quiz.questions) == 2
    assert [question.position for question in events[-1].quiz.questions] == [1, 2]


def test_a_preparation_that_writes_nothing_fails(lab):
    script = Script(replies={f"m{index:03d}": [UNREADABLE] * 3 for index in range(3)})

    with pytest.raises(GenerationError, match="no question"):
        lab(chapter(1, 3), script).events(count=3)


def test_closing_the_stream_stops_at_once(lab):
    quiz_lab = lab(chapter(1, 13))
    stream = quiz_lab.service.prepare("book_001", 1, 10, seed=0)

    next(stream)
    next(stream)
    next(stream)
    stream.close()

    assert len(quiz_lab.llm.calls) == 2


def test_a_provider_error_ends_the_stream(lab):
    script = Script(failure=ServiceUnavailableError("Ollama is down."))
    stream = lab(chapter(1, 13), script).service.prepare("book_001", 1, 5, seed=0)

    assert isinstance(next(stream), QuizStarted)
    with pytest.raises(ServiceUnavailableError):
        next(stream)


def test_the_chunks_are_read_once_and_nothing_is_written(lab, catalog, tmp_path):
    quiz_lab = lab(chapter(1, 13))
    before = catalog.get("book_001")
    files_before = sorted(path for path in tmp_path.rglob("*") if "downloads" not in path.parts)

    list(quiz_lab.service.prepare("book_001", 1, 10, seed=0))

    assert quiz_lab.chunks.loads == 1
    assert catalog.get("book_001") == before
    assert sorted(path for path in tmp_path.rglob("*") if "downloads" not in path.parts) == files_before


def test_the_writer_gets_the_book_its_author_and_the_chapter_title(lab):
    quiz_lab = lab(chapter(1, 13, title="Capítulo 1: A grande divergência"))

    quiz_lab.quiz(count=2)

    prompt = quiz_lab.llm.calls[0][0][-1].content
    assert "A grande divergência" in prompt
    assert "Robert C. Allen" in prompt


# Grading (T016)


def answers_for(quiz, right):
    """Answers with the first `right` questions right and the rest wrong."""
    wrong = {letter: next(other for other in "ABCDE" if other != letter) for letter in "ABCDE"}
    return [q.key if index < right else wrong[q.key] for index, q in enumerate(quiz.questions)]


@pytest.mark.parametrize(("count", "right"), [(10, 7), (3, 1), (7, 7), (13, 0)])
def test_the_score_is_counted_exactly(lab, count, right):
    quiz_lab = lab(chapter(1, 13))
    quiz = quiz_lab.quiz(count=count)

    result = quiz_lab.service.grade(quiz, answers_for(quiz, right))

    assert result.score == 100 * right / count
    assert result.right == tuple(index < right for index in range(count))


def test_an_unanswered_question_is_wrong(lab):
    quiz_lab = lab(chapter(1, 13))
    quiz = quiz_lab.quiz(count=4)
    answers = [question.key for question in quiz.questions]
    answers[2] = None

    result = quiz_lab.service.grade(quiz, answers)

    assert result.right == (True, True, False, True)
    assert result.score == 75
    assert result.answers[2] is None


@pytest.mark.parametrize("length", [3, 5])
def test_answers_of_the_wrong_length_are_refused(lab, length):
    quiz_lab = lab(chapter(1, 13))
    quiz = quiz_lab.quiz(count=4)

    with pytest.raises(ConfigurationError):
        quiz_lab.service.grade(quiz, ["A"] * length)


def test_a_graded_quiz_cannot_be_graded_again(lab):
    quiz_lab = lab(chapter(1, 13))
    quiz = quiz_lab.quiz(count=4)

    result = quiz_lab.service.grade(quiz, [None] * 4)

    assert result.quiz.state == QuizState.GRADED
    assert quiz.state == QuizState.READY
    with pytest.raises(QuizAlreadyGradedError, match="new quiz"):
        quiz_lab.service.grade(result.quiz, [None] * 4)


def test_a_one_chapter_quiz_has_no_ranking(lab):
    quiz_lab = lab(chapter(1, 13))
    quiz = quiz_lab.quiz(count=4)

    assert quiz_lab.service.grade(quiz, [None] * 4).ranking == ()


def test_grading_records_when(lab):
    quiz_lab = lab(chapter(1, 13))
    quiz = quiz_lab.quiz(count=2)

    assert quiz_lab.service.grade(quiz, [None, None]).submitted_at.tzinfo is not None


def test_the_random_module_is_left_alone(lab):
    state = random.getstate()

    lab(chapter(1, 13)).quiz(count=5, seed=None)

    assert random.getstate() == state


# The whole book (T037)


def book_of(sizes, words=100):
    """Chapters of the given numbers of passages, numbered from 1."""
    chunks, start = [], 0
    for number, size in enumerate(sizes, start=1):
        chunks.extend(chapter(number, size, words=words, start=start))
        start += size
    return chunks


def per_chapter(quiz):
    return Counter(question.passage.chapter_number for question in quiz.questions)


def shares(chunks, count, chapters):
    words = {number: sum(len(c.text.split()) for c in chunks if c.chapter_number == number) for number in chapters}
    total = sum(words.values())
    return {number: count * words[number] / total for number in chapters}


@pytest.mark.parametrize("count", [1, 2, 5, 9, 14, 20, 33])
def test_each_chapter_gets_its_share_of_the_book_within_one(lab, count):
    chunks = book_of([13, 20, 5, 9]) + chapter(5, 6, words=150, start=47)  # passages of about one size, as chunks are
    for seed in range(8):
        quiz = lab(chunks).quiz(chapter=None, count=count, seed=seed)
        counted = per_chapter(quiz)

        assert len(quiz.questions) == count
        for number, share in shares(chunks, count, range(1, 6)).items():
            assert abs(counted[number] - share) < 1


def test_a_chapter_gets_no_more_questions_than_it_has_passages(lab):
    chunks = book_of([10]) + chapter(2, 2, words=2000, start=10)

    quiz = lab(chunks).quiz(chapter=None, count=12, seed=0)

    assert per_chapter(quiz) == {1: 10, 2: 2}


def test_a_ruled_out_chapter_hands_its_questions_to_the_others(lab):
    chunks = book_of([13, 20, 5, 9])
    script = Script(skipping={f"m{index:03d}" for index in range(13, 33)})  # chapter 2

    events = lab(chunks, script).events(chapter=None, count=12, seed=1)

    final = events[-1]
    assert final.ruled_out_chapters == (2,)
    assert len(final.quiz.questions) == 12
    counted = per_chapter(final.quiz)
    assert counted[2] == 0
    for number, share in shares(chunks, 12, (1, 3, 4)).items():
        assert abs(counted[number] - share) < 1


def test_a_chapter_whose_passages_run_out_hands_its_questions_on(lab):
    chunks = chapter(1, 20) + chapter(2, 1, words=400, start=20) + chapter(3, 20, start=21)
    script = Script(skipping={"m020"})

    events = lab(chunks, script).events(chapter=None, count=11, seed=0)

    final = events[-1]
    assert len(final.quiz.questions) == 11
    assert per_chapter(final.quiz)[2] == 0
    assert final.ruled_out_chapters == ()  # one skip doesn't rule it out: it ran out
    assert final.skipped_passages == 1


def test_a_moved_question_keeps_its_place_and_letter(lab):
    chunks = book_of([13, 20, 5, 9])
    clean = lab(chunks).events(chapter=None, count=12, seed=1)
    script = Script(skipping={f"m{index:03d}" for index in range(13, 33)})

    moved = lab(chunks, script).events(chapter=None, count=12, seed=1)

    def letters(events):
        return [event.question.key for event in events if isinstance(event, QuestionReady)]

    assert letters(moved) == letters(clean)


def naming_its_chapter(chunks):
    """Writes a question naming its passage's chapter on the first attempt at each passage, then not."""
    chapters = {f"m{chunk.chunk_index:03d}": chunk.chapter_number for chunk in chunks}
    named = set()

    def respond(messages, parameters):
        marker = MARKER.search(messages[-1].content).group()
        reply = json.loads(draft_for(marker))
        if marker not in named:
            named.add(marker)
            reply["question"] = f"No Capítulo {chapters[marker]}, o que explica o caso {marker}?"
        return json.dumps(reply, ensure_ascii=False)

    return respond


def test_a_whole_book_question_may_not_name_its_chapter(settings, catalog, tmp_path):
    chunks = book_of([4, 4])
    quiz_lab = Lab(settings, catalog, chunks, tmp_path)
    quiz_lab.llm.respond = naming_its_chapter(chunks)

    events = quiz_lab.events(chapter=None, count=2, seed=0)

    ready = [event for event in events if isinstance(event, QuestionReady)]
    assert [event.refusals for event in ready] == [{"passage_reference": 1}] * 2


def test_a_one_chapter_question_may_name_its_chapter(settings, catalog, tmp_path):
    chunks = book_of([4, 4])
    quiz_lab = Lab(settings, catalog, chunks, tmp_path)
    quiz_lab.llm.respond = naming_its_chapter(chunks)

    events = quiz_lab.events(chapter=1, count=2, seed=0)

    ready = [event for event in events if isinstance(event, QuestionReady)]
    assert [event.refusals for event in ready] == [{}, {}]
    assert ready[0].question.text.startswith("No Capítulo 1")


def test_the_writer_gets_no_chapter_title_in_a_whole_book_quiz(lab):
    quiz_lab = lab(book_of([4, 4]))

    quiz_lab.quiz(chapter=None, count=2)

    assert all("Capítulo" not in call[0][-1].content for call in quiz_lab.llm.calls)


def graded_tallies(service, answers_by_chapter):
    """A whole-book quiz, graded with each chapter's questions answered as listed, in order."""
    questions = []
    for number, answers in answers_by_chapter.items():
        for answer in answers:
            passage = replace(make_chunk(index=len(questions), chapter=number), chapter_title=f"Capítulo {number}")
            questions.append((Question(len(questions) + 1, "Q?", tuple("abcde"), "A", "E.", passage), answer))
    quiz = Quiz(
        Scope("book_001", None), "B", None, "Portuguese", "w", None, len(questions),
        tuple(question for question, _ in questions), datetime.now(UTC), QuizState.READY,
    )  # fmt: skip
    return service.grade(quiz, [answer for _, answer in questions]).ranking


def test_the_ranking_orders_chapters_by_questions_missed(lab):
    service = lab(chapter(1, 13)).service

    ranking = graded_tallies(service, {1: ["A", "B"], 2: ["B", "B", "B"], 3: ["A", "A"]})

    tallies = [(tally.chapter_number, tally.questions, tally.missed) for tally in ranking]
    assert tallies == [(2, 3, 3), (1, 2, 1), (3, 2, 0)]
    assert ranking[0].chapter_title == "Capítulo 2"


def test_ties_go_to_the_larger_share_missed_then_to_book_order(lab):
    service = lab(chapter(1, 13)).service

    ranking = graded_tallies(service, {1: ["B", "A", "A"], 2: ["A", "B"], 3: [None, "A"], 4: ["A"]})

    assert [tally.chapter_number for tally in ranking] == [2, 3, 1, 4]


# The result document and its download (T041)


def graded(quiz_lab, chapter=1, count=3, answers=None):
    quiz = quiz_lab.quiz(chapter=chapter, count=count)
    answers = answers if answers is not None else [question.key for question in quiz.questions]
    return quiz_lab.service.grade(quiz, answers)


def test_the_documents_name_says_book_chapter_and_time(lab):
    quiz_lab = lab(book_of([5, 5]))

    one_chapter, _ = quiz_lab.service.result_document(graded(quiz_lab, chapter=2))
    whole_book, _ = quiz_lab.service.result_document(graded(quiz_lab, chapter=None))

    assert re.fullmatch(r"quiz-book_001-ch02-\d{8}T\d{6}Z\.md", one_chapter)
    assert re.fullmatch(r"quiz-book_001-\d{8}T\d{6}Z\.md", whole_book)


def test_a_one_chapter_document_holds_everything_the_contract_lists(lab):
    quiz_lab = lab(book_of([5, 5]))
    result = graded(quiz_lab, chapter=2, count=3)
    quiz = result.quiz

    _, document = quiz_lab.service.result_document(result)

    assert document.startswith("# Quiz: História econômica global, Capítulo 2\n")
    assert f"- **Taken**: {result.submitted_at:%Y-%m-%d %H:%M} UTC" in document
    assert "- **Book**: História econômica global (book_001)" in document
    assert "- **Chapter**: Capítulo 2" in document
    assert "- **Language**: Portuguese" in document
    assert "- **Written by**: fake-llm\n" in document
    assert "- **Score**: 3 of 3 (100%)" in document
    assert "## Chapters to reread" not in document
    for question in quiz.questions:
        assert f"### {question.position}. {question.text}" in document
        for letter, option in zip("ABCDE", question.options, strict=True):
            assert f"- {letter}) {option}" in document
        assert f"**Your answer**: {question.key} · **Right answer**: {question.key} ✓" in document
        assert question.explanation in document
    assert document.index("### 1.") < document.index("### 2.") < document.index("### 3.")


def test_a_whole_book_document_ranks_the_chapters(lab):
    quiz_lab = lab(book_of([5, 5]))
    quiz = quiz_lab.quiz(chapter=None, count=4)
    answers = [None if question.passage.chapter_number == 1 else question.key for question in quiz.questions]

    _, document = quiz_lab.service.result_document(quiz_lab.service.grade(quiz, answers))

    assert document.startswith("# Quiz: História econômica global\n")
    assert "- **Chapter**" not in document
    assert "## Chapters to reread" in document
    assert "| Capítulo 1 | 2 | 2 |" in document
    assert "| Capítulo 2 | 2 | 0 |" in document


def test_an_unanswered_question_says_so_in_the_document(lab):
    quiz_lab = lab(chapter(1, 13))
    result = graded(quiz_lab, count=2, answers=[None, None])

    _, document = quiz_lab.service.result_document(result)

    assert document.count("**Your answer**: not answered") == 2
    assert "✗" in document


def test_the_checker_appears_only_when_the_check_was_on(lab):
    quiz_lab = lab(chapter(1, 13))
    result = graded(quiz_lab, count=2)
    checked = replace(result, quiz=replace(result.quiz, checker="checker-model"))

    assert "checked by" not in quiz_lab.service.result_document(result)[1]
    assert "- **Written by**: fake-llm; **checked by**: checker-model" in quiz_lab.service.result_document(checked)[1]


def test_passages_appear_as_references_not_text(lab):
    quiz_lab = lab(chapter(1, 13))
    result = graded(quiz_lab, count=3)

    _, document = quiz_lab.service.result_document(result)

    for question in result.quiz.questions:
        passage = question.passage
        assert passage.text not in document
        pages = f"p. {passage.page_start}"
        assert f"*Source*: Capítulo 1, Section, {pages}" in document


def test_export_writes_the_document_into_the_download_directory(lab):
    quiz_lab = lab(chapter(1, 13))
    result = graded(quiz_lab, count=2)

    path = quiz_lab.service.export(result)

    name, document = quiz_lab.service.result_document(result)
    assert path == quiz_lab.downloads / name
    assert path.read_text(encoding="utf-8") == document
    assert list(quiz_lab.downloads.iterdir()) == [path]


def test_preparing_another_quiz_empties_the_download_directory(lab):
    quiz_lab = lab(chapter(1, 13))
    path = quiz_lab.service.export(graded(quiz_lab, count=2))

    list(quiz_lab.service.prepare("book_001", 1, 2, seed=0))

    assert not path.exists()
    assert list(quiz_lab.downloads.iterdir()) == []


def test_a_new_service_empties_the_download_directory(lab, settings, catalog, tmp_path):
    quiz_lab = lab(chapter(1, 13))
    path = quiz_lab.service.export(graded(quiz_lab, count=2))

    Lab(settings, catalog, chapter(1, 13), tmp_path)  # a restart

    assert not path.exists()


def test_the_document_writes_nothing_by_itself(lab):
    quiz_lab = lab(chapter(1, 13))
    result = graded(quiz_lab, count=2)

    quiz_lab.service.result_document(result)

    assert list(quiz_lab.downloads.iterdir()) == []


# The key check (T045)

OPTION = re.compile(r"^([A-E])\) (.*)$", re.MULTILINE)


class Checker:
    """Supports the right answer only, unless told otherwise for a passage.

    Args:
        rejecting: markers whose questions it rejects, supporting nothing.
        unreadable: markers whose verdicts it can't give, in any reply.
    """

    def __init__(self, rejecting=(), unreadable=()):
        self.rejecting = set(rejecting)
        self.unreadable = set(unreadable)
        self.llm = FakeLLM(respond=self)

    def __call__(self, messages, parameters):
        prompt = messages[-1].content
        marker = MARKER.search(prompt).group()
        if marker in self.unreadable:
            return "Não sei dizer."
        if marker in self.rejecting:
            return '{"supported": []}'
        right = next(letter for letter, text in OPTION.findall(prompt) if text.startswith("A explicação certa"))
        return json.dumps({"supported": [right]})


def checked_lab(lab, chunks, checker, script=None):
    quiz_lab = lab(chunks, script, checker.llm)
    check = quiz_lab.config.check.model_copy(update={"enabled": True})
    quiz_lab.config = quiz_lab.config.model_copy(update={"check": check})
    quiz_lab.writer = QuizWriter(quiz_lab.config, 0.1, quiz_lab.llm, checker.llm)
    catalog = quiz_lab.service._catalog
    quiz_lab.service = QuizService(
        quiz_lab.config, ("Portuguese",), catalog, quiz_lab.chunks, quiz_lab.writer, quiz_lab.downloads
    )
    return quiz_lab


def test_with_the_check_on_every_question_shown_was_accepted(lab):
    checker = Checker()
    quiz_lab = checked_lab(lab, chapter(1, 13), checker)

    events = quiz_lab.events(count=4)

    ready = [event for event in events if isinstance(event, QuestionReady)]
    assert all(event.check.accepted and event.check.readable for event in ready)
    assert len(checker.llm.calls) == 4
    assert events[-1].quiz.checker == "fake-llm"
    assert (events[-1].check_unreadable, events[-1].check_rejected) == (0, 0)


def test_a_rejected_question_is_replaced_from_its_stratum_keeping_its_place_and_letter(lab):
    chunks = chapter(1, 13)
    clean = checked_lab(lab, chunks, Checker())
    clean_events = clean.events(count=2, seed=5)
    first = clean.script.asked[0]
    checker = Checker(rejecting={first})
    quiz_lab = checked_lab(lab, chunks, checker)

    events = quiz_lab.events(count=2, seed=5)

    replacement = quiz_lab.script.asked[1]
    layout = strata(13, 2)
    assert layout[int(replacement[1:])] == layout[int(first[1:])]
    question = events[1].question
    assert (question.position, question.key) == (1, clean_events[1].question.key)
    assert MARKER.search(question.passage.text).group() == replacement
    assert events[-1].check_rejected == 1


def test_an_unreadable_verdict_leaves_the_question_shown_and_counted(lab):
    chunks = chapter(1, 13)
    clean = checked_lab(lab, chunks, Checker())
    clean.events(count=2, seed=6)
    first = clean.script.asked[0]
    checker = Checker(unreadable={first})
    quiz_lab = checked_lab(lab, chunks, checker)

    events = quiz_lab.events(count=2, seed=6)

    assert MARKER.search(events[1].question.passage.text).group() == first
    assert events[1].check.readable is False
    assert events[-1].check_unreadable == 1
    assert len(checker.llm.calls) == 3  # the unreadable verdict was asked again once


def test_the_check_runs_on_the_checkers_provider_not_the_writers(lab):
    checker = Checker()
    quiz_lab = checked_lab(lab, chapter(1, 13), checker)

    quiz_lab.events(count=3)

    assert len(checker.llm.calls) == 3
    assert all('"supported"' not in call[0][-1].content for call in quiz_lab.llm.calls)


def test_with_the_check_off_nothing_is_checked(lab):
    checker = Checker()
    quiz_lab = lab(chapter(1, 13), None, checker.llm)

    events = quiz_lab.events(count=3)

    assert checker.llm.calls == []
    assert all(event.check is None for event in events if isinstance(event, QuestionReady))
    assert events[-1].quiz.checker is None
