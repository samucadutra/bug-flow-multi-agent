import math

from mocks.fake_openai_server import DIMENSIONS, embed_text


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_same_text_gives_the_same_vector():
    assert embed_text("Checkout button") == embed_text("checkout BUTTON")


def test_vectors_have_1536_dimensions_and_unit_length():
    vector = embed_text("alpha beta")
    assert len(vector) == DIMENSIONS == 1536
    assert math.isclose(math.sqrt(sum(v * v for v in vector)), 1.0, rel_tol=1e-9)


def test_never_a_zero_vector():
    for text in ("", "   ", "!!!"):
        assert any(embed_text(text))


def test_more_shared_words_means_higher_similarity():
    query = embed_text("checkout button")
    both = embed_text("checkout button unresponsive")
    one = embed_text("checkout page layout broken")
    none = embed_text("nightly report timeout")
    assert cosine(query, both) > cosine(query, one) > cosine(query, none)
