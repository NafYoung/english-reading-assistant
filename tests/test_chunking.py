from era.nlp.chunking import split_text_into_chunks


def test_split_text_into_chunks_prefers_paragraph_boundaries():
    long_text = (
        "Paragraph one. " * 60
        + "\n\n"
        + "Paragraph two. " * 60
        + "\n\n"
        + "Paragraph three. " * 60
    )
    chunks = split_text_into_chunks(long_text, max_chars=500)
    assert len(chunks) > 1
    assert all(chunk.strip() for chunk in chunks)
    assert all(len(chunk) <= 500 for chunk in chunks)


def test_short_text_is_single_chunk():
    assert split_text_into_chunks("Hello world.") == ["Hello world."]
