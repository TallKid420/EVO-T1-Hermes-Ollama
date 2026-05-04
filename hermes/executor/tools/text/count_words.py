import re
from langchain_core.tools import tool




@tool("count_words", description="Count words, characters, and sentences in a block of text.", return_direct=False)
def count_words(text: str):
    """Count words, characters, and sentences in a block of text."""
    words = len(text.split())
    chars = len(text)
    chars_no_spaces = len(text.replace(" ", ""))
    sentences = len(re.findall(r'[.!?]+', text))
    return {"words": words, "characters": chars, "characters_no_spaces": chars_no_spaces, "sentences": sentences}
